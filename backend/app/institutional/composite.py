"""Institutional composite score 0-100 (auditable, regime-conditioned, fail-closed).

Inputs (all optional, PIT-safe only):
  flow_snapshot (daily cash z, lsr), options_flow (write pressure),
  breadth (ad_ratio), vix (level/percentile), fno (pcr, walls),
  regime (family conditions interpretation).

Weights (fixed v1, learned stacker later):
  flow 0.35, options-write 0.25, breadth 0.15, pcr-tilt 0.15, vix-defensive 0.10
Missing inputs are EXCLUDED with renormalisation (never zero-filled); if fewer
than 2 domains present -> status INSUFFICIENT (score None, downstream ignores).

Output: {"score": 0-100|None, "sentiment": BULLISH/BEARISH/NEUTRAL/INSUFFICIENT,
  "domains": {...}, "status": LIVE/DEGRADED/INSUFFICIENT, "reasons": [...]}
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def compute_composite(
    flow: Any = None,
    options_flow: Dict[str, Any] | None = None,
    breadth: Dict[str, Any] | None = None,
    vix: Dict[str, Any] | None = None,
    fno: Dict[str, Any] | None = None,
    regime: Any = None,
) -> Dict[str, Any]:
    reasons: list[str] = []
    parts: Dict[str, float] = {}
    weights = {"flow": 0.35, "write": 0.25, "breadth": 0.15, "pcr": 0.15, "vix": 0.10}

    # Flow domain: z-mean + lsr tilt, -1..+1 -> 0..100.
    try:
        fz = getattr(flow, "fii_cash_5d_z", None)
        dz = getattr(flow, "dii_cash_5d_z", None)
        lsr = getattr(flow, "fii_lsr", None)
        vals = [v for v in (fz, dz) if isinstance(v, (int, float))]
        if vals and getattr(flow, "pit_ok", False) is True:
            b = sum(max(-1.0, min(1.0, float(v) / 2.0)) for v in vals) / len(vals)
            if isinstance(lsr, (int, float)):
                b += 0.2 if float(lsr) > 1.05 else (-0.2 if float(lsr) < 0.95 else 0.0)
            parts["flow"] = _clip((max(-1.0, min(1.0, b)) + 1.0) * 50.0, 0, 100)
        else:
            reasons.append("flow-missing-or-unverifiable")
    except Exception:
        reasons.append("flow-error")

    # Options-write domain.
    try:
        if isinstance(options_flow, dict) and options_flow.get("status") == "LIVE":
            w = options_flow.get("net_write_pressure")
            if isinstance(w, (int, float)):
                parts["write"] = _clip((float(w) + 1.0) * 50.0, 0, 100)
            else:
                reasons.append("write-missing")
        else:
            reasons.append("write-insufficient-data")
    except Exception:
        reasons.append("write-error")

    # Breadth domain (proxy-labelled upstream).
    try:
        ad = (breadth or {}).get("ad_ratio") if isinstance(breadth, dict) else None
        if isinstance(ad, (int, float)):
            parts["breadth"] = _clip(float(ad) * 100.0, 0, 100)
        else:
            reasons.append("breadth-missing")
    except Exception:
        reasons.append("breadth-error")

    # PCR tilt domain.
    try:
        pcr = (fno or {}).get("pcr") if isinstance(fno, dict) else None
        if isinstance(pcr, (int, float)):
            tilt = _clip((float(pcr) - 1.0) / 0.5, -1.0, 1.0)
            parts["pcr"] = _clip((tilt + 1.0) * 50.0, 0, 100)
        else:
            reasons.append("pcr-missing")
    except Exception:
        reasons.append("pcr-error")

    # VIX defensive domain (high VIX = risk-off = bearish tilt for longs).
    try:
        vx = (vix or {}).get("vix") if isinstance(vix, dict) else None
        if isinstance(vx, (int, float)):
            # 12 calm -> 80, 25 stressed -> 20.
            score = _clip(80.0 - (float(vx) - 12.0) * (60.0 / 13.0), 0, 100)
            parts["vix"] = score
        else:
            reasons.append("vix-missing")
    except Exception:
        reasons.append("vix-error")

    if len(parts) < 2:
        return {"score": None, "sentiment": "INSUFFICIENT", "domains": parts,
                "status": "INSUFFICIENT", "reasons": reasons + ["need>=2-domains"]}
    wsum = sum(weights[k] for k in parts)
    score = sum(parts[k] * weights[k] for k in parts) / wsum
    score = round(score, 1)
    sent = "BULLISH" if score >= 60 else ("BEARISH" if score <= 40 else "NEUTRAL")
    status = "LIVE" if len(parts) >= 4 else "DEGRADED"
    return {"score": score, "sentiment": sent, "domains": parts, "status": status,
            "reasons": reasons, "regime": str(regime or "UNKNOWN")}
