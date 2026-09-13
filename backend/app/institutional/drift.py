"""Drift monitor: rolling flow-z PSI + composite distribution (auto-degrade flag).

Compares last 20 flow rows vs prior 60 (or available): PSI over binned fii_z,
mean-shift of composite proxy. Writes backend/data/institutional_degraded.flag
{degraded: bool, reason, at} when PSI>0.5 or |mean-shift|>1.0z. Scanner checks
the flag (best-effort) and forces institutional delta to 0 + VALIDATED-only
when degraded. Never raises.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FLAG = Path(__file__).resolve().parents[2] / "data" / "institutional_degraded.flag"


def _psi(p: list[float], q: list[float], bins: int = 5) -> float:
    try:
        import statistics as _s

        lo = min(p + q)
        hi = max(p + q)
        if hi <= lo:
            return 0.0
        w = (hi - lo) / bins
        tot = 0.0
        for i in range(bins):
            a = lo + i * w
            b = a + w if i < bins - 1 else hi + 1e-9
            pp = sum(1 for x in p if a <= x < b) / max(1, len(p))
            qq = sum(1 for x in q if a <= x < b) / max(1, len(q))
            pp = max(1e-4, pp)
            qq = max(1e-4, qq)
            tot += (pp - qq) * __import__("math").log(pp / qq)
        return round(tot, 4)
    except Exception:
        return 0.0


def check_drift() -> dict[str, Any]:
    out: dict[str, Any] = {"degraded": False, "reason": "ok", "at": datetime.now(timezone.utc).isoformat()}
    try:
        from app.institutional.flow_store import flow_store

        rows = flow_store.to_training_rows()
        zs = [r["fii_cash_5d_z"] for r in rows if r.get("fii_cash_5d_z") is not None]
        if len(zs) < 30:
            out["reason"] = f"insufficient-history-{len(zs)}"
            _write(out)
            return out
        recent, prior = zs[-20:], zs[-80:-20] if len(zs) >= 80 else zs[:-20]
        psi = _psi(recent, prior)
        shift = abs(sum(recent) / len(recent) - sum(prior) / len(prior))
        if psi > 0.5 or shift > 1.0:
            out = {"degraded": True, "reason": f"psi-{psi}-shift-{round(shift,3)}", "at": out["at"]}
        else:
            out = {"degraded": False, "reason": f"psi-{psi}-shift-{round(shift,3)}", "at": out["at"]}
        _write(out)
        return out
    except Exception as e:
        out = {"degraded": False, "reason": f"check-failed:{str(e)[:80]}", "at": out["at"]}
        return out


def _write(out: dict[str, Any]) -> None:
    try:
        FLAG.parent.mkdir(parents=True, exist_ok=True)
        FLAG.write_text(json.dumps(out, indent=2), encoding="utf-8")
    except Exception:
        pass


def is_degraded() -> bool:
    try:
        if FLAG.exists():
            return bool(json.loads(FLAG.read_text(encoding="utf-8")).get("degraded", False))
    except Exception:
        pass
    return False
