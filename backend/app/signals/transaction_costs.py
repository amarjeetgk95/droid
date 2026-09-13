"""
Transaction Cost Architecture & Statutory Indian F&O Friction Engine
Single source of truth for round-trip execution costs, slippage, and net R:R metrics.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class IndianFNOCostSchedule:
    brokerage_per_side: float = 20.0
    stt_sell_pct: float = 0.001
    exchange_txn_pct: float = 0.0005
    gst_pct: float = 0.18
    sebi_pct: float = 0.00003
    stamp_pct: float = 0.000001
    slippage_floor: float = 0.5
    slippage_pct: float = 0.005
    version: str = "2026.09"


DEFAULT_COST_SCHEDULE = IndianFNOCostSchedule()

# In-memory sizing and lifecycle limits (previously magic numbers)
FSM_MAX_SIGNALS_IN_MEMORY: int = 200
FSM_MAX_AUDIT_LOG_ENTRIES: int = 1000
DEFAULT_SIGNAL_TTL_MS: int = 300_000


def compute_option_friction_r(
    entry_premium: float,
    exit_premium: float,
    lots: int = 1,
    lot_size: int = 65,
    risk_points_premium: float = 20.0,
    schedule: IndianFNOCostSchedule = DEFAULT_COST_SCHEDULE,
) -> tuple[float, dict[str, Any]]:
    """
    Computes total round-trip transaction costs + slippage normalized to 1R for Indian Index Options.
    Brokerage: Rs 20 entry + Rs 20 exit
    STT: 0.1% on sell side turnover
    Exchange txn: 0.05% on total turnover
    GST: 18% on (brokerage + exchange txn)
    SEBI & Stamp duty: ~0.003%
    Slippage model: 0.5% of combined entry + exit premium
    Returns (friction_in_r, breakdown_dict).
    """
    lots = max(1, lots)
    lot_size = max(1, lot_size)
    qty = lots * lot_size
    turnover_entry = entry_premium * qty
    turnover_exit = exit_premium * qty

    brokerage = schedule.brokerage_per_side * 2.0
    stt = schedule.stt_sell_pct * turnover_exit
    txn_charges = schedule.exchange_txn_pct * (turnover_entry + turnover_exit)
    gst = schedule.gst_pct * (brokerage + txn_charges)
    sebi_stamp = (schedule.sebi_pct * turnover_entry) + (schedule.stamp_pct * (turnover_entry + turnover_exit))
    slippage_pts = max(schedule.slippage_floor, (entry_premium + exit_premium) * schedule.slippage_pct)
    slippage_cost = slippage_pts * qty

    total_cost_inr = brokerage + stt + txn_charges + gst + sebi_stamp + slippage_cost
    risk_inr = max(100.0, risk_points_premium * qty)
    friction_r = total_cost_inr / risk_inr

    breakdown = {
        "brokerage_inr": round(brokerage, 2),
        "stt_inr": round(stt, 2),
        "txn_charges_inr": round(txn_charges, 2),
        "gst_inr": round(gst, 2),
        "sebi_stamp_inr": round(sebi_stamp, 2),
        "slippage_cost_inr": round(slippage_cost, 2),
        "total_friction_inr": round(total_cost_inr, 2),
        "friction_r": round(friction_r, 4),
    }
    return round(friction_r, 4), breakdown


def estimate_exit_premium(sig: Any, market_price: Decimal | None, fallback_default: float | None = None) -> float:
    """
    Exit premium in the option domain for friction math.
    Transitions receive underlying SPOT ticks, but entry fills are option
    PREMIUMS. Estimate the exit premium via Black76 when the signal owns an
    option contract; otherwise fall back to the raw tick or fallback_default.
    """
    try:
        opt = getattr(sig, "option_contract", None) or {}
        strike = opt.get("strike")
        direction_str = str(getattr(sig, "direction", ""))
        if strike and ("CALL" in direction_str or "PUT" in direction_str):
            from app.signals.fill_reconciler import option_fill_reconciler
            otype = str(opt.get("option_type") or ("CE" if "CALL" in direction_str else "PE"))
            try:
                dte = float(opt.get("dte", 3.0) or 3.0)
            except Exception:
                dte = 3.0
            try:
                spot = float(market_price if market_price is not None else (getattr(sig, "trigger", None) or 0.0))
            except Exception:
                spot = 0.0
            if spot > 0 and float(strike) > 0:
                return float(
                    option_fill_reconciler.estimate_option_premium(
                        spot=spot, strike=float(strike), option_type=otype, dte_days=dte
                    )
                )
    except Exception:
        pass
    if market_price is not None:
        try:
            return float(market_price)
        except Exception:
            pass
    if fallback_default is not None:
        return float(fallback_default)
    try:
        return float(market_price or 0.0)
    except Exception:
        return 0.0


def compute_terminal_outcome(
    to_state: str,
    sig: Any,
    market_price: Decimal | None,
    schedule: IndianFNOCostSchedule = DEFAULT_COST_SCHEDULE,
) -> dict[str, Any]:
    """
    Calculates realized gross and net RR, friction cost breakdown,
    and terminal outcome fields for any terminal or milestone exit state.
    Eliminates the copy-pasted blocks in transition().
    """
    res: dict[str, Any] = {
        "exit_price": market_price,
    }

    if to_state == "TARGET_1_HIT":
        res["t1_hit"] = True
        res["outcome_status"] = "WIN_T1"
        res["terminal_outcome"] = "PARTIAL_WIN"
        gross_r = float(sig.risk_reward_t1)
        res["realized_rr"] = gross_r
        res["realized_rr_gross"] = gross_r
        entry_p = float(sig.actual_fill_price or sig.trigger or 100.0)
        exit_p = estimate_exit_premium(sig, market_price or sig.target_1 or 150.0)
        risk_pts = float(abs((sig.trigger or Decimal(100)) - (sig.stop_loss or Decimal(80))))
        f_r, bdown = compute_option_friction_r(
            entry_p, exit_p, lots=sig.lots or 1, risk_points_premium=risk_pts, schedule=schedule
        )
        res["realized_rr_net"] = round(gross_r - f_r, 4)
        res["cost_breakdown_r"] = bdown

    elif to_state == "TARGET_2_HIT":
        res["t2_hit"] = True
        res["outcome_status"] = "WIN_T2"
        res["terminal_outcome"] = "FULL_WIN"
        gross_r = float(sig.risk_reward_t2)
        res["realized_rr"] = gross_r
        res["realized_rr_gross"] = gross_r
        entry_p = float(sig.actual_fill_price or sig.trigger or 100.0)
        exit_p = estimate_exit_premium(sig, market_price or sig.target_2 or 200.0)
        risk_pts = float(abs((sig.trigger or Decimal(100)) - (sig.stop_loss or Decimal(80))))
        f_r, bdown = compute_option_friction_r(
            entry_p, exit_p, lots=sig.lots or 1, risk_points_premium=risk_pts, schedule=schedule
        )
        res["realized_rr_net"] = round(gross_r - f_r, 4)
        res["cost_breakdown_r"] = bdown

    elif to_state == "STOP_LOSS_HIT":
        res["outcome_status"] = "LOSS_SL"
        if getattr(sig, "breakeven_activated", False):
            res["terminal_outcome"] = "BREAKEVEN"
            gross_r = 0.0
        else:
            res["terminal_outcome"] = "STOP_LOSS_HIT"
            gross_r = -1.0
        res["realized_rr"] = gross_r
        res["realized_rr_gross"] = gross_r
        entry_p = float(sig.actual_fill_price or sig.trigger or 100.0)
        exit_p = estimate_exit_premium(sig, market_price or sig.stop_loss or 80.0)
        risk_pts = float(abs((sig.trigger or Decimal(100)) - (sig.stop_loss or Decimal(80))))
        f_r, bdown = compute_option_friction_r(
            entry_p, exit_p, lots=sig.lots or 1, risk_points_premium=risk_pts, schedule=schedule
        )
        res["realized_rr_net"] = round(gross_r - f_r, 4)
        res["cost_breakdown_r"] = bdown

    elif to_state == "TIME_STOP_HIT":
        res["outcome_status"] = "TIME_STOP"
        res["terminal_outcome"] = "TIME_STOP_LOSS"
        gross_r = 0.0
        res["realized_rr"] = gross_r
        res["realized_rr_gross"] = gross_r
        entry_p = float(sig.actual_fill_price or sig.trigger or 100.0)
        exit_p = estimate_exit_premium(sig, market_price) if market_price is not None else float(entry_p)
        risk_pts = float(abs((sig.trigger or Decimal(100)) - (sig.stop_loss or Decimal(80))))
        f_r, bdown = compute_option_friction_r(
            entry_p, exit_p, lots=sig.lots or 1, risk_points_premium=risk_pts, schedule=schedule
        )
        res["realized_rr_net"] = round(gross_r - f_r, 4)
        res["cost_breakdown_r"] = bdown

    elif to_state == "RUNNER_TIME_STOP_HIT":
        res["outcome_status"] = "RUNNER_TIME_STOP"
        res["terminal_outcome"] = "PARTIAL_WIN"
        gross_r = float(sig.risk_reward_t1)
        res["realized_rr"] = gross_r
        res["realized_rr_gross"] = gross_r
        entry_p = float(sig.actual_fill_price or sig.trigger or 100.0)
        exit_p = estimate_exit_premium(sig, market_price or sig.target_1 or 150.0)
        risk_pts = float(abs((sig.trigger or Decimal(100)) - (sig.stop_loss or Decimal(80))))
        f_r, bdown = compute_option_friction_r(
            entry_p, exit_p, lots=sig.lots or 1, risk_points_premium=risk_pts, schedule=schedule
        )
        res["realized_rr_net"] = round(gross_r - f_r, 4)
        res["cost_breakdown_r"] = bdown

    elif to_state == "EXPIRED":
        res["outcome_status"] = "EXPIRED"
        res["terminal_outcome"] = "EXPIRED"

    elif to_state == "INVALIDATED":
        res["outcome_status"] = "INVALIDATED"
        res["terminal_outcome"] = "INVALIDATED"

    return res
