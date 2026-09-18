"""Premium-domain sizing helpers for the signal paper engine.

Extracted verbatim from :mod:`app.signals.paper_engine`
(``SignalPaperEngine._premium_stop_for``) so the engine module stays inside
the LOC ratchet. The engine binds this function back onto the class as a
staticmethod, preserving the original call and patch surface.
"""
from __future__ import annotations

from typing import Any, Optional


def premium_stop_for(sig: Any, entry_premium: float) -> Optional[float]:
    """Project a signal's stop into premium terms for option-buyer sizing.

    Uses the canonical ``resolve_premium_risk_points`` (explicit premium
    stop > delta-gamma projection off the spot stop > conservative
    fallback). Returns None when no positive premium stop can be derived so
    the option-buyer resolver applies its own 35%-of-premium default.
    """
    try:
        from app.signals.transaction_costs import resolve_premium_risk_points

        try:
            spot_risk = abs(float(sig.trigger) - float(sig.stop_loss))
        except Exception:
            spot_risk = 0.0
        risk_pts = float(resolve_premium_risk_points(sig, float(entry_premium), spot_risk))
        if 0.0 < risk_pts < float(entry_premium):
            return round(float(entry_premium) - risk_pts, 4)
    except Exception:
        pass
    return None
