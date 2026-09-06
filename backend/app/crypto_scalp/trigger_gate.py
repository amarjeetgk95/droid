"""
Crypto Trigger Integrity Gate — §4, §16
Rejects no-edge or 'born-triggered' signals whose trigger level sits at (or inside) spot price.
Enforces realistic breakout distances, dust-stop filters, and stop/target geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional


TICK = Decimal("0.01")  # Standard crypto price tick (for BTC/ETH on Binance)
# Minimum trigger distance from spot: larger of 0.05% of spot or 0.10R.
MIN_GAP_PCT = Decimal("0.0005")
MIN_GAP_RISK_FRACTION = Decimal("0.10")
# Minimum risk size: 0.03% of spot (filters dust stops that inflate R:R).
MIN_RISK_PCT = Decimal("0.0003")
MIN_RR_T1 = 1.15
MIN_RR_T2 = 1.35


@dataclass
class CryptoTriggerCheckResult:
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


def min_crypto_trigger_gap_pts(spot: Any, risk_points: Any, is_scalp: bool = True) -> Decimal:
    """Minimum trigger distance from spot for a crypto signal to carry legitimate breakout edge."""
    d_spot = _dec(spot) or Decimal("1000.0")
    d_risk = _dec(risk_points) or Decimal("100.0")
    if is_scalp:
        pct_floor = abs(d_spot) * Decimal("0.0002")  # 0.02%
        risk_floor = abs(d_risk) * Decimal("0.05")  # 0.05R
        return max(pct_floor, risk_floor, TICK * 2)
    pct_floor = abs(d_spot) * MIN_GAP_PCT  # 0.05%
    risk_floor = abs(d_risk) * MIN_GAP_RISK_FRACTION  # 0.10R
    return max(pct_floor, risk_floor, TICK * 5)


def check_crypto_trigger_integrity(
    *,
    symbol: str = "BTCUSDT",
    strategy: str = "?",
    direction: str,
    spot_price: Any,
    entry_min: Any = None,
    entry_max: Any = None,
    trigger: Any,
    stop_loss: Any,
    target_1: Any,
    target_2: Any,
    risk_points: Any = None,
    risk_reward_t1: Any = 1.5,
    risk_reward_t2: Any = 2.5,
    is_scalp: bool = True,
    timeframe: str = "1m",
) -> CryptoTriggerCheckResult:
    """Pure validator ensuring crypto signals carry legitimate breakout edge and clean geometry."""
    spot = _dec(spot_price)
    trig = _dec(trigger)
    if trig is None or trig <= Decimal("0"):
        return CryptoTriggerCheckResult(False, "NO_TRIGGER", "Trigger level is missing or non-positive.")
    if spot is None or spot <= Decimal("0"):
        return CryptoTriggerCheckResult(False, "NO_SPOT", "Spot price is missing; trigger cannot be validated.")

    is_short = "SHORT" in str(direction).upper() or "BEARISH" in str(direction).upper() or "SELL" in str(direction).upper()

    # 1. Trigger orientation relative to spot (breakout side)
    if not is_short and trig <= spot:
        return CryptoTriggerCheckResult(
            False,
            "TRIGGER_WRONG_SIDE",
            f"LONG trigger ${trig} must be above spot ${spot} (else born-triggered without edge).",
            {"trigger": float(trig), "spot": float(spot), "symbol": symbol},
        )
    if is_short and trig >= spot:
        return CryptoTriggerCheckResult(
            False,
            "TRIGGER_WRONG_SIDE",
            f"SHORT trigger ${trig} must be below spot ${spot} (else born-triggered without edge).",
            {"trigger": float(trig), "spot": float(spot), "symbol": symbol},
        )

    risk = _dec(risk_points)
    sl = _dec(stop_loss)
    if risk is None or risk <= Decimal("0"):
        if sl is not None:
            risk = abs(trig - sl)

    if risk is None or risk <= Decimal("0"):
        return CryptoTriggerCheckResult(False, "RISK_TOO_SMALL", "Risk points are zero — stop loss equals trigger entry.")

    # 2. Minimum gap from spot (prevents instant fills with zero edge)
    gap = abs(trig - spot)
    min_gap = min_crypto_trigger_gap_pts(spot, risk, is_scalp=is_scalp)
    if gap < min_gap:
        return CryptoTriggerCheckResult(
            False,
            "TRIGGER_TOO_CLOSE",
            f"Trigger ${trig:.2f} is only ${gap:.2f} away from spot ${spot:.2f} (needs >= ${min_gap:.2f}). No breakout edge.",
            {"gap": float(gap), "min_gap": float(min_gap), "gap_pct": float(gap / spot * Decimal("100")), "symbol": symbol},
        )

    # 3. Dust stop filter
    min_risk_floor = (abs(spot) * Decimal("0.0001")) if is_scalp else (abs(spot) * MIN_RISK_PCT)
    if risk < min_risk_floor:
        return CryptoTriggerCheckResult(
            False,
            "RISK_TOO_SMALL",
            f"Risk ${risk:.2f} is dust for ${spot:.2f} spot (min allowable ${min_risk_floor:.2f}).",
            {"risk": float(risk), "min_risk_floor": float(min_risk_floor), "symbol": symbol},
        )

    # 4. Stop-Loss orientation
    if sl is not None:
        if not is_short and sl >= trig:
            return CryptoTriggerCheckResult(
                False,
                "SL_WRONG_SIDE",
                f"LONG stop-loss ${sl} must be strictly below trigger ${trig}.",
                {"sl": float(sl), "trigger": float(trig)},
            )
        if is_short and sl <= trig:
            return CryptoTriggerCheckResult(
                False,
                "SL_WRONG_SIDE",
                f"SHORT stop-loss ${sl} must be strictly above trigger ${trig}.",
                {"sl": float(sl), "trigger": float(trig)},
            )

    # 5. Targets orientation & R:R checks
    t1 = _dec(target_1)
    t2 = _dec(target_2)
    if t1 is not None:
        if not is_short and t1 <= trig:
            return CryptoTriggerCheckResult(False, "T1_WRONG_SIDE", f"LONG target 1 ${t1} must be above trigger ${trig}.")
        if is_short and t1 >= trig:
            return CryptoTriggerCheckResult(False, "T1_WRONG_SIDE", f"SHORT target 1 ${t1} must be below trigger ${trig}.")

        rr1 = float(abs(t1 - trig) / risk)
        if rr1 < MIN_RR_T1:
            return CryptoTriggerCheckResult(
                False,
                "INSUFFICIENT_RR_T1",
                f"Target 1 gives only {rr1:.2f}R (needs >= {MIN_RR_T1:.2f}R).",
                {"rr1": rr1, "min_rr1": MIN_RR_T1},
            )

    if t2 is not None:
        if not is_short and t2 <= (t1 or trig):
            return CryptoTriggerCheckResult(False, "T2_WRONG_SIDE", f"LONG target 2 ${t2} must be above target 1 ${t1}.")
        if is_short and t2 >= (t1 or trig):
            return CryptoTriggerCheckResult(False, "T2_WRONG_SIDE", f"SHORT target 2 ${t2} must be below target 1 ${t1}.")

        rr2 = float(abs(t2 - trig) / risk)
        if rr2 < MIN_RR_T2:
            return CryptoTriggerCheckResult(
                False,
                "INSUFFICIENT_RR_T2",
                f"Target 2 gives only {rr2:.2f}R (needs >= {MIN_RR_T2:.2f}R).",
                {"rr2": rr2, "min_rr2": MIN_RR_T2},
            )

    return CryptoTriggerCheckResult(
        passed=True,
        metrics={
            "symbol": symbol,
            "trigger": float(trig),
            "spot": float(spot),
            "gap": float(gap),
            "risk": float(risk),
            "rr1": float(abs(t1 - trig) / risk) if t1 else None,
            "rr2": float(abs(t2 - trig) / risk) if t2 else None,
        },
    )
