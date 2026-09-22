"""S6 Deterministic Execution Simulator (S6SPEC_v1.3).

Implements strictly causal, deterministic trade execution with zero future lookahead:
- Signal on bar t close -> Entry on bar t+1 open + adverse slippage (0.05 * atr5)
- Missing bar t+1 cancels candidate (MISSING_BAR)
- Same-bar TP/SL collision resolves SL FIRST (primary conservative convention)
- Adverse gap beyond SL fills at bar open
- Favorable gap through TP fills at TP price (no artificial price improvement)
- Time barrier exit at 15 bars held
- Force-flat exit at 15:15 IST
- Integration with DROID statutory cost engine (app.quant.costs)
- MFE, MAE, Gross P&L, Slippage, Statutory Drag, Net R-multiple tracking
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple, Any
import polars as pl
import numpy as np

from app.quant.strategies.s6_config import S6Config
from app.quant.strategies.s6_events import EntryCandidate
from app.quant.costs import (
    calculate_trade_costs,
    BSE_SENSEX_FUTURES,
    StatutorySchedule,
    CostBreakdown,
)

# Standard NSE Futures schedule if not already in costs.py
NSE_NIFTY_FUTURES = StatutorySchedule(
    venue="NSE",
    segment="FUTURES",
    stt_rate_sell=0.0002,
    exchange_rate=0.000019,
    sebi_rate=0.000001,
    stamp_duty_rate_buy=0.00002,
    gst_rate=0.18,
    flat_brokerage=20.0,
)


@dataclass(frozen=True)
class S6Trade:
    candidate_id: str
    strategy_id: str
    variant: str
    instrument: str
    direction: int            # +1 Long, -1 Short
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    bars_held: int
    exit_reason: str          # "TP", "SL", "TIME_BARRIER", "FORCE_FLAT", "SAME_BAR_SL_FIRST"
    gross_pnl_pts: float
    slippage_pts: float
    cost_pts: float
    net_pnl_pts: float
    mfe_pts: float
    mae_pts: float
    initial_risk_pts: float
    gross_R: float
    net_R: float
    mfe_R: float
    mae_R: float
    cost_drag_R: float
    slippage_drag_R: float
    same_bar_collision: bool
    episode_id: str
    event_id: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["signal_time"] = self.signal_time.isoformat() if hasattr(self.signal_time, "isoformat") else str(self.signal_time)
        d["entry_time"] = self.entry_time.isoformat() if hasattr(self.entry_time, "isoformat") else str(self.entry_time)
        d["exit_time"] = self.exit_time.isoformat() if hasattr(self.exit_time, "isoformat") else str(self.exit_time)
        return d


class S6ExecutionSimulator:
    """Deterministic, causal simulator for S6-A and S6-F candidate signals."""

    def __init__(self, config: S6Config, cost_stress: float = 1.0):
        self.config = config
        self.cost_stress = cost_stress

    def _get_ist_minute_of_day(self, t: datetime) -> int:
        if t.tzinfo is not None:
            ist_dt = t.astimezone(timezone(timedelta(hours=5, minutes=30)))
            return ist_dt.hour * 60 + ist_dt.minute
        return (t.hour * 60 + t.minute + 330) % 1440

    def _get_schedule(self, instrument: str) -> StatutorySchedule:
        if "SENSEX" in instrument.upper() or "BSE" in instrument.upper():
            return BSE_SENSEX_FUTURES
        return NSE_NIFTY_FUTURES

    def simulate_candidates(
        self,
        candidates: List[EntryCandidate],
        df_exec: pl.DataFrame,
    ) -> List[S6Trade]:
        """Simulates execution for each EntryCandidate on the execution timeframe dataset."""
        trades: List[S6Trade] = []
        if not candidates or len(df_exec) == 0:
            return trades

        df_exec = df_exec.sort("timestamp")
        timestamps = df_exec["timestamp"].to_list()
        opens = df_exec["open"].to_list()
        highs = df_exec["high"].to_list()
        lows = df_exec["low"].to_list()
        closes = df_exec["close"].to_list()
        n_bars = len(df_exec)

        ts_to_idx = {ts: i for i, ts in enumerate(timestamps)}
        time_barrier = self.config.exit.time_barrier_bars
        slippage_atr = self.config.simulation.slippage_atr
        schedule = self._get_schedule(self.config.instrument)

        force_flat_min = 15 * 60 + 15  # 15:15 IST = 915 minutes

        for cand in candidates:
            # 1. Entry must occur at open of t+1
            # Look up bar index corresponding to cand.entry_time
            entry_idx = ts_to_idx.get(cand.entry_time)
            if entry_idx is None or entry_idx >= n_bars:
                # Missing bar t+1: CANCEL candidate
                continue

            direction = cand.direction
            atr5 = cand.atr5
            slippage_pts = slippage_atr * atr5
            next_open = opens[entry_idx]

            # Modeled entry fill with adverse slippage
            if direction == 1:
                entry_fill = next_open + slippage_pts
                stop_price = entry_fill - cand.stop_distance
                target_price = entry_fill + cand.target_distance
            else:
                entry_fill = next_open - slippage_pts
                stop_price = entry_fill + cand.stop_distance
                target_price = entry_fill - cand.target_distance

            initial_risk_pts = max(1e-4, abs(entry_fill - stop_price))

            # Simulate intra-bar lifecycle from entry bar onward
            bars_held = 0
            exit_price = entry_fill
            exit_time = cand.entry_time
            exit_reason = "TIMEOUT"
            same_bar_collision = False

            peak_favorable = 0.0
            peak_adverse = 0.0

            for k in range(entry_idx, n_bars):
                bars_held += 1
                t_k = timestamps[k]
                o_k = opens[k]
                h_k = highs[k]
                l_k = lows[k]
                c_k = closes[k]

                # Update MFE / MAE
                if direction == 1:
                    fav = max(0.0, h_k - entry_fill)
                    adv = max(0.0, entry_fill - l_k)
                else:
                    fav = max(0.0, entry_fill - l_k)
                    adv = max(0.0, h_k - entry_fill)

                peak_favorable = max(peak_favorable, fav)
                peak_adverse = max(peak_adverse, adv)

                # Check gap on open (for k > entry_idx)
                if k > entry_idx:
                    if direction == 1:
                        # Adverse gap below SL -> exit at open
                        if o_k <= stop_price:
                            exit_price = o_k
                            exit_time = t_k
                            exit_reason = "SL"
                            break
                        # Favorable gap above TP -> exit at TP (no price improvement)
                        elif o_k >= target_price:
                            exit_price = target_price
                            exit_time = t_k
                            exit_reason = "TP"
                            break
                    else:
                        if o_k >= stop_price:
                            exit_price = o_k
                            exit_time = t_k
                            exit_reason = "SL"
                            break
                        elif o_k <= target_price:
                            exit_price = target_price
                            exit_time = t_k
                            exit_reason = "TP"
                            break

                # Check Intrabar SL / TP
                touched_sl = False
                touched_tp = False

                if direction == 1:
                    if l_k <= stop_price:
                        touched_sl = True
                    if h_k >= target_price:
                        touched_tp = True
                else:
                    if h_k >= stop_price:
                        touched_sl = True
                    if l_k <= target_price:
                        touched_tp = True

                # SL / TP Collision Check
                if touched_sl and touched_tp:
                    # RULE: Same-bar collision resolves SL FIRST
                    same_bar_collision = True
                    exit_price = stop_price
                    exit_time = t_k
                    exit_reason = "SAME_BAR_SL_FIRST"
                    break
                elif touched_sl:
                    exit_price = stop_price
                    exit_time = t_k
                    exit_reason = "SL"
                    break
                elif touched_tp:
                    exit_price = target_price
                    exit_time = t_k
                    exit_reason = "TP"
                    break

                # Force flat check at 15:15 IST
                ist_min = self._get_ist_minute_of_day(t_k)
                if ist_min >= force_flat_min:
                    exit_price = c_k
                    exit_time = t_k
                    exit_reason = "FORCE_FLAT"
                    break

                # Time barrier check
                if bars_held >= time_barrier:
                    exit_price = c_k
                    exit_time = t_k
                    exit_reason = "TIME_BARRIER"
                    break

            # Calculate Gross P&L in points
            if direction == 1:
                gross_pts = exit_price - entry_fill
            else:
                gross_pts = entry_fill - exit_price

            # Modeled statutory costs via DROID cost engine
            # Approximate notional turnover assuming 1 lot
            buy_turnover = entry_fill if direction == 1 else exit_price
            sell_turnover = exit_price if direction == 1 else entry_fill
            
            # Slippage on exit: 0 for limit TP, adverse slippage for market exits (SL, Time, Flat)
            exit_slippage_pts = 0.0 if exit_reason == "TP" else slippage_pts
            total_slippage_pts = slippage_pts + exit_slippage_pts

            cost_breakdown: CostBreakdown = calculate_trade_costs(
                buy_turnover=buy_turnover,
                sell_turnover=sell_turnover,
                num_orders=2,
                schedule=schedule,
                slippage_rate=0.0,  # Slippage modeled explicitly via ATR
                stress_multiplier=self.cost_stress,
            )
            # Total statutory taxes and brokerage in equivalent index points
            # (total_cost / turnover_pts) * 1.0
            statutory_pts = cost_breakdown.total_cost / max(1.0, (entry_fill + exit_price) * 0.5) * entry_fill * 0.0001
            # Or conservative flat tax: STT + exchange + GST + brokerage
            # For 1 lot index future, brokerage ₹40 + STT ~0.02% of turnover + GST
            turnover_inr = (buy_turnover + sell_turnover)
            cost_inr = (turnover_inr * 0.00003) + 40.0 + (cost_breakdown.stt)
            cost_pts = (cost_inr / max(1.0, entry_fill)) * 0.5  # scaled in points

            net_pts = gross_pts - total_slippage_pts - cost_pts
            gross_R = gross_pts / initial_risk_pts
            net_R = net_pts / initial_risk_pts
            mfe_R = peak_favorable / initial_risk_pts
            mae_R = peak_adverse / initial_risk_pts
            cost_drag_R = cost_pts / initial_risk_pts
            slippage_drag_R = total_slippage_pts / initial_risk_pts

            trades.append(S6Trade(
                candidate_id=cand.candidate_id,
                strategy_id=cand.strategy_id,
                variant=cand.variant,
                instrument=cand.instrument,
                direction=cand.direction,
                signal_time=cand.signal_time,
                entry_time=cand.entry_time,
                exit_time=exit_time,
                entry_price=entry_fill,
                exit_price=exit_price,
                stop_price=stop_price,
                target_price=target_price,
                bars_held=bars_held,
                exit_reason=exit_reason,
                gross_pnl_pts=gross_pts,
                slippage_pts=total_slippage_pts,
                cost_pts=cost_pts,
                net_pnl_pts=net_pts,
                mfe_pts=peak_favorable,
                mae_pts=peak_adverse,
                initial_risk_pts=initial_risk_pts,
                gross_R=gross_R,
                net_R=net_R,
                mfe_R=mfe_R,
                mae_R=mae_R,
                cost_drag_R=cost_drag_R,
                slippage_drag_R=slippage_drag_R,
                same_bar_collision=same_bar_collision,
                episode_id=cand.episode_id,
                event_id=cand.event_id,
            ))

        return trades
