"""
AI Staleness Guard — §23

This is mandatory for live trading.

At trigger time capture:
trigger_price, trigger_timestamp, trigger_ATR, trigger_state_version

When AI returns, compare against current market.

Initial configurable rule:
abs(current_price - trigger_price) > MAX_AI_PRICE_DRIFT_ATR × trigger_ATR → ABORT_SIGNAL

Default prototype: MAX_AI_PRICE_DRIFT_ATR = 0.5

Also invalidate if:
response age exceeds maximum
regime changed materially
P50 direction changed
VWAP state changed materially
OI changed materially
order-flow state changed materially
state version is no longer compatible

Result: ABORT_SIGNAL
Do not execute a stale AI result.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


class StalenessCheckResult(BaseModel):
    stale: bool
    reason: str | None = None
    abort_signal: bool = False
    details: dict[str, Any] = {}


# Configurable per §23
DEFAULT_MAX_AI_PRICE_DRIFT_ATR = 0.5
DEFAULT_MAX_RESPONSE_AGE_SECONDS = 30  # max age before stale
DEFAULT_MAX_REGIME_CHANGE = True


def check_staleness(
    trigger_price: float,
    trigger_atr: float,
    trigger_timestamp: datetime,
    trigger_state_version: int,
    trigger_regime: str | None = None,
    trigger_p50: float | None = None,
    trigger_vwap: float | None = None,
    current_price: float | None = None,
    current_regime: str | None = None,
    current_p50: float | None = None,
    current_vwap: float | None = None,
    current_timestamp: datetime | None = None,
    response_timestamp: datetime | None = None,
    max_drift_atr: float = DEFAULT_MAX_AI_PRICE_DRIFT_ATR,
    max_age_seconds: int = DEFAULT_MAX_RESPONSE_AGE_SECONDS,
    current_state_version: int | None = None,
) -> StalenessCheckResult:
    """
    Returns stale=True + abort_signal=True if any staleness condition hit.
    """
    if current_timestamp is None:
        current_timestamp = datetime.now(timezone.utc)
    if response_timestamp is None:
        response_timestamp = current_timestamp

    # Ensure timezone awareness
    if trigger_timestamp.tzinfo is None:
        trigger_timestamp = trigger_timestamp.replace(tzinfo=timezone.utc)
    if current_timestamp.tzinfo is None:
        current_timestamp = current_timestamp.replace(tzinfo=timezone.utc)
    if response_timestamp.tzinfo is None:
        response_timestamp = response_timestamp.replace(tzinfo=timezone.utc)

    # 1. Price drift check (§23 primary rule)
    if current_price is not None and trigger_price is not None and trigger_atr is not None and trigger_atr > 0:
        drift = abs(current_price - trigger_price)
        threshold = max_drift_atr * trigger_atr
        if drift > threshold:
            return StalenessCheckResult(
                stale=True,
                reason=f"price drift {drift:.2f} > {max_drift_atr}×ATR ({threshold:.2f})",
                abort_signal=True,
                details={"drift": drift, "threshold": threshold, "trigger_price": trigger_price, "current_price": current_price, "trigger_atr": trigger_atr},
            )

    # 2. Response age exceeds maximum
    age = (current_timestamp - trigger_timestamp).total_seconds()
    if age > max_age_seconds:
        return StalenessCheckResult(
            stale=True,
            reason=f"response age {age:.1f}s > max {max_age_seconds}s",
            abort_signal=True,
            details={"age_seconds": age, "max_age": max_age_seconds},
        )
    # Also check response timestamp itself vs now
    resp_age = (current_timestamp - response_timestamp).total_seconds()
    if resp_age > max_age_seconds:
        return StalenessCheckResult(
            stale=True,
            reason=f"response timestamp age {resp_age:.1f}s > max {max_age_seconds}s",
            abort_signal=True,
            details={"resp_age": resp_age},
        )

    # 3. Regime changed materially
    if trigger_regime and current_regime and trigger_regime != current_regime:
        # Treat any regime change as material for live trading
        return StalenessCheckResult(
            stale=True,
            reason=f"regime changed {trigger_regime} → {current_regime}",
            abort_signal=True,
            details={"trigger_regime": trigger_regime, "current_regime": current_regime},
        )

    # 4. P50 direction changed
    if trigger_p50 is not None and current_p50 is not None:
        # Direction is bullish if P50 > trigger_price (approx), else bearish
        # Simpler: check if P50 crossed price direction
        # Use sign of (P50 - price)
        try:
            trig_dir = 1 if trigger_p50 > trigger_price else -1 if trigger_p50 < trigger_price else 0
            curr_dir = 1 if current_p50 > (current_price or trigger_price) else -1 if current_p50 < (current_price or trigger_price) else 0
            if trig_dir != 0 and curr_dir != 0 and trig_dir != curr_dir:
                return StalenessCheckResult(
                    stale=True,
                    reason=f"P50 direction changed {trig_dir} → {curr_dir}",
                    abort_signal=True,
                    details={"trigger_p50": trigger_p50, "current_p50": current_p50},
                )
        except Exception:
            pass

    # 5. VWAP state changed materially (cross)
    if trigger_vwap is not None and current_vwap is not None and current_price is not None and trigger_price is not None:
        trig_above = trigger_price > trigger_vwap
        curr_above = current_price > current_vwap
        if trig_above != curr_above:
            return StalenessCheckResult(
                stale=True,
                reason=f"VWAP state changed (price {trigger_price} {'above' if trig_above else 'below'} VWAP {trigger_vwap} → {current_price} {'above' if curr_above else 'below'} {current_vwap})",
                abort_signal=True,
                details={"trigger_vwap": trigger_vwap, "current_vwap": current_vwap},
            )

    # 6. State version no longer compatible (if provided)
    if current_state_version is not None and trigger_state_version is not None:
        if current_state_version != trigger_state_version:
            # For strict live trading, any version mismatch is stale unless explicitly compatible
            # We treat mismatch as stale if drift or regime already not caught, but still signal
            # To avoid over-abort, only abort if age already high or other signals; here we just flag stale
            # Spec: state version is no longer compatible → ABORT
            # So we abort on mismatch if price already drifted? Simpler: abort on mismatch always for mandatory guard
            return StalenessCheckResult(
                stale=True,
                reason=f"state version changed {trigger_state_version} → {current_state_version}",
                abort_signal=True,
                details={"trigger_state_version": trigger_state_version, "current_state_version": current_state_version},
            )

    return StalenessCheckResult(stale=False, abort_signal=False, details={"age_seconds": age})
