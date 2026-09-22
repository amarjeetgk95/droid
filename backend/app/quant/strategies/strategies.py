"""Baseline Trading Strategies for Falsification Testing (Tier 0).

Implements the three pre-registered baseline hypotheses:
S1: Opening Range Breakout (ORB) (09:15 - 09:30 IST)
S2: 20-Bar Momentum Breakout (Volume ratio >= 1.2, upper 30% candle close)
S3: VWAP Reclaim / Reject with ADX trend filter
+
Random-Filter Baseline (R) matched for identical trade count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional, List, Any
import polars as pl
import numpy as np

CandidateDirection = Literal[1, -1]  # +1 = LONG, -1 = SHORT

DEFAULT_SESSION_WINDOWS: list[tuple[str, str]] = [("09:20", "10:30"), ("14:15", "15:15")]


def parse_time_to_minute(time_str: str) -> int:
    """Parses 'HH:MM' string into minute-of-day (0 to 1439)."""
    parts = time_str.strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def get_ist_minute(t: Any) -> int:
    """Extracts minute of day in Indian Standard Time (UTC+05:30)."""
    if isinstance(t, str):
        try:
            t = datetime.fromisoformat(t)
        except Exception:
            return 0
    if hasattr(t, "tzinfo") and t.tzinfo is not None:
        ist_dt = t.astimezone(timezone(timedelta(hours=5, minutes=30)))
        return ist_dt.hour * 60 + ist_dt.minute
    if hasattr(t, "hour") and hasattr(t, "minute"):
        return (t.hour * 60 + t.minute + 330) % 1440
    return 0


@dataclass
class StrategyCandidate:
    bar_index: int
    direction: CandidateDirection
    strategy_id: str
    entry_ref_price: float
    trigger_reason: str
    gate_margins: dict[str, float] = field(default_factory=dict)


class BaselineStrategyEngine:
    """Evaluates causal features to emit candidate signals."""

    def __init__(
        self,
        orb_buffer_atr: float = 0.1,
        momentum_vol_ratio: float = 1.2,
        momentum_lookback: int = 20,
        momentum_cooldown: int = 10,
        vwap_min_adx: float = 20.0,
        squeeze_lookback: int = 12,
        squeeze_compression_ratio: float = 0.90,
        squeeze_cooldown: int = 8,
        trend_aligned: bool = False,
        session_filter: bool = False,
        allowed_windows: list[tuple[str, str]] | None = None,
        s5_absorption_threshold: float = 0.40,
        s5_cooldown: int = 5,
        s5_k_sl: float = 1.5,
        s5_k_tp: float = 2.5,
        s7_config: Any | None = None,
    ):
        self.orb_buffer_atr = orb_buffer_atr
        self.momentum_vol_ratio = momentum_vol_ratio
        self.momentum_lookback = momentum_lookback
        self.momentum_cooldown = momentum_cooldown
        self.vwap_min_adx = vwap_min_adx
        self.squeeze_lookback = squeeze_lookback
        self.squeeze_compression_ratio = squeeze_compression_ratio
        self.squeeze_cooldown = squeeze_cooldown
        self.trend_aligned = trend_aligned
        self.s5_absorption_threshold = s5_absorption_threshold
        self.s5_cooldown = s5_cooldown
        self.s5_k_sl = s5_k_sl
        self.s5_k_tp = s5_k_tp
        self.s7_config = s7_config
        self.session_filter = session_filter or (allowed_windows is not None)
        self.allowed_windows = allowed_windows or (list(DEFAULT_SESSION_WINDOWS) if self.session_filter else None)
        self._parsed_windows = self._parse_windows(self.allowed_windows) if self.session_filter else []

    @staticmethod
    def _parse_windows(windows: list[tuple[str, str]] | None) -> list[tuple[int, int]]:
        if not windows:
            return []
        parsed = []
        for start_s, end_s in windows:
            parsed.append((parse_time_to_minute(start_s), parse_time_to_minute(end_s)))
        return parsed

    def set_session_filter(
        self,
        enabled: bool = True,
        allowed_windows: list[tuple[str, str]] | None = None,
    ) -> None:
        self.session_filter = enabled
        if allowed_windows is not None:
            self.allowed_windows = allowed_windows
        elif self.session_filter and (not hasattr(self, "allowed_windows") or self.allowed_windows is None):
            self.allowed_windows = list(DEFAULT_SESSION_WINDOWS)
        elif not self.session_filter:
            self.allowed_windows = None
        self._parsed_windows = self._parse_windows(self.allowed_windows) if self.session_filter else []

    def is_session_allowed(self, minute_of_day: int) -> bool:
        """Returns True if minute_of_day (IST) falls within any configured session liquidity window."""
        if not self.session_filter or not self._parsed_windows:
            return True
        for start_m, end_m in self._parsed_windows:
            if start_m <= minute_of_day <= end_m:
                return True
        return False

    def _get_ist_minutes(self, df: pl.DataFrame) -> list[int]:
        if "minute_of_day" in df.columns:
            return df["minute_of_day"].to_list()
        if "timestamp" in df.columns:
            timestamps = df["timestamp"].to_list()
            return [get_ist_minute(t) for t in timestamps]
        return [0] * len(df)

    def scan_s1_orb(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        """S1: Opening Range Breakout (after 09:30 IST).
        One candidate per direction per trade day.
        """
        candidates: list[StrategyCandidate] = []
        if len(df) == 0:
            return candidates

        # Must have computed or_high, or_low, atr, minute_of_day
        timestamps = df["timestamp"].to_list()
        closes = df["close"].to_list()
        or_highs = df["or_high"].to_list()
        or_lows = df["or_low"].to_list()
        atrs = df["atr"].to_list() if "atr" in df.columns else [c * 0.003 for c in closes]
        ema_fasts = df["ema_fast"].to_list() if "ema_fast" in df.columns else closes
        ema_slows = df["ema_slow"].to_list() if "ema_slow" in df.columns else closes
        rsis = df["rsi"].to_list() if "rsi" in df.columns else [50.0] * len(df)

        # Calculate minute_of_day from timestamp (IST)
        ist_minutes = self._get_ist_minutes(df)

        current_day = None
        traded_long_today = False
        traded_short_today = False

        for i in range(len(df)):
            t = timestamps[i]
            day_key = t.date() if hasattr(t, "date") else str(t)[:10]
            if day_key != current_day:
                current_day = day_key
                traded_long_today = False
                traded_short_today = False

            m_of_day = ist_minutes[i]
            # Only trade after Opening Range window closes (09:30 IST = 570 minutes)
            if m_of_day <= 570:
                continue
            if self.session_filter:
                if not self.is_session_allowed(m_of_day):
                    continue
            elif m_of_day >= 900:
                continue

            close = closes[i]
            or_h = or_highs[i]
            or_l = or_lows[i]
            atr = atrs[i] or (close * 0.003)
            efast = ema_fasts[i]
            eslow = ema_slows[i]

            if or_h is None or or_l is None:
                continue

            # Long breakout
            if not traded_long_today and close > (or_h + self.orb_buffer_atr * atr):
                if self.trend_aligned and efast is not None and eslow is not None and efast < eslow:
                    continue
                margin = (close - or_h) / atr
                candidates.append(StrategyCandidate(
                    bar_index=i,
                    direction=1,
                    strategy_id="S1_ORB_LONG",
                    entry_ref_price=close,
                    trigger_reason=f"Close {close:.1f} broke OR High {or_h:.1f} with margin {margin:.2f} ATR",
                    gate_margins={"or_margin_atr": margin, "atr": atr},
                ))
                traded_long_today = True

            # Short breakout
            elif not traded_short_today and close < (or_l - self.orb_buffer_atr * atr):
                if self.trend_aligned and efast is not None and eslow is not None and efast > eslow:
                    continue
                margin = (or_l - close) / atr
                candidates.append(StrategyCandidate(
                    bar_index=i,
                    direction=-1,
                    strategy_id="S1_ORB_SHORT",
                    entry_ref_price=close,
                    trigger_reason=f"Close {close:.1f} broke OR Low {or_l:.1f} with margin {margin:.2f} ATR",
                    gate_margins={"or_margin_atr": margin, "atr": atr},
                ))
                traded_short_today = True

        return candidates

    def scan_s2_momentum(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        """S2: 20-bar Momentum Breakout with Volume Confirmation."""
        candidates: list[StrategyCandidate] = []
        if len(df) < self.momentum_lookback + 5:
            return candidates

        closes = df["close"].to_list()
        highs = df["high"].to_list()
        lows = df["low"].to_list()
        v_ratios = df["volume_ratio"].to_list() if "volume_ratio" in df.columns else [1.5] * len(df)
        body_ratios = df["candle_body_ratio"].to_list() if "candle_body_ratio" in df.columns else [0.6] * len(df)
        upper_wicks = df["upper_wick_ratio"].to_list() if "upper_wick_ratio" in df.columns else [0.2] * len(df)
        lower_wicks = df["lower_wick_ratio"].to_list() if "lower_wick_ratio" in df.columns else [0.2] * len(df)
        ema_fasts = df["ema_fast"].to_list() if "ema_fast" in df.columns else closes
        ema_slows = df["ema_slow"].to_list() if "ema_slow" in df.columns else closes
        rsis = df["rsi"].to_list() if "rsi" in df.columns else [50.0] * len(df)
        ist_minutes = self._get_ist_minutes(df)

        last_signal_idx = -self.momentum_cooldown

        for i in range(self.momentum_lookback, len(df)):
            if self.session_filter and not self.is_session_allowed(ist_minutes[i]):
                continue

            if i - last_signal_idx < self.momentum_cooldown:
                continue

            # Lookback window (excluding current bar)
            prior_highs = highs[i - self.momentum_lookback : i]
            prior_lows = lows[i - self.momentum_lookback : i]
            max_h = max(prior_highs)
            min_l = min(prior_lows)

            close = closes[i]
            v_ratio = v_ratios[i] or 1.0
            u_wick = upper_wicks[i] or 0.0
            l_wick = lower_wicks[i] or 0.0
            efast = ema_fasts[i]
            eslow = ema_slows[i]
            rsi = rsis[i] or 50.0

            # Long setup: close breaks 20-bar high, volume ratio >= threshold, close in top 30%
            if close > max_h and v_ratio >= self.momentum_vol_ratio and u_wick <= 0.30:
                if self.trend_aligned and (efast < eslow or rsi < 50.0):
                    continue
                candidates.append(StrategyCandidate(
                    bar_index=i,
                    direction=1,
                    strategy_id="S2_MOM_LONG",
                    entry_ref_price=close,
                    trigger_reason=f"20-bar high breakout with volume ratio {v_ratio:.2f}",
                    gate_margins={"vol_ratio": v_ratio, "upper_wick": u_wick},
                ))
                last_signal_idx = i

            # Short setup: close breaks 20-bar low, volume ratio >= threshold, close in bottom 30%
            elif close < min_l and v_ratio >= self.momentum_vol_ratio and l_wick <= 0.30:
                if self.trend_aligned and (efast > eslow or rsi > 50.0):
                    continue
                candidates.append(StrategyCandidate(
                    bar_index=i,
                    direction=-1,
                    strategy_id="S2_MOM_SHORT",
                    entry_ref_price=close,
                    trigger_reason=f"20-bar low breakdown with volume ratio {v_ratio:.2f}",
                    gate_margins={"vol_ratio": v_ratio, "lower_wick": l_wick},
                ))
                last_signal_idx = i

        return candidates

    def scan_s3_vwap_reclaim(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        """S3: VWAP Reclaim / Reject with trend confirmation."""
        candidates: list[StrategyCandidate] = []
        if "vwap" not in df.columns or len(df) < 5:
            return candidates

        closes = df["close"].to_list()
        vwaps = df["vwap"].to_list()
        ema_slows = df["ema_slow"].to_list() if "ema_slow" in df.columns else closes
        rsis = df["rsi"].to_list() if "rsi" in df.columns else [50.0] * len(df)
        ist_minutes = self._get_ist_minutes(df)

        for i in range(1, len(df)):
            if self.session_filter and not self.is_session_allowed(ist_minutes[i]):
                continue

            prev_c = closes[i - 1]
            prev_v = vwaps[i - 1]
            curr_c = closes[i]
            curr_v = vwaps[i]
            eslow = ema_slows[i]
            rsi = rsis[i] or 50.0

            if prev_v is None or curr_v is None:
                continue

            # VWAP Reclaim Long: Crosses above VWAP
            if prev_c <= prev_v and curr_c > curr_v:
                if self.trend_aligned and (curr_c < eslow or rsi < 50.0):
                    continue
                candidates.append(StrategyCandidate(
                    bar_index=i,
                    direction=1,
                    strategy_id="S3_VWAP_RECLAIM_LONG",
                    entry_ref_price=curr_c,
                    trigger_reason=f"Close {curr_c:.1f} crossed above VWAP {curr_v:.1f}",
                    gate_margins={"vwap_dist": (curr_c - curr_v) / curr_v},
                ))

            # VWAP Reject Short: Crosses below VWAP
            elif prev_c >= prev_v and curr_c < curr_v:
                if self.trend_aligned and (curr_c > eslow or rsi > 50.0):
                    continue
                candidates.append(StrategyCandidate(
                    bar_index=i,
                    direction=-1,
                    strategy_id="S3_VWAP_REJECT_SHORT",
                    entry_ref_price=curr_c,
                    trigger_reason=f"Close {curr_c:.1f} crossed below VWAP {curr_v:.1f}",
                    gate_margins={"vwap_dist": (curr_v - curr_c) / curr_v},
                ))

        return candidates

    def scan_s4_volatility_squeeze(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        """S4: Volatility Squeeze Breakout.
        Requires narrow-range consolidation / ATR compression followed by an impulsive
        expansion breakout with volume and trend confluence.
        """
        candidates: list[StrategyCandidate] = []
        if len(df) < 25:
            return candidates

        closes = df["close"].to_list()
        highs = df["high"].to_list()
        lows = df["low"].to_list()
        atrs = df["atr"].to_list() if "atr" in df.columns else None
        v_ratios = df["volume_ratio"].to_list() if "volume_ratio" in df.columns else [1.2] * len(df)
        ema_fasts = df["ema_fast"].to_list() if "ema_fast" in df.columns else closes
        ema_slows = df["ema_slow"].to_list() if "ema_slow" in df.columns else closes
        rsis = df["rsi"].to_list() if "rsi" in df.columns else [50.0] * len(df)

        if not atrs:
            return candidates

        ist_minutes = self._get_ist_minutes(df)
        last_signal_idx = -self.squeeze_cooldown

        for i in range(25, len(df)):
            if self.session_filter and not self.is_session_allowed(ist_minutes[i]):
                continue

            if i - last_signal_idx < self.squeeze_cooldown:
                continue

            recent_atrs = [atrs[j] for j in range(i - 4, i) if atrs[j] is not None]
            prior_atrs = [atrs[j] for j in range(i - 20, i - 4) if atrs[j] is not None]
            if not recent_atrs or not prior_atrs:
                continue

            prior_median_atr = float(np.median(prior_atrs))
            if prior_median_atr <= 0:
                continue

            # Compression check: minimum recent ATR is below squeeze threshold
            is_compressed = min(recent_atrs) < (self.squeeze_compression_ratio * prior_median_atr)
            if not is_compressed:
                continue

            # Breakout beyond lookback high / low
            prior_high = max(highs[i - self.squeeze_lookback : i])
            prior_low = min(lows[i - self.squeeze_lookback : i])

            close = closes[i]
            vr = v_ratios[i] or 1.0
            efast = ema_fasts[i]
            eslow = ema_slows[i]
            rsi = rsis[i] or 50.0

            # Long breakout: close breaks prior high, volume confirmed, trend supportive
            if close > prior_high and vr >= 1.15:
                if self.trend_aligned and (efast < eslow or rsi < 52.0):
                    continue
                candidates.append(StrategyCandidate(
                    bar_index=i,
                    direction=1,
                    strategy_id="S4_SQUEEZE_LONG",
                    entry_ref_price=close,
                    trigger_reason=f"Volatility squeeze breakout above {prior_high:.1f} with volume ratio {vr:.2f}",
                    gate_margins={"squeeze_ratio": min(recent_atrs) / prior_median_atr, "vol_ratio": vr},
                ))
                last_signal_idx = i

            # Short breakdown: close breaks prior low, volume confirmed, trend supportive
            elif close < prior_low and vr >= 1.15:
                if self.trend_aligned and (efast > eslow or rsi > 48.0):
                    continue
                candidates.append(StrategyCandidate(
                    bar_index=i,
                    direction=-1,
                    strategy_id="S4_SQUEEZE_SHORT",
                    entry_ref_price=close,
                    trigger_reason=f"Volatility squeeze breakdown below {prior_low:.1f} with volume ratio {vr:.2f}",
                    gate_margins={"squeeze_ratio": min(recent_atrs) / prior_median_atr, "vol_ratio": vr},
                ))
                last_signal_idx = i

        return candidates

    def generate_random_filter_baseline(
        self,
        total_bars: int,
        target_count: int,
        seed: int = 42,
        df: Optional[pl.DataFrame] = None,
    ) -> list[StrategyCandidate]:
        """Generates a matched random-filter baseline R to verify selective edge."""
        np.random.seed(seed)
        if target_count <= 0 or total_bars <= target_count:
            return []

        if self.session_filter and df is not None and len(df) == total_bars:
            ist_minutes = self._get_ist_minutes(df)
            valid_indices = [
                i for i in range(total_bars - 1)
                if self.is_session_allowed(ist_minutes[i])
            ]
            if len(valid_indices) >= target_count:
                sampled_indices = np.sort(np.random.choice(valid_indices, size=target_count, replace=False))
            else:
                sampled_indices = np.sort(np.random.choice(total_bars - 1, size=target_count, replace=False))
        else:
            sampled_indices = np.sort(np.random.choice(total_bars - 1, size=target_count, replace=False))

        directions = np.random.choice([1, -1], size=target_count)

        candidates = []
        for idx, direction in zip(sampled_indices, directions):
            candidates.append(StrategyCandidate(
                bar_index=int(idx),
                direction=int(direction),
                strategy_id="R_RANDOM_BASELINE",
                entry_ref_price=0.0,
                trigger_reason="Matched random sampling",
                gate_margins={},
            ))
        return candidates

    def scan_s5_structural_breakout(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        """S5: Structural Volume & Absorption Breakout.
        
        Long setup: Candle closes above 20 EMA, ema_slope_50 > 0, price within [VWAP, VWAP + 2*sigma],
                    and absorption_ratio_5 > 0.40 (buying absorption).
        Short setup: Candle closes below 20 EMA, ema_slope_50 < 0, price within [VWAP - 2*sigma, VWAP],
                     and absorption_ratio_5 < -0.40 (selling absorption).
        Barriers: SL at 1.5 * ATR, TP at 2.5 * ATR.
        """
        candidates: list[StrategyCandidate] = []
        if len(df) < 50:
            return candidates

        closes = df["close"].to_list()
        ema_20s = df["ema_20"].to_list() if "ema_20" in df.columns else closes
        slopes = df["ema_slope_50"].to_list() if "ema_slope_50" in df.columns else [0.0] * len(df)
        vwaps = df["vwap"].to_list() if "vwap" in df.columns else closes
        upper_2stds = df["vwap_upper_2std"].to_list() if "vwap_upper_2std" in df.columns else [c * 1.02 for c in closes]
        lower_2stds = df["vwap_lower_2std"].to_list() if "vwap_lower_2std" in df.columns else [c * 0.98 for c in closes]
        absorptions = df["absorption_ratio_5"].to_list() if "absorption_ratio_5" in df.columns else [0.0] * len(df)
        atrs = df["atr"].to_list() if "atr" in df.columns else [c * 0.003 for c in closes]

        ist_minutes = self._get_ist_minutes(df)
        last_signal_idx = -self.s5_cooldown

        for i in range(50, len(df)):
            if self.session_filter and not self.is_session_allowed(ist_minutes[i]):
                continue

            if i - last_signal_idx < self.s5_cooldown:
                continue

            c = closes[i]
            e20 = ema_20s[i]
            slope = slopes[i]
            v = vwaps[i]
            up2 = upper_2stds[i]
            lo2 = lower_2stds[i]
            abs_ratio = absorptions[i]
            atr = atrs[i] or (c * 0.003)

            if any(x is None for x in (c, e20, slope, v, up2, lo2, abs_ratio)):
                continue

            # Long setup
            if c > e20 and slope > 0.0 and (v <= c <= up2) and abs_ratio > self.s5_absorption_threshold:
                candidates.append(StrategyCandidate(
                    bar_index=i,
                    direction=1,
                    strategy_id="S5_STRUCT_LONG",
                    entry_ref_price=c,
                    trigger_reason=(
                        f"Close {c:.1f} > EMA20 {e20:.1f}, slope {slope:.3f} > 0, "
                        f"in VWAP band [{v:.1f}, {up2:.1f}], absorption {abs_ratio:.2f} > {self.s5_absorption_threshold:.2f}"
                    ),
                    gate_margins={
                        "absorption_ratio": abs_ratio,
                        "ema_slope_50": slope,
                        "vwap_dist": (c - v) / v,
                        "atr": atr,
                        "k_sl": self.s5_k_sl,
                        "k_tp": self.s5_k_tp,
                    },
                ))
                last_signal_idx = i

            # Short setup
            elif c < e20 and slope < 0.0 and (lo2 <= c <= v) and abs_ratio < -self.s5_absorption_threshold:
                candidates.append(StrategyCandidate(
                    bar_index=i,
                    direction=-1,
                    strategy_id="S5_STRUCT_SHORT",
                    entry_ref_price=c,
                    trigger_reason=(
                        f"Close {c:.1f} < EMA20 {e20:.1f}, slope {slope:.3f} < 0, "
                        f"in VWAP band [{lo2:.1f}, {v:.1f}], absorption {abs_ratio:.2f} < -{self.s5_absorption_threshold:.2f}"
                    ),
                    gate_margins={
                        "absorption_ratio": abs_ratio,
                        "ema_slope_50": slope,
                        "vwap_dist": (v - c) / v,
                        "atr": atr,
                        "k_sl": self.s5_k_sl,
                        "k_tp": self.s5_k_tp,
                    },
                ))
                last_signal_idx = i

        return candidates

    def scan_s7_absorption_reversal(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        """Strategy S7: Structural Absorption Reversal scanner.
        
        Detects mean-reversion setups at key structural levels (Prev Day H/L, VWAP bands)
        where high institutional volume absorbs directional momentum.
        """
        from app.quant.strategies.s7_events import S7EventEngine
        from app.quant.strategies.s7_absorption import S7AbsorptionScanner

        engine = S7EventEngine(self.s7_config)
        events = engine.detect_events(df)
        scanner = S7AbsorptionScanner(self.s7_config)
        candidates = scanner.scan_candidates(events, df)

        if self.session_filter:
            ist_minutes = self._get_ist_minutes(df)
            candidates = [
                c for c in candidates
                if c.bar_index < len(ist_minutes) and self.is_session_allowed(ist_minutes[c.bar_index])
            ]

        return candidates

    def scan_s8_iv_regime(
        self,
        df: pl.DataFrame,
        custom_iv: float | None = None,
    ) -> list[StrategyCandidate]:
        """Strategy S8: IV Regime Mispricing scanner (S8SPEC_v1.0).

        Delegates to S8IVRegimeScanner (IV/RV compression + expansion).
        Applies the engine-level session filter on top when enabled so S8
        honours the same institutional liquidity windows as S1-S7.
        """
        from app.quant.strategies.s8_iv_regime import S8IVRegimeScanner

        scanner = S8IVRegimeScanner()
        candidates = scanner.scan_dataframe(df, custom_iv=custom_iv)

        if self.session_filter:
            ist_minutes = self._get_ist_minutes(df)
            candidates = [
                c for c in candidates
                if c.bar_index < len(ist_minutes) and self.is_session_allowed(ist_minutes[c.bar_index])
            ]

        return candidates

    def scan_single(self, df: pl.DataFrame, key: str) -> list[StrategyCandidate]:
        """Dispatches a single baseline key (S1-S5, S7, S8) to its scanner."""
        norm = key.strip().upper()
        if norm == "S1":
            return self.scan_s1_orb(df)
        if norm == "S2":
            return self.scan_s2_momentum(df)
        if norm == "S3":
            return self.scan_s3_vwap_reclaim(df)
        if norm == "S4":
            return self.scan_s4_volatility_squeeze(df)
        if norm == "S5":
            return self.scan_s5_structural_breakout(df)
        if norm == "S7":
            return self.scan_s7_absorption_reversal(df)
        if norm == "S8":
            return self.scan_s8_iv_regime(df)
        raise ValueError(f"Unknown confluence leg: {key!r} (expected S1-S5, S7, or S8)")

    def scan_confluence(
        self,
        df: pl.DataFrame,
        keys: list[str],
        tolerance_bars: int = 1,
    ) -> list[StrategyCandidate]:
        """Confluence (AND) filter: keeps primary-leg candidates confirmed by every
        other leg within ±tolerance_bars with matching direction.

        The first key is the primary (entry price, barriers); confirming legs act
        purely as vetoes. Output ids carry a CONF_ prefix so downstream barriers
        and audit trails stay distinguishable from single-leg signals.
        """
        if len(keys) < 2:
            raise ValueError("Confluence needs at least two legs (e.g. ['S4', 'S8'])")
        legs = [self.scan_single(df, k) for k in keys]
        primary = legs[0]
        if not primary:
            return []

        by_leg_bar: list[dict[int, list[StrategyCandidate]]] = []
        for leg in legs[1:]:
            index: dict[int, list[StrategyCandidate]] = {}
            for c in leg:
                index.setdefault(c.bar_index, []).append(c)
            by_leg_bar.append(index)

        merged: list[StrategyCandidate] = []
        primary_key = keys[0].strip().upper()
        tag = "+".join(k.strip().upper() for k in keys)
        for pc in primary:
            confirming: list[StrategyCandidate] = []
            ok = True
            for index in by_leg_bar:
                hit = None
                for b in range(pc.bar_index - tolerance_bars, pc.bar_index + tolerance_bars + 1):
                    for cc in index.get(b, []):
                        if cc.direction == pc.direction:
                            hit = cc
                            break
                    if hit is not None:
                        break
                if hit is None:
                    ok = False
                    break
                confirming.append(hit)
            if not ok:
                continue
            margins = dict(pc.gate_margins)
            margins.setdefault("k_tp", self._default_k_tp(primary_key))
            margins.setdefault("k_sl", self._default_k_sl(primary_key))
            margins["confluence_tag"] = 1.0
            merged.append(StrategyCandidate(
                bar_index=pc.bar_index,
                direction=pc.direction,
                strategy_id=f"CONF_{tag}_{'LONG' if pc.direction == 1 else 'SHORT'}",
                entry_ref_price=pc.entry_ref_price,
                trigger_reason=" + ".join(f"[{c.strategy_id}] {c.trigger_reason}" for c in [pc, *confirming]),
                gate_margins=margins,
            ))
        return merged

    @staticmethod
    def _default_k_tp(key: str) -> float:
        return {"S5": 2.5, "S8": 2.0, "S7": 1.5}.get(key, 1.5)

    @staticmethod
    def _default_k_sl(key: str) -> float:
        return {"S5": 1.5, "S8": 1.0, "S7": 0.5}.get(key, 1.0)


class StrategyS1ORB:
    """Strategy S1: Opening Range Breakout."""
    key: str = "S1"
    name: str = "Opening Range Breakout"
    k_sl: float = 1.0
    k_tp: float = 1.5

    def __init__(self, orb_buffer_atr: float = 0.1, trend_aligned: bool = False, session_filter: bool = False):
        self.orb_buffer_atr = orb_buffer_atr
        self.trend_aligned = trend_aligned
        self.session_filter = session_filter

    def scan(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        engine = BaselineStrategyEngine(orb_buffer_atr=self.orb_buffer_atr, trend_aligned=self.trend_aligned, session_filter=self.session_filter)
        return engine.scan_s1_orb(df)


class StrategyS2Momentum:
    """Strategy S2: 20-Bar Momentum Breakout with Volume Confirmation."""
    key: str = "S2"
    name: str = "20-Bar Momentum Breakout"
    k_sl: float = 1.0
    k_tp: float = 1.5

    def __init__(self, momentum_vol_ratio: float = 1.2, momentum_lookback: int = 20, momentum_cooldown: int = 10, trend_aligned: bool = False, session_filter: bool = False):
        self.momentum_vol_ratio = momentum_vol_ratio
        self.momentum_lookback = momentum_lookback
        self.momentum_cooldown = momentum_cooldown
        self.trend_aligned = trend_aligned
        self.session_filter = session_filter

    def scan(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        engine = BaselineStrategyEngine(
            momentum_vol_ratio=self.momentum_vol_ratio,
            momentum_lookback=self.momentum_lookback,
            momentum_cooldown=self.momentum_cooldown,
            trend_aligned=self.trend_aligned,
            session_filter=self.session_filter,
        )
        return engine.scan_s2_momentum(df)


class StrategyS3VWAPReclaim:
    """Strategy S3: VWAP Reclaim / Reject with trend confirmation."""
    key: str = "S3"
    name: str = "VWAP Reclaim / Reject"
    k_sl: float = 1.0
    k_tp: float = 1.5

    def __init__(self, trend_aligned: bool = False, session_filter: bool = False):
        self.trend_aligned = trend_aligned
        self.session_filter = session_filter

    def scan(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        engine = BaselineStrategyEngine(trend_aligned=self.trend_aligned, session_filter=self.session_filter)
        return engine.scan_s3_vwap_reclaim(df)


class StrategyS4VolatilitySqueeze:
    """Strategy S4: Volatility Squeeze Breakout."""
    key: str = "S4"
    name: str = "Volatility Squeeze Breakout"
    k_sl: float = 1.0
    k_tp: float = 1.5

    def __init__(self, squeeze_lookback: int = 12, squeeze_compression_ratio: float = 0.90, squeeze_cooldown: int = 8, trend_aligned: bool = False, session_filter: bool = False):
        self.squeeze_lookback = squeeze_lookback
        self.squeeze_compression_ratio = squeeze_compression_ratio
        self.squeeze_cooldown = squeeze_cooldown
        self.trend_aligned = trend_aligned
        self.session_filter = session_filter

    def scan(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        engine = BaselineStrategyEngine(
            squeeze_lookback=self.squeeze_lookback,
            squeeze_compression_ratio=self.squeeze_compression_ratio,
            squeeze_cooldown=self.squeeze_cooldown,
            trend_aligned=self.trend_aligned,
            session_filter=self.session_filter,
        )
        return engine.scan_s4_volatility_squeeze(df)


class StrategyS5StructuralBreakout:
    """Strategy S5: Structural Volume & Absorption Breakout.
    
    Long setup:
    - Candle closes above 20 EMA
    - ema_slope_50 > 0
    - Price within [VWAP, VWAP + 2*sigma] (not overbought)
    - absorption_ratio_5 > 0.40 (buying absorption)
    - SL: entry - 1.5 * ATR, TP: entry + 2.5 * ATR
    
    Short setup:
    - Candle closes below 20 EMA
    - ema_slope_50 < 0
    - Price within [VWAP - 2*sigma, VWAP] (not oversold)
    - absorption_ratio_5 < -0.40 (selling absorption)
    - SL: entry + 1.5 * ATR, TP: entry - 2.5 * ATR
    """
    key: str = "S5"
    name: str = "Structural Volume & Absorption Breakout"
    k_sl: float = 1.5
    k_tp: float = 2.5

    def __init__(
        self,
        absorption_threshold: float = 0.40,
        k_sl: float = 1.5,
        k_tp: float = 2.5,
        cooldown: int = 5,
        trend_aligned: bool = False,
        session_filter: bool = False,
        allowed_windows: list[tuple[str, str]] | None = None,
    ):
        self.absorption_threshold = absorption_threshold
        self.k_sl = k_sl
        self.k_tp = k_tp
        self.cooldown = cooldown
        self.trend_aligned = trend_aligned
        self.session_filter = session_filter
        self.allowed_windows = allowed_windows

    def scan(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        engine = BaselineStrategyEngine(
            s5_absorption_threshold=self.absorption_threshold,
            s5_cooldown=self.cooldown,
            s5_k_sl=self.k_sl,
            s5_k_tp=self.k_tp,
            trend_aligned=self.trend_aligned,
            session_filter=self.session_filter,
            allowed_windows=self.allowed_windows,
        )
        return engine.scan_s5_structural_breakout(df)


class StrategyS7AbsorptionReversal:
    """Strategy S7: Structural Absorption Reversal.
    
    Mean-reversion strategy fading momentum exhaustion at key structural
    boundaries (Previous Day High/Low, VWAP +/- 2std bands) with tight risk.
    """
    key: str = "S7"
    name: str = "Structural Absorption Reversal"
    k_sl: float = 0.5
    k_tp: float = 1.5

    def __init__(
        self,
        config: Any | None = None,
        trend_aligned: bool = False,
        session_filter: bool = False,
        allowed_windows: list[tuple[str, str]] | None = None,
    ):
        self.config = config
        self.trend_aligned = trend_aligned
        self.session_filter = session_filter
        self.allowed_windows = allowed_windows

    def scan(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        engine = BaselineStrategyEngine(
            s7_config=self.config,
            trend_aligned=self.trend_aligned,
            session_filter=self.session_filter,
            allowed_windows=self.allowed_windows,
        )
        return engine.scan_s7_absorption_reversal(df)


class StrategyS8IVRegime:
    """Strategy S8: IV Regime Mispricing (S8SPEC_v1.0).

    Compression (IV/RV cheap) rides trend momentum with long-option bias;
    Expansion (IV/RV rich) fades overbought/oversold extremes.
    Barriers default to the S8 config (k_tp=2.0, k_sl=1.0) unless the
    harness overrides them globally.
    """
    key: str = "S8"
    name: str = "IV Regime Mispricing"
    k_sl: float = 1.0
    k_tp: float = 2.0

    def __init__(
        self,
        custom_iv: float | None = None,
        trend_aligned: bool = False,
        session_filter: bool = False,
        allowed_windows: list[tuple[str, str]] | None = None,
    ):
        self.custom_iv = custom_iv
        self.trend_aligned = trend_aligned
        self.session_filter = session_filter
        self.allowed_windows = allowed_windows

    def scan(self, df: pl.DataFrame) -> list[StrategyCandidate]:
        engine = BaselineStrategyEngine(
            trend_aligned=self.trend_aligned,
            session_filter=self.session_filter,
            allowed_windows=self.allowed_windows,
        )
        return engine.scan_s8_iv_regime(df, custom_iv=self.custom_iv)


BASELINE_STRATEGIES: dict[str, type] = {
    "S1": StrategyS1ORB,
    "S2": StrategyS2Momentum,
    "S3": StrategyS3VWAPReclaim,
    "S4": StrategyS4VolatilitySqueeze,
    "S5": StrategyS5StructuralBreakout,
    "S7": StrategyS7AbsorptionReversal,
    "S8": StrategyS8IVRegime,
}


