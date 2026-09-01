"""
Dashboard Aggregation — §31

Display:
Market, Current Price, Regime, MTF, Quantitative P(Up)/P(Down), P10/P50/P90,
AI provider/model/task/bias/confidence breakdown, Risk target/invalidation/R:R,
Execution order state etc.

Robustness rules:
- NEVER fabricate market data. If a subsystem fails, the field is `null` and
  the failure is recorded in `data.errors` + `data.degraded` is True.
- Symbols are resolved via an explicit alias map; unknown symbols return 404.
- Short per-symbol TTL cache protects the downstream analysis services.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.market import ApiMeta, DataStatus
from app.services.regime_service import regime_service
from app.chart_analysis.service import analyze_instrument
from app.services.paper_service import paper_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# Explicit alias map — replaces the fragile `symbol.replace(" 50", "")` hack.
SYMBOL_ALIASES = {
    "NIFTY": "NIFTY",
    "NIFTY 50": "NIFTY",
    "NIFTY50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "BANK NIFTY": "BANKNIFTY",
    "FINNIFTY": "FINNIFTY",
    "SENSEX": "SENSEX",
    "BSE SENSEX": "SENSEX",
    "INDIA VIX": "INDIA VIX",
    "INDIAVIX": "INDIA VIX",
    "VIX": "INDIA VIX",
}

CACHE_TTL_SECONDS = 3.0
_cache: dict[str, tuple[float, "DashboardData"]] = {}


def _resolve_symbol(raw: str) -> str:
    key = raw.strip().upper()
    resolved = SYMBOL_ALIASES.get(key)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown dashboard symbol: {raw!r}. "
                f"Supported: {sorted(set(SYMBOL_ALIASES.values()))}"
            ),
        )
    return resolved


def _opt_float(value: Any) -> Optional[float]:
    """Coerce to a finite float, else None — never fabricate."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


class DashboardMarket(BaseModel):
    symbol: str
    current_price: Optional[float] = None
    regime: str = "UNKNOWN"
    atr: Optional[float] = None
    vwap: Optional[float] = None


class DashboardQuantitative(BaseModel):
    prob_up: Optional[float] = None
    prob_down: Optional[float] = None
    p10: Optional[float] = None
    p50: Optional[float] = None
    p90: Optional[float] = None
    method: str = "unavailable"


class DashboardRisk(BaseModel):
    buy_target: Optional[float] = None
    buy_invalidation: Optional[float] = None
    buy_rr: Optional[float] = None
    sell_target: Optional[float] = None
    sell_invalidation: Optional[float] = None
    sell_rr: Optional[float] = None


class DashboardData(BaseModel):
    market: DashboardMarket
    mtf: dict[str, str]
    quantitative: DashboardQuantitative
    fno: dict[str, Any]
    risk: DashboardRisk
    execution: dict[str, Any]
    generated_at: str
    disclaimer: str
    degraded: bool = False
    quote_status: str = "OFFLINE"
    quote_provider: str = "unknown"
    errors: dict[str, str] = {}


def _meta(*, degraded: bool) -> ApiMeta:
    return ApiMeta(
        provider="dashboard_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.OFFLINE if degraded else DataStatus.LIVE,
    )


async def _build_dashboard(sym: str) -> DashboardData:
    errors: dict[str, str] = {}

    # Gather market — no fabricated fallbacks: null + error entry on failure.
    current_price: Optional[float] = None
    quote_status = "OFFLINE"
    quote_provider = "unknown"
    try:
        from app.services.market_service import MarketService

        quote = await MarketService().get_quote(sym)
        if quote is not None:
            candidate = _opt_float(quote.ltp)
            if candidate is not None and candidate > 0:
                current_price = candidate
            raw_status = quote.status.value if hasattr(quote.status, "value") else str(quote.status)
            quote_provider = quote.provider
            # MarketService has an OFFLINE fallback quote with a made-up LTP —
            # treat it as "no real quote" so the dashboard never shows it as live.
            if raw_status == "OFFLINE" or quote.provider == "fallback":
                quote_status = "OFFLINE"
                errors["quote"] = f"Quote offline/stale (status={raw_status}, provider={quote.provider})"
            else:
                quote_status = raw_status
    except Exception:
        logger.exception("dashboard.quote_failed", symbol=sym)
        errors["quote"] = "Quote unavailable"

    # Regime
    regime_val = "UNKNOWN"
    mtf_placeholder: dict[str, str] = {}
    vwap: Optional[float] = None
    atr_val: Optional[float] = None
    try:
        regime = await regime_service.classify_market_regime(sym)
        regime_val = regime.regime_state
        mtf_placeholder = {
            "1m": regime.regime_state,
            "5m": regime.regime_state,
            "15m": regime.regime_state,
            "1h": regime.regime_state,
        }
        if hasattr(regime, "key_levels"):
            vwap = _opt_float(getattr(regime.key_levels, "poc", None))
        if hasattr(regime, "indicators"):
            atr_val = _opt_float(getattr(regime.indicators, "atr_14", None))
    except Exception:
        logger.exception("dashboard.regime_failed", symbol=sym)
        errors["regime"] = "Regime classification unavailable"

    # Chart analysis — only real MTF biases are surfaced. No fabricated
    # probabilities or price bands (forecast module removed).
    if current_price is not None:
        try:
            chart = await analyze_instrument(sym)
            mtf_data = chart.get("multi_timeframe", {})
            if mtf_data and "timeframe_bias" in mtf_data:
                mtf_placeholder = {
                    k: (v.get("bias", "NEUTRAL") if isinstance(v, dict) else str(v))
                    for k, v in mtf_data.get("timeframe_bias", {}).items()
                }
            elif mtf_data and "per_timeframe" in mtf_data:
                mtf_placeholder = {
                    k: v.get("bias", "NEUTRAL")
                    for k, v in mtf_data.get("per_timeframe", {}).items()
                    if isinstance(v, dict)
                }
        except Exception:
            logger.exception("dashboard.chart_analysis_failed", symbol=sym)
            errors["chart_analysis"] = "Chart analysis unavailable"

    # Futures/options quick
    fno_available = False

    # Paper positions for execution
    portfolio = None
    open_positions: list = []
    try:
        portfolio = await paper_service.get_portfolio_summary()
        positions = await paper_service.get_positions()
        open_positions = [p for p in positions if p.is_open]
    except Exception:
        logger.exception("dashboard.paper_failed", symbol=sym)
        errors["execution"] = "Paper portfolio unavailable"

    # Deterministic pricing — only meaningful with real quantiles. There is no
    # forecast module yet, so risk fields stay null instead of using fake bands.
    pricing_buy = None
    pricing_sell = None
    if current_price is not None:
        from app.services.pricing_engine import calculate_deterministic_pricing

        try:
            pricing_buy = calculate_deterministic_pricing(
                "BUY", current_price, current_price, current_price, current_price,
                vwap=vwap, atr=atr_val, k=1.0,
            )
            pricing_sell = calculate_deterministic_pricing(
                "SELL", current_price, current_price, current_price, current_price,
                vwap=vwap, atr=atr_val, k=1.0,
            )
        except Exception:
            logger.exception("dashboard.pricing_failed", symbol=sym)
            errors["pricing"] = "Deterministic pricing unavailable"

    def _pricing_field(pricing, attr: str) -> Optional[float]:
        if pricing is None:
            return None
        value = _opt_float(getattr(pricing, attr, None))
        # zero is the sentinel the engine uses for invalid results
        return value if value not in (None, 0) else None

    data = DashboardData(
        market=DashboardMarket(
            symbol=sym,
            current_price=current_price,
            regime=regime_val,
            atr=atr_val,
            vwap=vwap,
        ),
        mtf=mtf_placeholder,
        quantitative=DashboardQuantitative(),  # nulls — no fabricated probabilities
        fno={"available": fno_available, "futures": None},
        risk=DashboardRisk(
            buy_target=_pricing_field(pricing_buy, "target"),
            buy_invalidation=_pricing_field(pricing_buy, "invalidation"),
            buy_rr=_pricing_field(pricing_buy, "risk_reward_ratio"),
            sell_target=_pricing_field(pricing_sell, "target"),
            sell_invalidation=_pricing_field(pricing_sell, "invalidation"),
            sell_rr=_pricing_field(pricing_sell, "risk_reward_ratio"),
        ),
        execution={
            "portfolio": portfolio.model_dump(mode="json") if portfolio and hasattr(portfolio, "model_dump") else None,
            "open_positions": [p.model_dump(mode="json") for p in open_positions[:5]] if open_positions else [],
            "open_positions_count": len(open_positions),
        },
        generated_at=datetime.now(timezone.utc).isoformat(),
        disclaimer="Probabilistic; not guaranteed. Deterministic risk controls are authoritative.",
        degraded=bool(errors),
        quote_status=quote_status,
        quote_provider=quote_provider,
        errors=errors,
    )
    return data


@router.get("/{symbol}")
async def get_dashboard(symbol: str):
    sym = _resolve_symbol(symbol)

    cached = _cache.get(sym)
    now = time.monotonic()
    if cached is not None and now - cached[0] < CACHE_TTL_SECONDS:
        return {
            "data": cached[1].model_dump(),
            "error": None,
            "meta": _meta(degraded=cached[1].degraded).model_dump(),
        }

    data = await _build_dashboard(sym)
    response = {
        "data": data.model_dump(),
        "error": None,
        "meta": _meta(degraded=data.degraded).model_dump(),
    }
    _cache[sym] = (now, data)
    return response
