"""Target/risk v2 for 1H forecast v2.3 (P2-5). Pure math, no I/O.

EM (options expected move) is RISK-ONLY — it sizes targets/stops and the
neutral expected range, never the label (see ``app.ml.targets_v2``).

Formulas (pre-registered Cycle-1):
    EM               = atm_iv/100 * spot * sqrt(max(dte_days, 0.25) / 365)
    target_distance  = min(1.8 * ATR14_1h, 0.70 * EM)
    inval_distance   = max(1.1 * ATR14_1h, 0.35 * EM, barrier or 0)
    closing scale    = clamp(time_to_close_min / H, 0, 1)  (H = 60)

Guards: missing/non-positive IV or missing DTE/spot/ATR -> EM None and the
caller falls back to ATR-only distances with limitation
``target_basis=ATR-only`` (never a synthetic EM).
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

ATR_TARGET_MULT = 1.8
ATR_INVAL_MULT = 1.1
EM_TARGET_MULT = 0.70
EM_INVAL_MULT = 0.35
DTE_FLOOR_DAYS = 0.25
DAYS_PER_YEAR = 365.0


def _finite_positive(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f == float("inf") or f == float("-inf"):
        return None
    if f <= 0:
        return None
    return f


def expected_move(
    spot: Any,
    atm_iv_pct: Any,
    dte_days: Any,
    dte_floor: float = DTE_FLOOR_DAYS,
) -> Optional[float]:
    """Options expected move to expiry (same units as spot).

    Returns None when the move is not computable (missing IV/DTE, or
    non-positive spot/IV) so callers fall back to ATR-only. DTE is floored
    at 0.25 days (expiry-day guard); IV is in percent points (e.g. 15.0).
    """
    s = _finite_positive(spot)
    iv = _finite_positive(atm_iv_pct)
    if s is None or iv is None:
        return None
    try:
        dte = float(dte_days)
    except (TypeError, ValueError):
        return None
    if dte != dte or dte == float("inf") or dte == float("-inf"):
        return None
    dte_eff = max(dte, float(dte_floor))
    if not dte_eff > 0:
        return None
    return (iv / 100.0) * s * math.sqrt(dte_eff / DAYS_PER_YEAR)


def target_distances(
    atr14_1h: Any,
    em: Any,
    barrier: Any = None,
) -> Dict[str, Any]:
    """Target/invalidation distances from ATR14_1h, EM, and an optional barrier.

    Barrier is a *distance* (e.g. spot-to-wall on the invalidation side);
    non-positive/missing barriers are treated as 0. When EM is missing or
    non-positive the output is ATR-only with ``basis="ATR-only"``.

    Raises ValueError on missing/non-positive ATR (callers must supply the
    v1 spot*0.005 fallback before calling, never a zero ATR).
    """
    atr = _finite_positive(atr14_1h)
    if atr is None:
        raise ValueError(
            "risk_v2 needs positive atr14_1h (missing data must stay "
            "ATR-fallback upstream, never a zero-ATR target)"
        )
    try:
        b = float(barrier) if barrier is not None else 0.0
    except (TypeError, ValueError):
        b = 0.0
    if b != b or b < 0:
        b = 0.0
    em_v = None
    try:
        em_v = float(em) if em is not None else None
    except (TypeError, ValueError):
        em_v = None
    if em_v is None or em_v != em_v or not em_v > 0:
        return {
            "target_distance": ATR_TARGET_MULT * atr,
            "inval_distance": max(ATR_INVAL_MULT * atr, b),
            "basis": "ATR-only",
        }
    return {
        "target_distance": min(ATR_TARGET_MULT * atr, EM_TARGET_MULT * em_v),
        "inval_distance": max(ATR_INVAL_MULT * atr, EM_INVAL_MULT * em_v, b),
        "basis": "ATR+EM",
    }


def closing_scale(time_to_close_min: Any, H: float = 60.0) -> float:
    """Linear close-into-expiry shrink factor in [0, 1].

    ``time_to_close_min=None`` (unknown) means no scaling (1.0). Values at
    or beyond H return 1.0; values at/below 0 return 0.0.
    """
    if time_to_close_min is None:
        return 1.0
    try:
        t = float(time_to_close_min)
        h = float(H)
    except (TypeError, ValueError):
        return 1.0
    if t != t or h != h or not h > 0:
        return 1.0
    return min(1.0, max(0.0, t / h))


def expected_range_neutral(spot: Any, em: Any) -> Dict[str, float]:
    """Neutral expected range ``{lower, mid, upper}`` = spot ± EM.

    Raises ValueError on non-positive spot/EM (callers pass the ATR-based
    half-width as EM fallback so NEUTRAL never returns nulls).
    """
    s = _finite_positive(spot)
    e = _finite_positive(em)
    if s is None or e is None:
        raise ValueError("expected_range_neutral needs positive spot and EM half-width")
    return {
        "lower": round(s - e, 2),
        "mid": round(s, 2),
        "upper": round(s + e, 2),
    }


def compute_targets(
    direction: str,
    current_price: Any,
    atr14_1h: Any,
    em: Any,
    barrier: Any = None,
    time_to_close_min: Any = None,
    H: float = 60.0,
) -> Dict[str, Any]:
    """One-call directional target builder (pure).

    Returns ``{target_price, invalidation_price, target_distance,
    inval_distance, basis, closing_scale_factor, expected_range}`` where
    directional verdicts carry prices (expected_range None) and NEUTRAL
    carries ``expected_range`` (prices None). The neutral half-width is the
    closing-scaled EM, or the closing-scaled 1.8*ATR fallback when EM is
    missing (basis ATR-only + caller limitation).
    """
    d = str(direction or "NEUTRAL").upper()
    if d not in ("BULLISH", "BEARISH", "NEUTRAL"):
        raise ValueError(f"direction must be BULLISH/BEARISH/NEUTRAL, got {direction!r}")
    spot = _finite_positive(current_price)
    if spot is None:
        raise ValueError("compute_targets needs a positive current_price")
    dists = target_distances(atr14_1h, em, barrier)
    scale = closing_scale(time_to_close_min, H)
    tgt_d = dists["target_distance"] * scale
    inv_d = dists["inval_distance"] * scale
    basis = dists["basis"]
    if d == "NEUTRAL":
        em_v: Optional[float] = None
        try:
            em_v = float(em) if em is not None else None
        except (TypeError, ValueError):
            em_v = None
        half = (em_v if (em_v is not None and em_v > 0) else ATR_TARGET_MULT * float(atr14_1h)) * scale
        return {
            "target_price": None,
            "invalidation_price": None,
            "target_distance": round(tgt_d, 2),
            "inval_distance": round(inv_d, 2),
            "basis": basis,
            "closing_scale_factor": scale,
            "expected_range": expected_range_neutral(spot, half) if half > 0 else {
                "lower": round(spot, 2), "mid": round(spot, 2), "upper": round(spot, 2)},
        }
    if d == "BULLISH":
        return {
            "target_price": round(spot + tgt_d, 2),
            "invalidation_price": round(spot - inv_d, 2),
            "target_distance": round(tgt_d, 2),
            "inval_distance": round(inv_d, 2),
            "basis": basis,
            "closing_scale_factor": scale,
            "expected_range": None,
        }
    return {
        "target_price": round(spot - tgt_d, 2),
        "invalidation_price": round(spot + inv_d, 2),
        "target_distance": round(tgt_d, 2),
        "inval_distance": round(inv_d, 2),
        "basis": basis,
        "closing_scale_factor": scale,
        "expected_range": None,
    }


__all__ = [
    "ATR_TARGET_MULT",
    "ATR_INVAL_MULT",
    "EM_TARGET_MULT",
    "EM_INVAL_MULT",
    "DTE_FLOOR_DAYS",
    "expected_move",
    "target_distances",
    "closing_scale",
    "expected_range_neutral",
    "compute_targets",
]
