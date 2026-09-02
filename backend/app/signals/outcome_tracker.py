"""
Real-Time Signal Outcome Tracker & Quantitative Performance Engine
Tracks live price vs active signals:
  - Triggers & Confirmations
  - Target 1 Hit (1.5R), Target 2 Hit (3.0R), Stop Loss Hit
  - Max Favorable Excursion (MFE) & Max Adverse Excursion (MAE)
  - Historical Win Rate %, Profit Factor, Expectancy, Strategy Attribution
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any
import structlog
from pydantic import BaseModel, Field

from app.signals.fsm import signal_fsm, SignalInstance

logger = structlog.get_logger()


class PerformanceMetrics(BaseModel):
    total_signals: int = 0
    active_signals: int = 0
    completed_signals: int = 0
    winning_signals: int = 0
    losing_signals: int = 0
    expired_signals: int = 0

    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    average_rr: float = 0.0
    expectancy_r: float = 0.0

    target_1_hits: int = 0
    target_2_hits: int = 0
    stop_loss_hits: int = 0

    strategy_breakdown: dict[str, dict] = Field(default_factory=dict)
    underlying_breakdown: dict[str, dict] = Field(default_factory=dict)


class SignalOutcomeTracker:
    """
    Monitors price progression for active signals and calculates performance attribution.
    """

    def update_with_price(self, underlying: str, current_price: Decimal | float) -> list[dict]:
        d_price = Decimal(str(current_price))
        active = signal_fsm.list_active(underlying=underlying)
        events = []

        for sig in active:
            st = sig.fsm_state
            direction = sig.direction

            # ── 1. TRIGGER & CONFIRMATION ──
            if st in ("VALIDATED", "ARMED"):
                if direction == "LONG_CALL" and d_price >= sig.trigger:
                    signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=d_price, reason="TRIGGER_LEVEL_HIT")
                    signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=d_price, reason="ENTRY_CONFIRMED")
                    events.append({"signal_id": sig.signal_id, "event": "CONFIRMED", "price": float(d_price)})
                elif direction == "LONG_PUT" and d_price <= sig.trigger:
                    signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=d_price, reason="TRIGGER_LEVEL_HIT")
                    signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=d_price, reason="ENTRY_CONFIRMED")
                    events.append({"signal_id": sig.signal_id, "event": "CONFIRMED", "price": float(d_price)})

            # ── 2. TARGET & STOP LOSS MONITORING ──
            elif st in ("CONFIRMED", "TARGET_1_HIT"):
                if direction == "LONG_CALL":
                    # Check Target 2 Hit (Highest Priority Win)
                    if d_price >= sig.target_2:
                        signal_fsm.transition(sig.signal_id, "TARGET_2_HIT", market_price=d_price, reason="TARGET_2_ACHIEVED")
                        events.append({"signal_id": sig.signal_id, "event": "TARGET_2_HIT", "price": float(d_price), "rr": sig.risk_reward_t2})
                    # Check Target 1 Hit
                    elif d_price >= sig.target_1 and st != "TARGET_1_HIT":
                        signal_fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=d_price, reason="TARGET_1_ACHIEVED")
                        events.append({"signal_id": sig.signal_id, "event": "TARGET_1_HIT", "price": float(d_price), "rr": sig.risk_reward_t1})
                    # Check Stop Loss Hit
                    elif d_price <= sig.stop_loss:
                        signal_fsm.transition(sig.signal_id, "STOP_LOSS_HIT", market_price=d_price, reason="STOP_LOSS_TOUCHED")
                        events.append({"signal_id": sig.signal_id, "event": "STOP_LOSS_HIT", "price": float(d_price), "rr": -1.0})

                elif direction == "LONG_PUT":
                    if d_price <= sig.target_2:
                        signal_fsm.transition(sig.signal_id, "TARGET_2_HIT", market_price=d_price, reason="TARGET_2_ACHIEVED")
                        events.append({"signal_id": sig.signal_id, "event": "TARGET_2_HIT", "price": float(d_price), "rr": sig.risk_reward_t2})
                    elif d_price <= sig.target_1 and st != "TARGET_1_HIT":
                        signal_fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=d_price, reason="TARGET_1_ACHIEVED")
                        events.append({"signal_id": sig.signal_id, "event": "TARGET_1_HIT", "price": float(d_price), "rr": sig.risk_reward_t1})
                    elif d_price >= sig.stop_loss:
                        signal_fsm.transition(sig.signal_id, "STOP_LOSS_HIT", market_price=d_price, reason="STOP_LOSS_TOUCHED")
                        events.append({"signal_id": sig.signal_id, "event": "STOP_LOSS_HIT", "price": float(d_price), "rr": -1.0})

        return events

    def get_performance_metrics(self) -> PerformanceMetrics:
        """Calculate complete historical performance attribution."""
        all_signals = list(signal_fsm._signals.values())
        total = len(all_signals)
        active_ct = sum(1 for s in all_signals if s.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED"))
        
        t1_hits = sum(1 for s in all_signals if s.fsm_state == "TARGET_1_HIT" or s.outcome_status == "WIN_T1")
        t2_hits = sum(1 for s in all_signals if s.fsm_state == "TARGET_2_HIT" or s.outcome_status == "WIN_T2")
        sl_hits = sum(1 for s in all_signals if s.fsm_state == "STOP_LOSS_HIT" or s.outcome_status == "LOSS_SL")
        expired = sum(1 for s in all_signals if s.fsm_state == "EXPIRED" or s.outcome_status == "EXPIRED")

        completed_trades = (t1_hits + t2_hits) + sl_hits
        wins = t1_hits + t2_hits
        losses = sl_hits

        win_rate = (wins / completed_trades * 100.0) if completed_trades > 0 else 0.0

        # Profit Factor & R:R
        gross_profit_r = (t1_hits * 1.5) + (t2_hits * 3.0)
        gross_loss_r = losses * 1.0
        profit_factor = (gross_profit_r / gross_loss_r) if gross_loss_r > 0 else (gross_profit_r if gross_profit_r > 0 else 1.0)
        expectancy = ((win_rate / 100.0 * 2.0) - ((1.0 - (win_rate / 100.0)) * 1.0)) if completed_trades > 0 else 0.0

        # Strategy breakdown
        strat_breakdown = {}
        for s in all_signals:
            st_name = s.strategy
            entry = strat_breakdown.setdefault(st_name, {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0})
            entry["total"] += 1
            if s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT") or s.outcome_status in ("WIN_T1", "WIN_T2"):
                entry["wins"] += 1
            elif s.fsm_state == "STOP_LOSS_HIT" or s.outcome_status == "LOSS_SL":
                entry["losses"] += 1
            entry["win_rate"] = round((entry["wins"] / (entry["wins"] + entry["losses"]) * 100.0), 1) if (entry["wins"] + entry["losses"]) > 0 else 0.0

        # Underlying breakdown
        under_breakdown = {}
        for s in all_signals:
            u_name = s.underlying
            entry = under_breakdown.setdefault(u_name, {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0})
            entry["total"] += 1
            if s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT") or s.outcome_status in ("WIN_T1", "WIN_T2"):
                entry["wins"] += 1
            elif s.fsm_state == "STOP_LOSS_HIT" or s.outcome_status == "LOSS_SL":
                entry["losses"] += 1
            entry["win_rate"] = round((entry["wins"] / (entry["wins"] + entry["losses"]) * 100.0), 1) if (entry["wins"] + entry["losses"]) > 0 else 0.0

        return PerformanceMetrics(
            total_signals=total,
            active_signals=active_ct,
            completed_signals=completed_trades,
            winning_signals=wins,
            losing_signals=losses,
            expired_signals=expired,
            win_rate_pct=round(win_rate, 1),
            profit_factor=round(profit_factor, 2),
            average_rr=2.25 if wins > 0 else 0.0,
            expectancy_r=round(expectancy, 2),
            target_1_hits=t1_hits,
            target_2_hits=t2_hits,
            stop_loss_hits=sl_hits,
            strategy_breakdown=strat_breakdown,
            underlying_breakdown=under_breakdown,
        )


outcome_tracker = SignalOutcomeTracker()
