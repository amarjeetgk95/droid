"""
1H Forecast v2.3 — Primary Target Spec (P1-1).

``v2-atr-em-session``: sign of the 60m forward return from T to T+60m with a
±0.25×ATR14_1h neutral dead zone. Label math is IDENTICAL to the v1 primary
spec (``app.ml.targets.label_forward_return`` with ``NEUTRAL_BAND_ATR=0.25``);
only the version string, ATR source contract, and session rule differ:

- ATR source MUST be the primary 1h ``quant.atr_14`` (14-bar ATR on 1h).
- EM (options expected move) is RISK-ONLY (targets/stops in P2) — it never
  enters the label. A label needs only (spot_t, spot_th, atr14_1h_t).
- Windows crossing the NSE session close / holidays / specials are
  INSUFFICIENT_DATA (enforced by callers via ``app.ml.sessions``), never
  bridged across the close.

``app.ml.targets`` is frozen for compat; v1 re-exports live here so callers
can import both spec versions from one module.
"""
from __future__ import annotations

from app.ml.targets import (
    DEFAULT_HORIZON_MINUTES,
    INTRADAY_CLEAN_HORIZONS,
    INV_LABEL,
    LABEL_MAP,
    SUPPORTED_HORIZONS,
    TARGET_SPEC_VERSION as TARGET_SPEC_VERSION_V1,
    validate_horizon,
)

TARGET_SPEC_VERSION_V2 = "v2-atr-em-session"

# Primary 1H target constants.
NEUTRAL_BAND_ATR_V2 = 0.25
ATR_LEN = 14
# Product horizon for the v2 contract (60m; 30m is diagnostic-only).
V2_HORIZON_MINUTES = 60

# Re-export both spec versions from one module.
TARGET_SPEC_VERSIONS = (TARGET_SPEC_VERSION_V1, TARGET_SPEC_VERSION_V2)

__all__ = [
    "TARGET_SPEC_VERSION_V1",
    "TARGET_SPEC_VERSION_V2",
    "TARGET_SPEC_VERSIONS",
    "NEUTRAL_BAND_ATR_V2",
    "ATR_LEN",
    "V2_HORIZON_MINUTES",
    "LABEL_MAP",
    "INV_LABEL",
    "SUPPORTED_HORIZONS",
    "DEFAULT_HORIZON_MINUTES",
    "INTRADAY_CLEAN_HORIZONS",
    "validate_horizon",
    "label_forward_return_v2",
    "describe_target_v2",
]


def label_forward_return_v2(
    spot_t: float,
    spot_th: float,
    atr14_1h_t: float,
    neutral_band_atr: float = NEUTRAL_BAND_ATR_V2,
) -> int:
    """Label the realized 60m forward return under ``v2-atr-em-session``.

    Returns 0 (BEARISH), 1 (NEUTRAL) or 2 (BULLISH). Identical math to the
    v1 primary label: ``band = neutral_band_atr * atr / spot_t`` with strict
    ``>`` / ``<`` comparisons (exact ±band touches stay NEUTRAL).

    Raises ValueError on non-positive (or NaN/None-equivalent) inputs —
    callers map that to INSUFFICIENT_DATA, never a synthetic label.
    """
    try:
        s_t = float(spot_t)
        s_h = float(spot_th)
        atr = float(atr14_1h_t)
        band_mult = float(neutral_band_atr)
    except (TypeError, ValueError) as e:
        raise ValueError(
            "v2 labeling requires numeric spot_t, spot_th, atr14_1h_t "
            "(missing data must stay INSUFFICIENT_DATA, never a synthetic label)"
        ) from e
    if not (s_t > 0 and s_h > 0 and atr > 0 and band_mult > 0):
        raise ValueError(
            "v2 labeling requires positive spot_t, spot_th, atr14_1h_t "
            "(missing data must stay INSUFFICIENT_DATA, never a synthetic label)"
        )
    fwd = (s_h - s_t) / s_t
    band = (band_mult * atr) / s_t
    if fwd > band:
        return LABEL_MAP["BULLISH"]
    if fwd < -band:
        return LABEL_MAP["BEARISH"]
    return LABEL_MAP["NEUTRAL"]


def describe_target_v2(horizon_minutes: int = V2_HORIZON_MINUTES) -> dict:
    """Human/audit-readable definition of the v2 primary target."""
    return {
        "horizon_minutes": int(horizon_minutes),
        "target_spec_version": TARGET_SPEC_VERSION_V2,
        "definition": (
            f"Sign of forward return from T to T+{int(horizon_minutes)}m, "
            f"with a ±{NEUTRAL_BAND_ATR_V2}×ATR{ATR_LEN}_1h(T) neutral dead zone"
        ),
        "labels": dict(LABEL_MAP),
        "atr_source": f"primary 1h quant.atr_14 (ATR_LEN={ATR_LEN})",
        "em_note": "EM (options expected move) is risk-only (targets/stops), never a label input",
        "session_note": (
            "same-regular-session-only: windows crossing the NSE close, "
            "weekends, holidays, or touching a special session are "
            "INSUFFICIENT_DATA — never bridged across the close"
        ),
    }
