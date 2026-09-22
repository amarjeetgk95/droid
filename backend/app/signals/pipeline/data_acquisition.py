"""
Data Acquisition Module for Quantitative Scanning Pipeline (Phase 3)
Encapsulates:
  - Market session validation & feed circuit check
  - Multi-timeframe candle acquisition (1m, 5m, 15m, 1h)
  - True session-anchored VWAP calculation (>= 09:15 IST)
  - Quantitative market regime detection
  - F&O context and IV/VIX percentile resolution
  - Assembly of StrategyContext
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, UTC
from datetime import time as dt_time
from decimal import Decimal
from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.market import DataStatus
from app.multi_timeframe.alignment import compute_alignment
from app.services.calendar_service import calendar_service
from app.signals.contract_resolver import validate_underlying
from app.signals.features.engine import compute_feature_snapshot
from app.signals.safety.clocks import IST as IST_TZ
from app.signals.strategies.base import StrategyContext
from app.technical_analysis.analyzer import analyze_timeframe

logger = structlog.get_logger()


class ScanDiagnostics(BaseModel):
    """Per-underlying scan health — explains WHY a scan is empty instead of silent []."""
    underlying: str = "UNKNOWN"
    data_quality: str = "UNKNOWN"  # LIVE | DEGRADED | OFFLINE | CLOSED
    quote_status: str = "UNKNOWN"
    provider: str = "UNKNOWN"
    spot_price: float | None = None
    candles_count: int = 0
    strategies_evaluated: int = 0
    candidates_found: int = 0
    registered: int = 0
    reasons: list[str] = Field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0
    throttled_signals_count: int = 0
    fno_degraded: bool = False
    vwap_degraded: bool = False
    vwap_coverage_pct: float = 100.0


def is_fallback_quote(quote: Any) -> bool:
    # P0-2 KILL SYNTHETIC FALLBACKS: mirror quote_quality.SYNTHETIC_PROVIDERS.
    # Any fabricated provider is rejected even when it self-reports LIVE.
    try:
        from app.signals.quote_quality import SYNTHETIC_PROVIDERS as _SYNTH
        _synth = set(_SYNTH)
    except Exception:
        _synth = {"fallback", "synthetic", "mock", "simulated", "dummy",
                  "paper", "cache", "cached", "replay", "backtest",
                  "indicative", "delayed", "test"}
    try:
        status = str(getattr(quote, "status", "") or "").upper()
        provider = str(getattr(quote, "provider", "") or "").lower()
        if any(s in status for s in ("OFFLINE", "DEGRADED", "STALE", "CLOSED", "INVALID")):
            return True
        if provider in _synth:
            return True
    except Exception:
        pass
    return False


def calculate_session_vwap(active_candles: list[dict]) -> tuple[Decimal | None, bool, float]:
    """
    Computes true session-anchored VWAP (strictly >= 09:15:00 IST of current trading session).
    Returns (vwap_value, vwap_degraded, vwap_coverage_pct).
    """
    if not active_candles:
        return None, True, 0.0

    try:
        latest_candle_time = None
        for c in reversed(active_candles):
            ts = c.get("timestamp")
            if ts is not None:
                if isinstance(ts, datetime):
                    latest_candle_time = ts.astimezone(IST_TZ) if ts.tzinfo else ts.replace(tzinfo=IST_TZ)
                    break
                elif isinstance(ts, (int, float)):
                    latest_candle_time = datetime.fromtimestamp(ts if ts < 1e11 else ts / 1000.0, tz=IST_TZ)
                    break
                elif isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts)
                        latest_candle_time = dt.astimezone(IST_TZ) if dt.tzinfo else dt.replace(tzinfo=IST_TZ)
                        break
                    except Exception:
                        pass

        session_candles = []
        if latest_candle_time:
            session_open = datetime.combine(latest_candle_time.date(), dt_time(9, 15, 0), tzinfo=IST_TZ)
            for c in active_candles:
                ts = c.get("timestamp")
                c_dt = None
                if isinstance(ts, datetime):
                    c_dt = ts.astimezone(IST_TZ) if ts.tzinfo else ts.replace(tzinfo=IST_TZ)
                elif isinstance(ts, (int, float)):
                    c_dt = datetime.fromtimestamp(ts if ts < 1e11 else ts / 1000.0, tz=IST_TZ)
                elif isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts)
                        c_dt = dt.astimezone(IST_TZ) if dt.tzinfo else dt.replace(tzinfo=IST_TZ)
                    except Exception:
                        pass
                if c_dt and c_dt >= session_open and c_dt.date() == latest_candle_time.date():
                    session_candles.append(c)

        # P0-2 FAIL-CLOSE: never compute VWAP on a stale pool. When no
        # session-anchored candles exist the VWAP is UNKNOWN (None), not a
        # whole-day average masquerading as session VWAP.
        if not session_candles:
            return None, True, 0.0
        vwap_pool = session_candles
        vwap_degraded = False
        coverage_pct = round(len(session_candles) / max(1, len(active_candles)) * 100.0, 1)
        cum_vol = sum(float(c.get("volume", 0)) for c in vwap_pool)
        cum_pv = sum(
            float(c.get("volume", 0)) * ((float(c.get("high", 0)) + float(c.get("low", 0)) + float(c.get("close", 0))) / 3.0)
            for c in vwap_pool
        )
        if cum_vol > 0:
            return Decimal(str(round(cum_pv / cum_vol, 2))), vwap_degraded, coverage_pct
        return None, True, 0.0
    except Exception as v_err:
        logger.debug("session_vwap_calc_error", error=str(v_err))
        return None, True, 0.0


def detect_market_regime(ta_analysis: dict[str, Any]) -> str:
    """
    Detects quantitative market regime:
    TREND_UP / TREND_DOWN (ADX>=22 + trend), HIGH_VOL (atr_pct>=80),
    COMPRESSION_SQUEEZE (bb_width pct<=20 + adx<18), EVENT, else RANGE.
    P0-2 FAIL-CLOSE: no synthetic defaults. Missing ADX/ATR/BB inputs
    yield UNKNOWN instead of a fabricated RANGE that would let strategies
    fire on unevaluated structure.
    """
    if not isinstance(ta_analysis, dict) or not ta_analysis:
        return "UNKNOWN"
    trend_d = ta_analysis.get("trend", {}) if isinstance(ta_analysis.get("trend"), dict) else {}
    mom_d = ta_analysis.get("momentum", {}) if isinstance(ta_analysis.get("momentum"), dict) else {}
    vol_d = ta_analysis.get("volatility", {}) if isinstance(ta_analysis.get("volatility"), dict) else {}
    adx_raw = trend_d.get("adx") if trend_d.get("adx") is not None else mom_d.get("adx")
    if adx_raw is None:
        adx_raw = ta_analysis.get("adx")
    if adx_raw is None:
        return "UNKNOWN"
    try:
        adx_val = float(adx_raw)
    except Exception:
        return "UNKNOWN"
    trend_val = trend_d.get("trend", "RANGE")
    try:
        atr_pct_raw = vol_d.get("atr_percentile", None)
        if atr_pct_raw is None:
            return "UNKNOWN"
        atr_pct = float(atr_pct_raw)
    except Exception:
        return "UNKNOWN"
    try:
        bbw_raw = vol_d.get("bb_width_pctile", ta_analysis.get("bollinger_bandwidth_pctile", None))
        if bbw_raw is None:
            return "UNKNOWN"
        bbw = float(bbw_raw)
    except Exception:
        return "UNKNOWN"
    event_flag = bool(ta_analysis.get("event_flag", False) or ta_analysis.get("is_event_day", False))
    if event_flag:
        return "EVENT"
    elif adx_val >= 22.0 and trend_val == "BULLISH":
        return "TREND_UP"
    elif adx_val >= 22.0 and trend_val == "BEARISH":
        return "TREND_DOWN"
    elif atr_pct >= 80.0:
        return "HIGH_VOL"
    elif bbw <= 20.0 and adx_val < 18.0:
        return "COMPRESSION_SQUEEZE"
    return "RANGE"


def reconcile_pit_volume(ta_analysis: dict[str, Any], feat_snap: Any) -> float | None:
    """Reconcile legacy TA volume_ratio with the PIT snapshot's rvol.

    Legacy TA (analyze_volume) runs on the raw pool INCLUDING the forming
    bar, whose partial print reads ~0.1-0.4x mid-bar and would fail every
    volume gate (1.2x/1.3x/1.5x) on ~90% of scans. The snapshot's rvol is
    measured on the last CLOSED bar vs the prior 20 (forming bar dropped as
    lookahead) — the honest participation measure the gates intend.
    Returns the applied rvol, or None when the snapshot carries no usable
    value (TA surface left untouched, gates fail closed as before).
    """
    if not isinstance(ta_analysis, dict) or feat_snap is None:
        return None
    try:
        pit_rvol = float(getattr(feat_snap, "rvol", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    if pit_rvol <= 0:
        return None
    ta_analysis["volume_ratio"] = pit_rvol
    vol_section = ta_analysis.get("volume")
    if isinstance(vol_section, dict):
        vol_section["relative_volume"] = pit_rvol
    return pit_rvol


async def acquire_market_context(
    underlying: str,
    timeframe: str,
    market_svc: Any,
) -> tuple[StrategyContext | None, ScanDiagnostics]:
    """
    Performs complete market data acquisition and context assembly.
    Returns (StrategyContext, ScanDiagnostics).
    """
    started = time.time()
    u = validate_underlying(underlying)
    diag = ScanDiagnostics(underlying=u)

    # 1. Market Session Check
    perm = calendar_service.can_trade_now()
    if not perm.allowed:
        diag.data_quality = "CLOSED"
        diag.reasons.append(f"Market is closed ({perm.reason}: NSE trading hours 09:15 - 15:30 IST). Quantitative scanning paused.")
        diag.duration_ms = int((time.time() - started) * 1000)
        return None, diag

    # 2. Quote Acquisition
    try:
        quote = await asyncio.wait_for(market_svc.get_quote(u), timeout=8.0)
    except TimeoutError:
        diag.data_quality = "OFFLINE"
        diag.error = "quote_timeout_after_8s"
        diag.reasons.append("Quote fetch timed out — feed unreachable")
        diag.duration_ms = int((time.time() - started) * 1000)
        return None, diag
    except ValueError:
        raise
    except Exception as e:
        diag.data_quality = "OFFLINE"
        diag.error = f"quote_failed: {str(e)[:120]}"
        diag.reasons.append(f"Quote fetch failed: {str(e)[:120]}")
        diag.duration_ms = int((time.time() - started) * 1000)
        return None, diag

    if not quote or getattr(quote, "ltp", None) is None or float(getattr(quote, "ltp", 0.0) or 0.0) <= 0:
        diag.data_quality = "OFFLINE"
        diag.error = "no_quote_or_non_positive_ltp"
        diag.reasons.append(f"Quote unavailable or LTP ({getattr(quote, 'ltp', None)}) <= 0")
        diag.duration_ms = int((time.time() - started) * 1000)
        return None, diag

    raw_status = getattr(quote, "status", "UNKNOWN")
    diag.quote_status = str(getattr(raw_status, "value", raw_status))
    diag.provider = str(getattr(quote, "provider", "UNKNOWN"))
    try:
        diag.spot_price = float(quote.ltp)
    except Exception:
        diag.spot_price = None

    if is_fallback_quote(quote):
        diag.data_quality = "OFFLINE"
        diag.error = "fallback_quote"
        diag.reasons.append(f"Provider={diag.provider} status={diag.quote_status} — fallback price rejected, no signals generated")
        diag.duration_ms = int((time.time() - started) * 1000)
        return None, diag

    # Staleness check — P0-2 FAIL-CLOSE: a malformed timestamp is not
    # "fresh by assumption". Any parse failure rejects the quote outright.
    if getattr(quote, "timestamp", None):
        try:
            q_ts = quote.timestamp
            if not isinstance(q_ts, datetime):
                raise ValueError(f"malformed quote.timestamp type={type(q_ts).__name__}")
            if q_ts.tzinfo is None:
                q_ts = q_ts.replace(tzinfo=UTC)
            age_sec = (datetime.now(UTC) - q_ts).total_seconds()
            max_age = max(float(settings.scanner_quote_age_seconds), 30.0)
            if age_sec > max_age:
                diag.data_quality = "DEGRADED"
                diag.error = f"stale_quote_{round(age_sec, 1)}s"
                diag.reasons.append(f"Quote age ({round(age_sec, 1)}s) exceeds max allowed ({max_age}s)")
                diag.duration_ms = int((time.time() - started) * 1000)
                return None, diag
        except ValueError as ve:
            diag.data_quality = "OFFLINE"
            diag.error = f"malformed_quote_timestamp: {str(ve)[:120]}"
            diag.reasons.append(f"Quote timestamp malformed ({str(ve)[:100]}) — fail-closed, no signals")
            diag.duration_ms = int((time.time() - started) * 1000)
            return None, diag
        except Exception as e:
            diag.data_quality = "OFFLINE"
            diag.error = f"malformed_quote_timestamp: {str(e)[:120]}"
            diag.reasons.append(f"Quote timestamp unreadable ({str(e)[:100]}) — fail-closed, no signals")
            diag.duration_ms = int((time.time() - started) * 1000)
            return None, diag

    spot = Decimal(str(quote.ltp))
    prev_close = getattr(quote, "previous_close", None)
    gap_pct = 0.0
    if prev_close and prev_close > 0:
        gap_pct = float(abs((spot - Decimal(str(prev_close))) / Decimal(str(prev_close))) * Decimal("100.0"))

    # 3. Candles Acquisition
    target_tfs = ["1m", "5m", "15m", "1h"]

    async def _fetch_tf(tf_str: str):
        try:
            c_list = await market_svc.get_candles(u, timeframe=tf_str)
            return tf_str, [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in c_list]
        except Exception as ce:
            logger.debug("candle_tf_fetch_error", underlying=u, timeframe=tf_str, error=str(ce))
            return tf_str, []

    try:
        tf_results = await asyncio.wait_for(
            asyncio.gather(*[_fetch_tf(tf_str) for tf_str in target_tfs], return_exceptions=True),
            timeout=15.0,
        )
        candles_dict = {res[0]: res[1] for res in tf_results if isinstance(res, tuple) and len(res) == 2 and res[1]}
    except TimeoutError:
        candles_dict = {}
        diag.reasons.append("Candle fetch timed out — indicators degraded")
    except Exception as e:
        candles_dict = {}
        diag.reasons.append(f"Candle fetch failed: {str(e)[:120]}")

    target_tf = timeframe.lower()
    if target_tf == "1m":
        active_candles = candles_dict.get("1m") or []
        if not active_candles:
            diag.reasons.append("Scalp native 1m candles unavailable — fallback prohibited to prevent timeframe skew")
    else:
        active_candles = candles_dict.get(target_tf) or candles_dict.get("5m") or []
        if not active_candles and "1m" in candles_dict:
            active_candles = candles_dict.get("1m") or []

    diag.candles_count = len(active_candles)
    # P0-2 FAIL-CLOSE: no candles means no indicators, no VWAP, no regime.
    # Returning an empty-candle context would let every downstream default
    # (ADX 20 / RSI 50 / VWAP=spot) fabricate a tradable setup.
    if not active_candles:
        diag.data_quality = "OFFLINE"
        diag.error = "no_active_candles"
        diag.reasons.append(f"No {timeframe} candles available — fail-closed, no strategies evaluated")
        diag.duration_ms = int((time.time() - started) * 1000)
        return None, diag

    # 4. TA Analysis & MTF Alignment — P0-2: no synthetic TA defaults.
    ta_analysis: dict[str, Any] = {}
    if active_candles:
        try:
            ta_analysis = analyze_timeframe(active_candles, symbol=u, timeframe=timeframe) or {}
        except Exception as e:
            diag.reasons.append(f"TA analysis failed: {str(e)[:100]} — fail-closed, no defaults")
            ta_analysis = {}

    mtf_analyses = {}
    for tf_k, c_list in candles_dict.items():
        if c_list:
            try:
                mtf_analyses[tf_k] = analyze_timeframe(c_list, symbol=u, timeframe=tf_k)
            except Exception:
                pass
    mtf_result = compute_alignment(mtf_analyses) if mtf_analyses else {"overall_bias": ta_analysis.get("bias", "NEUTRAL"), "alignment_score": 70.0}

    # 5. F&O Context
    fno_data = {}
    fno_degraded = False
    try:
        from app.fno.context import get_fno_context
        fno_data = await asyncio.wait_for(get_fno_context(u), timeout=6.0) or {}
    except TimeoutError:
        fno_degraded = True
        diag.reasons.append("F&O context timed out — PCR/OI degraded")
    except Exception as e:
        fno_degraded = True
        diag.reasons.append(f"F&O context failed: {str(e)[:100]}")
    if not fno_data:
        fno_degraded = True
        fno_data = {}

    # 6. Regime & VWAP — P0-2: regime UNKNOWN when TA is unevaluated;
    # strategies are skipped (fail-closed) instead of running on defaults.
    regime = detect_market_regime(ta_analysis)
    if regime == "UNKNOWN" or not ta_analysis:
        diag.data_quality = "OFFLINE"
        diag.error = "ta_unavailable_regime_unknown"
        diag.reasons.append("TA unavailable or incomplete (ADX/ATR/BB missing) — regime UNKNOWN, strategies skipped")
        diag.duration_ms = int((time.time() - started) * 1000)
        return None, diag
    vwap_val, vwap_degraded, vwap_coverage_pct = calculate_session_vwap(active_candles)

    if ta_analysis:
        trend_d = ta_analysis.get("trend", {}) if isinstance(ta_analysis.get("trend"), dict) else {}
        mom_d = ta_analysis.get("momentum", {}) if isinstance(ta_analysis.get("momentum"), dict) else {}
        vol_d = ta_analysis.get("volatility", {}) if isinstance(ta_analysis.get("volatility"), dict) else {}
        volm_d = ta_analysis.get("volume", {}) if isinstance(ta_analysis.get("volume"), dict) else {}

        # P0-2: surface real values only — never invent ADX/RSI/ATR/vol_ratio.
        _adx_raw = trend_d.get("adx") if trend_d.get("adx") is not None else mom_d.get("adx")
        if _adx_raw is None:
            _adx_raw = ta_analysis.get("adx")
        ta_analysis["adx"] = float(_adx_raw) if _adx_raw is not None else None
        _rsi_raw = mom_d.get("rsi") if mom_d.get("rsi") is not None else ta_analysis.get("rsi")
        ta_analysis["rsi"] = float(_rsi_raw) if _rsi_raw is not None else None
        _atr_raw = vol_d.get("atr") if vol_d.get("atr") is not None else ta_analysis.get("atr")
        ta_analysis["atr"] = float(_atr_raw) if _atr_raw is not None else None

        rel_vol_raw = volm_d.get("relative_volume") if volm_d.get("relative_volume") is not None else volm_d.get("ratio")
        ta_analysis["volume_ratio"] = float(rel_vol_raw) if rel_vol_raw is not None else None
        rel_vol = ta_analysis["volume_ratio"]

        bb_u = vol_d.get("bollinger_upper")
        bb_m = vol_d.get("bollinger_middle")
        bb_l = vol_d.get("bollinger_lower")
        ta_analysis["bollinger_bands"] = {
            "upper": bb_u,
            "middle": bb_m,
            "lower": bb_l,
        }
        ta_analysis["bollinger_upper"] = bb_u
        ta_analysis["bollinger_middle"] = bb_m
        ta_analysis["bollinger_lower"] = bb_l

        # Compute breakout pressure from price action, trend, and volume.
        # P0-2: no invented volume_ratio — skip volume term when unknown.
        bp = 50.0
        if trend_d.get("trend") == "BULLISH":
            bp += 15.0
        elif trend_d.get("trend") == "BEARISH":
            bp -= 15.0
        try:
            _rv = float(rel_vol) if rel_vol is not None else None
        except Exception:
            _rv = None
        if _rv is not None:
            if _rv > 1.2:
                bp += 12.0
            elif _rv < 0.8:
                bp -= 10.0
        if vwap_val:
            if spot >= vwap_val:
                bp += 10.0
            else:
                bp -= 10.0
        ta_analysis["breakout_pressure"] = max(0.0, min(100.0, bp))

    vol_ma = None
    if len(active_candles) >= 20:
        vol_ma = sum(float(c.get("volume", 0)) for c in active_candles[-20:]) / 20.0

    now_ist = datetime.now(IST_TZ)
    ist_minute_of_day = now_ist.hour * 60 + now_ist.minute
    lunch_session = 720 <= ist_minute_of_day <= 810

    vix_pct_val = None
    if fno_data:
        vix_pct_val = fno_data.get("india_vix_percentile") or fno_data.get("vix_percentile") or fno_data.get("vix_pct")
    if vix_pct_val is None and ta_analysis:
        vix_pct_val = ta_analysis.get("volatility", {}).get("vix_percentile") or ta_analysis.get("volatility", {}).get("vix_pct")
    try:
        vix_percentile_val = float(vix_pct_val) if vix_pct_val is not None else None
    except (ValueError, TypeError):
        vix_percentile_val = None

    # P0-2: prior_day_high/low must come from DAILY candles, never from
    # quote.high/low (today's intraday range is not yesterday's range).
    prior_day_high: float | None = None
    prior_day_low: float | None = None
    try:
        _daily_raw = await market_svc.get_candles(u, timeframe="1D")
        _daily = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in (_daily_raw or [])]
        if len(_daily) >= 2:
            _prev = _daily[-2]
            _ph, _pl = _prev.get("high"), _prev.get("low")
            prior_day_high = float(_ph) if _ph is not None else None
            prior_day_low = float(_pl) if _pl is not None else None
        elif len(_daily) == 1:
            # Single daily bar: cannot prove it is "prior day" — leave None
            # rather than mislabelling today's developing range.
            prior_day_high, prior_day_low = None, None
    except Exception as _pd_err:
        logger.debug("prior_day_fetch_failed", underlying=u, error=str(_pd_err))
        prior_day_high, prior_day_low = None, None

    feat_snap = None
    try:
        feat_snap = compute_feature_snapshot(
            underlying=u,
            spot_price=float(spot),
            candles=active_candles,
            timeframe=timeframe,
            vwap=float(vwap_val) if vwap_val else None,
            indicators=ta_analysis,
            timestamp_ms=int(time.time() * 1000),
            prior_day_high=prior_day_high,
            prior_day_low=prior_day_low,
        )
    except Exception as _fs_err:
        # Feature engine is fail-closed (InsufficientData on <MIN_BARS or
        # forming candle). No snapshot means strategies cannot evaluate PIT-
        # safely — skip instead of running on neutral-50 fabrications.
        logger.info("feature_snapshot_unavailable_skip", underlying=u, error=str(_fs_err)[:120])
        diag.data_quality = "OFFLINE"
        diag.error = f"feature_snapshot_insufficient: {str(_fs_err)[:100]}"
        diag.reasons.append(f"Feature snapshot unavailable ({str(_fs_err)[:100]}) — strategies skipped")
        diag.duration_ms = int((time.time() - started) * 1000)
        return None, diag

    # PIT reconciliation (see reconcile_pit_volume): align the TA surface
    # with the closed-bar rvol so detect() gates and breakout-pressure agree
    # with the participation engine downstream.
    reconcile_pit_volume(ta_analysis, feat_snap)

    ctx = StrategyContext(
        underlying=u,  # type: ignore
        spot_price=spot,
        timeframe=timeframe,  # type: ignore
        indicators=ta_analysis,
        mtf=mtf_result,
        fno=fno_data,
        regime=regime,
        session_state="OPEN",
        candles=active_candles,
        vwap=vwap_val,
        volume_ma_20=vol_ma,
        # P0-2: case-insensitive — "1m"/"1M" are the same candle.
        is_new_1m_candle=(str(timeframe).upper() == "1M"),
        is_new_5m_candle=(str(timeframe).upper() == "5M"),
        fno_degraded=fno_degraded,
        vwap_degraded=vwap_degraded,
        vwap_coverage_pct=vwap_coverage_pct,
        timestamp_ms=int(time.time() * 1000),
        vix_percentile=vix_percentile_val,
        lunch_session=lunch_session,
        pre_market_gap_pct=float(gap_pct),
        feature_snapshot=feat_snap,
    )

    diag.fno_degraded = fno_degraded
    diag.vwap_degraded = vwap_degraded
    diag.vwap_coverage_pct = vwap_coverage_pct
    diag.duration_ms = int((time.time() - started) * 1000)
    if not diag.candles_count or fno_degraded or vwap_degraded:
        diag.data_quality = "DEGRADED"
    else:
        diag.data_quality = "LIVE"

    return ctx, diag
