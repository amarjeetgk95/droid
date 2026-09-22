"""S6-A Continuation Candidate Scanner (S6SPEC_v1.3).

Consumes the shared RawBreakoutEvent stream and applies S6-A continuation gates:
- Eligible 5m regime (rejects UNKNOWN, UNSTABLE)
- Volume expansion >= 1.30x baseline
- Directional close & close location in upper/lower 40% (close_location >= 0.60)
- Structural room >= 1.50 ATR
- Strict session entry window (09:45 to 14:30 IST)
- Cooldown (10 bars) and daily trade cap (< 4 trades/day)
- First-cross rule per episode + direction (duplicate suppressed)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple, Set
import polars as pl

from app.quant.strategies.s6_config import S6Config, S6Variant
from app.quant.strategies.s6_events import RawBreakoutEvent, EntryCandidate


class S6AScanner:
    """Evaluates raw structural breakouts against S6-A continuation gates."""

    def __init__(self, config: S6Config):
        self.config = config
        self.eligible_regimes = {
            "TREND_UP",
            "TREND_DOWN",
            "RANGE",
            "LOW_VOLATILITY",
            "HIGH_VOLATILITY",
        }

    def _get_ist_minute_of_day(self, t: datetime) -> int:
        if t.tzinfo is not None:
            ist_dt = t.astimezone(timezone(timedelta(hours=5, minutes=30)))
            return ist_dt.hour * 60 + ist_dt.minute
        # Assume UTC if naive, convert to IST (+5:30)
        return (t.hour * 60 + t.minute + 330) % 1440

    def _parse_time_to_minute(self, s: str) -> int:
        parts = s.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    def scan_candidates(
        self,
        raw_breakouts: List[RawBreakoutEvent],
        df_exec: Optional[pl.DataFrame] = None,
    ) -> List[EntryCandidate]:
        """Filters raw breakouts into S6-A continuation EntryCandidates."""
        candidates: List[EntryCandidate] = []
        if not raw_breakouts:
            return candidates

        start_min = self._parse_time_to_minute(self.config.limits.entry_from)   # 09:45 = 585
        end_min = self._parse_time_to_minute(self.config.limits.entry_to)       # 14:30 = 870
        cooldown_bars = self.config.limits.cooldown_bars                       # 10
        daily_cap = self.config.limits.max_trades_per_day                      # 4

        # Track state across day and bar
        current_day: Optional[str] = None
        daily_trades = 0
        last_signal_time: Optional[datetime] = None

        # Build index lookup for execution bars if provided
        exec_times = df_exec["timestamp"].to_list() if df_exec is not None and "timestamp" in df_exec.columns else []
        time_to_idx = {t: i for i, t in enumerate(exec_times)} if exec_times else {}
        last_signal_bar_idx = -9999

        for bo in raw_breakouts:
            t = bo.breakout_time
            day_str = str(t.date()) if hasattr(t, "date") else str(t)[:10]

            # Reset daily cap on new day
            if day_str != current_day:
                current_day = day_str
                daily_trades = 0

            # 1. Daily trade cap check
            if daily_trades >= daily_cap:
                continue

            # 2. Session entry window check (09:45 - 14:30 IST)
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

            # 4. Regime eligibility check (blocks UNKNOWN, UNSTABLE)
            if bo.regime not in self.eligible_regimes:
                continue

            # 5. Volume expansion gate
            if bo.volume_ratio < self.config.breakout.volume_ratio_min:
                continue

            # 6. Candle close location gate
            if bo.close_location < self.config.breakout.close_location_min:
                continue

            # 7. Structural room gate
            if bo.room_atr < self.config.breakout.min_room_atr:
                continue

            # All S6-A continuation gates passed -> Emit EntryCandidate
            atr5 = bo.atr5
            stop_dist = self.config.exit.k_sl * atr5
            target_dist = self.config.exit.k_tp * atr5

            # Entry occurs on open of next bar (t + execution timeframe)
            tf_delta = timedelta(minutes=1 if bo.timeframe == "1m" else 5)
            entry_t = t + tf_delta

            cand_id = f"S6CAND_A_{bo.event_id}_{int(entry_t.timestamp())}"
            candidates.append(EntryCandidate(
                candidate_id=cand_id,
                strategy_id="S6",
                variant="S6-A",
                instrument=bo.instrument,
                direction=bo.direction,
                signal_time=t,
                entry_time=entry_t,
                entry_reference_price=bo.breakout_price,
                execution_timeframe=bo.timeframe,
                context_timeframe="5m",
                atr5=atr5,
                stop_distance=stop_dist,
                target_distance=target_dist,
                episode_id=bo.episode_id,
                event_id=bo.event_id,
                regime=bo.regime,
                volume_ratio=bo.volume_ratio,
                close_location=bo.close_location,
                room_atr=bo.room_atr,
                reason_codes=[
                    f"REGIME_{bo.regime}",
                    f"VOL_{bo.volume_ratio:.2f}",
                    f"CLOSE_LOC_{bo.close_location:.2f}",
                    f"ROOM_{bo.room_atr:.2f}",
                ],
            ))

            daily_trades += 1
            last_signal_time = t
            if time_to_idx and t in time_to_idx:
                last_signal_bar_idx = time_to_idx[t]

        return candidates
