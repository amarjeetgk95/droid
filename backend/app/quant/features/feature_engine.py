"""Causal Feature Engine with Point-in-Time Availability Tracking (Tier 0).

Calculates vectorized market features in Polars with zero future lookahead.
Features:
- Multi-horizon returns (1m, 3m, 5m, 15m)
- Intraday VWAP & VWAP distance (resets daily at 09:15 IST)
- Moving averages: EMA fast (9), EMA slow (21)
- Momentum & Volatility: RSI (14), ATR (14), ADX (14), Realized Vol (20)
- Volume ratio vs rolling 20-bar baseline
- Candle anatomy: body ratio, upper wick ratio, lower wick ratio
- Opening range (09:15-09:30) high/low tracking
- Explicit Feature Availability States (CURRENT, HISTORICAL, PARTIAL, UNAVAILABLE)
- Feature Set SHA-256 Version Hash
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple
import polars as pl
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

FEATURE_ENGINE_VERSION = "features_v01"


class CausalFeatureEngine:
    """Vectorized causal feature calculator built on Polars."""

    def __init__(
        self,
        ema_fast: int = 9,
        ema_slow: int = 21,
        rsi_period: int = 14,
        atr_period: int = 14,
        adx_period: int = 14,
        vol_lookback: int = 20,
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.vol_lookback = vol_lookback
        self.feature_hash = self._compute_feature_hash()

    def _compute_feature_hash(self) -> str:
        params = {
            "version": FEATURE_ENGINE_VERSION,
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
            "rsi_period": self.rsi_period,
            "atr_period": self.atr_period,
            "adx_period": self.adx_period,
            "vol_lookback": self.vol_lookback,
        }
        encoded = json.dumps(params, sort_keys=True).encode("utf-8")
        return f"{FEATURE_ENGINE_VERSION}_sha_{hashlib.sha256(encoded).hexdigest()[:12]}"

    def compute_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """Computes all causal features on an OHLCV Polars DataFrame.
        
        Requires: timestamp, open, high, low, close, volume.
        Guarantees that row t only depends on row <= t.
        """
        if len(df) == 0:
            return df

        # Ensure strict sort by timestamp
        df = df.sort("timestamp")

        # 1. Trading Day identifier (grouping for daily VWAP and Opening Range)
        # Using timestamp + 5:30 for IST date boundary
        df = df.with_columns([
            (pl.col("timestamp") + pl.duration(hours=5, minutes=30)).dt.date().alias("trade_date"),
            ((pl.col("timestamp") + pl.duration(hours=5, minutes=30)).dt.hour().cast(pl.Int32) * 60 + 
             (pl.col("timestamp") + pl.duration(hours=5, minutes=30)).dt.minute().cast(pl.Int32)).alias("minute_of_day"),
        ])

        # 2. Multi-horizon returns (causal lookback)
        df = df.with_columns([
            ((pl.col("close") - pl.col("close").shift(1)) / pl.col("close").shift(1)).alias("return_1m"),
            ((pl.col("close") - pl.col("close").shift(3)) / pl.col("close").shift(3)).alias("return_3m"),
            ((pl.col("close") - pl.col("close").shift(5)) / pl.col("close").shift(5)).alias("return_5m"),
            ((pl.col("close") - pl.col("close").shift(15)) / pl.col("close").shift(15)).alias("return_15m"),
        ])

        # 3. Candle anatomy & Multi-bar absorption wick ratio
        range_expr = pl.max_horizontal(pl.col("high") - pl.col("low"), pl.lit(1e-6))
        lower_wick = pl.min_horizontal(pl.col("open"), pl.col("close")) - pl.col("low")
        upper_wick = pl.col("high") - pl.max_horizontal(pl.col("open"), pl.col("close"))
        
        sum_lower_5 = lower_wick.rolling_sum(window_size=5, min_samples=1)
        sum_upper_5 = upper_wick.rolling_sum(window_size=5, min_samples=1)
        sum_range_5 = range_expr.rolling_sum(window_size=5, min_samples=1)
        
        buy_absorption_5 = sum_lower_5 / sum_range_5
        sell_absorption_5 = sum_upper_5 / sum_range_5
        absorption_ratio_5 = pl.when(sum_lower_5 >= sum_upper_5).then(buy_absorption_5).otherwise(-sell_absorption_5)

        df = df.with_columns([
            ((pl.col("close") - pl.col("open")).abs() / range_expr).alias("candle_body_ratio"),
            (upper_wick / range_expr).alias("upper_wick_ratio"),
            (lower_wick / range_expr).alias("lower_wick_ratio"),
            absorption_ratio_5.alias("absorption_ratio_5"),
        ])

        # 4. Intraday VWAP & VWAP Standard Deviation Bands (Reset at 09:15 each trade_date)
        typical_price = (pl.col("high") + pl.col("low") + pl.col("close")) / 3.0
        day_open = pl.col("open").first().over("trade_date")
        tp_diff = typical_price - day_open
        
        cum_vol = pl.col("volume").cum_sum().over("trade_date")
        cum_tp_diff_vol = (tp_diff * pl.col("volume")).cum_sum().over("trade_date")
        cum_tp_diff2_vol = ((tp_diff ** 2) * pl.col("volume")).cum_sum().over("trade_date")

        vwap_expr = pl.when(cum_vol > 0).then(day_open + (cum_tp_diff_vol / cum_vol)).otherwise(pl.col("close"))
        mean_d = pl.when(cum_vol > 0).then(cum_tp_diff_vol / cum_vol).otherwise(0.0)
        mean_d2 = pl.when(cum_vol > 0).then(cum_tp_diff2_vol / cum_vol).otherwise(0.0)
        var_vwap = pl.max_horizontal(mean_d2 - (mean_d ** 2), pl.lit(0.0))
        std_dev_vwap = var_vwap.sqrt()

        df = df.with_columns([
            vwap_expr.alias("vwap"),
            std_dev_vwap.alias("std_dev_vwap"),
            (vwap_expr + 2.0 * std_dev_vwap).alias("vwap_upper_2std"),
            (vwap_expr - 2.0 * std_dev_vwap).alias("vwap_lower_2std"),
        ])
        df = df.with_columns([
            ((pl.col("close") - pl.col("vwap")) / pl.col("vwap")).alias("vwap_distance")
        ])

        # 5. Moving Averages (EMA fast & slow, EMA 20, EMA 50, EMA 50 slope)
        ema_20 = pl.col("close").ewm_mean(span=20, adjust=False)
        ema_50 = pl.col("close").ewm_mean(span=50, adjust=False)
        ema_slope_50 = (ema_50 - ema_50.shift(3)) / 3.0

        df = df.with_columns([
            pl.col("close").ewm_mean(span=self.ema_fast, adjust=False).alias("ema_fast"),
            pl.col("close").ewm_mean(span=self.ema_slow, adjust=False).alias("ema_slow"),
            ema_20.alias("ema_20"),
            ema_50.alias("ema_50"),
            ema_slope_50.alias("ema_slope_50"),
        ])
        df = df.with_columns([
            ((pl.col("ema_fast") - pl.col("ema_slow")) / pl.col("close")).alias("ema_cross_spread")
        ])

        # 6. Volume Ratio vs Rolling 20-bar baseline
        vol_baseline = pl.col("volume").rolling_mean(window_size=self.vol_lookback, min_samples=1)
        df = df.with_columns([
            (pl.col("volume") / pl.max_horizontal(vol_baseline, pl.lit(1.0))).alias("volume_ratio")
        ])

        # 7. True Range & ATR (Average True Range)
        prev_close = pl.col("close").shift(1)
        tr1 = pl.col("high") - pl.col("low")
        tr2 = (pl.col("high") - prev_close).abs()
        tr3 = (pl.col("low") - prev_close).abs()
        tr = pl.max_horizontal(tr1, tr2, tr3)
        
        df = df.with_columns(tr.alias("true_range"))
        df = df.with_columns([
            pl.col("true_range").ewm_mean(span=self.atr_period, adjust=False).alias("atr")
        ])
        df = df.with_columns([
            (pl.col("atr") / pl.col("close")).alias("atr_pct")
        ])

        # 8. RSI (Relative Strength Index - 14)
        delta = pl.col("close") - pl.col("close").shift(1)
        gain = pl.when(delta > 0).then(delta).otherwise(0.0)
        loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
        
        avg_gain = gain.ewm_mean(span=self.rsi_period, adjust=False)
        avg_loss = loss.ewm_mean(span=self.rsi_period, adjust=False)
        rs = avg_gain / pl.max_horizontal(avg_loss, pl.lit(1e-9))
        rsi = 100.0 - (100.0 / (1.0 + rs))
        df = df.with_columns(rsi.alias("rsi"))

        # 9. Realized Volatility (Rolling 20-bar standard deviation of 1m returns annualized)
        min_samp = min(5, self.vol_lookback)
        df = df.with_columns([
            (pl.col("return_1m").rolling_std(window_size=self.vol_lookback, min_samples=min_samp) * np.sqrt(375.0 * 252.0)).alias("realized_vol_20")
        ])

        # 10. Opening Range (09:15 to 09:30 IST, i.e. minute_of_day between 555 and 570)
        # Strictly causal: during OR (<=570), expanding max/min; after 570, frozen at OR end
        is_or = pl.col("minute_of_day") <= 570
        or_cand_h = pl.when(is_or).then(pl.col("high")).otherwise(None)
        or_cand_l = pl.when(is_or).then(pl.col("low")).otherwise(None)
        
        or_high = or_cand_h.cum_max().over("trade_date").forward_fill().over("trade_date")
        or_low = or_cand_l.cum_min().over("trade_date").forward_fill().over("trade_date")
        
        df = df.with_columns([
            or_high.alias("or_high"),
            or_low.alias("or_low"),
        ])
        df = df.with_columns([
            ((pl.col("close") - pl.col("or_high")) / pl.col("close")).alias("or_high_distance"),
            ((pl.col("close") - pl.col("or_low")) / pl.col("close")).alias("or_low_distance"),
        ])

        # 11. Structural Level & Absorption Features
        # Previous Day High & Low (strictly previous completed trading day)
        day_summary = (
            df.group_by("trade_date")
            .agg([
                pl.col("high").max().alias("day_high"),
                pl.col("low").min().alias("day_low"),
            ])
            .sort("trade_date")
        )
        day_summary = day_summary.with_columns([
            pl.col("day_high").shift(1).alias("prev_day_high"),
            pl.col("day_low").shift(1).alias("prev_day_low"),
        ])
        df = df.join(
            day_summary.select(["trade_date", "prev_day_high", "prev_day_low"]),
            on="trade_date",
            how="left",
        ).sort("timestamp")

        safe_atr = pl.max_horizontal(pl.col("atr"), pl.lit(1e-6))
        price_disp = (pl.col("close") - pl.col("open")).abs() / safe_atr
        dist_prev_high = pl.when(pl.col("prev_day_high").is_not_null()).then(
            (pl.col("close") - pl.col("prev_day_high")) / safe_atr
        ).otherwise(None)
        dist_prev_low = pl.when(pl.col("prev_day_low").is_not_null()).then(
            (pl.col("close") - pl.col("prev_day_low")) / safe_atr
        ).otherwise(None)
        wick_rejection = pl.max_horizontal(pl.col("upper_wick_ratio"), pl.col("lower_wick_ratio"))
        vwap_touch = pl.when(
            (pl.col("high") >= pl.col("vwap_upper_2std")) | (pl.col("low") <= pl.col("vwap_lower_2std"))
        ).then(pl.lit(1, dtype=pl.Int8)).otherwise(pl.lit(0, dtype=pl.Int8))

        # Directional streak (+/- consecutive closes in same direction)
        closes = df["close"].to_list()
        n = len(closes)
        streaks = [0] * n
        curr = 0
        for i in range(1, n):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                curr = (curr + 1) if curr > 0 else 1
            elif diff < 0:
                curr = (curr - 1) if curr < 0 else -1
            else:
                curr = 0
            streaks[i] = curr

        df = df.with_columns([
            price_disp.alias("price_displacement"),
            dist_prev_high.alias("distance_to_prev_high"),
            dist_prev_low.alias("distance_to_prev_low"),
            wick_rejection.alias("wick_rejection_ratio"),
            vwap_touch.alias("vwap_band_touch"),
            pl.Series("directional_streak", streaks, dtype=pl.Int32),
        ])

        # 12. Feature Availability State
        # Warmup period needed for features: max(vol_lookback, ema_slow, rsi_period) = 21 bars
        # For opening range: available only after 09:30 IST (minute_of_day >= 570)
        bar_idx_over_day = pl.int_range(0, pl.len()).over("trade_date")
        
        availability_expr = (
            pl.when(bar_idx_over_day < self.vol_lookback)
            .then(pl.lit("PARTIAL"))
            .when(pl.col("return_15m").is_null() | pl.col("rsi").is_null())
            .then(pl.lit("UNAVAILABLE"))
            .otherwise(pl.lit("CURRENT"))
        )
        
        df = df.with_columns([
            availability_expr.alias("feature_availability"),
            pl.lit(self.feature_hash).alias("feature_version"),
        ])

        # Clean up intermediate columns
        df = df.drop(["trade_date", "minute_of_day", "true_range"])

        return df

    def compute_all_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """Computes all causal features on an OHLCV Polars DataFrame."""
        return self.compute_features(df)

