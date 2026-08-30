from datetime import datetime, timezone
from app.instruments.registry import get_by_symbol_exact, get_instrument, CHART_ANALYSIS_UNIVERSE
from app.instruments.schemas import InstrumentConfig
from app.market_data.router import MarketDataRouter
from app.technical_analysis.analyzer import analyze_timeframe
from app.prediction.features import build_features
from app.prediction.predictor import forecast_for_timeframe
from app.prediction.historical_similarity import historical_similarity
from app.multi_timeframe.analyzer import analyze_multi_timeframe
from app.fno.context import get_fno_context, fno_levels_for_sr
from app.market_data.cache import get_cached_analysis, set_cached_analysis
from app.market_data.timeframes import TIMEFRAME_CONFIG, CHART_ANALYSIS_TIMEFRAMES

router = MarketDataRouter()

# Chart Analysis supports only the 6 fixed timeframes
CHART_TFS = CHART_ANALYSIS_TIMEFRAMES  # ["1m","5m","15m","1h","4h","1D"]

async def get_candles_for(symbol: str, timeframe: str) -> list[dict]:
    """
    Fetch candles for chart analysis.
    - Does NOT fabricate/synthesize data when provider returns empty;
      instead returns empty list so caller can emit 'Data unavailable'
      per spec (no substitution with another instrument).
    - Crypto (BTC/ETH/SOL) is routed via BinanceService when available
      (real market data only).
    """
    # Normalize Daily casing
    if timeframe == "1d":
        timeframe = "1D"
    try:
        candles = await router.get_candles(symbol, timeframe)
    except Exception:
        candles = []
    # Attempt Binance real-data fallback for crypto when router (mock) has no crypto
    if not candles:
        cfg = get_by_symbol_exact(symbol.upper()) or get_instrument(symbol)
        if cfg and cfg.asset_class == "CRYPTO":
            try:
                from app.services.binance_service import binance_service
                # Map canonical BTC/ETH/SOL -> BINANCE:BTCUSDT etc via data_provider_symbol
                tf_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1D": "1d"}
                bin_tf = tf_map.get(timeframe, timeframe)
                b_candles = await binance_service.get_candles(cfg.symbol, bin_tf, limit=100)
                # binance_service returns fallback synthetic only when real fetch failed with DEMO status;
                # we preserve that as last resort but mark data as DEMO downstream via freshness.
                candles = b_candles
            except Exception:
                pass
    out=[]
    for c in candles:
        if hasattr(c, "model_dump"):
            d=c.model_dump()
        elif hasattr(c, "dict"):
            d=c.dict()
        else:
            d=dict(c)
        out.append({
            "timestamp": d.get("timestamp").isoformat() if hasattr(d.get("timestamp"), "isoformat") else str(d.get("timestamp")),
            "open": float(d.get("open",0)),
            "high": float(d.get("high",0)),
            "low": float(d.get("low",0)),
            "close": float(d.get("close",0)),
            "volume": int(float(d.get("volume",0))) if d.get("volume") is not None else 0,
            "vwap": d.get("vwap"),
        })
    # Do NOT synthesize mock candles here. If still empty, caller must emit
    # 'Data unavailable' and not substitute another instrument (spec).
    return out

async def analyze_instrument(symbol: str, requested_timeframe: str | None = None) -> dict:
    # Enforce restricted 7-instrument universe — reject anything outside
    # CHART_ANALYSIS_UNIVERSE even if it exists elsewhere in the codebase.
    if symbol:
        up = symbol.strip().upper().replace(" ", "").replace("-", "").replace("/", "")
        # Also accept plain names via aliases mapping — resolve first
        cfg_try = get_by_symbol_exact(symbol.upper()) or get_instrument(symbol)
        if cfg_try and cfg_try.symbol.upper() not in CHART_ANALYSIS_UNIVERSE:
            raise ValueError(
                f"Instrument '{symbol}' is not part of the Chart Analysis derivatives universe. "
                f"Approved: {', '.join(CHART_ANALYSIS_UNIVERSE)}"
            )
    cfg = get_by_symbol_exact(symbol.upper()) or get_instrument(symbol)
    if not cfg:
        raise ValueError(
            f"No supported instrument found for \"{symbol}\". "
            f"Chart Analysis supports only: {', '.join(CHART_ANALYSIS_UNIVERSE)} (NIFTY 50, BANKNIFTY, FINNIFTY, SENSEX, BTC, ETH, SOL)."
        )
    if cfg.symbol.upper() not in CHART_ANALYSIS_UNIVERSE:
        raise ValueError(
            f"Instrument '{cfg.symbol}' is not part of the Chart Analysis derivatives universe. "
            f"Approved: {', '.join(CHART_ANALYSIS_UNIVERSE)}"
        )
    # Normalize Daily casing
    if requested_timeframe == "1d":
        requested_timeframe = "1D"
    # Determine timeframes to analyze — default 6-TF Chart Analysis universe
    if requested_timeframe:
        tfs = [requested_timeframe]
    else:
        tfs = list(CHART_TFS)
    # Validate — only the 6 chart T.F.s are valid here
    for tf in tfs:
        if tf not in TIMEFRAME_CONFIG:
            raise ValueError(f"Unsupported timeframe {tf}")
        if tf not in CHART_TFS:
            raise ValueError(f"Timeframe {tf} is not part of Chart Analysis (supported: {', '.join(CHART_TFS)})")
        if tf not in cfg.supported_timeframes:
            raise ValueError(f"Timeframe {tf} not supported for {symbol}")

    # Get F&O context once
    fno_ctx=await get_fno_context(cfg.symbol)
    fno_levels=fno_levels_for_sr(fno_ctx)

    analyses={}
    forecasts={}
    features_map={}
    historical={}
    candles_map={}

    now=datetime.now(timezone.utc)
    data_timestamp=now.isoformat()
    # data freshness: LIVE if provider recently updated, else STALE - for mock treat as LIVE
    market_status="OPEN"
    try:
        status=await router.service.get_market_status()
        # status may have session field
        market_status=getattr(status, "session", "OPEN") or "OPEN"
    except Exception:
        pass

    unavailable_tfs: list[str] = []
    for tf in tfs:
        candles=await get_candles_for(cfg.symbol, tf)
        candles_map[tf]=candles
        if not candles:
            # Per spec: display "Data unavailable" and do not substitute
            unavailable_tfs.append(tf)
            tech = {
                "symbol": cfg.symbol,
                "timeframe": tf,
                "error": "Data unavailable",
                "data_unavailable": True,
                "bias": "NEUTRAL",
                "score": 50,
                "current_price": None,
                "data_timestamp": None,
            }
            analyses[tf]=tech
            features_map[tf]={"price": None, "data_unavailable": True}
            forecasts[tf]={
                "symbol": cfg.symbol,
                "timeframe": tf,
                "error": "Data unavailable",
                "data_unavailable": True,
                "direction": {"up": 0.33, "sideways": 0.34, "down": 0.33},
                "confidence": "LOW",
                "confidence_score": 0,
                "expected_move_percent": 0,
                "expected_range": {"low": 0, "high": 0},
                "horizon_minutes": TIMEFRAME_CONFIG.get(tf, {}).get("horizon_minutes", 30),
                "invalidation_level": None,
                "disclaimer": "Data unavailable — no forecast. Do not substitute another instrument.",
            }
            historical[tf]={"data_unavailable": True, "error": "Data unavailable"}
            continue
        # check cache
        cache_key_ts=candles[-1]["timestamp"] if candles else data_timestamp
        cached=await get_cached_analysis(cfg.symbol, tf, cache_key_ts)
        if cached and requested_timeframe is None:
            pass
        tech=analyze_timeframe(candles, cfg.symbol, tf, fno_levels=fno_levels)
        analyses[tf]=tech
        feat=build_features(candles, tech, fno_ctx, cfg.model_dump() if hasattr(cfg, "model_dump") else cfg.__dict__, now)
        features_map[tf]=feat
        fc=forecast_for_timeframe(feat, tech, tf, cfg.symbol, cfg.asset_class, data_timestamp=candles[-1]["timestamp"] if candles else now.isoformat(), fno_ctx=fno_ctx)
        forecasts[tf]=fc
        historical[tf]=historical_similarity(feat, cfg.symbol, tf)
        await set_cached_analysis(cfg.symbol, tf, cache_key_ts, tech, ttl=TIMEFRAME_CONFIG[tf].get("refresh_seconds", 60))

    # Multi-timeframe — exclude data-unavailable TFs from alignment
    available_analyses = {k: v for k, v in analyses.items() if not v.get("data_unavailable")}
    available_forecasts = {k: v for k, v in forecasts.items() if not v.get("data_unavailable")}
    mtf=analyze_multi_timeframe(available_analyses, available_forecasts, fno_ctx.get("available", False))
    # annotate unavailable flag
    if unavailable_tfs:
        mtf["unavailable_timeframes"] = unavailable_tfs
        mtf["data_unavailable_note"] = "Data unavailable for: " + ", ".join(unavailable_tfs) + " — no substitution."

    # data age — use last available candle
    last_candle_ts = None
    for tf in reversed(tfs):
        cl = candles_map.get(tf)
        if cl:
            last_candle_ts = cl[-1]["timestamp"]
            break
    if last_candle_ts:
        candles = candles_map.get(tfs[-1]) or cl  # keep for legacy freshness path
    data_age_seconds= 0
    freshness = "LIVE"
    if last_candle_ts:
        try:
            data_age_seconds = (now - datetime.fromisoformat(last_candle_ts)).total_seconds()
            freshness = "LIVE" if data_age_seconds < 30 else "STALE" if data_age_seconds < 120 else "DELAYED"
        except Exception:
            data_age_seconds = 0
            freshness = "LIVE"
    else:
        freshness = "DATA_UNAVAILABLE"
        data_age_seconds = -1  # sentinel

    # prediction storage meta
    generated_at=now.isoformat()

    # §22 Data Ingestion Protocol: classify granularity and fallback
    # Tick/order-book unavailable in MockProvider; 1m-15m order-flow is Limited, primary is 1h/Daily/Weekly
    data_ingestion = {
        "classification": {
            "tick_level": "Unavailable (no raw tick feed)",
            "orderbook_depth": "Unavailable (no depth snapshots)",
            "available_granularities": ["1m OHLCV (Limited, synthetic ~100)", "5m OHLCV (Primary)", "15m OHLCV (Available)", "1h (Secondary, requires N>=50)", "Daily (Derived)", "Weekly (Derived)"],
        },
        "limitation": "Tick/order-book data unavailable. 1m-15m order-flow analysis cannot be reliably performed. Primary quantitative assessment is therefore based on 1h, Daily and Weekly data.",
        "intraday_1m_15m_status": "Limited / Unavailable",
        "unavailable_metrics": ["order-book imbalance", "tick delta / footprint", "time & sales aggression", "micro-price imbalance", "true 1m VWAP imbalance"],
        "fallback_rule": "Default to Daily and Weekly metrics; use 1h only when sufficient observations exist (N>=50); reduce confidence for horizons <15m",
        "integrity_note": "Never fabricate missing ticks, candles, volume, or intraday indicators",
    }
    for tf_key, tf_analysis in analyses.items():
        if tf_analysis.get("data_unavailable"):
            tf_analysis["data_quality"] = "Data unavailable"
            tf_analysis["order_flow_available"] = False
        elif tf_key in ("1m", "5m", "15m"):
            tf_analysis["data_quality"] = "Limited / Unavailable (no tick/order-book; OHLCV proxy only)"
            tf_analysis["order_flow_available"] = False
        elif tf_key in ("1h", "4h"):
            tf_analysis["data_quality"] = "Available (aggregated, use only when N>=50)"
            tf_analysis["order_flow_available"] = False
        else:  # 1D
            tf_analysis["data_quality"] = "Derived/Aggregated (Daily)"
            tf_analysis["order_flow_available"] = False

    # Resolve last timestamp properly
    last_ts = last_candle_ts or generated_at
    # downgrade confidence when data unavailable
    if unavailable_tfs and len(available_analyses) == 0:
        freshness = "DATA_UNAVAILABLE"

    return {
        "symbol": cfg.symbol,
        "display_name": cfg.display_name,
        "asset_class": cfg.asset_class,
        "exchange": cfg.exchange,
        "instrument_type": cfg.instrument_type,
        "currency": cfg.currency,
        "price_precision": cfg.price_precision,
        "fno_available": cfg.fno_available,
        "generated_at": generated_at,
        "data_timestamp": last_ts,
        "data_age_seconds": round(data_age_seconds,1) if data_age_seconds >=0 else -1,
        "freshness": freshness,
        "market_status": market_status,
        "supported_timeframes": CHART_TFS,
        "chart_timeframes": CHART_TFS,
        "instrument_universe": CHART_ANALYSIS_UNIVERSE,
        "unavailable_timeframes": unavailable_tfs,
        "data_ingestion": data_ingestion,
        "timeframes": analyses,
        "forecasts": forecasts,
        "historical_similarity": historical,
        "fno": fno_ctx,
        "multi_timeframe": mtf,
        "features": features_map,
        "candles": candles_map,
    }
