"""Point-in-Time Feature Extractor V3 (f28-v3) for DROID ML Engine.

Implements Section 9 and Section 8 of the DROID ML Production & Research Specification.
Strictly enforces:
    max_source_timestamp <= feature_timestamp
Any violation immediately raises a TemporalLeakageError.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from app.ml.features.schema import (
    FEATURE_NAMES_V3,
    FEATURE_SCHEMA_V3,
    NEUTRAL_IMPUTE_V3,
    FeatureVectorV3,
)

IST = timezone(timedelta(hours=5, minutes=30))


class TemporalLeakageError(ValueError):
    """Raised when an input observation violates point-in-time causality."""
    pass


def extract_features_v3(
    instrument: str,
    feature_timestamp_ms: int,
    candles_1m: List[Dict[str, Any]],
    indicators: Optional[Dict[str, Any]] = None,
    options_analytics: Optional[Dict[str, Any]] = None,
    vix_quote: Optional[Dict[str, Any]] = None,
    expiry_date: Optional[datetime] = None,
) -> FeatureVectorV3:
    """
    Extracts a strictly point-in-time validated 28-feature vector.
    
    Args:
        instrument: Symbol (e.g., "NIFTY", "BANKNIFTY")
        feature_timestamp_ms: Point-in-time evaluation timestamp in epoch ms (T)
        candles_1m: Historical 1-minute bars up to T
        indicators: Precomputed technical indicators at or before T
        options_analytics: Options chain analytics snapshot at or before T
        vix_quote: India VIX quote snapshot at or before T
        expiry_date: Nearest expiry datetime
    """
    max_source_ts = 0
    missing_count = 0
    f_dict: Dict[str, float] = dict(NEUTRAL_IMPUTE_V3)

    # 1. Filter and validate candles_1m strictly <= feature_timestamp_ms
    valid_candles: List[Dict[str, Any]] = []
    for c in candles_1m:
        ts = int(c.get("timestamp_ms") or c.get("time") or 0)
        if ts > feature_timestamp_ms:
            raise TemporalLeakageError(
                f"Leakage detected: candle timestamp ({ts}) > feature_timestamp ({feature_timestamp_ms})"
            )
        if ts > max_source_ts:
            max_source_ts = ts
        valid_candles.append(c)

    if not valid_candles:
        raise ValueError("No historical candles available at or before feature_timestamp")

    curr = valid_candles[-1]
    close = float(curr.get("close", 0.0))
    open_p = float(curr.get("open", close))
    high_p = float(curr.get("high", close))
    low_p = float(curr.get("low", close))
    bar_range = max(0.05, high_p - low_p)

    # Returns calculation
    def _pct_change(lookback_idx: int) -> float:
        if len(valid_candles) > lookback_idx:
            prev_close = float(valid_candles[-1 - lookback_idx].get("close", close))
            if prev_close > 0:
                return (close - prev_close) / prev_close
        return 0.0

    f_dict["ret_1m"] = _pct_change(1)
    f_dict["ret_3m"] = _pct_change(3)
    f_dict["ret_5m"] = _pct_change(5)
    f_dict["ret_15m"] = _pct_change(15)

    # ATR (14-period)
    if len(valid_candles) >= 14:
        trs = []
        for i in range(len(valid_candles) - 14, len(valid_candles)):
            h = float(valid_candles[i].get("high", 0))
            l = float(valid_candles[i].get("low", 0))
            pc = float(valid_candles[i - 1].get("close", l)) if i > 0 else l
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = sum(trs) / len(trs) if trs else 20.0
    else:
        atr = max(5.0, bar_range)
    f_dict["atr_14"] = atr
    f_dict["range_expansion_ratio"] = min(5.0, bar_range / max(0.1, atr))
    f_dict["body_to_range_ratio"] = min(1.0, abs(close - open_p) / bar_range)
    f_dict["upper_wick_ratio"] = min(1.0, (high_p - max(open_p, close)) / bar_range)
    f_dict["lower_wick_ratio"] = min(1.0, (min(open_p, close) - low_p) / bar_range)
    f_dict["atr_percentile"] = min(100.0, max(0.0, (atr / close) * 10000.0))

    # 2. Indicators & Trend Structure
    ind = indicators or {}
    vwap = float(ind.get("vwap") or 0.0)
    if vwap > 0:
        f_dict["vwap_distance_pct"] = (close - vwap) / vwap * 100.0
    else:
        f_dict["vwap_distance_pct"] = 0.0
        missing_count += 1

    ema20 = float(ind.get("ema20") or 0.0)
    ema50 = float(ind.get("ema50") or 0.0)
    ema200 = float(ind.get("ema200") or 0.0)
    if ema20 > 0 and ema50 > 0 and ema200 > 0:
        if ema20 > ema50 > ema200:
            f_dict["ema_alignment_score"] = 1.0
        elif ema20 < ema50 < ema200:
            f_dict["ema_alignment_score"] = -1.0
        else:
            f_dict["ema_alignment_score"] = 0.0
    else:
        f_dict["ema_alignment_score"] = 0.0

    st_dir = str(ind.get("supertrend_direction", "")).upper()
    f_dict["supertrend_direction"] = 1.0 if "BULL" in st_dir or st_dir == "1" else (-1.0 if "BEAR" in st_dir or st_dir == "-1" else 0.0)
    f_dict["adx_14"] = float(ind.get("adx_14") or ind.get("adx") or 20.0)

    # Trend persistence (last 10 bars close above open)
    lookback_bars = min(10, len(valid_candles))
    bull_bars = sum(1 for c in valid_candles[-lookback_bars:] if float(c.get("close", 0)) >= float(c.get("open", 0)))
    f_dict["trend_persistence_score"] = (bull_bars / lookback_bars) * 2.0 - 1.0  # [-1.0, 1.0]

    # Realized vol (std dev of 1m returns)
    if len(valid_candles) >= 15:
        rets = [
            (float(valid_candles[i].get("close", 1)) - float(valid_candles[i - 1].get("close", 1)))
            / float(valid_candles[i - 1].get("close", 1))
            for i in range(len(valid_candles) - 15, len(valid_candles))
        ]
        mean_r = sum(rets) / len(rets)
        var_r = sum((r - mean_r) ** 2 for r in rets) / len(rets)
        f_dict["realized_vol_15m"] = math.sqrt(var_r) * math.sqrt(252 * 375)
    else:
        f_dict["realized_vol_15m"] = 0.12

    # 3. Volatility Context & India VIX
    if vix_quote:
        vix_ts = int(vix_quote.get("timestamp_ms") or vix_quote.get("time") or 0)
        if vix_ts > feature_timestamp_ms:
            raise TemporalLeakageError(f"Leakage detected: VIX timestamp ({vix_ts}) > feature_timestamp ({feature_timestamp_ms})")
        if vix_ts > max_source_ts:
            max_source_ts = vix_ts
        vix_val = float(vix_quote.get("ltp") or vix_quote.get("close") or 14.0)
        f_dict["vix_level"] = vix_val
        f_dict["vix_normalized"] = max(0.0, min(1.0, (vix_val - 9.0) / 20.0))
    else:
        missing_count += 1

    f_dict["vol_expansion_flag"] = 1.0 if f_dict["range_expansion_ratio"] > 1.5 else 0.0

    # 4. F&O Context
    if options_analytics:
        opt_ts = int(options_analytics.get("timestamp_ms") or 0)
        if opt_ts > feature_timestamp_ms:
            raise TemporalLeakageError(f"Leakage detected: options timestamp ({opt_ts}) > feature_timestamp ({feature_timestamp_ms})")
        if opt_ts > max_source_ts:
            max_source_ts = opt_ts
        f_dict["pcr_oi"] = float(options_analytics.get("pcr", 1.0) or 1.0)
        f_dict["pcr_oi_change"] = float(options_analytics.get("pcr_change", 0.0) or 0.0)
        ce_oi = float(options_analytics.get("total_ce_oi", 1.0) or 1.0)
        pe_oi = float(options_analytics.get("total_pe_oi", 1.0) or 1.0)
        tot_oi = ce_oi + pe_oi
        f_dict["oi_imbalance_ratio"] = (pe_oi - ce_oi) / tot_oi if tot_oi > 0 else 0.0
        f_dict["atm_iv"] = float(options_analytics.get("atm_iv", 14.0) or 14.0)
        f_dict["spread_bps"] = float(options_analytics.get("spread_bps", 2.5) or 2.5)
    else:
        missing_count += 1

    # 5. Session and Expiry Dynamics
    dt_ist = datetime.fromtimestamp(feature_timestamp_ms / 1000.0, tz=IST)
    market_open = dt_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = dt_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    mins_open = max(0.0, (dt_ist - market_open).total_seconds() / 60.0)
    mins_close = max(0.0, (market_close - dt_ist).total_seconds() / 60.0)
    f_dict["minutes_since_open"] = min(375.0, mins_open)
    f_dict["minutes_to_close"] = min(375.0, mins_close)

    if expiry_date:
        exp_ist = expiry_date.astimezone(IST) if expiry_date.tzinfo else expiry_date.replace(tzinfo=IST)
        dte = max(0.0, (exp_ist.date() - dt_ist.date()).days)
        f_dict["days_to_expiry"] = float(dte)
        f_dict["is_expiry_day"] = 1.0 if dte == 0 else 0.0
    else:
        f_dict["days_to_expiry"] = 3.0
        f_dict["is_expiry_day"] = 0.0

    # Build ordered vector
    ordered_features = [f_dict[k] for k in FEATURE_NAMES_V3]

    feature_vec = FeatureVectorV3(
        schema_version=FEATURE_SCHEMA_V3,
        instrument=instrument,
        feature_timestamp=feature_timestamp_ms,
        max_source_timestamp=max(max_source_ts, feature_timestamp_ms),
        features=ordered_features,
        feature_dict=f_dict,
        missing_imputed_count=missing_count,
    )
    return feature_vec
