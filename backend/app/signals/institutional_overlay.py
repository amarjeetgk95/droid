"""Institutional overlay: regime-conditioned flow interpretation + divergence guard.

Pure functions (no I/O) so they are unit-testable and auditable.

Design (honest, capped):
- Flow snapshot is DAILY (T+1 available). It must NEVER flip an intraday
  signal by itself. Max adjustment is +-5 fused points, applied inside
  confluence.fuse() AFTER the linear blend, and only when pit_ok and
  fno not degraded-beyond-use.
- Regime conditioning: same FII print means different things:
    TREND_DOWN + FII selling (z<0) + futures net short -> bearish confirm (+ toward SHORT)
    RANGE/COMPRESSION + same selling -> muted (x0.25), never full bearish
    VOLATILE/EVENT -> capped further, needs stronger evidence
- Divergence guard (most important): FII selling + price holding support +
  short-covering/put-writing signals -> possible bullish divergence:
  suppress SHORT ARMED -> force VALIDATED (watch-only), never auto-execute.
  Symmetric for LONG.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


def _regime_family(regime: Any) -> str:
    r = str(regime or "").upper()
    if "TREND_DOWN" in r or "BEAR" in r:
        return "TREND_DOWN"
    if "TREND_UP" in r or "BULL" in r:
        return "TREND_UP"
    if "VOLAT" in r or "EVENT" in r or "HIGH_VOL" in r:
        return "VOLATILE"
    if "COMPRESS" in r or "RANGE" in r or "SIDEWAYS" in r:
        return "RANGE"
    if "TREND" in r:
        return "TREND"
    return "UNKNOWN"


def compute_institutional_adjustment(
    direction: str,
    regime: Any,
    flow: Any,
    fno: Dict[str, Any] | None = None,
    participation: Dict[str, Any] | None = None,
) -> Tuple[float, Dict[str, Any]]:
    """Return (delta_points in [-5,+5], info dict).

    Positive delta = supports candidate direction; negative = contradicts.
    Downgrade flag forces VALIDATED when divergence is detected.
    """
    info: Dict[str, Any] = {
        "applied": False,
        "delta": 0.0,
        "reasons": [],
        "downgrade_to_validated": False,
        "regime_family": _regime_family(regime),
        "flow_event_date": None,
    }
    if flow is None or getattr(flow, "pit_ok", False) is not True:
        info["reasons"].append("no-pit-safe-flow")
        return 0.0, info
    info["flow_event_date"] = getattr(flow, "event_date", None)

    is_call = "CALL" in str(direction or "").upper()
    fam = info["regime_family"]
    fno = fno or {}
    participation = participation or {}

    fii_z = getattr(flow, "fii_cash_5d_z", None)
    dii_z = getattr(flow, "dii_cash_5d_z", None)
    fii_net = getattr(flow, "fii_fut_net", None)
    lsr = getattr(flow, "fii_lsr", None)

    # Base institutional bias from daily flow: +1 bullish .. -1 bearish.
    bias = 0.0
    if isinstance(fii_z, (int, float)):
        bias += max(-1.0, min(1.0, float(fii_z) / 2.0)) * 0.6
    if isinstance(dii_z, (int, float)):
        bias += max(-1.0, min(1.0, float(dii_z) / 2.0)) * 0.4
    if isinstance(lsr, (int, float)):
        try:
            if float(lsr) > 1.05:
                bias += 0.25
            elif float(lsr) < 0.95:
                bias -= 0.25
        except Exception:
            pass
    if isinstance(fii_net, (int, float)):
        try:
            if float(fii_net) > 0:
                bias += 0.15
            elif float(fii_net) < 0:
                bias -= 0.15
        except Exception:
            pass
    bias = max(-1.0, min(1.0, bias))

    # Alignment with candidate: +1 aligned, -1 opposed.
    align = 0.0
    if bias > 0.15 and is_call:
        align = 1.0
    elif bias < -0.15 and not is_call:
        align = 1.0
    elif bias > 0.15 and not is_call:
        align = -1.0
    elif bias < -0.15 and is_call:
        align = -1.0
    else:
        info["reasons"].append(f"flow-neutral-bias-{bias:.2f}")
        return 0.0, info

    # Regime-conditioned weight (same print, different meaning).
    if fam in ("TREND_DOWN", "TREND_UP", "TREND"):
        w = 5.0
    elif fam == "RANGE":
        w = 1.25  # muted in sideways: 5 * 0.25
    elif fam == "VOLATILE":
        w = 2.5
    else:
        w = 2.0
    # Expiry/DTE guard: options weight halves on DTE<=1 (mirror forecast gate).
    try:
        dte = fno.get("distance_to_expiry_days", fno.get("days_to_expiry"))
        if dte is not None and float(dte) <= 1.0:
            w *= 0.5
            info["reasons"].append("dte<=1-halved")
    except Exception:
        pass

    delta = round(align * w, 2)
    delta = max(-5.0, min(5.0, delta))
    info["applied"] = True
    info["delta"] = delta
    info["reasons"].append(f"flow-bias-{bias:.2f}-align-{align:.0f}-regime-{fam}-w-{w}")

    # Divergence guard: institutional selling BUT intraday structure shows
    # absorption (support hold + short-covering/put-writing).
    # Signals come from participation engine + fno walls; flow itself is daily.
    try:
        part_label = str(participation.get("label", participation.get("positioning", ""))).upper()
        support_hold = bool(participation.get("support_hold", False))
        put_writing = bool(participation.get("put_writing", False)) or "PUT" in str(fno.get("buildup_note", "")).upper()
        short_cover = "SHORT_COVER" in part_label or "COVER" in part_label
        fii_selling = isinstance(fii_z, (int, float)) and float(fii_z) < -0.5
        fii_buying = isinstance(fii_z, (int, float)) and float(fii_z) > 0.5
        if not is_call and fii_selling and (support_hold or short_cover or put_writing):
            info["downgrade_to_validated"] = True
            info["reasons"].append("bearish-divergence-short-covering-absorption-force-VALIDATED")
        if is_call and fii_buying and (support_hold is False and ("SHORT_BUILDUP" in part_label or "CALL_WRITE" in part_label)):
            info["downgrade_to_validated"] = True
            info["reasons"].append("bullish-divergence-call-supply-force-VALIDATED")
    except Exception as e:
        info["reasons"].append(f"divergence-check-skipped:{e}")

    return delta, info
