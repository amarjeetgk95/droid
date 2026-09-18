"""Historical performance attribution for signal outcomes.

Holds :class:`PerformanceMetrics` and the metrics engine extracted from
:class:`SignalOutcomeTracker`; re-exported from :mod:`outcome_tracker` so
existing imports keep working.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from app.signals.fsm import signal_fsm, SignalInstance


class PerformanceMetrics(BaseModel):
    total_signals: int = 0
    active_signals: int = 0
    completed_signals: int = 0
    winning_signals: int = 0
    losing_signals: int = 0
    expired_signals: int = 0
    throttled_signals_total: int = 0

    win_rate_pct: float = 0.0
    confirmation_rate_pct: float = 0.0
    expiry_rate_pct: float = 0.0
    profit_factor: float = 0.0
    average_rr: float = 0.0
    expectancy_r: float = 0.0
    realized_rr_gross_sum: float = 0.0
    realized_rr_net_sum: float = 0.0

    target_1_hits: int = 0
    target_2_hits: int = 0
    stop_loss_hits: int = 0
    time_stop_hits: int = 0
    runner_time_stop_hits: int = 0
    full_wins: int = 0
    partial_wins: int = 0
    breakeven_hits: int = 0

    strategy_breakdown: dict[str, dict] = Field(default_factory=dict)
    underlying_breakdown: dict[str, dict] = Field(default_factory=dict)
    scalp_summary: dict = Field(default_factory=dict)
    intraday_summary: dict = Field(default_factory=dict)
    calibration_buckets: dict[str, dict] = Field(default_factory=dict)
    audit_summary: Optional[dict] = None


class OutcomeMetricsMixin:
    """``get_performance_metrics``: historical performance attribution (§31)."""

    def get_performance_metrics(self) -> PerformanceMetrics:
        """Calculate complete historical performance attribution split across Desks (§31)."""
        demo_ids = {"SIG-NIFTY-BKO-01", "SIG-BNF-TRP-02", "SIG-SNX-MRV-03", "SIG-NIFTY-ORB-04"}
        all_signals = [
            s for s in signal_fsm._signals.values()
            if not str(s.signal_id).lower().startswith(("sig-test-", "sig-wallet-", "test-", "sig-persist-sanitize"))
            and s.signal_id not in demo_ids
        ]
        total = len(all_signals)
        active_ct = sum(1 for s in all_signals if s.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED", "TARGET_1_HIT"))

        t1_hits = sum(1 for s in all_signals if s.fsm_state == "TARGET_1_HIT" or s.outcome_status == "WIN_T1")
        t2_hits = sum(1 for s in all_signals if s.fsm_state == "TARGET_2_HIT" or s.outcome_status == "WIN_T2")
        sl_hits = sum(1 for s in all_signals if s.fsm_state == "STOP_LOSS_HIT" or s.outcome_status == "LOSS_SL")

        # Distinct runner time stops (partial wins, locked in T1) vs pure time stops (timed out with no profit)
        runner_time_stops = sum(
            1 for s in all_signals
            if s.fsm_state == "RUNNER_TIME_STOP_HIT" or s.outcome_status == "RUNNER_TIME_STOP" or getattr(s, "terminal_outcome", None) == "PARTIAL_WIN"
        )
        pure_time_stops = sum(
            1 for s in all_signals
            if (s.fsm_state == "TIME_STOP_HIT" or s.outcome_status == "TIME_STOP" or getattr(s, "terminal_outcome", None) == "TIME_STOP_LOSS")
            and not (s.fsm_state == "RUNNER_TIME_STOP_HIT" or s.outcome_status == "RUNNER_TIME_STOP")
        )
        time_stops = pure_time_stops + runner_time_stops
        expired = sum(1 for s in all_signals if s.fsm_state == "EXPIRED" or s.outcome_status == "EXPIRED")

        completed_trades = (t1_hits + t2_hits) + sl_hits + time_stops
        # Runner time stops are partial wins (+1.5R secured at T1)
        wins = t1_hits + t2_hits + runner_time_stops
        # Only pure time stops and SL hits are losses
        losses = sl_hits + pure_time_stops

        win_rate = (wins / completed_trades * 100.0) if completed_trades > 0 else 0.0
        confirmation_rate = (completed_trades / total * 100.0) if total > 0 else 0.0
        expiry_rate = (expired / total * 100.0) if total > 0 else 0.0

        # Completed trades list for empirical metrics (§6)
        completed_signals_list = [
            s for s in all_signals
            if s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT")
            or s.outcome_status in ("WIN_T1", "WIN_T2", "LOSS_SL", "TIME_STOP", "RUNNER_TIME_STOP")
            or getattr(s, "terminal_outcome", None) in ("FULL_WIN", "PARTIAL_WIN", "STOP_LOSS_HIT", "TIME_STOP_LOSS", "BREAKEVEN")
        ]

        def _signal_is_win(s: SignalInstance) -> bool:
            return (
                s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT", "RUNNER_TIME_STOP_HIT")
                or s.outcome_status in ("WIN_T1", "WIN_T2", "RUNNER_TIME_STOP")
                or getattr(s, "terminal_outcome", None) in ("FULL_WIN", "PARTIAL_WIN")
            )

        # Empirical Average Win R (average_rr)
        win_r_list: list[float] = []
        for s in completed_signals_list:
            if _signal_is_win(s):
                r_val = getattr(s, "realized_rr_net", None)
                if r_val is None:
                    r_val = getattr(s, "realized_rr_gross", None)
                if r_val is None:
                    r_val = s.realized_rr
                if r_val is not None:
                    win_r_list.append(float(r_val))
                else:
                    target_ref = s.risk_reward_t2 if (s.fsm_state == "TARGET_2_HIT" or s.outcome_status == "WIN_T2") else s.risk_reward_t1
                    win_r_list.append(float(target_ref or 1.5))

        empirical_average_rr = (sum(win_r_list) / len(win_r_list)) if win_r_list else 0.0

        # Empirical Expectancy & Profit Factor based on realized net R
        all_completed_net_r: list[float] = []
        gross_profit_r = 0.0
        gross_loss_r = 0.0

        for s in completed_signals_list:
            net_r = getattr(s, "realized_rr_net", None)
            if net_r is None:
                net_r = getattr(s, "realized_rr_gross", None)
            if net_r is None:
                net_r = s.realized_rr
            if net_r is None:
                if _signal_is_win(s):
                    target_ref = s.risk_reward_t2 if (s.fsm_state == "TARGET_2_HIT" or s.outcome_status == "WIN_T2") else s.risk_reward_t1
                    net_r = float(target_ref or 1.5)
                else:
                    net_r = -1.0

            val = float(net_r)
            all_completed_net_r.append(val)
            if val > 0:
                gross_profit_r += val
            elif val < 0:
                gross_loss_r += abs(val)

        profit_factor = (gross_profit_r / gross_loss_r) if gross_loss_r > 0 else (gross_profit_r if gross_profit_r > 0 else 1.0)
        empirical_expectancy = (sum(all_completed_net_r) / len(all_completed_net_r)) if all_completed_net_r else 0.0

        # Net Realized R Sum (Reconciliation Invariant)
        def _get_signal_net_r(s: SignalInstance) -> float:
            net_r = getattr(s, "realized_rr_net", None)
            if net_r is None:
                net_r = getattr(s, "realized_rr_gross", None)
            if net_r is None:
                net_r = s.realized_rr
            if net_r is None:
                if _signal_is_win(s):
                    target_ref = s.risk_reward_t2 if (s.fsm_state == "TARGET_2_HIT" or s.outcome_status == "WIN_T2") else s.risk_reward_t1
                    net_r = float(target_ref or 1.5)
                else:
                    net_r = -1.0 if (s.fsm_state == "STOP_LOSS_HIT" or s.outcome_status == "LOSS_SL") else 0.0
            return float(net_r)

        def _get_signal_gross_r(s: SignalInstance) -> float:
            gross_r = getattr(s, "realized_rr_gross", None)
            if gross_r is None:
                gross_r = s.realized_rr
            if gross_r is None:
                if _signal_is_win(s):
                    target_ref = s.risk_reward_t2 if (s.fsm_state == "TARGET_2_HIT" or s.outcome_status == "WIN_T2") else s.risk_reward_t1
                    gross_r = float(target_ref or 1.5)
                else:
                    gross_r = -1.0 if (s.fsm_state == "STOP_LOSS_HIT" or s.outcome_status == "LOSS_SL") else 0.0
            return float(gross_r)

        net_r_sum = sum(_get_signal_net_r(s) for s in completed_signals_list)
        gross_r_sum = sum(_get_signal_gross_r(s) for s in completed_signals_list)

        full_win_ct = t2_hits
        partial_win_ct = t1_hits + runner_time_stops
        be_ct = sum(1 for s in all_signals if getattr(s, "terminal_outcome", None) == "BREAKEVEN")

        # Desk breakdowns
        def _calc_desk(sub_list: list[SignalInstance]) -> dict:
            sub_total = len(sub_list)
            sub_w = sum(
                1 for s in sub_list
                if s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT", "RUNNER_TIME_STOP_HIT")
                or s.outcome_status in ("WIN_T1", "WIN_T2", "RUNNER_TIME_STOP")
                or getattr(s, "terminal_outcome", None) in ("FULL_WIN", "PARTIAL_WIN")
            )
            sub_l = sum(
                1 for s in sub_list
                if (s.fsm_state in ("STOP_LOSS_HIT", "TIME_STOP_HIT")
                    or s.outcome_status in ("LOSS_SL", "TIME_STOP")
                    or getattr(s, "terminal_outcome", None) in ("STOP_LOSS_HIT", "TIME_STOP_LOSS"))
                and not (s.fsm_state == "RUNNER_TIME_STOP_HIT" or s.outcome_status == "RUNNER_TIME_STOP")
            )
            sub_comp = sub_w + sub_l
            sub_wr = round((sub_w / sub_comp * 100.0), 1) if sub_comp > 0 else 0.0
            return {"total": sub_total, "completed": sub_comp, "wins": sub_w, "losses": sub_l, "win_rate_pct": sub_wr}

        scalp_sigs = [s for s in all_signals if getattr(s, "is_scalp", False)]
        intraday_sigs = [s for s in all_signals if not getattr(s, "is_scalp", False)]

        # Strategy breakdown
        strat_breakdown = {}
        for s in all_signals:
            st_name = s.strategy
            entry = strat_breakdown.setdefault(st_name, {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0})
            entry["total"] += 1
            is_win = (
                s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT", "RUNNER_TIME_STOP_HIT")
                or s.outcome_status in ("WIN_T1", "WIN_T2", "RUNNER_TIME_STOP")
                or getattr(s, "terminal_outcome", None) in ("FULL_WIN", "PARTIAL_WIN")
            )
            is_loss = (
                (s.fsm_state in ("STOP_LOSS_HIT", "TIME_STOP_HIT")
                 or s.outcome_status in ("LOSS_SL", "TIME_STOP")
                 or getattr(s, "terminal_outcome", None) in ("STOP_LOSS_HIT", "TIME_STOP_LOSS"))
                and not is_win
            )
            if is_win:
                entry["wins"] += 1
            elif is_loss:
                entry["losses"] += 1
            entry["win_rate"] = round((entry["wins"] / (entry["wins"] + entry["losses"]) * 100.0), 1) if (entry["wins"] + entry["losses"]) > 0 else 0.0

        # Underlying breakdown
        under_breakdown = {}
        for s in all_signals:
            u_name = s.underlying
            entry = under_breakdown.setdefault(u_name, {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0})
            entry["total"] += 1
            is_win = (
                s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT", "RUNNER_TIME_STOP_HIT")
                or s.outcome_status in ("WIN_T1", "WIN_T2", "RUNNER_TIME_STOP")
                or getattr(s, "terminal_outcome", None) in ("FULL_WIN", "PARTIAL_WIN")
            )
            is_loss = (
                (s.fsm_state in ("STOP_LOSS_HIT", "TIME_STOP_HIT")
                 or s.outcome_status in ("LOSS_SL", "TIME_STOP")
                 or getattr(s, "terminal_outcome", None) in ("STOP_LOSS_HIT", "TIME_STOP_LOSS"))
                and not is_win
            )
            if is_win:
                entry["wins"] += 1
            elif is_loss:
                entry["losses"] += 1
            entry["win_rate"] = round((entry["wins"] / (entry["wins"] + entry["losses"]) * 100.0), 1) if (entry["wins"] + entry["losses"]) > 0 else 0.0

        audit_stats = None
        try:
            from app.signals.audit_ledger import signal_audit_ledger
            audit_stats = signal_audit_ledger.get_summary_metrics()
        except Exception:
            pass

        throttled_total = 0
        try:
            from app.signals.scanner import signal_scanner
            throttled_total = sum(getattr(d, "throttled_signals_count", 0) for d in signal_scanner._last_diagnostics.values())
        except Exception:
            pass

        # Score Calibration Buckets (§45)
        calibration_buckets: dict[str, dict] = {
            "70-75": {"total": 0, "completed": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0, "expectancy_r": 0.0, "net_r_sum": 0.0},
            "75-80": {"total": 0, "completed": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0, "expectancy_r": 0.0, "net_r_sum": 0.0},
            "80-85": {"total": 0, "completed": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0, "expectancy_r": 0.0, "net_r_sum": 0.0},
            "85+":   {"total": 0, "completed": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0, "expectancy_r": 0.0, "net_r_sum": 0.0},
        }
        for s in all_signals:
            sc = float(getattr(s, "confidence", 0.0) or 0.0)
            if sc < 75.0:
                b_key = "70-75"
            elif sc < 80.0:
                b_key = "75-80"
            elif sc < 85.0:
                b_key = "80-85"
            else:
                b_key = "85+"

            b_data = calibration_buckets[b_key]
            b_data["total"] += 1
            if s in completed_signals_list:
                b_data["completed"] += 1
                if _signal_is_win(s):
                    b_data["wins"] += 1
                else:
                    b_data["losses"] += 1
                b_data["net_r_sum"] = round(b_data["net_r_sum"] + _get_signal_net_r(s), 2)

        for b_data in calibration_buckets.values():
            comp = b_data["completed"]
            b_data["win_rate_pct"] = round((b_data["wins"] / comp * 100.0), 1) if comp > 0 else 0.0
            b_data["expectancy_r"] = round((b_data["net_r_sum"] / comp), 2) if comp > 0 else 0.0

        return PerformanceMetrics(
            total_signals=total,
            active_signals=active_ct,
            completed_signals=completed_trades,
            winning_signals=wins,
            losing_signals=losses,
            expired_signals=expired,
            throttled_signals_total=throttled_total,
            win_rate_pct=round(win_rate, 1),
            confirmation_rate_pct=round(confirmation_rate, 1),
            expiry_rate_pct=round(expiry_rate, 1),
            profit_factor=round(profit_factor, 2),
            average_rr=round(empirical_average_rr, 2),
            expectancy_r=round(empirical_expectancy, 2),
            realized_rr_gross_sum=round(gross_r_sum, 2),
            realized_rr_net_sum=round(net_r_sum, 2),
            target_1_hits=t1_hits,
            target_2_hits=t2_hits,
            stop_loss_hits=sl_hits,
            time_stop_hits=pure_time_stops,
            runner_time_stop_hits=runner_time_stops,
            full_wins=full_win_ct,
            partial_wins=partial_win_ct,
            breakeven_hits=be_ct,
            strategy_breakdown=strat_breakdown,
            underlying_breakdown=under_breakdown,
            scalp_summary=_calc_desk(scalp_sigs),
            intraday_summary=_calc_desk(intraday_sigs),
            calibration_buckets=calibration_buckets,
            audit_summary=audit_stats,
        )
