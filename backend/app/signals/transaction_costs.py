"""
Transaction Cost Architecture & Statutory Indian F&O Friction Engine
Single source of truth for round-trip execution costs, slippage, and net R:R metrics.

P1: canonical schedule shared by friction_gate + path_simulator (one imported
constant). Risk is normalized on the OPTION PREMIUM stop (entry_p - stop_p),
never on a spot-point diff. EXPIRED_ITM models assignment (intrinsic exit +
assignment STT). Mark age / spread are surfaced so callers can fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


# ── Single canonical schedule ──────────────────────────────────────────
# friction_gate and path_simulator MUST import these (no local copies).
# STT: 0.10% on option sell-side premium turnover (sell leg only).
UNIFIED_STT_SELL_RATE: float = 0.001
UNIFIED_EXCHANGE_TXN_RATE: float = 0.0005
UNIFIED_GST_RATE: float = 0.18
UNIFIED_SEBI_RATE: float = 0.000001
UNIFIED_STAMP_BUY_RATE: float = 0.00003
# Assignment / exercise: STT on intrinsic turnover when an ITM long expires.
UNIFIED_STT_EXERCISE_RATE: float = 0.00125


@dataclass(frozen=True)
class IndianFNOCostSchedule:
    brokerage_per_side: float = 20.0
    stt_sell_pct: float = UNIFIED_STT_SELL_RATE
    exchange_txn_pct: float = UNIFIED_EXCHANGE_TXN_RATE
    gst_pct: float = UNIFIED_GST_RATE
    sebi_pct: float = UNIFIED_SEBI_RATE
    stamp_pct: float = UNIFIED_STAMP_BUY_RATE
    # Exercise / assignment STT applied on intrinsic value at expiry.
    stt_exercise_pct: float = UNIFIED_STT_EXERCISE_RATE
    slippage_floor: float = 0.5
    slippage_pct: float = 0.005
    version: str = "2026.09"


DEFAULT_COST_SCHEDULE = IndianFNOCostSchedule()
# Canonical alias — import this everywhere instead of re-declaring rates.
UNIFIED_COST_SCHEDULE = DEFAULT_COST_SCHEDULE

# In-memory sizing and lifecycle limits (previously magic numbers)
FSM_MAX_SIGNALS_IN_MEMORY: int = 200
FSM_MAX_AUDIT_LOG_ENTRIES: int = 1000
DEFAULT_SIGNAL_TTL_MS: int = 300_000

# Viability constants shared with path_simulator / friction_gate / selector.
MIN_NET_RR: float = 1.2
MAX_COST_TO_TARGET_RATIO: float = 0.30
MAX_SPREAD_PCT_OF_PREMIUM: float = 2.5


def resolve_premium_risk_points(
    sig: Any,
    entry_premium: float,
    fallback_spot_risk_pts: float | None = None,
) -> float:
    """Premium-domain risk per share: entry_p - option stop premium.

    Prefers an explicit premium stop carried on the signal
    (``option_stop_premium``); then a delta-gamma projection off the spot
    stop; only as a last resort falls back to the caller-supplied spot risk
    (already converted). Never returns <= 0.
    """
    try:
        stop_p = getattr(sig, "option_stop_premium", None)
        if stop_p is not None and float(stop_p) > 0 and entry_premium > 0:
            risk = float(entry_premium) - float(stop_p)
            if risk > 0:
                return risk
    except Exception:
        pass
    # Delta-gamma projection: risk = |delta|*spot_risk - 0.5*gamma*spot_risk^2
    try:
        greeks = getattr(sig, "greeks", None) or {}
        if isinstance(greeks, dict) and fallback_spot_risk_pts and fallback_spot_risk_pts > 0:
            d = abs(float(greeks.get("delta", 0) or 0))
            g = float(greeks.get("gamma", 0) or 0)
            if d >= 0.05:
                proj = d * float(fallback_spot_risk_pts) - 0.5 * max(0.0, g) * float(fallback_spot_risk_pts) ** 2
                # Floor at half the linear term so convexity never zeroes risk.
                floor = 0.5 * d * float(fallback_spot_risk_pts)
                proj = max(floor, proj)
                # Cap at 90% of entry premium (premium stop can't go negative).
                if entry_premium > 0:
                    proj = min(proj, entry_premium * 0.90)
                if proj > 0:
                    return float(proj)
    except Exception:
        pass
    if fallback_spot_risk_pts and fallback_spot_risk_pts > 0:
        return float(fallback_spot_risk_pts)
    return max(1.0, entry_premium * 0.35 if entry_premium > 0 else 20.0)


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
    STT: unified sell-side rate on sell turnover (see UNIFIED_STT_SELL_RATE)
    Exchange txn: unified rate on total turnover
    GST: 18% on (brokerage + exchange txn)
    SEBI & Stamp duty: canonical micro rates
    Slippage model: max(floor, slippage_pct of combined entry + exit premium)
    Returns (friction_in_r, breakdown_dict).

    NOTE: ``risk_points_premium`` MUST be in the premium domain
    (entry_p - option stop_p). Callers passing a spot-point diff overstate
    or understate R. Use :func:`resolve_premium_risk_points`.
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
    # Premium-domain risk: never let a spot-scale number leak in here.
    risk_inr = max(100.0, float(risk_points_premium) * qty)
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
        "risk_points_premium": round(float(risk_points_premium), 2),
        "risk_inr": round(risk_inr, 2),
        "schedule_version": schedule.version,
        "stt_rate": schedule.stt_sell_pct,
    }
    return round(friction_r, 4), breakdown


def compute_expiry_assignment_friction(
    intrinsic_per_share: float,
    lots: int = 1,
    lot_size: int = 75,
    schedule: IndianFNOCostSchedule = DEFAULT_COST_SCHEDULE,
) -> tuple[float, dict[str, Any]]:
    """Friction for an ITM long held to expiry (assignment / exercise).

    Exit is intrinsic value; STT applies at the exercise rate on intrinsic
    turnover plus exchange/SEBI micro-charges. No exit brokerage beyond the
    standard two-leg assumption is modelled separately — the caller already
    paid entry brokerage inside the round trip.
    """
    lots = max(1, lots)
    lot_size = max(1, lot_size)
    qty = lots * lot_size
    intrinsic_per_share = max(0.0, float(intrinsic_per_share or 0.0))
    turnover = intrinsic_per_share * qty
    stt = schedule.stt_exercise_pct * turnover
    txn = schedule.exchange_txn_pct * turnover
    sebi = schedule.sebi_pct * turnover
    gst = schedule.gst_pct * txn
    total = round(stt + txn + sebi + gst, 2)
    return total, {
        "intrinsic_per_share": round(intrinsic_per_share, 2),
        "quantity": qty,
        "assignment_stt_inr": round(stt, 2),
        "exchange_inr": round(txn, 2),
        "sebi_inr": round(sebi, 2),
        "gst_inr": round(gst, 2),
        "total_assignment_friction_inr": total,
        "stt_exercise_rate": schedule.stt_exercise_pct,
    }


def resolve_realized_exit_premium(sig: Any, market_price: Decimal | None) -> float | None:
    """Exit premium in the option domain for friction math — REAL marks only.

    Transitions receive underlying SPOT ticks, but entry fills are option
    PREMIUMS. Two earlier behaviours were both wrong: re-deriving the premium
    with Black-76 fabricated a model exit, and simply passing the spot tick
    through computed friction against an index level (a T1 win showed -7.28R).

    Fail-closed: an option signal with no live chain mark yields ``None`` so the
    caller reports *no* net-R rather than a meaningless one. Non-option signals
    price off the tick itself, where entry and exit share a domain.
    """
    opt = getattr(sig, "option_contract", None) or {}
    direction_str = str(getattr(sig, "direction", ""))
    is_option = bool(opt) or "CALL" in direction_str or "PUT" in direction_str

    if is_option:
        sym = str(opt.get("broker_symbol") or "").strip() if isinstance(opt, dict) else str(getattr(opt, "broker_symbol", "") or "").strip()
        if not sym:
            return None
        try:
            from app.signals.option_marks import option_mark_registry

            mark = option_mark_registry.get_usable(sym, allow_model=False)
            if mark is not None and mark.price is not None and mark.price > 0:
                return float(mark.price)
        except Exception:
            return None
        return None

    if market_price is None:
        return None
    try:
        return float(market_price)
    except Exception:
        return None


#: Backward-compat alias — the Black-76 estimator was removed. Fail-closed only.
estimate_exit_premium = resolve_realized_exit_premium


def resolve_exit_mark_meta(sig: Any) -> dict[str, Any]:
    """Surface exit-mark age / spread for audit (fail-closed transparency)."""
    meta: dict[str, Any] = {"exit_source": None, "mark_age_ms": None, "spread_pts": None, "spread_pct": None}
    try:
        opt = getattr(sig, "option_contract", None) or {}
        sym = str(opt.get("broker_symbol") or "").strip() if isinstance(opt, dict) else str(getattr(opt, "broker_symbol", "") or "").strip()
        if not sym:
            return meta
        from app.signals.option_marks import option_mark_registry

        mark = option_mark_registry.get(sym)
        if mark is None:
            return meta
        meta["exit_source"] = getattr(mark, "source", None)
        try:
            meta["mark_age_ms"] = int(mark.age_ms())
        except Exception:
            pass
        try:
            meta["spread_pts"] = mark.spread_pts if hasattr(mark, "spread_pts") else None
            meta["spread_pct"] = mark.spread_pct if hasattr(mark, "spread_pct") else None
        except Exception:
            pass
    except Exception:
        pass
    return meta


def resolve_contract_lot_size(sig: Any) -> int:
    """Real lot size for the signal's contract.

    `compute_option_friction_r` defaults to 65, which is no instrument's lot
    size, so friction was normalized on the wrong quantity for NIFTY (75),
    BANKNIFTY (30) and SENSEX (10).
    """
    opt = getattr(sig, "option_contract", None) or {}
    try:
        lot = int(opt.get("lot_size") if isinstance(opt, dict) else getattr(opt, "lot_size", 0))
        if lot > 0:
            return lot
    except Exception:
        pass
    underlying = str(getattr(sig, "underlying", "") or "").upper()
    if underlying == "BANKNIFTY":
        return 30
    if underlying == "SENSEX":
        return 10
    if underlying == "NIFTY":
        return 75
    # Authoritative fallback via contract configs (never the stale 65/20).
    try:
        from app.signals.contract_resolver import INDEX_CONTRACT_CONFIGS

        cfg = INDEX_CONTRACT_CONFIGS.get(underlying)
        if cfg and int(cfg.get("lot_size", 0)) > 0:
            return int(cfg["lot_size"])
    except Exception:
        pass
    return 75


def resolve_lot_size_for_underlying(underlying: str) -> int:
    """Lot size without a signal object (risk_engine / selector path)."""
    u = str(underlying or "").upper()
    try:
        from app.signals.contract_resolver import INDEX_CONTRACT_CONFIGS

        cfg = INDEX_CONTRACT_CONFIGS.get(u)
        if cfg and int(cfg.get("lot_size", 0)) > 0:
            return int(cfg["lot_size"])
    except Exception:
        pass
    if u == "BANKNIFTY":
        return 30
    if u == "SENSEX":
        return 10
    return 75


def _resolve_intrinsic_at_expiry(sig: Any, market_price: Decimal | None) -> float | None:
    """Intrinsic value for an expired long option, else None."""
    try:
        opt = getattr(sig, "option_contract", None) or {}
        if isinstance(opt, dict):
            strike = float(opt.get("strike") or 0)
            otype = str(opt.get("option_type") or "").upper()
        else:
            strike = float(getattr(opt, "strike", 0) or 0)
            otype = str(getattr(opt, "option_type", "") or "").upper()
        if strike <= 0 or otype not in ("CE", "PE"):
            return None
        spot = float(market_price) if market_price is not None else float(getattr(sig, "spot_price", 0) or 0)
        if spot <= 0:
            return None
        if otype == "CE":
            return max(0.0, spot - strike)
        return max(0.0, strike - spot)
    except Exception:
        return None


def _record_friction_r(
    sig: Any,
    res: dict[str, Any],
    gross_r: float,
    market_price: Decimal | None,
    schedule: IndianFNOCostSchedule,
    spot_fallback: float | None = None,
) -> None:
    """Write realized_rr_net / cost_breakdown_r, or leave them unset.

    Shared by every terminal branch so the fail-closed rule lives in exactly
    one place: no real exit price means no net-R, never a substituted one.
    Risk is premium-domain (entry_p - premium stop), never a spot diff.
    """
    exit_p = resolve_realized_exit_premium(
        sig, market_price if market_price is not None else spot_fallback
    )
    meta = resolve_exit_mark_meta(sig)
    if exit_p is None or exit_p <= 0:
        res["realized_rr_net"] = None
        res["cost_breakdown_r"] = None
        return

    entry_p = float(sig.actual_fill_price or sig.trigger or 100.0)
    try:
        spot_risk = float(abs((sig.trigger or Decimal(100)) - (sig.stop_loss or Decimal(80))))
    except Exception:
        spot_risk = 25.0
    risk_pts_premium = resolve_premium_risk_points(sig, entry_p, spot_risk)
    f_r, bdown = compute_option_friction_r(
        entry_p,
        exit_p,
        lots=sig.lots or 1,
        lot_size=resolve_contract_lot_size(sig),
        risk_points_premium=risk_pts_premium,
        schedule=schedule,
    )
    bdown.update(meta)
    res["realized_rr_net"] = round(gross_r - f_r, 4)
    res["cost_breakdown_r"] = bdown


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
        _record_friction_r(sig, res, gross_r, market_price, schedule, spot_fallback=float(sig.target_1 or 150.0))

    elif to_state == "TARGET_2_HIT":
        res["t2_hit"] = True
        res["outcome_status"] = "WIN_T2"
        res["terminal_outcome"] = "FULL_WIN"
        gross_r = float(sig.risk_reward_t2)
        res["realized_rr"] = gross_r
        res["realized_rr_gross"] = gross_r
        _record_friction_r(sig, res, gross_r, market_price, schedule, spot_fallback=float(sig.target_2 or 200.0))

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
        _record_friction_r(sig, res, gross_r, market_price, schedule, spot_fallback=float(sig.stop_loss or 80.0))

    elif to_state == "TIME_STOP_HIT":
        res["outcome_status"] = "TIME_STOP"
        res["terminal_outcome"] = "TIME_STOP_LOSS"
        gross_r = 0.0
        res["realized_rr"] = gross_r
        res["realized_rr_gross"] = gross_r
        _record_friction_r(sig, res, gross_r, market_price, schedule)

    elif to_state == "RUNNER_TIME_STOP_HIT":
        res["outcome_status"] = "RUNNER_TIME_STOP"
        res["terminal_outcome"] = "PARTIAL_WIN"
        gross_r = float(sig.risk_reward_t1)
        res["realized_rr"] = gross_r
        res["realized_rr_gross"] = gross_r
        _record_friction_r(sig, res, gross_r, market_price, schedule, spot_fallback=float(sig.target_1 or 150.0))

    elif to_state in ("EXPIRED_ITM", "ASSIGNED", "EXPIRED"):
        # Assignment branch: ITM long held to expiry exits at intrinsic with
        # exercise STT. OTM expiry is worthless (full premium loss, no STT).
        intrinsic = _resolve_intrinsic_at_expiry(sig, market_price)
        entry_p = float(getattr(sig, "actual_fill_price", None) or getattr(sig, "trigger", None) or 100.0)
        try:
            spot_risk = float(abs((sig.trigger or Decimal(100)) - (sig.stop_loss or Decimal(80))))
        except Exception:
            spot_risk = 25.0
        risk_pts_premium = resolve_premium_risk_points(sig, entry_p, spot_risk)
        lots = int(getattr(sig, "lots", None) or 1)
        lot_size = resolve_contract_lot_size(sig)
        qty = max(1, lots * lot_size)
        risk_inr = max(100.0, risk_pts_premium * qty)
        if intrinsic is None:
            res["outcome_status"] = "EXPIRED"
            res["terminal_outcome"] = "EXPIRED"
            res["realized_rr"] = None
            res["realized_rr_gross"] = None
            res["realized_rr_net"] = None
            res["cost_breakdown_r"] = None
        elif intrinsic <= 0:
            # OTM expiry: premium goes to zero, no assignment STT.
            gross_r = -(entry_p / risk_pts_premium) if risk_pts_premium > 0 else -1.0
            assign_total, assign_bdown = compute_expiry_assignment_friction(0.0, lots, lot_size, schedule)
            friction_r = assign_total / risk_inr if risk_inr > 0 else 0.0
            res["outcome_status"] = "EXPIRED_OTM"
            res["terminal_outcome"] = "EXPIRED"
            res["intrinsic_per_share"] = 0.0
            res["realized_rr"] = round(gross_r, 4)
            res["realized_rr_gross"] = round(gross_r, 4)
            res["realized_rr_net"] = round(gross_r - friction_r, 4)
            res["cost_breakdown_r"] = {**assign_bdown, "friction_r": round(friction_r, 4), **resolve_exit_mark_meta(sig)}
        else:
            gross_pnl = (intrinsic - entry_p) * qty
            gross_r = gross_pnl / risk_inr if risk_inr > 0 else 0.0
            assign_total, assign_bdown = compute_expiry_assignment_friction(intrinsic, lots, lot_size, schedule)
            friction_r = assign_total / risk_inr if risk_inr > 0 else 0.0
            res["outcome_status"] = "EXPIRED_ITM"
            res["terminal_outcome"] = "ASSIGNED"
            res["intrinsic_per_share"] = round(intrinsic, 2)
            res["realized_rr"] = round(gross_r, 4)
            res["realized_rr_gross"] = round(gross_r, 4)
            res["realized_rr_net"] = round(gross_r - friction_r, 4)
            res["cost_breakdown_r"] = {**assign_bdown, "friction_r": round(friction_r, 4), **resolve_exit_mark_meta(sig)}

    elif to_state == "INVALIDATED":
        res["outcome_status"] = "INVALIDATED"
        res["terminal_outcome"] = "INVALIDATED"

    return res
