"""
Dashboard Aggregation — §31

Display:
Market, Current Price, Regime, MTF, Quantitative P(Up)/P(Down), P10/P50/P90,
AI provider/model/task/bias/confidence breakdown, Risk target/invalidation/R:R,
Execution order state etc.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Query

from app.models.market import ApiMeta, DataStatus
from app.services.central_feed import central_feed
from app.services.regime_service import regime_service
from app.services.futures_service import futures_service
from app.services.options_service import options_service
from app.prediction.predictor import forecast_for_timeframe
from app.prediction.features import build_features
from app.chart_analysis.service import analyze_instrument
from app.services.paper_service import paper_service

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _meta() -> ApiMeta:
    return ApiMeta(provider="dashboard_engine", timestamp=datetime.now(timezone.utc), status=DataStatus.DEMO)


@router.get("/{symbol}")
async def get_dashboard(symbol: str):
    sym = symbol.upper().replace(" 50", "")
    # Gather market
    try:
        from app.services.market_service import MarketService
        ms = MarketService()
        quote = await ms.get_quote(sym)
        current_price = quote.ltp
        atr = 38  # fallback; try regime
    except Exception:
        quote = None
        current_price = 24750
        atr = 38

    # Regime
    try:
        regime = await regime_service.classify_market_regime(sym)
        regime_val = regime.regime_state
        mtf_placeholder = {"1m": regime.regime_state, "5m": regime.regime_state, "15m": regime.regime_state, "1h": regime.regime_state}
        vwap = getattr(regime.key_levels, "poc", current_price) if hasattr(regime, "key_levels") else current_price
        atr_val = getattr(regime.indicators, "atr_14", atr) if hasattr(regime, "indicators") else atr
    except Exception:
        regime = None
        regime_val = "UNKNOWN"
        mtf_placeholder = {"1m": "UNKNOWN", "5m": "UNKNOWN", "15m": "UNKNOWN", "1h": "UNKNOWN"}
        vwap = current_price
        atr_val = atr

    # Chart analysis for quant
    try:
        chart = await analyze_instrument(sym)
        # Extract latest forecast per timeframe? Use 5m p10/p50/p90 approximated from forecast expected_range
        # For now use synthetic mapping: forecasts[tf] has expected_range low/high -> approximate p10/p50/p90 via quant
        # Use deterministic pricing placeholder
        forecasts = chart.get("forecasts", {})
        # Pick 5m
        fc5 = forecasts.get("5m", {})
        if fc5 and "expected_range" in fc5:
            low = fc5["expected_range"]["low"]
            high = fc5["expected_range"]["high"]
            p10, p50, p90 = low, (low + high) / 2, high
            prob_up = fc5.get("direction", {}).get("up", 0.5)
            prob_down = fc5.get("direction", {}).get("down", 0.5)
        else:
            p10, p50, p90 = current_price * 0.99, current_price, current_price * 1.01
            prob_up, prob_down = 0.52, 0.48
        mtf_data = chart.get("multi_timeframe", {})
        if mtf_data and "timeframe_bias" in mtf_data:
            mtf_placeholder = {k: v.get("bias", "NEUTRAL") if isinstance(v, dict) else str(v) for k, v in mtf_data.get("timeframe_bias", {}).items()}
    except Exception:
        p10, p50, p90 = current_price * 0.99, current_price, current_price * 1.01
        prob_up, prob_down = 0.52, 0.48

    # Futures/options quick
    try:
        futures = await futures_service.get_futures_overview(sym)
        fno_available = True
    except Exception:
        futures = None
        fno_available = False

    # Paper positions for execution
    try:
        portfolio = await paper_service.get_portfolio_summary()
        positions = await paper_service.get_positions()
        open_positions = [p for p in positions if p.is_open]
    except Exception:
        portfolio = None
        positions = []
        open_positions = []

    # Deterministic pricing example for dashboard (BUY case)
    from app.services.pricing_engine import calculate_deterministic_pricing
    try:
        pricing_buy = calculate_deterministic_pricing("BUY", current_price, p10, p50, p90, vwap=vwap, atr=atr_val, k=1.0)
        pricing_sell = calculate_deterministic_pricing("SELL", current_price, p10, p50, p90, vwap=vwap, atr=atr_val, k=1.0)
    except Exception:
        pricing_buy = None
        pricing_sell = None

    return {
        "data": {
            "market": {"symbol": sym, "current_price": current_price, "regime": regime_val, "atr": atr_val, "vwap": vwap},
            "mtf": mtf_placeholder,
            "quantitative": {"prob_up": prob_up, "prob_down": prob_down, "p10": p10, "p50": p50, "p90": p90},
            "fno": {"available": fno_available, "futures": futures.model_dump(mode="json") if futures and hasattr(futures, "model_dump") else None},
            "risk": {
                "buy_target": pricing_buy.target if pricing_buy else None,
                "buy_invalidation": pricing_buy.invalidation if pricing_buy else None,
                "buy_rr": pricing_buy.risk_reward_ratio if pricing_buy else None,
                "sell_target": pricing_sell.target if pricing_sell else None,
                "sell_invalidation": pricing_sell.invalidation if pricing_sell else None,
                "sell_rr": pricing_sell.risk_reward_ratio if pricing_sell else None,
            },
            "execution": {
                "portfolio": portfolio.model_dump(mode="json") if portfolio and hasattr(portfolio, "model_dump") else None,
                "open_positions": [p.model_dump(mode="json") for p in open_positions[:5]] if open_positions else [],
                "open_positions_count": len(open_positions),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": "Probabilistic; not guaranteed. Deterministic risk controls are authoritative.",
        },
        "error": None,
        "meta": _meta().model_dump(),
    }
