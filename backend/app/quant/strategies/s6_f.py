"""S6-F Failed-Breakout Reversal Candidate Scanner (S6SPEC_v1.3).

Consumes the shared FailureEvent stream and emits reversal EntryCandidates:
- Direction: strictly OPPOSITE the original structural breakout
- Dynamic Stop: beyond failure extreme + 0.25 ATR (capped at 2.0 ATR)
- Target: 2.0 ATR baseline
- Session window (09:45 to 14:30 IST), cooldown (10 bars), and daily trade cap (< 4 trades/day)
- Evaluates failed breakouts regardless of whether S6-A continuation gates passed
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
import polars as pl

from app.quant.strategies.s6_config import S6Config, S6Variant
from app.quant.strategies.s6_events import FailureEvent, EntryCandidate


class S6FScanner:
    """Evaluates failure events into S6-F failed-breakout reversal EntryCandidates."""

    def __init__(self, config: S6Config):
        self.config = config

    def _get_ist_minute_of_day(self, t: datetime) -> int:
        if t.tzinfo is not None:
            ist_dt = t.astimezone(timezone(timedelta(hours=5, minutes=30)))
            return ist_dt.hour * 60 + ist_dt.minute
        return (t.hour * 60 + t.minute + 330) % 1440

    def _parse_time_to_minute(self, s: str) -> int:
        parts = s.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    def scan_candidates(
        self,
        failure_events: List[FailureEvent],
        atr5_lookup: Dict[str, float],
        df_exec: Optional[pl.DataFrame] = None,
        timeframe: str = "1m",
    ) -> List[EntryCandidate]:
        """Filters FailureEvents into S6-F reversal EntryCandidates."""
        candidates: List[EntryCandidate] = []
        if not failure_events:
            return candidates

        start_min = self._parse_time_to_minute(self.config.limits.entry_from)   # 09:45 = 585
        end_min = self._parse_time_to_minute(self.config.limits.entry_to)       # 14:30 = 870
        cooldown_bars = self.config.limits.cooldown_bars                       # 10
        daily_cap = self.config.limits.max_trades_per_day                      # 4

        current_day: Optional[str] = None
        daily_trades = 0
        last_signal_time: Optional[datetime] = None

        exec_times = df_exec["timestamp"].to_list() if df_exec is not None and "timestamp" in df_exec.columns else []
        time_to_idx = {t: i for i, t in enumerate(exec_times)} if exec_times else {}
        last_signal_bar_idx = -9999

        for fe in failure_events:
            t = fe.failure_time
            day_str = str(t.date()) if hasattr(t, "date") else str(t)[:10]

            if day_str != current_day:
                current_day = day_str
                daily_trades = 0

            # 1. Daily trade cap
            if daily_trades >= daily_cap:
                continue

            # 2. Session entry window (09:45 - 14:30 IST)
            ist_min = self._get_ist_minute_of_day(t)
            if ist_min < start_min or ist_min > end_min:
                continue

            # 3. Cooldown check
            if time_to_idx and t in time_to_idx:
                curr_idx = time_to_idx[t]
                if curr_idx - last_signal_bar_idx < cooldown_bars:
                    continue
            elif last_signal_time is not None and (t - last_signal_time) < timedelta(minutes=cooldown_bars):
                continue

            # Retrieve ATR5 for this event
            atr5 = atr5_lookup.get(fe.breakout_event_id, 1.0)
            
            # 4. Stop Loss calculation: beyond failure extreme + 0.25 ATR, capped at 2.0 ATR
            stop_buf = self.config.failure.stop_buffer_atr * atr5
            stop_cap = self.config.failure.stop_cap_atr * atr5
            
            if fe.direction == -1:  # Short failure trade (failed long breakout)
                raw_stop = (fe.failure_extreme - fe.failure_price) + stop_buf
            else:                   # Long failure trade (failed short breakout)
                raw_stop = (fe.failure_price - fe.failure_extreme) + stop_buf

            stop_dist = max(0.5 * atr5, min(stop_cap, abs(raw_stop)))
            target_dist = self.config.failure.target_atr * atr5

            # Entry occurs on open of next bar (t + execution timeframe)
            tf_delta = timedelta(minutes=1 if timeframe == "1m" else 5)
            entry_t = t + tf_delta

            cand_id = f"S6CAND_F_{fe.event_id}_{int(entry_t.timestamp())}"
            candidates.append(EntryCandidate(
                candidate_id=cand_id,
                strategy_id="S6",
                variant="S6-F",
                instrument=fe.instrument,
                direction=fe.direction,
                signal_time=t,
                entry_time=entry_t,
                entry_reference_price=fe.failure_price,
                execution_timeframe=timeframe,
                context_timeframe="5m",
                atr5=atr5,
                stop_distance=stop_dist,
                target_distance=target_dist,
                episode_id=fe.breakout_event_id,
                event_id=fe.event_id,
                regime="REVERSAL",
                volume_ratio=1.0,
                close_location=0.5,
                room_atr=2.0,
                reason_codes=[
                    f"FAILED_REENTRY_ATR_{fe.reentry_distance_atr:.2f}",
                    f"BARS_{fe.bars_since_breakout}",
                    f"STOP_{stop_dist/atr5:.2f}ATR",
                ],
            ))

            daily_trades += 1
            last_signal_time = t
            if time_to_idx and t in time_to_idx:
                last_signal_bar_idx = time_to_idx[t]

        return candidates
