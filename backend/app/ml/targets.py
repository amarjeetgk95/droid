"""
Multi-Horizon Target-Label Specification — Phase 0

Defines WHAT each prediction horizon means, versioned so labels, artifacts,
and calibration can never silently drift apart.

Label rule (per horizon H, observation at T):
    fwd = (spot(T+H) - spot(T)) / spot(T)
    band = NEUTRAL_BAND_ATR * atr(T) / spot(T)   # ATR-normalized dead zone
    fwd > +band  -> BULLISH (2)
    fwd < -band  -> BEARISH (0)
    else         -> NEUTRAL (1)

PIT discipline: a training row for observation T may only use information
published at or before T, plus the realized spots at T and T+H (both known
only when the row is built AFTER T+H). Inference at time T never sees T+H.

Horizons crossing the NSE EOD boundary (60m+) require session-aware spot
lookup (skip overnight gap or mark INSUFFICIENT_DATA) — enforced by callers,
not silently interpolated here.
"""
from __future__ import annotations

TARGET_SPEC_VERSION = "v1-atr-band"

# Phase 0 supported horizons (minutes). 60/90/120 are accepted but served
# uncalibrated until session-aware labeling + per-horizon artifacts exist.
SUPPORTED_HORIZONS: tuple[int, ...] = (5, 15, 30, 60, 90, 120)
DEFAULT_HORIZON_MINUTES = 15

# Horizons with enough same-session samples for intraday calibration.
INTRADAY_CLEAN_HORIZONS: tuple[int, ...] = (5, 15, 30)

NEUTRAL_BAND_ATR = 0.25

LABEL_MAP = {"BEARISH": 0, "NEUTRAL": 1, "BULLISH": 2}
INV_LABEL = {v: k for k, v in LABEL_MAP.items()}


def validate_horizon(horizon_minutes: int) -> int:
    """Raise ValueError for unsupported horizons — never silently remap."""
    if horizon_minutes not in SUPPORTED_HORIZONS:
        raise ValueError(
            f"Unsupported horizon {horizon_minutes}m. "
            f"Supported: {list(SUPPORTED_HORIZONS)}"
        )
    return horizon_minutes


def label_forward_return(
    spot_at_t: float,
    spot_at_t_plus_h: float,
    atr_at_t: float,
    neutral_band_atr: float = NEUTRAL_BAND_ATR,
) -> int:
    """Label the realized forward return over horizon H.

    Returns 0 (BEARISH), 1 (NEUTRAL) or 2 (BULLISH) per TARGET_SPEC_VERSION.
    Raises ValueError on non-positive inputs instead of inventing a label.
    """
    if not (spot_at_t > 0 and spot_at_t_plus_h > 0 and atr_at_t > 0):
        raise ValueError(
            "Labeling requires positive spot_at_t, spot_at_t_plus_h and atr_at_t "
            "(missing data must stay INSUFFICIENT_DATA, never a synthetic label)"
        )
    fwd = (spot_at_t_plus_h - spot_at_t) / spot_at_t
    band = (neutral_band_atr * atr_at_t) / spot_at_t
    if fwd > band:
        return LABEL_MAP["BULLISH"]
    if fwd < -band:
        return LABEL_MAP["BEARISH"]
    return LABEL_MAP["NEUTRAL"]


def describe_target(horizon_minutes: int) -> dict:
    """Human/audit-readable definition of what a horizon label means."""
    return {
        "horizon_minutes": validate_horizon(horizon_minutes),
        "target_spec_version": TARGET_SPEC_VERSION,
        "definition": (
            f"Sign of forward return from T to T+{horizon_minutes}m, "
            f"with a ±{NEUTRAL_BAND_ATR}×ATR(T) neutral dead zone"
        ),
        "labels": LABEL_MAP,
        "session_note": (
            "intraday-clean"
            if horizon_minutes in INTRADAY_CLEAN_HORIZONS
            else "may cross EOD — requires session-aware spot lookup"
        ),
    }
