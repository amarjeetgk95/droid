"""S7 Absorption Reversal Scanner (S7SPEC_v1.0).

Filters raw AbsorptionEvents through institutional qualification gates:
1. Session window (09:45 - 14:30 IST)
2. Daily trade cap (<= 3 trades/day)
3. Bar cooldown (>= 10 bars between signals)
4. RSI context (prevents fading already-exhausted counter-momentum)
5. VWAP alignment (reversal target points toward VWAP magnet)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Optional
import polars as pl

from app.quant.strategies.s7_config import S7Config, create_s7_default_config
from app.quant.strategies.s7_events import AbsorptionEvent, S7EventEngine
from app.quant.strategies.strategies import StrategyCandidate, parse_time_to_minute, get_ist_minute


class S7AbsorptionScanner:
    """Candidate scanner enforcing institutional risk and qualification gates for S7."""

    def __init__(self, config: S7Config | None = None):
        self.config = config or create_s7_default_config()
        self.window_start = parse_time_to_minute(self.config.limits.entry_window_start)
        self.window_end = parse_time_to_minute(self.config.limits.entry_window_end)

    def scan_candidates(
        self,
        events: list[AbsorptionEvent],
        df: pl.DataFrame,
    ) -> list[StrategyCandidate]:
        """Evaluates absorption events against qualification gates, emitting StrategyCandidate objects."""
        candidates: list[StrategyCandidate] = []
        last_signal_bar = -9999
        daily_trades: dict[str, int] = {}

        timestamps = df["timestamp"].to_list()

        for ev in events:
            # 1. Bar cooldown gate
            if ev.bar_index - last_signal_bar < self.config.limits.cooldown_bars:
                continue

            # 2. Daily trade cap gate
            t = ev.timestamp
            ist_minute = get_ist_minute(t)
            # Date key in IST
            if hasattr(t, "tzinfo") and t.tzinfo is not None:
                ist_dt = t.astimezone(timezone(timedelta(hours=5, minutes=30)))
                date_key = ist_dt.strftime("%Y-%m-%d")
            else:
                date_key = str(t)[:10]

            trades_today = daily_trades.get(date_key, 0)
            if trades_today >= self.config.limits.max_trades_per_day:
                continue

            # 3. Session window gate (09:45 - 14:30 IST)
            if not (self.window_start <= ist_minute <= self.window_end):
                continue

            # 4. RSI sanity gate
            # For SHORT reversal, RSI shouldn't be oversold (< 40)
            # For LONG reversal, RSI shouldn't be overbought (> 60)
            if ev.reversal_direction == -1 and ev.rsi < 40.0:
                continue
            if ev.reversal_direction == 1 and ev.rsi > 60.0:
                continue

            # 5. VWAP alignment
            # For SHORT reversal, entry price should ideally be >= VWAP (or within 0.3 ATR below)
            # For LONG reversal, entry price should ideally be <= VWAP (or within 0.3 ATR above)
            vwap_dist = (ev.entry_ref_price - ev.vwap) / ev.atr
            if ev.reversal_direction == -1 and vwap_dist < -0.3:
                continue
            if ev.reversal_direction == 1 and vwap_dist > 0.3:
                continue

            # 6. Target and Stop-Loss geometry
            # Mean-reversion target towards VWAP with ATR cap
            if self.config.exit.use_vwap_target:
                raw_target_atr = abs(ev.entry_ref_price - ev.vwap) / ev.atr
                effective_k_tp = min(max(raw_target_atr, 0.8), self.config.exit.vwap_target_atr_cap)
            else:
                effective_k_tp = self.config.exit.k_tp

            effective_k_sl = self.config.exit.k_sl

            strat_id = "S7_ABSORPTION_LONG" if ev.reversal_direction == 1 else "S7_ABSORPTION_SHORT"
            gate_margins = {
                "volume_ratio": ev.volume_ratio,
                "price_displacement": ev.price_displacement,
                "wick_rejection": ev.wick_rejection,
                "rsi": ev.rsi,
                "vwap_distance_atr": vwap_dist,
                "atr": ev.atr,
                "k_sl": effective_k_sl,
                "k_tp": effective_k_tp,
                "level_type": ev.level.level_type,
                "level_price": ev.level.price,
            }

            candidate = StrategyCandidate(
                bar_index=ev.bar_index,
                direction=ev.reversal_direction,
                strategy_id=strat_id,
                entry_ref_price=ev.entry_ref_price,
                trigger_reason=ev.trigger_reason,
                gate_margins=gate_margins,
            )

            candidates.append(candidate)
            last_signal_bar = ev.bar_index
            daily_trades[date_key] = trades_today + 1

        return candidates
