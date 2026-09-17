"""
Central Feature Engine & Snapshot Provider (§17).
Produces unified, immutable FeatureSnapshot objects combining Price, Trend, Momentum,
Volatility, Volume, EMA states, and Market Structure.

P0-2 FAIL-CLOSE: forming candles are dropped, MIN_BARS are enforced via
InsufficientData (never neutral-50), RVOL excludes the current bar, VWAP slope
comes from the VWAP series, and the snapshot carries PIT timestamps.
"""
from __future__ import annotations

import math
import time as _time
from datetime import datetime as _dt
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field

from app.signals.features.ema_features import EMAFeatures, extract_ema_features
from app.signals.features.structure import MarketStructureFeatures, extract_market_structure
from app.signals.safety.clocks import IST as IST_TZ

# P0-2 MIN_BARS (mirrors sub-modules; enforced here before any math).
MIN_BARS_EMA50 = 60
MIN_BARS_EMA200 = 210
MIN_BARS_STRUCTURE = 20


class InsufficientData(RuntimeError):
    """Not enough PIT-safe bars to evaluate features — caller must skip."""


_CLOSE_KEYS = ("close_time", "close_timestamp_ms", "close_timestamp", "closeTime", "end_time", "end_timestamp")


def _to_ms(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, _dt):
        try:
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST_TZ)
            return int(dt.timestamp() * 1000)
        except Exception:
            return None
    if isinstance(value, (int, float)):
        try:
            v = float(value)
        except Exception:
            return None
        if v <= 0:
            return None
        return int(v if v > 1e11 else v * 1000)
    if isinstance(value, str):
        try:
            text = value.strip().replace("Z", "+00:00")
            dt = _dt.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST_TZ)
            return int(dt.timestamp() * 1000)
        except Exception:
            return None
    return None


def _candle_close_ms(candle: dict, timeframe: str = "5M") -> Optional[int]:
    """Resolve a candle's close time in ms. Prefers explicit close_time keys."""
    for k in _CLOSE_KEYS:
        if candle.get(k) is not None:
            ms = _to_ms(candle.get(k))
            if ms is not None:
                return ms
    # Fallback: timestamp + one timeframe period (the bar closes one period
    # after it opens). Without this the forming bar looks "closed".
    ts_ms = _to_ms(candle.get("timestamp"))
    if ts_ms is None:
        return None
    tf = str(timeframe or "5M").upper()
    _dur = {"1M": 60_000, "3M": 180_000, "5M": 300_000, "15M": 900_000,
            "30M": 1_800_000, "1H": 3_600_000, "4H": 14_400_000,
            "1D": 86_400_000, "1W": 604_800_000}.get(tf, 300_000)
    return ts_ms + _dur


def drop_forming_candles(candles: list[dict], decision_ts_ms: int, timeframe: str = "5M") -> list[dict]:
    """Drop any bar whose close_time > decision_ts (unclosed/forming)."""
    kept: list[dict] = []
    for c in candles or []:
        if not isinstance(c, dict):
            continue
        close_ms = _candle_close_ms(c, timeframe)
        if close_ms is not None and close_ms > (decision_ts_ms + 250):
            continue
        # Hard lookahead guard: open timestamp itself beyond decision.
        ts_ms = _to_ms(c.get("timestamp"))
        if ts_ms is not None and ts_ms > (decision_ts_ms + 250):
            continue
        kept.append(c)
    return kept


class FeatureSnapshot(BaseModel):
    underlying: str
    spot_price: float
    timeframe: str
    timestamp_ms: int
    # P0-2 PIT: decision_ts that priced this snapshot + newest input bar that
    # fed it. Validators must prove inputs_max_ts <= timestamp_ms.
    inputs_max_ts: Optional[int] = None

    # Feature Domains
    ema: EMAFeatures = Field(default_factory=EMAFeatures)
    structure: MarketStructureFeatures = Field(default_factory=MarketStructureFeatures)

    # Momentum & Velocity
    roc_1: float = 0.0                     # 1-bar return %
    roc_3: float = 0.0                     # 3-bar return %
    roc_5: float = 0.0                     # 5-bar return %
    momentum_acceleration: float = 0.0     # Change in ROC
    rsi: Optional[float] = None
    macd_histogram: Optional[float] = None

    # Volatility & Range Compression
    atr: float = 20.0
    atr_pct: float = 0.0                   # ATR as % of spot
    is_volatility_compressed: bool = False # Bollinger squeeze / ATR contraction
    is_volatility_expanding: bool = False

    # Volume & Participation Proxies
    rvol: float = 1.0                      # Relative Volume vs prior-20 MA (excl current)
    volume_acceleration: float = 0.0       # Volume ROC
    vwap: Optional[float] = None
    distance_to_vwap_pct: float = 0.0
    vwap_slope: float = 0.0

    # Raw context pass-through
    raw_indicators: dict[str, Any] = Field(default_factory=dict)


def compute_feature_snapshot(
    underlying: str,
    spot_price: float,
    candles: list[dict],
    timeframe: str = "5M",
    vwap: Optional[float] = None,
    indicators: Optional[dict[str, Any]] = None,
    timestamp_ms: Optional[int] = None,
    prior_day_high: Optional[float] = None,
    prior_day_low: Optional[float] = None,
    decision_ts_ms: Optional[int] = None,
    vwap_series: Optional[list[float]] = None,
) -> FeatureSnapshot:
    """Computes a complete, unified FeatureSnapshot from candle data and live context.

    P0-2 FAIL-CLOSE:
      * forming candle dropped (require close_time <= decision_ts)
      * <MIN_BARS raises InsufficientData (never neutral-50)
      * RVOL denominator is the PRIOR 20 bars excluding the current bar
      * VWAP slope comes from the VWAP series, never from spot-vs-close
      * timestamp_ms = decision_ts; inputs_max_ts = newest input bar (PIT)
    """
    decision_ts = int(decision_ts_ms) if decision_ts_ms is not None else (
        int(timestamp_ms) if timestamp_ms is not None else int(_time.time() * 1000)
    )
    ind = indicators or {}

    # 0. Drop the unclosed forming bar — it is lookahead, not data.
    pit_candles = drop_forming_candles(list(candles or []), decision_ts, timeframe)
    if len(pit_candles) < MIN_BARS_STRUCTURE:
        raise InsufficientData(
            f"Need >= {MIN_BARS_STRUCTURE} closed bars for structure, got {len(pit_candles)} "
            f"(raw {len(candles or [])}, decision_ts={decision_ts})"
        )
    if len(pit_candles) < MIN_BARS_EMA50:
        raise InsufficientData(
            f"Need >= {MIN_BARS_EMA50} closed bars for EMA50, got {len(pit_candles)}"
        )

    closes = [float(c.get("close", 0)) for c in pit_candles]

    # 1. EMA Features (strict=True raises when <MIN_BARS_EMA50).
    try:
        ema_feat = extract_ema_features(closes, current_price=spot_price, strict=True)
    except Exception as e:
        # Normalize sub-module InsufficientData to the engine type so callers
        # can catch a single symbol.
        raise InsufficientData(str(e)) from e

    # 2. Market Structure Features (strict=True raises when <20).
    try:
        struct_feat = extract_market_structure(
            pit_candles,
            current_price=spot_price,
            prior_day_high=prior_day_high,
            prior_day_low=prior_day_low,
            strict=True,
        )
    except Exception as e:
        raise InsufficientData(str(e)) from e

    # 3. Momentum & Velocity (on PIT-closed bars only).
    r1, r3, r5, acc = 0.0, 0.0, 0.0, 0.0
    if len(closes) >= 2 and closes[-2] > 0:
        r1 = round((closes[-1] - closes[-2]) / closes[-2] * 100.0, 3)
    if len(closes) >= 4 and closes[-4] > 0:
        r3 = round((closes[-1] - closes[-4]) / closes[-4] * 100.0, 3)
    if len(closes) >= 6 and closes[-6] > 0:
        r5 = round((closes[-1] - closes[-6]) / closes[-6] * 100.0, 3)
        # Acceleration: r1 vs prior r1
        prior_r1 = (closes[-2] - closes[-3]) / closes[-3] * 100.0 if closes[-3] > 0 else 0.0
        acc = round(r1 - prior_r1, 4)

    rsi_val = None
    if "momentum" in ind and isinstance(ind["momentum"], dict):
        rsi_val = ind["momentum"].get("rsi")
    elif "rsi" in ind:
        rsi_val = ind.get("rsi")

    macd_hist = None
    if "momentum" in ind and isinstance(ind["momentum"], dict):
        macd_hist = ind["momentum"].get("macd_hist")

    # 4. Volatility & Compression (no synthetic 20.0 when indicators carry ATR).
    atr_val: float
    if "volatility" in ind and isinstance(ind["volatility"], dict) and ind["volatility"].get("atr") is not None:
        try:
            atr_val = float(ind["volatility"].get("atr"))
        except Exception:
            atr_val = 20.0
    elif "atr" in ind and ind.get("atr") is not None:
        try:
            atr_val = float(ind.get("atr"))
        except Exception:
            atr_val = 20.0
    else:
        atr_val = 20.0

    atr_pct_val = round((atr_val / spot_price * 100.0), 3) if spot_price > 0 else 0.0

    # Compression check: Bandwidth or range narrowness
    is_compressed = False
    is_expanding = False
    if "volatility" in ind and isinstance(ind["volatility"], dict):
        try:
            bw = float(ind["volatility"].get("bollinger_bandwidth", 0.0) or 0.0)
        except Exception:
            bw = 0.0
        if bw > 0:
            is_compressed = bw < 0.015  # <1.5% bandwidth
            is_expanding = bw > 0.035
    elif ema_feat.is_compressed:
        is_compressed = True

    # 5. Volume & Participation — P0-2: RVOL denominator is the PRIOR 20 bars
    # EXCLUDING the current bar. Including the current bar dilutes spikes
    # (a 3x volume burst divided by an average that contains itself reads ~1x).
    rvol_val = 1.0
    vol_acc_val = 0.0
    if len(pit_candles) >= 2:
        try:
            _prior = pit_candles[-21:-1] if len(pit_candles) >= 21 else pit_candles[:-1]
            _prior_vols = [float(c.get("volume", 0) or 0) for c in _prior[-20:]]
            _cur_vol = float(pit_candles[-1].get("volume", 0) or 0)
            _avg = sum(_prior_vols) / max(1, len(_prior_vols)) if _prior_vols else 0.0
            if _avg > 0:
                rvol_val = round(_cur_vol / _avg, 2)
            _prev_vol = float(pit_candles[-2].get("volume", 0) or 0)
            if _prev_vol > 0:
                vol_acc_val = round((_cur_vol - _prev_vol) / _prev_vol, 3)
        except Exception:
            pass

    # 6. VWAP Distance & Slope — P0-2: slope comes from the VWAP SERIES, never
    # from spot-vs-close (which measures price momentum, not VWAP drift).
    vwap_val = vwap
    dist_vwap = 0.0
    vwap_slope_val = 0.0
    if vwap_val and vwap_val > 0:
        dist_vwap = round((spot_price - vwap_val) / vwap_val * 100.0, 3)
        try:
            if vwap_series is not None and len(vwap_series) >= 4 and vwap_series[-4]:
                vwap_slope_val = round(
                    (float(vwap_series[-1]) - float(vwap_series[-4])) / float(vwap_series[-4]) * 100.0, 4
                )
            else:
                vwap_slope_val = 0.0
        except Exception:
            vwap_slope_val = 0.0

    # PIT timestamps: snapshot is stamped at the decision, with the newest
    # input bar recorded so validators can prove inputs_max_ts <= decision.
    try:
        _max_ts: Optional[int] = None
        for c in pit_candles:
            _m = _to_ms((c or {}).get("timestamp"))
            if _m is not None and (_max_ts is None or _m > _max_ts):
                _max_ts = _m
    except Exception:
        _max_ts = None

    return FeatureSnapshot(
        underlying=underlying,
        spot_price=spot_price,
        timeframe=timeframe,
        timestamp_ms=decision_ts,
        inputs_max_ts=_max_ts,
        ema=ema_feat,
        structure=struct_feat,
        roc_1=r1,
        roc_3=r3,
        roc_5=r5,
        momentum_acceleration=acc,
        rsi=rsi_val,
        macd_histogram=macd_hist,
        atr=atr_val,
        atr_pct=atr_pct_val,
        is_volatility_compressed=is_compressed,
        is_volatility_expanding=is_expanding,
        rvol=rvol_val,
        volume_acceleration=vol_acc_val,
        vwap=vwap_val,
        distance_to_vwap_pct=dist_vwap,
        vwap_slope=vwap_slope_val,
        raw_indicators=ind,
    )
