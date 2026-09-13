"""ML v3 institutional feature pack (schema f20-v1, PIT-safe, missing-aware).

Extends the v2 row (15) with 5 institutional features (all PIT-safe, None when
unverifiable — never zero-filled except via documented neutrals with flags):

  16. fii_cash_z      (daily cash z, T+1 available; None if <3d window)
  17. dii_cash_z
  18. fii_lsr_dev     ((lsr-1)/0.3 clipped; None when positioning missing)
  19. options_write   (net_write_pressure from options_flow_engine; None if INSUFFICIENT_DATA)
  20. breadth_ad      (ad_ratio centered (ad-0.5)*2; None when UNAVAILABLE/PROXY-missing)

Plus interaction helpers (derived, NOT stored — avoids collinearity):
  flow_x_regime(), pcr_x_adx() via build_interactions().

Width contract: 20. Trainers must validate width==20 and record schema f20-v1.
No artifact ships with this change (honest: needs >=200 aligned sessions +
forward returns). Callers use try_v3_vector() and fall back to v2 when None.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

FEATURE_SCHEMA_V3 = "f20-v1"
FEATURE_NAMES_V3: List[str] = [
    "rsi_1h", "adx_1h", "supertrend_1h", "supertrend_15m", "supertrend_4h",
    "bb_pct_b_1h", "atr_pct_1h", "ret_5", "ret_15", "relative_volume",
    "vwap_distance", "pcr_oi", "max_pain_distance", "vix", "minutes_to_close",
    "fii_cash_z", "dii_cash_z", "fii_lsr_dev", "options_write", "breadth_ad",
]

NEUTRAL_V3: Dict[str, float] = {
    "fii_cash_z": 0.0, "dii_cash_z": 0.0, "fii_lsr_dev": 0.0,
    "options_write": 0.0, "breadth_ad": 0.0,
}


def _clip(v: Optional[float], lo: float, hi: float) -> Optional[float]:
    if v is None:
        return None
    try:
        return round(min(hi, max(lo, float(v))), 4)
    except Exception:
        return None


def build_v3_extension(
    flow_snapshot: Any,
    options_flow: Dict[str, Any] | None,
    breadth: Dict[str, Any] | None,
) -> Tuple[Dict[str, Optional[float]], Dict[str, int]]:
    vals: Dict[str, Optional[float]] = {}
    try:
        vals["fii_cash_z"] = _clip(getattr(flow_snapshot, "fii_cash_5d_z", None), -3.0, 3.0)
    except Exception:
        vals["fii_cash_z"] = None
    try:
        vals["dii_cash_z"] = _clip(getattr(flow_snapshot, "dii_cash_5d_z", None), -3.0, 3.0)
    except Exception:
        vals["dii_cash_z"] = None
    try:
        lsr = getattr(flow_snapshot, "fii_lsr", None)
        vals["fii_lsr_dev"] = _clip((float(lsr) - 1.0) / 0.3, -2.0, 2.0) if lsr is not None else None
    except Exception:
        vals["fii_lsr_dev"] = None
    try:
        w = (options_flow or {}).get("net_write_pressure")
        vals["options_write"] = _clip(w, -1.0, 1.0) if (options_flow or {}).get("status") == "LIVE" else None
    except Exception:
        vals["options_write"] = None
    try:
        ad = (breadth or {}).get("ad_ratio")
        vals["breadth_ad"] = _clip((float(ad) - 0.5) * 2.0, -1.0, 1.0) if ad is not None else None
    except Exception:
        vals["breadth_ad"] = None
    mask = {k: (1 if v is None else 0) for k, v in vals.items()}
    return vals, mask


def to_v3_vector(v2_model_vector: List[float], ext: Dict[str, Optional[float]]) -> Tuple[List[float], List[int]]:
    """Append institutional pack to a v2 model_vector (len 15) -> (vector20, mask20)."""
    if len(v2_model_vector) != 15:
        raise ValueError(f"v3 needs v2 width 15 (got {len(v2_model_vector)})")
    tail = [ext.get(k) if ext.get(k) is not None else NEUTRAL_V3[k] for k in FEATURE_NAMES_V3[15:]]
    vec = [float(x) for x in v2_model_vector] + [float(x) for x in tail]
    mask = [0] * 15 + [1 if ext.get(k) is None else 0 for k in FEATURE_NAMES_V3[15:]]
    return vec, mask


def build_interactions(
    v3_values: Dict[str, Any],
    regime_family: str,
    adx_1h: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Derived cross terms (not stored): flow×regime, pcr×adx, write×vwap."""
    out: Dict[str, Optional[float]] = {}
    try:
        fii = v3_values.get("fii_cash_z")
        mult = {"TREND_DOWN": 1.0, "TREND_UP": 1.0, "TREND": 1.0, "VOLATILE": 0.5, "RANGE": 0.25}.get(str(regime_family).upper(), 0.4)
        out["flow_x_regime"] = round(float(fii) * mult, 4) if fii is not None else None
    except Exception:
        out["flow_x_regime"] = None
    try:
        pcr = v3_values.get("pcr_oi")
        adx = (float(adx_1h) if adx_1h is not None else None)
        out["pcr_x_adx"] = round(float(pcr) * (adx / 50.0), 4) if pcr is not None and adx is not None else None
    except Exception:
        out["pcr_x_adx"] = None
    return out
