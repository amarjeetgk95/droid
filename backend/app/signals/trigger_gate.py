"""
Trigger integrity gate — rejects no-edge signals whose trigger sits at (or inside) spot.

Root cause it fixes: MEAN_REVERSION and GAMMA_SQUEEZE built
`trigger = spot ± 1 tick (0.05 pts)`, so the signal was born already-triggered:
instant CONFIRMED, zero edge, pure noise. The scanner only checked confluence
score, never trigger geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional


TICK = Decimal("0.05")
# Minimum trigger distance from spot: the larger of 0.05% of spot or 0.10R.
MIN_GAP_PCT = Decimal("0.0005")
MIN_GAP_RISK_FRACTION = Decimal("0.10")
# Minimum risk size: 0.03% of spot (filters dust stops that make R:R meaningless).
MIN_RISK_PCT = Decimal("0.0003")
# Minimum reward bar for a fresh signal.
MIN_RR_T2 = 1.2
# Entry zone wider than 2R means the "setup" is just chop.
MAX_ENTRY_WIDTH_R = Decimal("2.0")


@dataclass
class TriggerCheckResult:
    passed: bool
    reason_code: Optional[str] = None
    message: Optional[str] = None
    metrics: dict[str, Any] = field(default_factory=dict)


def _dec(v: Any) -> Optional[Decimal]:
    try:
        d = Decimal(str(v))
    except Exception:
        return None
    if not d.is_finite():
        return None
    return d


def min_trigger_gap_pts(spot: Decimal, risk_points: Decimal) -> Decimal:
    """Minimum trigger distance from spot for a signal to carry edge."""
    pct_floor = abs(spot) * MIN_GAP_PCT
    risk_floor = abs(risk_points) * MIN_GAP_RISK_FRACTION
    return max(pct_floor, risk_floor, TICK * 2)


def check_trigger_integrity(
    *,
    underlying: str = "?",
    strategy: str = "?",
    direction: str,
    spot_price: Any,
    entry_min: Any,
    entry_max: Any,
    trigger: Any,
    stop_loss: Any,
    target_1: Any,
    target_2: Any,
    risk_points: Any,
    risk_reward_t1: Any = 1.5,
    risk_reward_t2: Any = 3.0,
) -> TriggerCheckResult:
    """Pure validator shared by the scanner pipeline and manual /generate."""
    spot = _dec(spot_price)
    trig = _dec(trigger)
    if trig is None or trig <= 0:
        return TriggerCheckResult(False, "NO_TRIGGER", "Trigger level is missing or non-positive.")

    is_put = "PUT" in str(direction).upper() or "BEARISH" in str(direction).upper()
    if spot is None or spot <= 0:
        return TriggerCheckResult(False, "NO_SPOT", "Spot price is missing; trigger cannot be validated.")

    # 1. Trigger must sit on the breakout side (this engine confirms CALL on price >= trigger).
    if not is_put and trig <= spot:
        return TriggerCheckResult(
            False, "TRIGGER_WRONG_SIDE",
            f"CALL trigger ₹{trig} must be above spot ₹{spot} (else born-triggered).",
            {"trigger": float(trig), "spot": float(spot)},
        )
    if is_put and trig >= spot:
        return TriggerCheckResult(
            False, "TRIGGER_WRONG_SIDE",
            f"PUT trigger ₹{trig} must be below spot ₹{spot} (else born-triggered).",
            {"trigger": float(trig), "spot": float(spot)},
        )

    risk = _dec(risk_points)
    sl = _dec(stop_loss)
    if risk is None or risk <= 0:
        # Derive from SL distance when risk_points is absent/zero.
        emn, emx = _dec(entry_min), _dec(entry_max)
        if sl is not None and emn is not None and emx is not None:
            ref = emx if is_put else emn
            risk = abs(sl - ref)
    if risk is None or risk <= 0:
        return TriggerCheckResult(False, "RISK_TOO_SMALL", "Risk points are zero — SL equals entry.")

    # 2. Minimum gap from spot (the no-edge killer).
    gap = abs(trig - spot)
    min_gap = min_trigger_gap_pts(spot, risk)
    if gap < min_gap:
        return TriggerCheckResult(
            False, "TRIGGER_TOO_CLOSE",
            f"Trigger ₹{trig} is only {gap:.2f}pts from spot ₹{spot} "
            f"(needs ≥ {min_gap:.2f}pts). No breakout to confirm — signal would fill instantly.",
            {"gap_pts": float(gap), "min_gap_pts": float(min_gap),
             "gap_pct": float(gap / abs(spot) * 100), "risk_pts": float(risk)},
        )

    # 3. Dust-stop filter.
    if risk < abs(spot) * MIN_RISK_PCT:
        return TriggerCheckResult(
            False, "RISK_TOO_SMALL",
            f"Risk {risk:.2f}pts is dust for ₹{spot} spot (min {abs(spot) * MIN_RISK_PCT:.2f}pts).",
            {"risk_pts": float(risk)},
        )

    t1 = _dec(target_1)
    t2 = _dec(target_2)

    # 4. Stop-Loss orientation relative to trigger
    if sl is not None:
        if not is_put and sl >= trig:
            return TriggerCheckResult(
                False, "SL_WRONG_SIDE",
                f"CALL stop loss ₹{sl} must be below trigger ₹{trig}.",
                {"stop_loss": float(sl), "trigger": float(trig)},
            )
        if is_put and sl <= trig:
            return TriggerCheckResult(
                False, "SL_WRONG_SIDE",
                f"PUT stop loss ₹{sl} must be above trigger ₹{trig}.",
                {"stop_loss": float(sl), "trigger": float(trig)},
            )

    # 5. Target geometry and ordering
    if t1 is not None and t2 is not None:
        if not is_put:
            if t1 <= trig:
                return TriggerCheckResult(
                    False, "TARGET_WRONG_SIDE",
                    f"CALL Target 1 ₹{t1} must be above trigger ₹{trig}.",
                    {"target_1": float(t1), "trigger": float(trig)},
                )
            if t2 <= t1:
                return TriggerCheckResult(
                    False, "TARGETS_MISORDERED",
                    f"CALL Target 2 ₹{t2} must be above Target 1 ₹{t1}.",
                    {"target_1": float(t1), "target_2": float(t2)},
                )
        else:
            if t1 >= trig:
                return TriggerCheckResult(
                    False, "TARGET_WRONG_SIDE",
                    f"PUT Target 1 ₹{t1} must be below trigger ₹{trig}.",
                    {"target_1": float(t1), "trigger": float(trig)},
                )
            if t2 >= t1:
                return TriggerCheckResult(
                    False, "TARGETS_MISORDERED",
                    f"PUT Target 2 ₹{t2} must be below Target 1 ₹{t1}.",
                    {"target_1": float(t1), "target_2": float(t2)},
                )

    # 4. Reward bar (independently verified from actual target levels if present).
    if t2 is not None and risk > 0:
        rr2 = float(abs(t2 - trig) / risk)
    else:
        try:
            rr2 = float(risk_reward_t2)
        except Exception:
            rr2 = 0.0
    if not (rr2 >= MIN_RR_T2):
        return TriggerCheckResult(
            False, "RR_TOO_LOW",
            f"Risk:reward 1:{rr2:.1f} below minimum 1:{MIN_RR_T2}.",
            {"rr_t2": rr2},
        )

    # 5. Entry zone sanity (zone wider than 2R = chop, not a setup).
    emn, emx = _dec(entry_min), _dec(entry_max)
    if emn is not None and emx is not None and risk > 0:
        width = abs(emx - emn)
        if width > abs(risk) * MAX_ENTRY_WIDTH_R:
            return TriggerCheckResult(
                False, "ENTRY_ZONE_TOO_WIDE",
                f"Entry zone {width:.2f}pts wide vs {risk:.2f}pts risk — no precise trigger possible.",
                {"zone_width_pts": float(width), "risk_pts": float(risk)},
            )

    return TriggerCheckResult(
        True, None, None,
        {"gap_pts": float(gap), "min_gap_pts": float(min_gap), "risk_pts": float(risk), "rr_t2": rr2},
    )
