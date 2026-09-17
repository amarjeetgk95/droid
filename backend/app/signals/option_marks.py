"""
Option Mark Authority — one priced answer per contract, with provenance.

The bug this module exists to kill: a signal's *entry* fill came from a real
FYERS option-chain quote (`contract_resolver` -> `live_premium`), while its
*mark-to-market* was recomputed by re-deriving a Black-76 premium from the
index spot. Two pricing bases in one audit record — so P&L drifted away from
the fill it was supposed to measure, and the displayed premium was a model
output dressed up as a market price.

Every mark now carries a `source`:

  CHAIN_BIDASK   real chain mid from broker bid/ask  — best
  CHAIN_LTP      real broker last-traded price       — good
  MODEL_BLACK76  Black-76 theoretical (explicitly labeled, never silent)
  UNAVAILABLE    no price at all — callers must fail closed, not fabricate

`MODEL_BLACK76` is a legitimate fallback, but it is *labeled*, so the ledger
and the UI can badge it and never confuse it with a broker print.
"""
from __future__ import annotations

import time
from typing import Any, Iterable, Optional
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

# ── Provenance ranks ──
CHAIN_BIDASK = "CHAIN_BIDASK"
CHAIN_LTP = "CHAIN_LTP"
MODEL_BLACK76 = "MODEL_BLACK76"
UNAVAILABLE = "UNAVAILABLE"

#: Ranked best → worst. Used to decide whether an incoming mark is an upgrade.
_SOURCE_RANK = {CHAIN_BIDASK: 3, CHAIN_LTP: 2, MODEL_BLACK76: 1, UNAVAILABLE: 0}

#: A mark older than this cannot price an exit or an MTM tick.
DEFAULT_TTL_MS = 5_000

#: Chain (Tier-2) marks stay valid for one refresh cycle + slack.
CHAIN_TTL_MS = 90_000

#: P1 usability gates — spread as % of premium, age per desk, liquidity floors.
MAX_SPREAD_PCT = 2.5
SCALP_MAX_AGE_MS = 15_000
INTRADAY_MAX_AGE_MS = 60_000
MIN_OI_CONTRACTS = 1000
MIN_VOLUME_CONTRACTS = 50
STALE_IV_DTE_DAYS = 1.0

#: Max contracts per /data/quotes call. FYERS accepts long comma lists but we
#: keep batches modest so a slow response cannot stall the 3s risk loop.
MAX_SYMBOLS_PER_FETCH = 50


def source_rank(source: str) -> int:
    """Higher is better. Unknown sources rank as UNAVAILABLE."""
    return _SOURCE_RANK.get(str(source or "").upper(), 0)


def is_chain_source(source: str) -> bool:
    return str(source or "").upper() in (CHAIN_BIDASK, CHAIN_LTP)


class OptionMark(BaseModel):
    """A single priced observation of one option contract."""

    broker_symbol: str
    underlying: str = ""
    strike: float = 0.0
    option_type: str = ""
    expiry: Optional[str] = None

    bid: Optional[float] = None
    ask: Optional[float] = None
    ltp: Optional[float] = None

    # Liquidity / vol context (when the chain row carries it).
    oi: Optional[float] = None
    volume: Optional[float] = None
    iv: Optional[float] = None

    source: str = UNAVAILABLE
    #: When the underlying observation was taken (epoch ms).
    as_of_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    #: Free-text provenance detail (e.g. "black76 dte=3.0 iv=0.15 spot=24880").
    note: Optional[str] = None

    # ── price accessors ──
    @property
    def mid(self) -> Optional[float]:
        """Bid/ask mid when both sides are real, else None."""
        if self.bid and self.ask and self.bid > 0 and self.ask > 0 and self.ask >= self.bid:
            return round((self.bid + self.ask) / 2.0, 2)
        return None

    @property
    def price(self) -> Optional[float]:
        """The single number to mark against: chain mid, else LTP, else None."""
        m = self.mid
        if m is not None and m > 0:
            return m
        if self.ltp is not None and self.ltp > 0:
            return round(float(self.ltp), 2)
        return None

    @property
    def spread_pts(self) -> Optional[float]:
        """Ask - bid when both sides are real, else None (unknown, not zero)."""
        try:
            if self.bid and self.ask and self.bid > 0 and self.ask > 0 and self.ask >= self.bid:
                return round(float(self.ask) - float(self.bid), 2)
        except Exception:
            pass
        return None

    @property
    def spread_pct(self) -> Optional[float]:
        """Spread as % of executable premium (mid else LTP). None when unknown."""
        sp = self.spread_pts
        px = self.price
        if sp is None or px is None or px <= 0:
            return None
        try:
            return round(sp / float(px) * 100.0, 2)
        except Exception:
            return None

    def executable_buy(self, slip_pts: float = 0.0) -> Optional[float]:
        """BUY fills at ask + slip (never at mid). None when no ask."""
        try:
            if self.ask is not None and float(self.ask) > 0:
                return round(float(self.ask) + max(0.0, float(slip_pts or 0.0)), 2)
            # LTP-only mark: no executable ask — caller must fail closed upstream.
            return None
        except Exception:
            return None

    def executable_sell(self, slip_pts: float = 0.0) -> Optional[float]:
        """SELL fills at bid - slip (never at mid). None when no bid."""
        try:
            if self.bid is not None and float(self.bid) > 0:
                return round(float(self.bid) - max(0.0, float(slip_pts or 0.0)), 2)
            return None
        except Exception:
            return None

    @property
    def buy_at(self) -> Optional[float]:
        """Executable buy (ask). Prefer executable_buy(slip) for slippage."""
        return self.executable_buy(0.0)

    @property
    def sell_at(self) -> Optional[float]:
        """Executable sell (bid). Prefer executable_sell(slip) for slippage."""
        return self.executable_sell(0.0)

    @property
    def is_stale_iv(self) -> bool:
        """Expiry-day model marks: IV is decaying too fast to trust."""
        try:
            if str(self.source or "").upper() != MODEL_BLACK76:
                return False
            note = str(self.note or "")
            if "STALE_IV" in note:
                return True
            # Parse dte= from the provenance note when present.
            import re
            m = re.search(r"dte=([0-9.]+)", note)
            if m and float(m.group(1)) <= STALE_IV_DTE_DAYS:
                return True
        except Exception:
            pass
        return False

    def usability_veto(self, desk: Optional[str] = None) -> Optional[str]:
        """P1 gate: spread%<=2.5% + OI/volume floors. None = pass.

        Unknown spread/OI (LTP-only marks) passes here — the desk-age gate in
        get_usable() still applies. Strict callers should require bid/ask via
        executable_buy/executable_sell returning non-None.
        """
        try:
            sp = self.spread_pct
            if sp is not None and sp > MAX_SPREAD_PCT:
                return f"WIDE_SPREAD_{sp:.1f}pct"
        except Exception:
            pass
        try:
            if self.oi is not None and float(self.oi) < MIN_OI_CONTRACTS:
                return f"LOW_OI_{float(self.oi):.0f}"
            if self.volume is not None and float(self.volume) < 0:
                return "BAD_VOLUME"
        except Exception:
            pass
        if self.is_stale_iv:
            return "STALE_IV"
        return None

    # ── provenance / freshness ──
    @property
    def is_chain(self) -> bool:
        return is_chain_source(self.source)

    @property
    def is_model(self) -> bool:
        return str(self.source or "").upper() == MODEL_BLACK76

    @property
    def is_usable(self) -> bool:
        """True when this mark can price something. Models count — they're labeled."""
        return str(self.source or "").upper() != UNAVAILABLE and self.price is not None

    def age_ms(self, now_ms: Optional[int] = None) -> int:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        return max(0, now - int(self.as_of_utc))

    def is_fresh(self, ttl_ms: int = DEFAULT_TTL_MS, now_ms: Optional[int] = None) -> bool:
        return self.age_ms(now_ms) <= ttl_ms

    def ttl_ms(self) -> int:
        """Chain marks tolerate the 60s refresh cadence; models are pure math."""
        return CHAIN_TTL_MS if self.is_chain else DEFAULT_TTL_MS
class OptionMarkRegistry:
    """Thread-safe last-known mark per broker symbol.

    Deliberately dumb storage — no fetching, no policy. The service below
    decides what to fetch; this just remembers the best answer seen.
    """

    def __init__(self) -> None:
        import threading
        self._lock = threading.RLock()
        self._marks: dict[str, OptionMark] = {}
        self._writes = 0

    def put(self, mark: Optional[OptionMark]) -> bool:
        """Store a mark if it is an upgrade. Returns True when stored.

        Upgrade = strictly better provenance, or equal provenance and newer.
        This stops a 60s chain refresh from clobbering a fresher Tier-1 LTP,
        and stops a Black-76 model mark from ever overwriting a broker print.
        """
        if mark is None or not mark.broker_symbol:
            return False
        sym = str(mark.broker_symbol).strip()
        mark.broker_symbol = sym
        with self._lock:
            cur = self._marks.get(sym)
            if cur is not None:
                new_rank = source_rank(mark.source)
                cur_rank = source_rank(cur.source)
                if new_rank < cur_rank:
                    return False
                if new_rank == cur_rank and int(mark.as_of_utc) < int(cur.as_of_utc):
                    return False
            self._marks[sym] = mark
            self._writes += 1
            return True

    def put_many(self, marks: Iterable[OptionMark]) -> int:
        return sum(1 for m in marks if self.put(m))

    def get(self, broker_symbol: Optional[str]) -> Optional[OptionMark]:
        if not broker_symbol:
            return None
        with self._lock:
            return self._marks.get(str(broker_symbol).strip())

    def get_usable(
        self,
        broker_symbol: Optional[str],
        ttl_ms: Optional[int] = None,
        allow_model: bool = True,
        desk: Optional[str] = None,
        max_spread_pct: Optional[float] = MAX_SPREAD_PCT,
        min_oi: Optional[float] = None,
        min_volume: Optional[float] = None,
    ) -> Optional[OptionMark]:
        """A mark fit to price with, else None (never a fabricated number).

        P1 gates: spread%<=2.5% (when quotable), age<=15s scalp / 60s
        intraday (when desk is known), OI/volume floors when enforced.
        Model marks keep the short 5s TTL and are rejected on expiry-day
        STALE_IV.
        """
        mark = self.get(broker_symbol)
        if mark is None or not mark.is_usable:
            return None
        if not allow_model and mark.is_model:
            return None
        # Desk-aware age gate overrides the generic TTL when stricter.
        effective_ttl = ttl_ms if ttl_ms is not None else mark.ttl_ms()
        try:
            d = str(desk or "").upper()
            if d == "SCALP":
                effective_ttl = min(effective_ttl, SCALP_MAX_AGE_MS if ttl_ms is None else ttl_ms)
            elif d in ("INTRADAY", "SWING", "POSITIONAL"):
                effective_ttl = min(effective_ttl, INTRADAY_MAX_AGE_MS if ttl_ms is None else ttl_ms)
        except Exception:
            pass
        if not mark.is_fresh(ttl_ms=effective_ttl):
            return None
        # Spread gate (only when the mark is quotable).
        try:
            sp = mark.spread_pct
            if max_spread_pct is not None and sp is not None and sp > float(max_spread_pct):
                return None
        except Exception:
            pass
        # OI / volume floors (only when the caller enforces them AND the
        # mark carries the field — unknown liquidity is not a veto here).
        try:
            if min_oi is not None and mark.oi is not None and float(mark.oi) < float(min_oi):
                return None
            if min_volume is not None and mark.volume is not None and float(mark.volume) < float(min_volume):
                return None
        except Exception:
            pass
        if mark.is_stale_iv:
            return None
        veto = mark.usability_veto()
        if veto is not None and veto.startswith(("WIDE_SPREAD", "STALE_IV")):
            return None
        return mark

    def snapshot(self) -> dict[str, OptionMark]:
        with self._lock:
            return dict(self._marks)

    def clear(self) -> None:
        with self._lock:
            self._marks.clear()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_source: dict[str, int] = {}
            for m in self._marks.values():
                by_source[m.source] = by_source.get(m.source, 0) + 1
            return {"marks": len(self._marks), "writes": self._writes, "by_source": by_source}


option_mark_registry = OptionMarkRegistry()


class OptionMarkService:
    """Fetches real broker marks and builds labeled model fallbacks."""

    # ── real marks from the broker ──
    async def fetch_chain_marks(self, broker_symbols: list[str]) -> dict[str, OptionMark]:
        """`/data/quotes` for exact contract symbols → real LTP marks.

        The FYERS quotes endpoint is instrument-agnostic: pass a contract
        symbol (`NSE:NIFTY26SEP25000CE`) and it returns that contract's LTP and
        OI, exactly as it does for an index. This is what makes Tier-1 mark
        freshness possible between 60s chain refreshes.

        Returns {} on any failure — callers fall back to the chain cache or a
        labeled model mark. Never raises.
        """
        syms = [str(s).strip() for s in (broker_symbols or []) if s and str(s).strip()]
        if not syms:
            return {}

        try:
            from app.providers import get_provider
            provider = get_provider()
        except Exception as e:
            logger.debug("option_marks_no_provider", error=str(e)[:150])
            return {}

        fetcher = getattr(provider, "_fetch_fyers_quotes", None)
        if fetcher is None:
            logger.debug(
                "option_marks_provider_lacks_quote_fetch",
                provider=getattr(provider, "provider_name", "?"),
            )
            return {}

        marks: dict[str, OptionMark] = {}
        now_ms = int(time.time() * 1000)

        for start in range(0, len(syms), MAX_SYMBOLS_PER_FETCH):
            batch = syms[start:start + MAX_SYMBOLS_PER_FETCH]
            try:
                quotes = await fetcher(batch)
            except Exception as e:
                logger.debug("option_marks_fetch_failed", count=len(batch), error=str(e)[:150])
                continue

            for sym, q in (quotes or {}).items():
                ltp = getattr(q, "ltp", None)
                if ltp is None or float(ltp) <= 0:
                    continue
                try:
                    _oi = getattr(q, "oi", getattr(q, "open_interest", None))
                    _oi_f = float(_oi) if _oi is not None else None
                except Exception:
                    _oi_f = None
                try:
                    _vol = getattr(q, "volume", None)
                    _vol_f = float(_vol) if _vol is not None else None
                except Exception:
                    _vol_f = None
                mark = OptionMark(
                    broker_symbol=str(sym),
                    ltp=round(float(ltp), 2),
                    oi=_oi_f,
                    volume=_vol_f,
                    source=CHAIN_LTP,
                    as_of_utc=now_ms,
                    note=f"data/quotes ltp provider={getattr(q, 'provider', '?')}",
                )
                # Upgrade to a bid/ask mid when the chain cache holds both
                # sides for this exact symbol — mid is the honest fill mark.
                marks[str(sym)] = self._upgrade_with_chain_cache(mark)

        return marks

    @staticmethod
    def _upgrade_with_chain_cache(mark: OptionMark) -> OptionMark:
        """Attach bid/ask/identity from the chain cache when the symbol is known."""
        try:
            from app.signals.live_contract_cache import live_contract_cache
            info = live_contract_cache.find_by_symbol(mark.broker_symbol)
            if info is None:
                return mark
            mark.bid = float(info.bid) if info.bid else None
            mark.ask = float(info.ask) if info.ask else None
            mark.underlying = mark.underlying or info.underlying
            mark.strike = mark.strike or float(info.strike)
            mark.option_type = mark.option_type or info.option_type
            mark.expiry = mark.expiry or info.expiry_date.isoformat()
            if mark.mid is not None:
                mark.source = CHAIN_BIDASK
                mark.note = f"{mark.note} +chain bid/ask"
            # Fall back to the chain LTP when quotes returned nothing usable.
            if mark.ltp is None and info.ltp and info.ltp > 0:
                mark.ltp = round(float(info.ltp), 2)
        except Exception:
            pass
        return mark

    async def refresh_and_register(self, broker_symbols: list[str]) -> dict[str, OptionMark]:
        """Fetch, upgrade, store. The one call the worker loop needs."""
        marks = await self.fetch_chain_marks(broker_symbols)
        if marks:
            option_mark_registry.put_many(marks.values())
        return marks

    # ── marks derived from the 60s chain refresh ──
    def register_chain_strike(self, info: Any) -> Optional[OptionMark]:
        """Adapt a `LiveStrikeInfo` (chain cache row) into a labeled mark and store in registry."""
        try:
            sym = str(getattr(info, "broker_symbol", "") or "").strip()
            if not sym:
                return None
            has_book = bool(getattr(info, "bid", 0)) and bool(getattr(info, "ask", 0))
            # OI / volume ride along when the chain row carries them.
            _oi = getattr(info, "oi", getattr(info, "open_interest", None))
            try:
                _oi_f = float(_oi) if _oi is not None else None
            except Exception:
                _oi_f = None
            try:
                _vv = getattr(info, "volume", None)
                _vol_f = float(_vv) if _vv is not None else None
            except Exception:
                _vol_f = None
            try:
                _ivv = getattr(info, "iv", None)
                _iv_f = float(_ivv) if _ivv is not None else None
            except Exception:
                _iv_f = None
            mark = OptionMark(
                broker_symbol=sym,
                underlying=str(getattr(info, "underlying", "") or ""),
                strike=float(getattr(info, "strike", 0) or 0),
                option_type=str(getattr(info, "option_type", "") or ""),
                expiry=getattr(getattr(info, "expiry_date", None), "isoformat", lambda: None)(),
                bid=float(getattr(info, "bid", 0) or 0) or None,
                ask=float(getattr(info, "ask", 0) or 0) or None,
                ltp=float(getattr(info, "ltp", 0) or 0) or None,
                oi=_oi_f,
                volume=_vol_f,
                iv=_iv_f,
                source=CHAIN_BIDASK if has_book else CHAIN_LTP,
                as_of_utc=int(getattr(info, "fetched_at_ms", 0) or int(time.time() * 1000)),
                note="options-chain-v3",
            )
            if mark.price is None:
                return None
            option_mark_registry.put(mark)
            return mark
        except Exception:
            return None

    # ── labeled model fallback ──
    def model_mark(
        self,
        broker_symbol: str,
        spot: float,
        strike: float,
        option_type: str,
        dte_days: float = 3.0,
        iv: float = 0.15,
        risk_free_rate: float = 0.07,
        underlying: str = "",
        expiry: Optional[str] = None,
        register: bool = False,
    ) -> OptionMark:
        """Build an explicitly-labeled Black-76 mark. Never silent."""
        from app.signals.fill_reconciler import option_fill_reconciler

        # Short model TTL is enforced by DEFAULT_TTL_MS (5s); expiry-day
        # models are additionally flagged STALE_IV so get_usable() rejects.
        stale_flag = " STALE_IV" if float(dte_days or 0) <= STALE_IV_DTE_DAYS else ""
        mark = OptionMark(
            broker_symbol=broker_symbol,
            underlying=underlying,
            strike=float(strike or 0.0),
            option_type=str(option_type or ""),
            expiry=expiry,
            source=MODEL_BLACK76,
            note=f"black76 spot={spot} strike={strike} dte={dte_days} iv={iv} r={risk_free_rate}{stale_flag}",
        )
        try:
            prem = option_fill_reconciler.estimate_option_premium(
                spot=float(spot),
                strike=float(strike),
                option_type=str(option_type),
                dte_days=float(dte_days),
                iv=float(iv),
                risk_free_rate=float(risk_free_rate),
            )
            if prem and prem > 0:
                mark.ltp = round(float(prem), 2)
        except Exception as e:
            logger.debug("model_mark_failed", symbol=broker_symbol, error=str(e)[:150])
            return OptionMark(
                broker_symbol=broker_symbol,
                source=UNAVAILABLE,
                note=f"black76 failed: {str(e)[:80]}",
            )

        if register and mark.is_usable:
            option_mark_registry.put(mark)
        return mark

    def unavailable(self, broker_symbol: str, reason: str = "") -> OptionMark:
        """Explicit no-price mark. Callers must fail closed on this."""
        return OptionMark(
            broker_symbol=broker_symbol,
            source=UNAVAILABLE,
            note=reason or "no chain quote and no model inputs",
        )

    # ── convenience: mark for an audit record ──
    def mark_for_record(
        self,
        record: Any,
        spot: Optional[float] = None,
        allow_model: bool = True,
        register_model: bool = False,
    ) -> OptionMark:
        """Resolve the best available mark for an option audit record.

        Chain first (fresh registry mark), then fallback to LiveContractCache,
        then a labeled Black-76 model mark built from the record's own contract
        terms, then UNAVAILABLE. There is deliberately no fourth option that invents a number.
        """
        sym = str(getattr(record, "option_symbol", "") or "").strip()
        if not sym:
            try:
                from app.signals.live_contract_cache import live_contract_cache
                from datetime import date
                u = str(getattr(record, "underlying", "") or "").upper()
                strike = int(float(getattr(record, "option_strike", 0) or 0))
                otype = str(getattr(record, "option_type", "") or "").upper()
                exp = getattr(record, "expiry", None)
                if exp and strike > 0 and otype in ("CE", "PE"):
                    exp_date = date.fromisoformat(str(exp)) if isinstance(exp, str) and len(str(exp)) == 10 else None
                    if exp_date:
                        info = live_contract_cache.lookup(u, exp_date, strike, otype)
                        if info and info.broker_symbol:
                            sym = info.broker_symbol
                            try:
                                record.option_symbol = sym
                            except Exception:
                                pass
            except Exception:
                pass

        if not sym:
            return self.unavailable("", "record has no option_symbol")

        chain = option_mark_registry.get_usable(sym, allow_model=False)
        if chain is not None:
            return chain

        # Fallback to chain cache (LiveContractCache) if registry missed
        try:
            from app.signals.live_contract_cache import live_contract_cache
            info = live_contract_cache.find_by_symbol(sym)
            if info is not None:
                mark = self.register_chain_strike(info)
                if mark is not None and mark.is_usable:
                    return mark
        except Exception:
            pass

        if not allow_model:
            return self.unavailable(sym, "no fresh chain mark (model disallowed)")

        strike = float(getattr(record, "option_strike", 0) or 0.0)
        otype = str(getattr(record, "option_type", "") or "")
        ref_spot = float(spot or getattr(record, "spot_price_at_creation", 0) or 0.0)
        if strike <= 0 or not otype or ref_spot <= 0:
            return self.unavailable(
                sym,
                f"chain miss and model inputs incomplete (strike={strike} type={otype} spot={ref_spot})",
            )

        return self.model_mark(
            broker_symbol=sym,
            spot=ref_spot,
            strike=strike,
            option_type=otype,
            underlying=str(getattr(record, "underlying", "") or ""),
            expiry=getattr(record, "expiry", None),
            register=register_model,
        )


option_mark_service = OptionMarkService()
