"""
Live Contract Cache — FYERS option chain as source of truth for tradable symbols.

The formula builder in contract_resolver derives symbols from weekday rules.
Those rules rot (Sep-2025 expiry harmonization, FYERS weekly M-code). The
chain API returns the broker's own symbol per strike plus live bid/ask —
that is authoritative. This cache refreshes it in the background; the sync
resolver consults it first and falls back to the formula offline.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_FILE = Path("live_contracts_cache.json")
REFRESH_INTERVAL_MS = 60_000


class LiveStrikeInfo(BaseModel):
    broker_symbol: str
    underlying: str
    expiry_date: date
    strike: int
    option_type: str
    bid: float = 0.0
    ask: float = 0.0
    ltp: float = 0.0
    fetched_at_ms: int = Field(default_factory=lambda: int(time.time() * 1000))

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return round((self.bid + self.ask) / 2.0, 2)
        return round(self.ltp, 2)


def _today_ist() -> date:
    return datetime.now(IST).date()


def _key(underlying: str, expiry: date, strike: int, option_type: str) -> str:
    return f"{underlying.upper()}|{expiry.isoformat()}|{int(strike)}|{option_type.upper()}"


class LiveContractCache:
    """Thread-safe live strike map with local JSON persistence."""

    def __init__(self) -> None:
        import threading
        self._lock = threading.RLock()
        self._map: dict[str, LiveStrikeInfo] = {}
        self._last_refresh_ms: int = 0
        self._refresh_task: Optional[asyncio.Task] = None
        self.restore()

    # ── persistence ──
    def save(self) -> None:
        try:
            payload = {
                "updated_at_ms": int(time.time() * 1000),
                "strikes": {k: v.model_dump(mode="json") for k, v in self._map.items()},
            }
            tmp = CACHE_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, default=str)
            tmp.replace(CACHE_FILE)
        except Exception as e:
            logger.debug("live_contracts_save_failed", error=str(e)[:150])

    def restore(self) -> int:
        try:
            if not CACHE_FILE.exists() or CACHE_FILE.stat().st_size <= 10:
                return 0
            payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            count = 0
            for k, v in (payload.get("strikes") or {}).items():
                try:
                    info = LiveStrikeInfo(**v)
                    self._map[str(k)] = info
                    count += 1
                except Exception:
                    continue
            return count
        except Exception:
            return 0

    # ── sync read path (used by the formula resolver) ──
    def lookup(
        self,
        underlying: str,
        expiry: date,
        strike: int,
        option_type: str,
    ) -> Optional[LiveStrikeInfo]:
        """True broker symbol for an exact (underlying, expiry, strike, type).

        Only serves entries fetched during the current IST session — a
        yesterday-expiry symbol must never leak into today's orders.
        """
        try:
            info = self._map.get(_key(underlying, expiry, strike, option_type))
            if info is None:
                return None
            fetched_day = datetime.fromtimestamp(info.fetched_at_ms / 1000.0, tz=IST).date()
            if fetched_day != _today_ist():
                return None
            if not info.broker_symbol or info.broker_symbol.endswith("_OPT"):
                return None
            return info
        except Exception:
            return None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "strikes": len(self._map),
                "last_refresh_ms": self._last_refresh_ms,
                "age_ms": int(time.time() * 1000) - self._last_refresh_ms if self._last_refresh_ms else -1,
            }

    # ── background refresh ──
    def refresh_due(self) -> bool:
        return int(time.time() * 1000) - self._last_refresh_ms >= REFRESH_INTERVAL_MS

    async def refresh(self, market_svc: Any = None) -> int:
        """Pull fresh chains for the approved universe. Returns strike count."""
        from app.signals.contract_resolver import APPROVED_UNDERLYINGS

        if market_svc is None:
            try:
                from app.services.market_service import MarketService
                market_svc = MarketService()
            except Exception as e:
                logger.debug("live_contracts_no_market_svc", error=str(e)[:150])
                return 0
        added = 0
        for u in sorted(APPROVED_UNDERLYINGS):
            try:
                chain = await market_svc.get_option_chain(u)
            except Exception as e:
                logger.debug("live_contracts_chain_failed", underlying=u, error=str(e)[:150])
                continue
            now_ms = int(time.time() * 1000)
            for q in chain or []:
                try:
                    sym = str(getattr(q, "contract_id", "") or "").strip()
                    if not sym or ":" not in sym or sym.endswith("_OPT"):
                        continue
                    exp = getattr(q, "expiry", None)
                    exp_date = exp.date() if isinstance(exp, datetime) else exp
                    if not isinstance(exp_date, date):
                        continue
                    strike = int(float(getattr(q, "strike", 0) or 0))
                    otype = str(getattr(q, "option_type", "") or "").upper()
                    if strike <= 0 or otype not in ("CE", "PE"):
                        continue
                    info = LiveStrikeInfo(
                        broker_symbol=sym,
                        underlying=u,
                        expiry_date=exp_date,
                        strike=strike,
                        option_type=otype,
                        bid=float(getattr(q, "bid", 0) or 0),
                        ask=float(getattr(q, "ask", 0) or 0),
                        ltp=float(getattr(q, "ltp", 0) or 0),
                        fetched_at_ms=now_ms,
                    )
                    with self._lock:
                        self._map[_key(u, exp_date, strike, otype)] = info
                    added += 1
                except Exception:
                    continue
        with self._lock:
            self._last_refresh_ms = int(time.time() * 1000)
        if added:
            self.save()
            logger.info("live_contracts_refreshed", strikes=added)
        return added

    def schedule_refresh(self, market_svc: Any = None) -> None:
        """Fire-and-forget refresh, at most one in flight, min interval honored."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if not self.refresh_due():
            return
        if self._refresh_task is not None and not self._refresh_task.done():
            return
        # Reserve the slot now so concurrent ticks don't stampede.
        with self._lock:
            self._last_refresh_ms = int(time.time() * 1000)
        self._refresh_task = loop.create_task(self._guarded_refresh(market_svc))

    async def _guarded_refresh(self, market_svc: Any = None) -> None:
        try:
            # Release the reservation so a real refresh runs now.
            with self._lock:
                self._last_refresh_ms = 0
            await self.refresh(market_svc)
        except Exception as e:
            logger.debug("live_contracts_refresh_err", error=str(e)[:150])


live_contract_cache = LiveContractCache()
