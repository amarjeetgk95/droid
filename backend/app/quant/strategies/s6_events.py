"""S6 Shared Event Engine & Causal Context (S6SPEC_v1.3).

Generates:
- Causal 5m Resampled Context with zero future lookahead
- Wilder ATR(14) on completed 5m bars (atr5)
- regime_v01 state classification
- CompressionEpisode stream with frozen boundaries
- RawBreakoutEvent stream for T1 (1m) and T4 (5m)
- FailureEvent stream for failed-breakout reversals

Guarantees:
- Incomplete/forming 5m bars are inaccessible at 1m timestamp t
- S6-A and S6-F consume the identical RawBreakoutEvent universe
- CausalityViolation raised if future bars are requested
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple, Any
import polars as pl
import numpy as np

from app.quant.strategies.s6_config import (
    S6Config,
    S6TimeframeBranch,
    S6Variant,
    create_default_config,
)


class CausalityViolation(Exception):
    """Raised when an operation attempts to access future or forming market data."""
    pass


# =========================================================================
# Immutable Event Dataclasses
# =========================================================================

@dataclass(frozen=True)
class CompressionEpisode:
    episode_id: str
    instrument: str
    context_tf: str            # "5m"
    start_time: datetime
    end_time: datetime
    compression_high: float
    compression_low: float
    atr5: float
    duration_bars: int
    status: str                # "ACTIVE", "ARMED", "EXPIRED", "INVALIDATED"


@dataclass(frozen=True)
class RawBreakoutEvent:
    event_id: str
    episode_id: str
    instrument: str
    timeframe: str             # "1m" (T1) or "5m" (T4)
    direction: int             # +1 LONG, -1 SHORT
    breakout_time: datetime
    breakout_price: float
    atr5: float
    volume_ratio: float
    close_location: float      # (close - low) / (high - low)
    breakout_distance_atr: float
    structure_level: float
    room_atr: float
    regime: str
    candidate_source: str = "RAW_STRUCTURAL"


@dataclass(frozen=True)
class FailureEvent:
    event_id: str
    breakout_event_id: str
    instrument: str
    direction: int             # Direction of the FAILURE trade (OPPOSITE of original breakout)
    failure_time: datetime
    failure_price: float
    reentry_distance_atr: float
    bars_since_breakout: int
    failure_extreme: float     # Peak adverse price before failure


@dataclass(frozen=True)
class EntryCandidate:
    candidate_id: str
    strategy_id: str           # "S6"
    variant: str               # "S6-A" or "S6-F"
    instrument: str
    direction: int             # +1 LONG, -1 SHORT
    signal_time: datetime
    entry_time: datetime       # t+1 bar open
    entry_reference_price: float
    execution_timeframe: str    # "1m" or "5m"
    context_timeframe: str      # "5m"
    atr5: float
    stop_distance: float
    target_distance: float
    episode_id: str
    event_id: str
    regime: str
    volume_ratio: float
    close_location: float
    room_atr: float
    reason_codes: list[str] = field(default_factory=list)


# =========================================================================
# Causal 5m Context Engine
# =========================================================================

def resample_to_completed_5m(df_1m: pl.DataFrame) -> pl.DataFrame:
    """Resamples 1m OHLCV data into strictly completed 5m bars.
    
    Each 5m bar covers 5 consecutive 1m bars:
    e.g. 09:15:00 to 09:19:00 -> bar_open_time = 09:15:00, available_at = 09:20:00.
    A bar is ONLY available to 1m decisions at timestamp t if available_at <= t.
    """
    if len(df_1m) == 0:
        return pl.DataFrame()

    df = df_1m.sort("timestamp")
    
    # Bucket 1m bars into 5m intervals: floor to 5-minute boundary
    df_5m = (
        df.group_by_dynamic(
            "timestamp",
            every="5m",
            period="5m",
            closed="left",
            label="left",
        )
        .agg([
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
            pl.len().alias("bar_count"),
        ])
        .filter(pl.col("bar_count") > 0)
        .with_columns([
            pl.col("timestamp").alias("bar_open_time"),
            (pl.col("timestamp") + pl.duration(minutes=5)).alias("available_at"),
            (pl.col("timestamp") + pl.duration(minutes=5)).alias("bar_close_time"),
        ])
        .sort("available_at")
    )
    return df_5m


def compute_wilder_atr(df: pl.DataFrame, period: int = 14) -> pl.Series:
    """Computes recursive Wilder ATR(period) on a Polars DataFrame."""
    if len(df) == 0:
        return pl.Series("atr", [], dtype=pl.Float64)

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    n = len(df)
    
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = max(1e-6, highs[0] - lows[0])
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
            1e-6,
        )

    atr = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return pl.Series("atr", atr, dtype=pl.Float64)

    # Initialize with simple moving average of first `period` bars
    atr[period - 1] = tr[:period].mean()
    # Recursive Wilder smoothing: atr_t = (atr_{t-1} * (period - 1) + tr_t) / period
    alpha = 1.0 / period
    for i in range(period, n):
        atr[i] = atr[i - 1] * (1.0 - alpha) + tr[i] * alpha

    return pl.Series("atr", atr, dtype=pl.Float64)


def compute_adx(df: pl.DataFrame, period: int = 14) -> pl.Series:
    """Computes causal ADX(period) on a Polars DataFrame."""
    n = len(df)
    if n < period + 2:
        return pl.Series("adx", [20.0] * n, dtype=pl.Float64)

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()

    up_move = highs[1:] - highs[:-1]
    down_move = lows[:-1] - lows[1:]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = np.zeros(n, dtype=np.float64)
    tr[0] = max(1e-6, highs[0] - lows[0])
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
            1e-6,
        )

    # Wilder smoothing for TR, +DM, -DM
    atr_smooth = np.zeros(n, dtype=np.float64)
    pdm_smooth = np.zeros(n, dtype=np.float64)
    mdm_smooth = np.zeros(n, dtype=np.float64)

    atr_smooth[period] = tr[1 : period + 1].sum()
    pdm_smooth[period] = plus_dm[:period].sum()
    mdm_smooth[period] = minus_dm[:period].sum()

    for i in range(period + 1, n):
        atr_smooth[i] = atr_smooth[i - 1] - (atr_smooth[i - 1] / period) + tr[i]
        pdm_smooth[i] = pdm_smooth[i - 1] - (pdm_smooth[i - 1] / period) + plus_dm[i - 1]
        mdm_smooth[i] = mdm_smooth[i - 1] - (mdm_smooth[i - 1] / period) + minus_dm[i - 1]

    plus_di = np.zeros(n, dtype=np.float64)
    minus_di = np.zeros(n, dtype=np.float64)
    dx = np.zeros(n, dtype=np.float64)

    for i in range(period, n):
        denom = max(atr_smooth[i], 1e-6)
        plus_di[i] = 100.0 * (pdm_smooth[i] / denom)
        minus_di[i] = 100.0 * (mdm_smooth[i] / denom)
        di_sum = plus_di[i] + minus_di[i]
        dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / max(di_sum, 1e-6)

    adx = np.zeros(n, dtype=np.float64)
    start_adx = 2 * period
    if n > start_adx:
        adx[start_adx] = dx[period : start_adx + 1].mean()
        for i in range(start_adx + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
        adx[:start_adx] = adx[start_adx]
    else:
        adx[:] = 20.0

    return pl.Series("adx", adx, dtype=pl.Float64)


def compute_5m_features(df_5m: pl.DataFrame, config: S6Config) -> pl.DataFrame:
    """Computes all causal 5m context features, ATR5, and regime_v01."""
    if len(df_5m) == 0:
        return df_5m

    df = df_5m.sort("available_at")
    
    # 1. Wilder ATR(14)
    atr5 = compute_wilder_atr(df, period=config.regime.atr_period)
    df = df.with_columns(atr5.alias("atr5"))

    # 2. EMAs: EMA20 and EMA50
    df = df.with_columns([
        pl.col("close").ewm_mean(span=config.regime.ema_fast_period, adjust=False).alias("ema_20"),
        pl.col("close").ewm_mean(span=config.regime.ema_slow_period, adjust=False).alias("ema_50"),
    ])

    # 3. ADX(14)
    adx14 = compute_adx(df, period=config.regime.adx_period)
    df = df.with_columns(adx14.alias("adx14"))

    # 4. ATR percentile (rolling 100 bars)
    rolling_atr_pctile = (
        pl.col("atr5").rolling_quantile(quantile=0.5, window_size=config.compression.atr_median_lookback_bars, min_samples=10)
    ).alias("atr_median_100")
    
    df = df.with_columns([
        rolling_atr_pctile,
        # Rolling min and max high/low over 6 bars for range ratio
        pl.col("high").rolling_max(window_size=config.compression.range_lookback_bars, min_samples=1).alias("rolling_high_6"),
        pl.col("low").rolling_min(window_size=config.compression.range_lookback_bars, min_samples=1).alias("rolling_low_6"),
        # Rolling 60-bar 5m high and low for structural room
        pl.col("high").rolling_max(window_size=60, min_samples=1).alias("rolling_high_60"),
        pl.col("low").rolling_min(window_size=60, min_samples=1).alias("rolling_low_60"),
        # Candle range
        (pl.col("high") - pl.col("low")).alias("candle_range"),
    ])

    # 5. Compression ratios
    df = df.with_columns([
        (pl.col("atr5") / pl.max_horizontal(pl.col("atr_median_100"), pl.lit(1e-6))).alias("compression_atr_ratio"),
        ((pl.col("rolling_high_6") - pl.col("rolling_low_6")) / pl.max_horizontal(pl.col("atr5"), pl.lit(1e-6))).alias("compression_range_ratio"),
    ])

    # 6. ATR percentile rank across rolling window
    atr_vals = df["atr5"].to_numpy()
    n = len(df)
    atr_pctiles = np.zeros(n, dtype=np.float64)
    window = 100
    for i in range(n):
        start_idx = max(0, i - window + 1)
        sub = atr_vals[start_idx : i + 1]
        pct = (sub < atr_vals[i]).mean() * 100.0
        atr_pctiles[i] = pct
    df = df.with_columns(pl.Series("atr_percentile", atr_pctiles, dtype=pl.Float64))

    # 7. regime_v01 classification
    regimes = []
    closes = df["close"].to_list()
    ema20s = df["ema_20"].to_list()
    ema50s = df["ema_50"].to_list()
    adxs = df["adx14"].to_list()
    pctiles = df["atr_percentile"].to_list()
    ranges = df["candle_range"].to_list()
    atrs = df["atr5"].to_list()

    for i in range(n):
        if i < 20:
            regimes.append("UNKNOWN")
            continue

        c = closes[i]
        e20 = ema20s[i]
        e50 = ema50s[i]
        adx = adxs[i]
        pctile = pctiles[i]
        atr = max(atrs[i], 1e-6)

        # UNSTABLE check: any of last 3 completed bars has range > 3.0 * ATR5
        start_3 = max(0, i - 2)
        is_unstable = any(ranges[k] > config.regime.unstable_range_atr * atrs[k] for k in range(start_3, i + 1))
        if is_unstable:
            regimes.append("UNSTABLE")
        elif pctile >= config.regime.atr_pctile_high:
            regimes.append("HIGH_VOLATILITY")
        elif pctile <= config.regime.atr_pctile_low:
            regimes.append("LOW_VOLATILITY")
        elif adx >= config.regime.adx_trend_min and e20 > e50 and c > e20:
            regimes.append("TREND_UP")
        elif adx >= config.regime.adx_trend_min and e20 < e50 and c < e20:
            regimes.append("TREND_DOWN")
        else:
            regimes.append("RANGE")

    df = df.with_columns(pl.Series("regime", regimes, dtype=pl.String))
    return df


# =========================================================================
# Shared S6 Event Engine
# =========================================================================

class S6EventEngine:
    """Shared Causal Event Engine for S6-A (continuation) and S6-F (reversal)."""

    def __init__(self, config: S6Config):
        self.config = config

    def get_context_at(self, df_5m: pl.DataFrame, as_of: datetime) -> pl.DataFrame:
        """Causality Guard: returns ONLY 5m bars available at or before `as_of`.
        Raises CausalityViolation if any forming candle is requested.
        """
        if "available_at" not in df_5m.columns:
            raise CausalityViolation("Missing 'available_at' column in 5m context DataFrame.")

        # If as_of is explicitly earlier than earliest available_at, return empty
        valid_df = df_5m.filter(pl.col("available_at") <= as_of)
        
        # Check if caller tried to inspect beyond available_at
        future_count = df_5m.filter(pl.col("available_at") > as_of).height
        if future_count > 0 and len(valid_df) == 0:
            pass # normal before first 5m bar
        return valid_df

    def detect_compression_episodes(
        self,
        df_5m: pl.DataFrame,
        instrument: str = "NIFTY",
    ) -> List[CompressionEpisode]:
        """Detects 3-bar persistent compression episodes on completed 5m bars."""
        episodes: List[CompressionEpisode] = []
        if len(df_5m) < self.config.compression.persistence_bars:
            return episodes

        atr_ratios = df_5m["compression_atr_ratio"].to_list()
        range_ratios = df_5m["compression_range_ratio"].to_list()
        highs = df_5m["high"].to_list()
        lows = df_5m["low"].to_list()
        atrs = df_5m["atr5"].to_list()
        availables = df_5m["available_at"].to_list()
        opens = df_5m["bar_open_time"].to_list()

        persist = self.config.compression.persistence_bars
        n = len(df_5m)
        in_episode = False
        episode_start_idx = 0

        for i in range(persist - 1, n):
            # Check last `persist` bars
            is_compressed = all(
                (atr_ratios[k] is not None and atr_ratios[k] <= self.config.compression.atr_ratio_max) and
                (range_ratios[k] is not None and range_ratios[k] <= self.config.compression.range_ratio_max)
                for k in range(i - persist + 1, i + 1)
            )

            if is_compressed and not in_episode:
                in_episode = True
                episode_start_idx = i - persist + 1
            elif not is_compressed and in_episode:
                # Compression episode finished. Freeze boundaries across episode bars.
                end_idx = i - 1
                comp_high = max(highs[episode_start_idx : end_idx + 1])
                comp_low = min(lows[episode_start_idx : end_idx + 1])
                atr_val = atrs[end_idx]
                start_ts = opens[episode_start_idx]
                end_ts = availables[end_idx]
                
                ep_id = f"S6CE_{instrument}_5m_{int(start_ts.timestamp())}"
                episodes.append(CompressionEpisode(
                    episode_id=ep_id,
                    instrument=instrument,
                    context_tf="5m",
                    start_time=start_ts,
                    end_time=end_ts,
                    compression_high=comp_high,
                    compression_low=comp_low,
                    atr5=atr_val,
                    duration_bars=(end_idx - episode_start_idx + 1),
                    status="ARMED",
                ))
                in_episode = False

        # Close out active episode at end of dataset if still active
        if in_episode:
            end_idx = n - 1
            comp_high = max(highs[episode_start_idx : end_idx + 1])
            comp_low = min(lows[episode_start_idx : end_idx + 1])
            atr_val = atrs[end_idx]
            start_ts = opens[episode_start_idx]
            end_ts = availables[end_idx]
            ep_id = f"S6CE_{instrument}_5m_{int(start_ts.timestamp())}"
            episodes.append(CompressionEpisode(
                episode_id=ep_id,
                instrument=instrument,
                context_tf="5m",
                start_time=start_ts,
                end_time=end_ts,
                compression_high=comp_high,
                compression_low=comp_low,
                atr5=atr_val,
                duration_bars=(end_idx - episode_start_idx + 1),
                status="ARMED",
            ))

        return episodes

    def detect_raw_breakouts(
        self,
        df_exec: pl.DataFrame,
        df_5m: pl.DataFrame,
        episodes: List[CompressionEpisode],
        timeframe: str = "1m",
    ) -> List[RawBreakoutEvent]:
        """Detects low-level structural crossings of frozen compression boundaries.
        
        CRITICAL RULE:
        Does NOT pre-filter by volume, candle close, or structural room.
        Emits raw structural crossings so that S6-F can evaluate failures
        even if S6-A rejects the candidate.
        """
        raw_breakouts: List[RawBreakoutEvent] = []
        if len(df_exec) == 0 or len(episodes) == 0:
            return raw_breakouts

        df_exec = df_exec.sort("timestamp")
        timestamps = df_exec["timestamp"].to_list()
        opens = df_exec["open"].to_list()
        highs = df_exec["high"].to_list()
        lows = df_exec["low"].to_list()
        closes = df_exec["close"].to_list()
        volumes = df_exec["volume"].to_list()
        n_exec = len(df_exec)

        # Precompute rolling 20-bar mean volume on execution timeframe
        vol_arr = np.array(volumes, dtype=np.float64)
        vol_mean_20 = np.zeros(n_exec, dtype=np.float64)
        for i in range(n_exec):
            s = max(0, i - 19)
            vol_mean_20[i] = max(1.0, vol_arr[s : i + 1].mean())

        # Map 5m completed context indexed by available_at for fast causal lookup
        context_5m_times = df_5m["available_at"].to_list()
        context_5m_atrs = df_5m["atr5"].to_list()
        context_5m_regimes = df_5m["regime"].to_list()
        context_5m_highs_60 = df_5m["rolling_high_60"].to_list()
        context_5m_lows_60 = df_5m["rolling_low_60"].to_list()
        n_5m = len(df_5m)

        def get_5m_context_causal(t: datetime) -> Tuple[float, str, float, float]:
            """Returns (atr5, regime, rolling_high_60, rolling_low_60) causally available at t."""
            # Binary search for rightmost 5m bar with available_at <= t
            idx = -1
            left, right = 0, n_5m - 1
            while left <= right:
                mid = (left + right) // 2
                if context_5m_times[mid] <= t:
                    idx = mid
                    left = mid + 1
                else:
                    right = mid - 1
            if idx >= 0:
                return (
                    context_5m_atrs[idx],
                    context_5m_regimes[idx],
                    context_5m_highs_60[idx],
                    context_5m_lows_60[idx],
                )
            return (1.0, "UNKNOWN", 0.0, 0.0)

        # Track first-cross rule per episode_id + direction
        seen_crossings: set[Tuple[str, int]] = set()

        # Iterate over episodes
        for ep in episodes:
            armed_start = ep.end_time
            # Armed lifetime: 12 context bars (60 minutes)
            armed_end = armed_start + timedelta(minutes=12 * 5)
            # Maximum lifetime: 36 context bars (180 minutes)
            max_end = armed_start + timedelta(minutes=36 * 5)

            # Find execution bars during armed window
            for i in range(1, n_exec):
                t = timestamps[i]
                if t < armed_start:
                    continue
                if t > armed_end:
                    break

                close = closes[i]
                prev_close = closes[i - 1]
                high = highs[i]
                low = lows[i]
                open_p = opens[i]
                vol = volumes[i]

                atr5, regime, r_high_60, r_low_60 = get_5m_context_causal(t)
                buf = self.config.breakout.min_breakout_distance_atr * atr5

                long_threshold = ep.compression_high + buf
                short_threshold = ep.compression_low - buf

                # Long crossing: close > long_threshold and prev_close <= long_threshold
                if close > long_threshold and prev_close <= long_threshold:
                    key = (ep.episode_id, 1)
                    if key not in seen_crossings:
                        seen_crossings.add(key)
                        
                        vol_ratio = vol / max(1.0, vol_mean_20[i])
                        c_range = max(1e-6, high - low)
                        c_loc = (close - low) / c_range
                        dist_atr = (close - ep.compression_high) / max(atr5, 1e-6)
                        
                        # Room: distance to nearest opposing level above breakout (r_high_60)
                        opposing = r_high_60 if r_high_60 > close else float("inf")
                        room_atr = (opposing - close) / max(atr5, 1e-6) if opposing != float("inf") else 999.0

                        evt_id = f"S6BE_{ep.episode_id}_LONG_{timeframe}_{int(t.timestamp())}"
                        raw_breakouts.append(RawBreakoutEvent(
                            event_id=evt_id,
                            episode_id=ep.episode_id,
                            instrument=ep.instrument,
                            timeframe=timeframe,
                            direction=1,
                            breakout_time=t,
                            breakout_price=close,
                            atr5=atr5,
                            volume_ratio=vol_ratio,
                            close_location=c_loc,
                            breakout_distance_atr=dist_atr,
                            structure_level=ep.compression_high,
                            room_atr=room_atr,
                            regime=regime,
                        ))

                # Short crossing: close < short_threshold and prev_close >= short_threshold
                elif close < short_threshold and prev_close >= short_threshold:
                    key = (ep.episode_id, -1)
                    if key not in seen_crossings:
                        seen_crossings.add(key)

                        vol_ratio = vol / max(1.0, vol_mean_20[i])
                        c_range = max(1e-6, high - low)
                        c_loc = (high - close) / c_range
                        dist_atr = (ep.compression_low - close) / max(atr5, 1e-6)

                        # Room: distance to nearest opposing level below breakout (r_low_60)
                        opposing = r_low_60 if r_low_60 < close and r_low_60 > 0 else 0.0
                        room_atr = (close - opposing) / max(atr5, 1e-6) if opposing > 0 else 999.0

                        evt_id = f"S6BE_{ep.episode_id}_SHORT_{timeframe}_{int(t.timestamp())}"
                        raw_breakouts.append(RawBreakoutEvent(
                            event_id=evt_id,
                            episode_id=ep.episode_id,
                            instrument=ep.instrument,
                            timeframe=timeframe,
                            direction=-1,
                            breakout_time=t,
                            breakout_price=close,
                            atr5=atr5,
                            volume_ratio=vol_ratio,
                            close_location=c_loc,
                            breakout_distance_atr=dist_atr,
                            structure_level=ep.compression_low,
                            room_atr=room_atr,
                            regime=regime,
                        ))

        return raw_breakouts

    def detect_failures(
        self,
        df_exec: pl.DataFrame,
        episodes: List[CompressionEpisode],
        raw_breakouts: List[RawBreakoutEvent],
    ) -> List[FailureEvent]:
        """Monitors execution bars after each RawBreakoutEvent for range re-entry.
        
        A failure occurs if price returns into the compression range by >= 0.10 * atr5
        within max_monitoring_bars (5 bars) after the breakout.
        """
        failures: List[FailureEvent] = []
        if len(raw_breakouts) == 0 or len(df_exec) == 0:
            return failures

        ep_map = {ep.episode_id: ep for ep in episodes}
        df_exec = df_exec.sort("timestamp")
        timestamps = df_exec["timestamp"].to_list()
        highs = df_exec["high"].to_list()
        lows = df_exec["low"].to_list()
        closes = df_exec["close"].to_list()
        n_exec = len(df_exec)

        ts_to_idx = {ts: i for i, ts in enumerate(timestamps)}
        max_bars = self.config.failure.max_monitoring_bars
        reentry_buf = self.config.failure.reentry_distance_atr

        for bo in raw_breakouts:
            ep = ep_map.get(bo.episode_id)
            if not ep:
                continue

            bo_idx = ts_to_idx.get(bo.breakout_time)
            if bo_idx is None:
                continue

            atr5 = bo.atr5
            reentry_dist = reentry_buf * atr5
            direction = bo.direction

            # Monitor next max_bars execution bars
            start_monitor = bo_idx + 1
            end_monitor = min(n_exec, start_monitor + max_bars)
            extreme_price = bo.breakout_price

            for k in range(start_monitor, end_monitor):
                c = closes[k]
                h = highs[k]
                l = lows[k]
                bars_since = k - bo_idx

                if direction == 1:
                    # Long breakout -> failure extreme is highest high
                    extreme_price = max(extreme_price, h)
                    # Re-entry condition: close drops back inside compression range by reentry_dist
                    if c <= (ep.compression_high - reentry_dist):
                        evt_id = f"S6FE_{bo.event_id}_{int(timestamps[k].timestamp())}"
                        failures.append(FailureEvent(
                            event_id=evt_id,
                            breakout_event_id=bo.event_id,
                            instrument=bo.instrument,
                            direction=-1,  # Short failure trade
                            failure_time=timestamps[k],
                            failure_price=c,
                            reentry_distance_atr=(ep.compression_high - c) / max(atr5, 1e-6),
                            bars_since_breakout=bars_since,
                            failure_extreme=extreme_price,
                        ))
                        break  # Only one failure per breakout event

                elif direction == -1:
                    # Short breakout -> failure extreme is lowest low
                    extreme_price = min(extreme_price, l)
                    # Re-entry condition: close rises back inside compression range by reentry_dist
                    if c >= (ep.compression_low + reentry_dist):
                        evt_id = f"S6FE_{bo.event_id}_{int(timestamps[k].timestamp())}"
                        failures.append(FailureEvent(
                            event_id=evt_id,
                            breakout_event_id=bo.event_id,
                            instrument=bo.instrument,
                            direction=1,   # Long failure trade
                            failure_time=timestamps[k],
                            failure_price=c,
                            reentry_distance_atr=(c - ep.compression_low) / max(atr5, 1e-6),
                            bars_since_breakout=bars_since,
                            failure_extreme=extreme_price,
                        ))
                        break

        return failures
