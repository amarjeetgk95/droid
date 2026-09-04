from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.services.historical_service import historical_service
from app.models.market import ApiMeta, DataStatus

router = APIRouter(tags=["historical"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="historical_intelligence_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.OFFLINE,
    )


@router.get("/api/v1/history/{symbol}/patterns")
async def get_detected_patterns(
    symbol: str,
    timeframe: str = Query(default="5m", description="Candle timeframe e.g. 5m, 15m, 1h, 1D"),
):
    """Detect recent candlestick and volatility price action patterns."""
    try:
        patterns = await historical_service.scan_patterns(symbol, timeframe)
        return {
            "data": [p.model_dump(mode="json") for p in patterns],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/history/{symbol}/shifts")
async def get_historical_shifts(
    symbol: str,
    days: int = Query(default=10, description="Number of historical sessions"),
):
    """Retrieve multi-session historical shifts for PCR, Max Pain, and ATM IV."""
    try:
        shifts = await historical_service.get_historical_shifts(symbol, days)
        return {
            "data": shifts.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/history/{symbol}/seasonality")
async def get_seasonality(symbol: str):
    """Retrieve day-of-the-week return and volatility distribution."""
    try:
        seasonality = historical_service.get_seasonality(symbol)
        return {
            "data": seasonality.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/watchlist")
async def get_watchlist():
    """Retrieve user watchlist instruments with live quotes and active patterns."""
    try:
        items = await historical_service.get_watchlist()
        return {
            "data": [item.model_dump(mode="json") for item in items],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/add")
async def add_to_watchlist(symbol: str = Query(description="Instrument symbol e.g. NIFTY 50")):
    """Add an instrument to the user watchlist."""
    try:
        historical_service.add_to_watchlist(symbol)
        return {"data": {"symbol": symbol, "status": "added"}, "error": None, "meta": _make_meta().model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/remove")
async def remove_from_watchlist(symbol: str = Query(description="Instrument symbol to remove")):
    """Remove an instrument from the user watchlist."""
    try:
        historical_service.remove_from_watchlist(symbol)
        return {"data": {"symbol": symbol, "status": "removed"}, "error": None, "meta": _make_meta().model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Pattern Outcome Tracking Endpoints (Historical Intelligence v2)
# ============================================================

@router.get("/api/v1/history/{symbol}/hit-rates")
async def get_pattern_hit_rates(
    symbol: str,
    timeframe: Optional[str] = Query(default=None, description="Filter by timeframe e.g. 5m, 15m, 1h, 1D"),
):
    """Get aggregated hit-rate statistics for detected patterns."""
    try:
        hit_rates = await historical_service.get_hit_rates(symbol, timeframe)
        return {
            "data": hit_rates.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/history/{symbol}/outcomes")
async def get_recent_pattern_outcomes(
    symbol: str,
    pattern_types: Optional[str] = Query(default=None, description="Comma-separated pattern types"),
    timeframe: Optional[str] = Query(default=None, description="Filter by timeframe"),
    limit: int = Query(default=20, description="Max outcomes to return"),
):
    """Get recent labeled pattern outcomes for a symbol."""
    try:
        pattern_list = pattern_types.split(",") if pattern_types else None
        outcomes = await historical_service.get_recent_outcomes(symbol, pattern_list, timeframe, limit)
        return {
            "data": [o.model_dump(mode="json") for o in outcomes],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/history/{symbol}/label-outcomes")
async def label_pattern_outcomes(
    symbol: str,
    pattern_types: Optional[str] = Query(default=None, description="Comma-separated pattern types"),
    timeframe: Optional[str] = Query(default=None, description="Filter by timeframe"),
):
    """Trigger on-demand outcome labeling for unlabeled patterns."""
    try:
        pattern_list = pattern_types.split(",") if pattern_types else None
        labeled_count = await historical_service.label_outcomes_for_symbol(symbol, pattern_list, timeframe, "on_demand")
        return {
            "data": {"symbol": symbol, "labeled_count": labeled_count, "status": "completed"},
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/history/hit-rates/refresh")
async def refresh_hit_rates_view():
    """Refresh the materialized view for hit rates."""
    try:
        success = await historical_service.refresh_hit_rates_view()
        return {
            "data": {"refreshed": success},
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Empirical S/R & Analog Similarity APIs (§30)
# ============================================================

@router.get("/api/v1/historical/analogs")
async def get_historical_analogs(
    symbol: str = Query(default="NIFTY", description="Instrument symbol (NIFTY, BANKNIFTY, BTCUSD)"),
    timeframe: str = Query(default="5M", description="Timeframe e.g. 1M, 5M, 15M"),
    pattern_window: int = Query(default=15, ge=5, le=50, description="Pattern length in bars"),
    min_similarity: float = Query(default=0.70, ge=0.5, le=0.99, description="Minimum similarity threshold"),
    top_k: int = Query(default=20, ge=1, le=50, description="Max top analogs to return"),
    forward_horizon: int = Query(default=10, ge=3, le=50, description="Forward outcome bars"),
):
    """
    Search historical archive for matching pattern analogs with zero lookahead,
    returning empirical probabilities, MFE targets, and MAE stop losses.
    """
    try:
        summary = await historical_service.get_historical_analogs(
            symbol=symbol,
            timeframe=timeframe,
            pattern_window=pattern_window,
            min_similarity=min_similarity,
            top_k=top_k,
            forward_horizon=forward_horizon,
        )
        return {
            "data": summary,
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/historical/sr-levels")
async def get_support_resistance_levels(
    symbol: str = Query(default="NIFTY", description="Instrument symbol"),
    timeframe: str = Query(default="5M", description="Timeframe"),
    max_zones: int = Query(default=8, ge=1, le=20, description="Max S/R zones to return"),
):
    """
    Detect multi-touch price pivot clusters, Volume Profile POC, and Options OI strike walls.
    """
    try:
        zones = await historical_service.get_support_resistance_levels(
            symbol=symbol,
            timeframe=timeframe,
            max_zones=max_zones,
        )
        return {
            "data": {"symbol": symbol.upper(), "zones": zones, "count": len(zones)},
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Production Historical Intelligence Engine (HIE) APIs — §§24, 25, 36
# ============================================================

@router.get("/api/v1/hie/status")
async def get_hie_status():
    """Returns engine version manifest, index lifecycle state, and latency metrics (§§35, 36, 39)."""
    from app.historical_intelligence import CURRENT_VERSIONS, hie_monitor
    return {
        "data": {
            "versions": CURRENT_VERSIONS.to_dict(),
            "health": {
                "lifecycle_state": hie_monitor.health.lifecycle_state.value,
                "total_records": hie_monitor.health.total_records,
                "total_embeddings": hie_monitor.health.total_embeddings,
                "feature_version_valid": hie_monitor.health.feature_version_valid,
                "pit_integrity_passed": hie_monitor.health.pit_integrity_passed,
                "query_count": hie_monitor.health.query_count,
                "avg_latency_ms": round(hie_monitor.health.avg_latency_ms, 2),
            },
        },
        "error": None,
        "meta": _make_meta().model_dump(),
    }


async def _fetch_or_simulate_candles(symbol: str, timeframe: str):
    from app.services.market_service import MarketService
    from app.historical_intelligence import CandleData

    mkt_svc = MarketService()
    try:
        candles_raw = await mkt_svc.get_candles(symbol, timeframe=timeframe)
    except Exception:
        candles_raw = []

    if candles_raw and len(candles_raw) >= 15:
        return [
            CandleData(
                timestamp_utc=int(c.timestamp.timestamp() * 1000) if hasattr(c, "timestamp") else 0,
                open=float(c.open),
                high=float(c.high),
                low=float(c.low),
                close=float(c.close),
                volume=float(c.volume),
            )
            for c in candles_raw
        ]

    # Fallback simulated baseline candles anchored on spot quote
    try:
        quote = await mkt_svc.get_quote(symbol)
        spot_p = float(quote.ltp) if quote and quote.ltp > 0 else (50000.0 if "BANK" in symbol else 24000.0)
    except Exception:
        spot_p = 50000.0 if "BANK" in symbol else 24000.0

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    simulated = []
    p = spot_p - 40.0
    for i in range(25):
        simulated.append(CandleData(
            timestamp_utc=now_ms - (25 - i) * 60000,
            open=round(p, 2),
            high=round(p + 6.0, 2),
            low=round(p - 3.0, 2),
            close=round(p + 3.0, 2),
            volume=2000.0,
        ))
        p += 3.0

    return simulated


@router.get("/api/v1/hie/query")
async def query_historical_intelligence(
    symbol: str = Query(default="NIFTY", description="Instrument symbol"),
    timeframe: str = Query(default="1m", description="Timeframe e.g. 1m, 5m"),
    top_k: int = Query(default=50, ge=5, le=100, description="Top-K analogues"),
    min_similarity: float = Query(default=0.65, ge=0.40, le=0.95),
):
    """
    Mode A: Continuously converts the current market state into empirically supported
    historical probabilities across 15m, 30m, and 60m horizons (§1, §24, §25).
    """
    try:
        from app.historical_intelligence import hie_service

        underlying = symbol.upper().replace(" 50", "")
        hie_candles = await _fetch_or_simulate_candles(underlying, timeframe)

        result = await hie_service.analyze_state(
            instrument=underlying,
            candles=hie_candles,
            timeframe=timeframe,
            top_k=top_k,
            min_similarity=min_similarity,
            mode="MARKET_STATE",
        )

        return {
            "data": result.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/hie/candidate-analysis")
async def analyze_candidate_analogs(payload: dict):
    """
    Mode B: Candidate Analysis (§24) — Triggered when Candidate Engine creates a setup.
    Answers: 'How did comparable setups perform historically?'
    """
    try:
        from app.historical_intelligence import hie_service

        symbol = payload.get("instrument") or payload.get("symbol") or "NIFTY"
        timeframe = payload.get("timeframe", "1m")
        strategy_id = payload.get("strategy_id")

        underlying = symbol.upper().replace(" 50", "")
        hie_candles = await _fetch_or_simulate_candles(underlying, timeframe)

        result = await hie_service.analyze_state(
            instrument=underlying,
            candles=hie_candles,
            timeframe=timeframe,
            top_k=payload.get("top_k", 50),
            min_similarity=payload.get("min_similarity", 0.65),
            mode="CANDIDATE",
            candidate_meta={"strategy_id": strategy_id},
        )

        return {
            "data": result.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/hie/ai-context")
async def get_hie_ai_context(
    symbol: str = Query(default="NIFTY", description="Instrument symbol"),
    timeframe: str = Query(default="1m"),
):
    """
    Returns structured factual evidence for the AI / LLM Context Layer (§26, §27).
    """
    try:
        from app.historical_intelligence import hie_service, ai_context_generator

        underlying = symbol.upper().replace(" 50", "")
        hie_candles = await _fetch_or_simulate_candles(underlying, timeframe)

        result = await hie_service.analyze_state(underlying, hie_candles, timeframe=timeframe)
        ai_ctx = ai_context_generator.generate_context(result)

        return {
            "data": ai_ctx.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


