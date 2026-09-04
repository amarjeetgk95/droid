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

import asyncio
import math
import time
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.market import ApiMeta, DataStatus
from app.services.regime_service import regime_service
from app.services.paper_service import paper_service
from app.services.market_service import MarketService
from app.services.market_data_coordinator import market_data_coordinator

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


class DashboardSummary(BaseModel):
    cards: list[dict[str, Any]] = []
    breadth: dict[str, Any] | None = None
    health: dict[str, Any] | None = None
    market_status: dict[str, Any] | None = None
    ml_prediction: dict[str, Any] | None = None
    fii_dii: dict[str, Any] | None = None
    regime_overview: dict[str, Any] | None = None
    errors: dict[str, str] = {}
    degraded: bool = False
    generated_at: str


SUMMARY_FRESH_TTL = 3.0
_summary_cache: dict[str, tuple[float, DashboardSummary]] = {}
_summary_refresh_lock = asyncio.Lock()
_summary_refresh_task: asyncio.Task | None = None

_symbol_refresh_tasks: dict[str, asyncio.Task] = {}


def _make_summary_meta(degraded: bool) -> ApiMeta:
    return ApiMeta(
        provider="dashboard_summary",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.OFFLINE if degraded else DataStatus.LIVE,
    )


def _to_dict(v: Any) -> Any:
    if v is None:
        return None
    if hasattr(v, "model_dump"):
        return v.model_dump(mode="json")
    if isinstance(v, list):
        return [_to_dict(x) for x in v]
    return v


async def _compute_summary() -> DashboardSummary:
    errors: dict[str, str] = {}
    service = MarketService()

    async def _fetch_cards():
        c = await service.fetch_index_cards_raw()
        return [x.model_dump(mode="json") for x in c]

    async def _fetch_breadth():
        b = await service.fetch_market_breadth_raw()
        return b.model_dump(mode="json")

    async def _fetch_health():
        h = await service.fetch_health_raw()
        return h.model_dump(mode="json")

    async def _fetch_status():
        s = await service.fetch_market_status_raw()
        return s.model_dump(mode="json")

    async def _fetch_ml():
        from app.ml.predictor import ml_predictor
        m = await ml_predictor.predict_probabilities("NIFTY")
        return m.model_dump(mode="json")

    async def _fetch_fii():
        from app.services.fii_dii_service import fii_dii_service
        fn = getattr(fii_dii_service, "get_fii_dii_overview", None) or getattr(fii_dii_service, "get_institutional_overview")
        f = fn()
        if hasattr(f, "__await__"):
            f = await f
        return f.model_dump(mode="json")

    async def _fetch_regime():
        r = await regime_service.classify_market_regime("NIFTY")
        return r.model_dump(mode="json")

    fetch_specs = {
        "cards": (_fetch_cards, "market_service"),
        "breadth": (_fetch_breadth, "market_service"),
        "health": (_fetch_health, "market_service"),
        "status": (_fetch_status, "market_service"),
        "ml": (_fetch_ml, "ml_predictor"),
        "fii_dii": (_fetch_fii, "fii_dii_service"),
        "regime": (_fetch_regime, "regime_service"),
    }

    results = await market_data_coordinator.get_many(fetch_specs)

    # Process cards
    cards_val = results.get("cards")
    cards: list[dict[str, Any]] = []
    if cards_val is None or cards_val.status == "UNAVAILABLE" or not cards_val.data:
        cards_raw = cards_val.data if (cards_val and isinstance(cards_val.data, list)) else []
        cards = [_to_dict(c) for c in cards_raw]
        errors["cards"] = "Index cards unavailable"
    else:
        cards_raw = cards_val.data if isinstance(cards_val.data, list) else []
        cards = [_to_dict(c) for c in cards_raw]
        if not cards or all(
            (c.get("ltp") or 0) <= 0 or str(c.get("status", "")).upper() == "OFFLINE"
            for c in cards
            if isinstance(c, dict)
        ):
            errors["cards"] = "Index cards offline — no live quotes (re-auth broker if persistent)"

    # Process breadth
    breadth_val = results.get("breadth")
    breadth_dict = _to_dict(breadth_val.data) if breadth_val else None
    if breadth_val is None or breadth_val.status == "UNAVAILABLE" or breadth_dict is None:
        errors["breadth"] = "Market breadth unavailable"

    # Process health
    health_val = results.get("health")
    health_dict = _to_dict(health_val.data) if health_val else None
    if health_val is None or health_val.status == "UNAVAILABLE" or health_dict is None:
        errors["health"] = "Market health unavailable"

    # Process status
    status_val = results.get("status")
    status_dict = _to_dict(status_val.data) if status_val else None
    if status_val is None or status_val.status == "UNAVAILABLE" or status_dict is None:
        errors["status"] = "Market status unavailable"

    # Process ml
    ml_val = results.get("ml")
    ml_dict = _to_dict(ml_val.data) if ml_val else None
    if ml_val is None or ml_val.status == "UNAVAILABLE" or ml_dict is None:
        errors["ml"] = "ML prediction unavailable"

    # Process fii_dii
    fii_val = results.get("fii_dii")
    fii_dict = _to_dict(fii_val.data) if fii_val else None
    if fii_val is None or fii_val.status == "UNAVAILABLE" or fii_dict is None:
        errors["fii_dii"] = "FII/DII data unavailable"

    # Process regime
    regime_val = results.get("regime")
    regime_dict = _to_dict(regime_val.data) if regime_val else None
    if regime_val is None or regime_val.status == "UNAVAILABLE" or regime_dict is None:
        errors["regime"] = "Regime classification unavailable"

    is_degraded = bool(errors) or any(
        v.status == "DEGRADED" for v in results.values() if v is not None
    )

    return DashboardSummary(
        cards=cards,
        breadth=breadth_dict,
        health=health_dict,
        market_status=status_dict,
        ml_prediction=ml_dict,
        fii_dii=fii_dict,
        regime_overview=regime_dict,
        errors=errors,
        degraded=is_degraded,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


async def _refresh_summary_background() -> None:
    """Non-blocking background refresh for SWR."""
    async with _summary_refresh_lock:
        try:
            data = await _compute_summary()
            _summary_cache["default"] = (time.monotonic(), data)
            logger.debug("dashboard_summary_background_refreshed")
        except Exception as e:
            logger.warning("background_summary_refresh_failed", error=str(e)[:150])


def _trigger_background_summary_refresh() -> None:
    """Schedule background refresh without blocking response delivery."""
    global _summary_refresh_task
    if _summary_refresh_lock.locked():
        return
    if _summary_refresh_task is None or _summary_refresh_task.done():
        try:
            loop = asyncio.get_running_loop()
            _summary_refresh_task = loop.create_task(_refresh_summary_background())
        except RuntimeError:
            pass


async def prewarm_dashboard_summary() -> None:
    """Pre-compute dashboard summary at startup so the very first request is instant."""
    try:
        data = await _compute_summary()
        _summary_cache["default"] = (time.monotonic(), data)
        logger.info("dashboard_summary_prewarmed", cards_count=len(data.cards))
    except Exception as e:
        logger.warning("dashboard_summary_prewarm_failed", error=str(e)[:150])


@router.get("/summary")
async def get_dashboard_summary():
    cached = _summary_cache.get("default")
    now = time.monotonic()

    # Stale-While-Revalidate: return immediately (<1ms) if cached, trigger async refresh if stale
    if cached is not None:
        cached_time, data = cached
        if now - cached_time >= SUMMARY_FRESH_TTL:
            _trigger_background_summary_refresh()
        return {
            "data": data.model_dump(),
            "error": None,
            "meta": _make_summary_meta(data.degraded).model_dump(),
        }

    # Cold start: first request before background prewarm finishes
    data = await _compute_summary()
    _summary_cache["default"] = (now, data)
    return {
        "data": data.model_dump(),
        "error": None,
        "meta": _make_summary_meta(data.degraded).model_dump(),
    }


async def _refresh_symbol_dashboard_background(sym: str) -> None:
    try:
        data = await _build_dashboard(sym)
        _cache[sym] = (time.monotonic(), data)
        logger.debug("symbol_dashboard_background_refreshed", symbol=sym)
    except Exception as e:
        logger.warning("background_symbol_dashboard_refresh_failed", symbol=sym, error=str(e)[:150])


@router.get("/{symbol}")
async def get_dashboard(symbol: str):
    sym = _resolve_symbol(symbol)

    cached = _cache.get(sym)
    now = time.monotonic()
    if cached is not None:
        cached_time, data = cached
        if now - cached_time >= CACHE_TTL_SECONDS:
            t = _symbol_refresh_tasks.get(sym)
            if t is None or t.done():
                try:
                    loop = asyncio.get_running_loop()
                    _symbol_refresh_tasks[sym] = loop.create_task(_refresh_symbol_dashboard_background(sym))
                except RuntimeError:
                    pass
        return {
            "data": data.model_dump(),
            "error": None,
            "meta": _meta(degraded=data.degraded).model_dump(),
        }

    data = await _build_dashboard(sym)
    _cache[sym] = (now, data)
    return {
        "data": data.model_dump(),
        "error": None,
        "meta": _meta(degraded=data.degraded).model_dump(),
    }
