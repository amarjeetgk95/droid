"""Options-flow engine: ΔOI velocity, writing pressure, ATM pressure, skew (PIT-stamped).

Takes CURRENT chain snapshot + PREVIOUS snapshot (same instrument) and returns
flow features. No previous snapshot -> all flow fields None + status
INSUFFICIENT_DATA (never zero-filled). Pure apart from timestamps.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _num(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def compute_options_flow(current: Dict[str, Any] | None, previous: Dict[str, Any] | None) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    base = {
        "status": "INSUFFICIENT_DATA",
        "timestamp": now.isoformat(),
        "available_time": (current or {}).get("available_time", now.isoformat()),
        "timestamp_ms": (current or {}).get("timestamp_ms", int(now.timestamp() * 1000)),
        "ce_oi_change": None,
        "pe_oi_change": None,
        "ce_oi_change_pct": None,
        "pe_oi_change_pct": None,
        "net_write_pressure": None,  # +1 put-writing .. -1 call-writing
        "atm_pressure": None,  # +1 support .. -1 resistance from walls
        "iv_skew": None,  # put95-call105 when greeks/iv surface present
        "short_covering_hint": False,
        "reasons": [],
    }
    if not current or not previous:
        base["reasons"].append("need current+previous snapshots for dOI")
        return base
    try:
        ce_now = _num(current.get("total_call_oi"))
        pe_now = _num(current.get("total_put_oi"))
        ce_prev = _num(previous.get("total_call_oi"))
        pe_prev = _num(previous.get("total_put_oi"))
        if ce_now is None or pe_now is None or ce_prev is None or pe_prev is None:
            base["reasons"].append("missing OI totals")
            return base
        ce_chg = ce_now - ce_prev
        pe_chg = pe_now - pe_prev
        out = dict(base)
        out.update(
            {
                "status": "LIVE",
                "ce_oi_change": round(ce_chg, 0),
                "pe_oi_change": round(pe_chg, 0),
                "ce_oi_change_pct": round(ce_chg / max(1.0, ce_prev) * 100.0, 3),
                "pe_oi_change_pct": round(pe_chg / max(1.0, pe_prev) * 100.0, 3),
            }
        )
        # Writing pressure: rising PE OI + flat/falling CE OI = put writing (+).
        tot = abs(ce_chg) + abs(pe_chg)
        if tot > 0:
            out["net_write_pressure"] = round((pe_chg - ce_chg) / tot, 3)
        # ATM pressure from walls.
        spot = _num(current.get("spot"))
        cw = current.get("call_wall")
        pw = current.get("put_wall")
        try:
            if spot and cw and pw:
                cw_f, pw_f = float(cw), float(pw)
                # +1 when spot nearer put wall (support), -1 nearer call wall.
                dc = abs(cw_f - spot)
                dp = abs(spot - pw_f)
                out["atm_pressure"] = round((dc - dp) / max(1.0, dc + dp), 3)
        except Exception:
            pass
        # IV skew passthrough when computed upstream.
        skew = current.get("iv_skew", current.get("skew"))
        if skew is not None:
            try:
                out["iv_skew"] = round(float(skew), 3)
            except Exception:
                pass
        # Short-covering hint: PE OI falling fast while price holds/rises is
        # evaluated downstream with price; here flag only the OI leg.
        if out["pe_oi_change_pct"] is not None and out["pe_oi_change_pct"] < -1.5:
            out["short_covering_hint"] = True
        out["reasons"].append("dOI-from-consecutive-snapshots")
        return out
    except Exception as e:
        base["reasons"].append(f"failed:{str(e)[:120]}")
        return base
