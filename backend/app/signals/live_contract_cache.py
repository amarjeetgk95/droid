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
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field
import structlog

from app.core.atomic_json import atomic_write_json, read_json

logger = structlog.get_logger()

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_FILE = Path("live_contracts_cache.json")
REFRESH_INTERVAL_MS = 60_000


#: A chain row older than this is not a live mark (one refresh cycle + slack).
CHAIN_ROW_MAX_AGE_MS = 90_000


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
    def spread_healthy(self) -> bool:
        """True only when both sides are positive and uncrossed (ask >= bid)."""
        try:
            return float(self.bid) > 0 and float(self.ask) > 0 and float(self.ask) >= float(self.bid)
        except Exception:
            return False

    @property
    def mid(self) -> float:
        # Fail-closed mid: a crossed book (ask < bid) or a zero side is never
        # averaged — fall back to the broker LTP instead of a fabricated mid.
        if self.spread_healthy:
            return round((self.bid + self.ask) / 2.0, 2)
        return round(self.ltp, 2)

    def quote_mid(self, allow_stale: bool = False) -> float:
        """Strict mid: 0.0 when the book is crossed/empty unless explicitly allowed.

        ``allow_stale=True`` falls back to the (possibly LTP-derived) ``mid``
        for display-only paths; pricing paths must keep the default and treat
        0.0 as "no usable mark".
        """
        if self.spread_healthy:
            return round((self.bid + self.ask) / 2.0, 2)
        if allow_stale:
            return round(self.ltp, 2)
        return 0.0

    def age_ms(self, now_ms: int | None = None) -> int:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        try:
            return max(0, now - int(self.fetched_at_ms))
        except Exception:
            return 0

    def is_fresh(self, max_age_ms: int = CHAIN_ROW_MAX_AGE_MS, now_ms: int | None = None) -> bool:
        return self.age_ms(now_ms) <= max_age_ms


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
            atomic_write_json(
                CACHE_FILE,
                payload,
                log_event="live_contracts_save_failed",
                log_level="debug",
                max_error_chars=150,
            )
        except Exception as e:
            logger.debug("live_contracts_save_failed", error=str(e)[:150])

    def restore(self) -> int:
        try:
            if not CACHE_FILE.exists() or CACHE_FILE.stat().st_size <= 10:
                return 0
            payload = read_json(CACHE_FILE, default={})
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
        max_age_ms: int = CHAIN_ROW_MAX_AGE_MS,
        allow_stale: bool = False,
    ) -> Optional[LiveStrikeInfo]:
        """True broker symbol for an exact (underlying, expiry, strike, type).

        Only serves entries fetched during the current IST session — a
        yesterday-expiry symbol must never leak into today's orders. Rows
        older than ``max_age_ms`` (default 90s) are stale and rejected, and a
        crossed/empty book is rejected unless ``allow_stale`` is explicit.
        """
        try:
            info = self._map.get(_key(underlying, expiry, strike, option_type))
            if info is None:
                return None
            fetched_day = datetime.fromtimestamp(info.fetched_at_ms / 1000.0, tz=IST).date()
            if fetched_day != _today_ist():
                return None
            if not allow_stale and info.age_ms() > max_age_ms:
                return None
            if not info.broker_symbol or info.broker_symbol.endswith("_OPT"):
                return None
            if not allow_stale:
                # Crossed book or empty book with no LTP fallback: no mark.
                if info.bid and info.ask and float(info.ask) < float(info.bid):
                    return None
                if not info.spread_healthy and not (info.ltp and float(info.ltp) > 0):
                    return None
            return info
        except Exception:
            return None

    def find_by_symbol(
        self,
        broker_symbol: str,
        max_age_ms: int = CHAIN_ROW_MAX_AGE_MS,
        allow_stale: bool = False,
    ) -> Optional[LiveStrikeInfo]:
        """Reverse lookup: exact broker symbol -> strike info (current session).

        The cache is keyed by (underlying, expiry, strike, type); the mark
        registry is keyed by broker symbol. This bridges the two without
        scanning, and enforces the same same-session/freshness rules as `lookup`.
        """
        if not broker_symbol:
            return None
        target = str(broker_symbol).strip()
        if not target:
            return None
        try:
            with self._lock:
                candidates = list(self._map.values())
            for info in candidates:
                if info.broker_symbol != target:
                    continue
                fetched_day = datetime.fromtimestamp(info.fetched_at_ms / 1000.0, tz=IST).date()
                if fetched_day != _today_ist():
                    return None
                if not allow_stale and info.age_ms() > max_age_ms:
                    return None
                if not allow_stale and info.bid and info.ask and float(info.ask) < float(info.bid):
                    return None
                return info
        except Exception:
            return None
        return None

    def snapshot(self) -> dict[str, LiveStrikeInfo]:
        """Same-session filtered view of the strike map for read-only consumers.

        Stale rows (fetched on a prior IST day) and expired contracts
        (expiry before today IST) are never served — consumers must not see
        yesterday's symbols as today's tradables.
        """
        today = _today_ist()
        with self._lock:
            out: dict[str, LiveStrikeInfo] = {}
            for k, info in self._map.items():
                try:
                    fetched_day = datetime.fromtimestamp(info.fetched_at_ms / 1000.0, tz=IST).date()
                    if fetched_day != today:
                        continue
                    if info.expiry_date < today:
                        continue
                    out[k] = info
                except Exception:
                    continue
            return out

    def purge_expired(self) -> int:
        """Drop expired/stale rows (expiry before today IST, or fetched on a
        prior session and older than one refresh cycle). Returns drop count."""
        today = _today_ist()
        now_ms = int(time.time() * 1000)
        dropped = 0
        with self._lock:
            for k in list(self._map.keys()):
                info = self._map.get(k)
                if info is None:
                    continue
                try:
                    expired = info.expiry_date < today
                    try:
                        fetched_day = datetime.fromtimestamp(info.fetched_at_ms / 1000.0, tz=IST).date()
                    except Exception:
                        fetched_day = today
                    stale_session = fetched_day != today and (now_ms - int(info.fetched_at_ms)) > REFRESH_INTERVAL_MS
                    if expired and (fetched_day != today or (now_ms - int(info.fetched_at_ms)) > REFRESH_INTERVAL_MS):
                        self._map.pop(k, None)
                        dropped += 1
                    elif stale_session:
                        self._map.pop(k, None)
                        dropped += 1
                except Exception:
                    continue
        return dropped

    def register_mark_info(
        self,
        underlying: str,
        expiry: date,
        strike: int,
        option_type: str,
        bid: float,
        ask: float,
        ltp: float,
        broker_symbol: str,
    ) -> None:
        """Upsert a single strike's mark without a full chain refetch.

        Used by the Tier-1 held-contract poller: it refreshes the price of a
        contract we already hold, so the entry resolver and the mark registry
        see current bid/ask rather than a 60s-old chain row.
        """
        try:
            sym = str(broker_symbol or "").strip()
            if not sym or strike <= 0:
                return
            otype = str(option_type or "").upper()
            if otype not in ("CE", "PE"):
                return
            info = LiveStrikeInfo(
                broker_symbol=sym,
                underlying=str(underlying or "").upper(),
                expiry_date=expiry,
                strike=int(strike),
                option_type=otype,
                bid=float(bid or 0),
                ask=float(ask or 0),
                ltp=float(ltp or 0),
                fetched_at_ms=int(time.time() * 1000),
            )
            with self._lock:
                self._map[_key(underlying, expiry, int(strike), otype)] = info
            try:
                from app.signals.option_marks import option_mark_service
                option_mark_service.register_chain_strike(info)
            except Exception:
                pass
        except Exception as e:
            logger.debug("live_contracts_register_mark_failed", error=str(e)[:150])

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
                    try:
                        from app.signals.option_marks import option_mark_service
                        option_mark_service.register_chain_strike(info)
                    except Exception:
                        pass
                    added += 1
                except Exception:
                    continue
        with self._lock:
            self._last_refresh_ms = int(time.time() * 1000)
        # Background hygiene: drop contracts whose expiry is before today IST
        # (and prior-session stale rows) so dead symbols never leak forward.
        try:
            purged = self.purge_expired()
            if purged:
                logger.info("live_contracts_purged_expired", purged=purged)
        except Exception:
            pass
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
