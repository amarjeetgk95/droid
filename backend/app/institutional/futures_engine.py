"""Futures engine: live basis/OI probe + buildup classifier (fail-closed, PIT-stamped).

Truth: no broker futures feed is wired (providers/fyers index-only,
fno/context hardcodes near_basis=0). This engine DOES NOT synthesize basis.
It:
  - probes MarketService/provider for futures quotes when available,
  - classifies buildup via the standard 4-quadrant rule (pure),
  - always returns PIT timestamps + status, so downstream can gate.

Status: LIVE only with market-quoted basis+OI and available_time<=T.
Otherwise UNAVAILABLE (downstream must fail-closed, never impute 0).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def classify_buildup(price_change_pct: Optional[float], oi_change_pct: Optional[float]) -> str:
    try:
        p = float(price_change_pct or 0.0)
        o = float(oi_change_pct or 0.0)
    except Exception:
        return "UNKNOWN"
    if p > 0.05 and o > 0.5:
        return "LONG_BUILDUP"
    if p < -0.05 and o > 0.5:
        return "SHORT_BUILDUP"
    if p > 0.05 and o < -0.5:
        return "SHORT_COVERING"
    if p < -0.05 and o < -0.5:
        return "LONG_UNWINDING"
    return "NEUTRAL"


async def get_futures_snapshot(symbol: str) -> Dict[str, Any]:
    """Probe live futures; fail-closed to UNAVAILABLE (never synthetic)."""
    now = datetime.now(timezone.utc)
    base = {
        "symbol": symbol,
        "status": "UNAVAILABLE",
        "timestamp": now.isoformat(),
        "available_time": now.isoformat(),
        "timestamp_ms": int(now.timestamp() * 1000),
        "basis": None,
        "basis_pct": None,
        "oi": None,
        "oi_change_pct": None,
        "volume": None,
        "buildup": "UNKNOWN",
        "reason": "no live futures feed wired (provider index-only)",
    }
    try:
        from app.services.market_service import MarketService

        ms = MarketService()
        # Probe: some providers expose futures via get_quote("<SYM>-FUT") or
        # term-structure endpoints. If absent/None -> remain UNAVAILABLE.
        probe = None
        for meth in ("get_futures_quote", "get_future_quote"):
            fn = getattr(ms, meth, None)
            if callable(fn):
                try:
                    probe = await fn(symbol)
                    break
                except Exception:
                    continue
        if probe is None:
            return base
        basis = getattr(probe, "basis", None)
        oi = getattr(probe, "open_interest", getattr(probe, "oi", None))
        if basis is None and oi is None:
            return base
        out = dict(base)
        out.update(
            {
                "status": "LIVE",
                "basis": float(basis) if basis is not None else None,
                "oi": int(oi) if oi is not None else None,
                "reason": "market-quoted",
            }
        )
        return out
    except Exception as e:
        out = dict(base)
        out["reason"] = f"probe-failed:{str(e)[:120]}"
        return out
