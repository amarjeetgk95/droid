"""Breadth + VIX-rank engines (honest proxy labels, PIT-stamped, rolling).

Breadth truth: no NSE advance/decline feed is wired; MarketService aggregates
5 index quotes as a proxy (see services/market_service breadth). This engine
labels it proxy, timestamps it, and adds a percentile vs its own rolling
history (persisted to backend/data/breadth_history.json, best-effort).

VIX truth: India VIX quote IS live (regime_service). This engine adds
rank/percentile over a rolling window (persisted to backend/data/vix_history.json).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.atomic_json import atomic_write_json, read_json

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load(path: Path) -> List[float]:
    v = read_json(path)
    if isinstance(v, list):
        try:
            return [float(x) for x in v[-120:]]
        except Exception:
            return []
    return []


def _save(path: Path, vals: List[float]) -> None:
    atomic_write_json(
        path,
        vals[-120:],
        create_parents=True,
        log_event="market_engine_history_persist_failed",
        log_level="debug",
    )


def _pct_rank(val: float, hist: List[float]) -> Optional[float]:
    if len(hist) < 10:
        return None
    try:
        below = sum(1 for x in hist if x <= val)
        return round(below / max(1, len(hist)) * 100.0, 1)
    except Exception:
        return None


async def get_breadth_snapshot() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    out: Dict[str, Any] = {
        "status": "PROXY",
        "source": "5-index-quote-proxy (NOT NSE advance/decline)",
        "timestamp": now.isoformat(),
        "available_time": now.isoformat(),
        "timestamp_ms": int(now.timestamp() * 1000),
        "advances": None,
        "declines": None,
        "ad_ratio": None,
        "ad_percentile": None,
    }
    try:
        from app.services.market_service import MarketService

        ms = MarketService()
        fn = getattr(ms, "get_breadth", None) or getattr(ms, "get_market_breadth", None)
        if fn is None:
            out["status"] = "UNAVAILABLE"
            out["reason"] = "no breadth method on MarketService"
            return out
        b = await fn() if callable(fn) else None
        adv = getattr(b, "advances", None) if not isinstance(b, dict) else b.get("advances")
        dec = getattr(b, "declines", None) if not isinstance(b, dict) else b.get("declines")
        if adv is None or dec is None:
            out["reason"] = "breadth payload missing advances/declines"
            return out
        out["advances"] = int(adv)
        out["declines"] = int(dec)
        tot = max(1, int(adv) + int(dec))
        out["ad_ratio"] = round(int(adv) / tot, 4)
        hist = _load(DATA_DIR / "breadth_history.json")
        out["ad_percentile"] = _pct_rank(out["ad_ratio"], hist)
        hist.append(out["ad_ratio"])
        _save(DATA_DIR / "breadth_history.json", hist)
        return out
    except Exception as e:
        out["status"] = "UNAVAILABLE"
        out["reason"] = f"probe-failed:{str(e)[:120]}"
        return out


async def get_vix_snapshot() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    out: Dict[str, Any] = {
        "status": "UNAVAILABLE",
        "source": "INDIA VIX quote",
        "timestamp": now.isoformat(),
        "available_time": now.isoformat(),
        "timestamp_ms": int(now.timestamp() * 1000),
        "vix": None,
        "vix_percentile": None,
        "vix_rank_note": "percentile over rolling local history (needs 10+ samples)",
    }
    try:
        from app.services.regime_service import regime_service

        info = await regime_service.get_vix_regime()
        v = getattr(info, "vix", None) if not isinstance(info, dict) else info.get("vix", info.get("value"))
        if v is None:
            out["reason"] = "vix quote missing"
            return out
        out["vix"] = round(float(v), 2)
        out["status"] = "LIVE"
        hist = _load(DATA_DIR / "vix_history.json")
        out["vix_percentile"] = _pct_rank(out["vix"], hist)
        hist.append(out["vix"])
        _save(DATA_DIR / "vix_history.json", hist)
        return out
    except Exception as e:
        out["reason"] = f"probe-failed:{str(e)[:120]}"
        return out
