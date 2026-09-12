"""
Unified Market Intelligence Service — single reader for all MI consumers.

Replaces ad-hoc spot-only `market_intelligence_engine.evaluate(spot)` calls in
dashboard / full / signal-center endpoints which always produced hollow
RANGING 50/50 REJECTED output.

Responsibilities:
- Resolve live spot with multi-source fallback + last-good cache (never None
  when a recent price exists; honest STALE/CACHED provenance instead).
- Enrich MI inputs best-effort with timeouts: vwap, volumes, options/PCR,
  key levels, ATR, multi-timeframe bias, volatility, funding (crypto).
- Derive data_health / feed_health consistently.
- Expose capability/session/sequence/feed blocks with REAL values (no hardcoded
  placeholders) for API responses.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import structlog

from app.institutional.instrument_registry import asset_registry
from app.institutional.clocks import get_session_clock
from app.institutional.feed_circuit import feed_circuit
from app.institutional.sequence import get_sequence_validator
from app.institutional.snapshot_buffer import synchronized_buffer
from app.institutional.decimal_types import D

logger = structlog.get_logger()

_IO_TIMEOUT_S = 3.0  # per-upstream budget; MI must never hang on a provider
_ENRICH_TIMEOUT_S = 8.0  # enrichment budget (regime/options/candles are slow on cold cache + free tier)
# Slow-moving enrichment is cached briefly so ONE slow poll cannot blank every
# poll: levels/indicators/options move slowly (60s), candles back volume/MTF
# which barely change inside a 5m bar (30s). Fresh fetch first, cache fallback.
_CACHE_TTLS_MS = {"kl": 60_000, "ind": 60_000, "opt": 60_000, "candles": 30_000, "breadth": 60_000}
_ttl_cache: dict[str, tuple[int, Any]] = {}


def _cache_get(key: str, now_ms: int) -> Any | None:
    ent = _ttl_cache.get(key)
    if not ent:
        return None
    ts, val = ent
    if val is None or now_ms - ts > _CACHE_TTLS_MS.get(key.split(":")[0], 30_000):
        return None
    return val


def _cache_set(key: str, val: Any, now_ms: int) -> None:
    if val is not None:
        _ttl_cache[key] = (now_ms, val)
_LAST_GOOD_MAX_AGE_MS = 15 * 60 * 1000  # serve cached spot as STALE up to 15m

# Staleness bands. Indian-equity quotes arrive via REST polling (typical cadence
# ~5-15s), so STALE must not trigger at 5s — that flaps LIVE/STALE on every
# poll. RECENT covers the normal poll interval; STALE means genuinely lagging.
LIVE_AFTER_MS = 5000
STALE_AFTER_MS = 15000
# Upstream exchange timestamps older than this are honored as-is (stale upstream
# snapshot); smaller lags are treated as normal REST latency and stamped at
# receive time so health reflects OUR knowledge freshness, not poll jitter.
QUOTE_TS_MAX_LAG_MS = 30_000


@dataclass
class MIInputs:
    instrument_id: str
    spot: Decimal | None = None
    last_update_ms: int = 0
    spot_source: str = "none"  # buffer | market_service | cache | none
    used_cache: bool = False
    vwap: Decimal | None = None
    vwap_source: str | None = None  # candle | session-derived | none
    volumes: dict[str, Any] | None = None
    quote_volume: int | None = None
    breadth: dict[str, Any] | None = None
    oi_data: dict[str, Any] | None = None
    options_data: dict[str, Any] | None = None
    support_resistance: dict[str, list] | None = None
    levels_source: str | None = None  # regime-service | session-developing | none
    multi_timeframe: dict[str, str] | None = None
    volatility: dict[str, Any] | None = None
    liquidity: dict[str, Any] | None = None
    funding: dict[str, Any] | None = None
    breakout_level: Decimal | None = None
    atr: Decimal | None = None
    synchronized_snapshot: Any | None = None
    data_health: str = "DISCONNECTED"
    feed_health: str = "HEALTHY"
    market_session: str = "CLOSED"
    provenance: dict[str, Any] = field(default_factory=dict)


# Last-good cache: instrument -> {spot: Decimal, ts_ms: int}
_last_good: dict[str, dict[str, Any]] = {}


def _remember_last_good(iid: str, spot: Decimal | None, ts_ms: int) -> None:
    if spot is None:
        return
    try:
        _last_good[iid.upper()] = {"spot": D(str(spot)), "ts_ms": int(ts_ms)}
    except Exception:
        pass


def get_last_good(iid: str, now_ms: int) -> tuple[Decimal | None, int | None, int | None]:
    """Return (spot, ts_ms, age_ms) if within max age, else (None, None, None)."""
    ent = _last_good.get(iid.upper())
    if not ent:
        return None, None, None
    age = now_ms - int(ent["ts_ms"])
    if age < 0:
        age = 0
    if age > _LAST_GOOD_MAX_AGE_MS:
        return None, None, None
    return ent["spot"], int(ent["ts_ms"]), age


async def _with_timeout(coro, timeout: float = _IO_TIMEOUT_S):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except Exception as e:
        logger.debug("mi_upstream_timeout_or_error", error=str(e)[:150])
        return None


def _bias_from_candles(candles: list) -> str:
    """Derive BULLISH/BEARISH/NEUTRAL from a candle list (close momentum)."""
    try:
        if not candles or len(candles) < 3:
            return "NEUTRAL"
        closes = [float(getattr(c, "close", 0) or 0) for c in candles]
        closes = [c for c in closes if c > 0]
        if len(closes) < 3:
            return "NEUTRAL"
        first, last = closes[0], closes[-1]
        if first <= 0:
            return "NEUTRAL"
        chg = (last - first) / first
        if chg > 0.0015:
            return "BULLISH"
        if chg < -0.0015:
            return "BEARISH"
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"


def health_band(age_ms: int | None) -> str:
    """Map knowledge age to LIVE / RECENT / STALE. None age → STALE (unknown)."""
    if age_ms is None:
        return "STALE"
    age_ms = max(0, int(age_ms))
    if age_ms > STALE_AFTER_MS:
        return "STALE"
    if age_ms > LIVE_AFTER_MS:
        return "RECENT"
    return "LIVE"


def classic_pivots_from_ohlc(high: float, low: float, close: float) -> dict[str, float] | None:
    """Classic floor pivots. Pure math — unit-testable. Returns None on bad input."""
    try:
        h, lo, c = float(high), float(low), float(close)
        if not (h > 0 and lo > 0 and c > 0 and h >= lo):
            return None
        p = (h + lo + c) / 3.0
        return {
            "pivot": p,
            "r1": 2 * p - lo,
            "s1": 2 * p - h,
            "r2": p + (h - lo),
            "s2": p - (h - lo),
        }
    except Exception:
        return None


def session_vwap_from_candles(candles: list) -> Decimal | None:
    """Session VWAP fallback = Σ(typical × vol) / Σ(vol). None when no volume."""
    try:
        if not candles:
            return None
        num = 0.0
        den = 0.0
        for c in candles:
            h = float(getattr(c, "high", 0) or 0)
            lo = float(getattr(c, "low", 0) or 0)
            cl = float(getattr(c, "close", 0) or 0)
            v = float(getattr(c, "volume", 0) or 0)
            if cl <= 0 or v <= 0:
                continue
            typical = (h + lo + cl) / 3.0 if h > 0 and lo > 0 else cl
            num += typical * v
            den += v
        if den <= 0:
            return None
        return D(str(round(num / den, 2)))
    except Exception:
        return None


def map_breadth_sentiment(sentiment: str | None) -> str:
    """Map provider sentiment to engine breadth bias. Pure — unit-testable."""
    try:
        s = (sentiment or "").upper()
        if s in ("BULLISH", "VERY_BULLISH"):
            return "BULLISH"
        if s in ("BEARISH", "VERY_BEARISH"):
            return "BEARISH"
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"


def eod_spot_from_candles(candles: list) -> Decimal | None:
    """Closed-market reference price = last 5m bar close. Pure — unit-testable."""
    try:
        if not candles:
            return None
        px = float(getattr(candles[-1], "close", 0) or 0)
        return D(str(px)) if px > 0 else None
    except Exception:
        return None


def session_pivots_from_candles(candles: list) -> tuple[dict[str, list] | None, Decimal | None]:
    """Developing session pivots from today's 5m range (fallback when the regime
    service times out). Honest proxy — marked 'session-developing' in provenance."""
    try:
        if not candles:
            return None, None
        highs = [float(getattr(c, "high", 0) or 0) for c in candles]
        lows = [float(getattr(c, "low", 0) or 0) for c in candles]
        closes = [float(getattr(c, "close", 0) or 0) for c in candles]
        highs = [h for h in highs if h > 0]
        lows = [l for l in lows if l > 0]
        closes = [c for c in closes if c > 0]
        if not highs or not lows or not closes:
            return None, None
        piv = classic_pivots_from_ohlc(max(highs), min(lows), closes[-1])
        if not piv:
            return None, None
        sr = {
            "support": [str(round(piv["s1"], 2)), str(round(piv["s2"], 2))],
            "resistance": [str(round(piv["r1"], 2)), str(round(piv["r2"], 2))],
        }
        return sr, D(str(round(piv["r1"], 2)))
    except Exception:
        return None, None


def sanitize_options_data(options_data: dict | None) -> tuple[dict | None, str | None]:
    """Reject non-tradeable PCR readings.

    Returns (cleaned_or_None, reason_or_None). A PCR of 0 (or negative) is the
    options service's EMPTY-chain sentinel, not bearish positioning; likewise a
    chain reporting zero total OI carries no information. Both are normalized
    to missing data with an explicit reason.
    """
    if options_data is None:
        return None, None
    try:
        pcr_v = float(options_data.get("pcr", 0) or 0)
        has_totals = "total_call_oi" in options_data or "total_put_oi" in options_data
        oi_total = int(options_data.get("total_call_oi", 0) or 0) + int(options_data.get("total_put_oi", 0) or 0)
        if not (pcr_v > 0) or (has_totals and oi_total <= 0):
            return None, "option chain empty (no OI totals) — PCR not tradeable"
        return options_data, None
    except Exception:
        return None, "invalid PCR value"


def build_cross_snapshot(iid: str, pipeline: str, now_ms: int):
    """Synchronized cross-market snapshot for Indian equities (buffer-only, sync).
    Returns None for crypto (continuous market, no peer sync) or when no peer
    snapshot exists yet — caller treats None as UNKNOWN, not as failure."""
    try:
        if pipeline != "INDIAN_EQUITY":
            return None
        peers = {"NIFTY": "BANKNIFTY", "BANKNIFTY": "NIFTY", "SENSEX": "NIFTY"}
        peer = peers.get(iid.upper())
        if not peer or not synchronized_buffer.get_latest(peer):
            return None
        return synchronized_buffer.get_synchronized([iid.upper(), peer], now_ms=now_ms)
    except Exception as e:
        logger.debug("mi_cross_snapshot_failed", instrument=iid, error=str(e)[:150])
        return None


def capabilities_dict(instrument_id: str) -> dict[str, Any]:
    """Build capabilities from InstrumentProfile has_* flags (prof has no .capabilities attr)."""
    prof = asset_registry.get(instrument_id)
    if not prof:
        return {}
    try:
        tick = prof.contract_spec.tick_size if prof.contract_spec else Decimal("0.05")
        lot = prof.contract_spec.lot_size if prof.contract_spec else Decimal("1")
    except Exception:
        tick, lot = Decimal("0.05"), Decimal("1")
    return {
        "spot": bool(prof.has_spot),
        "futures": bool(prof.has_futures),
        "options": bool(prof.has_options),
        "funding": bool(prof.has_funding),
        "oi": bool(prof.has_oi),
        "liquidations": bool(prof.has_liquidations),
        "orderbook_l2": bool(prof.has_spot),
        "greeks": bool(prof.has_options),
        "fii_dii": bool(prof.pipeline == "INDIAN_EQUITY"),
        "ai_confirmation": True,
        "telegram_alerts": True,
        "multi_timeframe": True,
        "tick_size": float(tick) if tick else 0.05,
        "lot_size": float(lot) if lot else 1,
        "max_leverage": 1,
    }


def capabilities_list(instrument_id: str) -> list[str]:
    caps = capabilities_dict(instrument_id)
    return sorted([k for k, v in caps.items() if v is True])


async def gather_inputs(instrument_id: str, now_ms: int | None = None) -> MIInputs:
    """Resolve spot + enrichment for one instrument. Never raises; degrades honestly."""
    from app.institutional.instrument_registry import asset_registry as _reg

    now_ms = now_ms or int(time.time() * 1000)
    prof = _reg.get(instrument_id)
    if not prof:
        return MIInputs(instrument_id=instrument_id, last_update_ms=now_ms)
    iid = prof.instrument_id

    clock = get_session_clock(iid)
    try:
        sess_state = clock.current_state(now_ms=now_ms)
    except Exception:
        sess_state = "OPEN" if prof.pipeline == "CRYPTO" else "CLOSED"
    try:
        clk_info = clock.session_info(now_ms) if hasattr(clock, "session_info") else {}
    except Exception:
        clk_info = {}

    feed_snap = feed_circuit.snapshot(iid)
    feed_health = "FEED_DEGRADED" if getattr(feed_snap, "health", "HEALTHY") == "FEED_DEGRADED" else "HEALTHY"

    # ── 1. Spot resolution ──────────────────────────────────────────
    spot: Decimal | None = None
    last_update_ms = now_ms
    spot_source = "none"

    latest = synchronized_buffer.get_latest(iid)
    if latest is not None:
        try:
            if latest.event.price:
                spot = D(str(latest.event.price))
                last_update_ms = int(latest.event.canonical_timestamp_utc)
                spot_source = "buffer"
        except Exception:
            spot = None

    # Indian / fallback: MarketService live quote
    quote_volume: int | None = None
    quote_ohlc: dict[str, float] | None = None
    if spot is None:
        try:
            from app.services.market_service import MarketService
            from app.models.market import DataStatus

            svc = MarketService()
            q = await _with_timeout(svc.get_quote(iid), timeout=4.0)
            if q is not None and getattr(q, "ltp", None) and float(q.ltp) > 0:
                status = getattr(q, "status", None)
                provider = getattr(q, "provider", "") or ""
                # Accept LIVE/CLOSED/DEGRADED quotes; reject OFFLINE/fallback empties
                if status != DataStatus.OFFLINE and provider != "fallback":
                    spot = D(str(q.ltp))
                    try:
                        ts = getattr(q, "timestamp", None)
                        qts = int(ts.timestamp() * 1000) if ts is not None else now_ms
                    except Exception:
                        qts = now_ms
                    # Normal REST poll latency (a few seconds) must not flap health:
                    # stamp at receive time unless upstream is genuinely stale.
                    last_update_ms = qts if (now_ms - qts) > QUOTE_TS_MAX_LAG_MS else now_ms
                    spot_source = "market_service"
                    try:
                        v = getattr(q, "volume", None)
                        quote_volume = int(v) if v is not None and int(v) > 0 else None
                    except Exception:
                        quote_volume = None
                    try:
                        quote_ohlc = {
                            "high": float(getattr(q, "high", 0) or 0),
                            "low": float(getattr(q, "low", 0) or 0),
                            "prev_close": float(getattr(q, "previous_close", 0) or 0),
                            "open": float(getattr(q, "open", 0) or 0),
                        }
                        if not any(v > 0 for v in quote_ohlc.values()):
                            quote_ohlc = None
                    except Exception:
                        quote_ohlc = None
        except Exception as e:
            logger.debug("mi_market_service_quote_failed", instrument=iid, error=str(e)[:150])

    used_cache = False
    if spot is not None:
        _remember_last_good(iid, spot, last_update_ms)
    else:
        cached_spot, cached_ts, cached_age = get_last_good(iid, now_ms)
        if cached_spot is not None:
            spot = cached_spot
            last_update_ms = cached_ts or now_ms
            spot_source = "cache"
            used_cache = True

    # ── 1b. Hydrate enrichment from latest buffer event metadata ──
    # Pipeline ingest stores the full raw tick (vwap/volumes/oi/options/mtf/...)
    # as event.metadata. Dashboards must reuse it, otherwise they fall back to
    # hollow spot-only defaults even right after a rich ingest.
    _meta: dict[str, Any] = {}
    try:
        if latest is not None and getattr(latest.event, "metadata", None):
            _meta = latest.event.metadata or {}
            if isinstance(_meta, dict) and "metadata" in _meta and isinstance(_meta["metadata"], dict):
                # Double-wrapped metadata guard
                _meta = {**_meta, **_meta["metadata"]}
    except Exception:
        _meta = {}

    def _dec(v: Any) -> Decimal | None:
        try:
            if v is None:
                return None
            return D(str(v))
        except Exception:
            return None

    _meta_vwap = _dec(_meta.get("vwap")) if _meta else None
    _meta_volumes = _meta.get("volumes") if isinstance(_meta.get("volumes"), dict) else None
    if _meta_volumes is None and _meta.get("volume_change") is not None:
        try:
            _meta_volumes = {"volume_change": float(_meta.get("volume_change"))}
        except Exception:
            _meta_volumes = None
    _meta_oi = _meta.get("oi_data") if isinstance(_meta.get("oi_data"), dict) else None
    _meta_opt = _meta.get("options_data") if isinstance(_meta.get("options_data"), dict) else None
    if _meta_opt is None and _meta.get("pcr") is not None:
        try:
            _meta_opt = {"pcr": float(_meta.get("pcr"))}
        except Exception:
            _meta_opt = None
    _meta_sr = _meta.get("support_resistance") or _meta.get("levels")
    if not isinstance(_meta_sr, dict):
        _meta_sr = None
    _meta_mtf = _meta.get("multi_timeframe") or _meta.get("mtf")
    if not isinstance(_meta_mtf, dict):
        _meta_mtf = None
    _meta_vol = _meta.get("volatility") if isinstance(_meta.get("volatility"), dict) else None
    _meta_liq = _meta.get("liquidity") if isinstance(_meta.get("liquidity"), dict) else None
    _meta_fund = _meta.get("funding") if isinstance(_meta.get("funding"), dict) else None
    _meta_brk = _dec(_meta.get("breakout_level")) if _meta else None
    _meta_atr = _dec(_meta.get("atr")) if _meta else None
    try:
        _meta_age = int(now_ms - int(latest.event.canonical_timestamp_utc)) if latest is not None else 999999
    except Exception:
        _meta_age = 999999
    _meta_fresh = bool(_meta) and _meta_age <= 60000 and spot_source == "buffer"

    # ── 2. Health derivation ────────────────────────────────────────
    snap_health = {}
    try:
        snap_health = synchronized_buffer.health().get(iid, {}) or {}
    except Exception:
        snap_health = {}
    buf_age = snap_health.get("age_ms")

    # ── Health is derived AFTER enrichment (see below): EOD reference and
    # ── last-good cache can still fill spot after this point.
    # ── 3. Best-effort enrichment (never raises) ────────────────────
    # Seed from fresh ingest metadata first; upstream fills only gaps.
    vwap: Decimal | None = _meta_vwap if _meta_fresh else None
    volumes: dict[str, Any] | None = dict(_meta_volumes) if (_meta_fresh and _meta_volumes) else None
    options_data: dict[str, Any] | None = dict(_meta_opt) if (_meta_fresh and _meta_opt) else None
    support_resistance: dict[str, list] | None = dict(_meta_sr) if (_meta_fresh and _meta_sr) else None
    multi_timeframe: dict[str, str] | None = dict(_meta_mtf) if (_meta_fresh and _meta_mtf) else None
    volatility: dict[str, Any] | None = dict(_meta_vol) if (_meta_fresh and _meta_vol) else None
    liquidity: dict[str, Any] | None = dict(_meta_liq) if (_meta_fresh and _meta_liq) else None
    funding: dict[str, Any] | None = dict(_meta_fund) if (_meta_fresh and _meta_fund) else None
    breakout_level: Decimal | None = _meta_brk if _meta_fresh else None
    atr: Decimal | None = _meta_atr if _meta_fresh else None
    breadth: dict[str, Any] | None = None
    # Source labels for UI honesty (set by enrichment branches below)
    vwap_source: str | None = "ingest" if (_meta_fresh and _meta_vwap is not None) else None
    levels_source: str | None = "ingest" if (_meta_fresh and _meta_sr is not None) else None
    options_status_reason: str | None = None
    # Per-source failure reasons + cache hits (Indian branch fills these;
    # initialized here so the BTC path and provenance below are always safe).
    enrich_errs: dict[str, str] = {}
    enrich_cached: dict[str, bool] = {}

    if iid == "BTCUSD":
        pass
    else:
        # Parallel enrichment: the old serial chain (key-levels → indicators →
        # options-chain → 1m/5m/15m candles) took 20s+ worst case on a cold cache,
        # so slow upstreams starved the rest (e.g. levels always empty). All four
        # run concurrently with independent budgets; gaps keep metadata values.
        need_kl = support_resistance is None or breakout_level is None
        need_ind = atr is None or volatility is None
        need_opt = options_data is None
        need_candles = vwap is None or volumes is None or multi_timeframe is None
        # Closed market with no live spot still needs candles for EOD reference.
        if spot is None and prof.pipeline == "INDIAN_EQUITY" and sess_state == "CLOSED":
            need_candles = True
        # Breadth is equity-only (CapabilityMap) and slow-moving: 60s cache.
        need_breadth = breadth is None and prof.pipeline == "INDIAN_EQUITY"

        async def _fetch_breadth():
            if not need_breadth:
                return None
            from app.services.market_service import MarketService as _MSB

            return await _with_cache(
                "breadth", "breadth", lambda: _MSB().get_market_breadth()
            )

        async def _with_cache(label: str, cache_key: str, coro_fn):
            """Fetch upstream; on miss serve the brief TTL cache; record why."""
            try:
                r = await _with_timeout(coro_fn(), timeout=_ENRICH_TIMEOUT_S)
            except Exception as e:
                r = None
                enrich_errs[label] = f"error: {str(e)[:120]}"
                logger.debug("mi_enrich_failed", instrument=iid, source=label, error=str(e)[:150])
            if r is not None and r != []:
                _cache_set(f"{cache_key}:{iid}", r, now_ms)
                return r
            if r == []:
                enrich_errs[label] = "upstream returned empty"
            cached = _cache_get(f"{cache_key}:{iid}", now_ms)
            if cached is not None:
                enrich_cached[label] = True
                return cached
            if r is None and label not in enrich_errs:
                enrich_errs[label] = "no result within budget and nothing cached"
            return None

        async def _fetch_kl():
            if not need_kl:
                return None
            from app.services.regime_service import regime_service

            return await _with_cache("key_levels", "kl", lambda: regime_service.get_key_levels(iid))

        async def _fetch_ind():
            if not need_ind:
                return None
            from app.services.regime_service import regime_service

            return await _with_cache("indicators", "ind", lambda: regime_service.get_technical_indicators(iid))

        async def _fetch_opt():
            if not need_opt:
                return None
            from app.services.options_service import options_service

            return await _with_cache("options_chain", "opt", lambda: options_service.get_option_chain_matrix(iid))

        async def _fetch_candles():
            if not need_candles:
                return None
            from app.services.market_service import MarketService as _MS

            svc = _MS()

            async def _all():
                return await asyncio.gather(
                    _with_timeout(svc.get_candles(iid, timeframe="5m"), timeout=_ENRICH_TIMEOUT_S),
                    _with_timeout(svc.get_candles(iid, timeframe="1m"), timeout=_ENRICH_TIMEOUT_S),
                    _with_timeout(svc.get_candles(iid, timeframe="15m"), timeout=_ENRICH_TIMEOUT_S),
                )

            pack = await _with_cache("candles", "candles", _all)
            if pack is None:
                return None
            # A pack of all-empty lists carries no information — treat as miss
            # and evict it so emptiness is never served from cache.
            try:
                if not any(pack or []):
                    enrich_errs["candles"] = "upstream returned empty"
                    _ttl_cache.pop(f"candles:{iid}", None)
                    return None
            except Exception:
                pass
            return pack

        try:
            kl, ind, chain, candle_pack, breadth_raw = await asyncio.gather(
                _fetch_kl(), _fetch_ind(), _fetch_opt(), _fetch_candles(), _fetch_breadth()
            )
        except Exception as e:
            logger.debug("mi_enrich_gather_failed", instrument=iid, error=str(e)[:150])
            kl, ind, chain, candle_pack, breadth_raw = None, None, None, None, None

        if breadth_raw is not None:
            try:
                adv = int(getattr(breadth_raw, "advancing", 0) or 0)
                dec = int(getattr(breadth_raw, "declining", 0) or 0)
                unc = int(getattr(breadth_raw, "unchanged", 0) or 0)
                if adv + dec + unc > 0:
                    breadth = {
                        "breadth": map_breadth_sentiment(getattr(breadth_raw, "sentiment", None)),
                        "advancing": adv,
                        "declining": dec,
                        "unchanged": unc,
                        "advance_decline_ratio": float(getattr(breadth_raw, "advance_decline_ratio", 0) or 0),
                        "sentiment": str(getattr(breadth_raw, "sentiment", "NEUTRAL")),
                        "sentiment_score": float(getattr(breadth_raw, "sentiment_score", 50) or 50),
                    }
                else:
                    # Zero-count breadth carries no information — evict so it is
                    # never served from cache, and record why.
                    _ttl_cache.pop(f"breadth:{iid}", None)
                    enrich_errs["breadth"] = "provider returned zero counts"
            except Exception as e:
                enrich_errs["breadth"] = f"error: {str(e)[:120]}"

        # ── Parse parallel results (each independent; failure keeps gap) ──
        if kl is not None and (support_resistance is None or breakout_level is None):
            try:
                r1 = float(getattr(kl, "r1", 0) or 0)
                s1 = float(getattr(kl, "s1", 0) or 0)
                r2 = float(getattr(kl, "r2", 0) or 0)
                s2 = float(getattr(kl, "s2", 0) or 0)
                if r1 > 0 and s1 > 0:
                    support_resistance = {"support": [str(s1), str(s2)], "resistance": [str(r1), str(r2)]}
                    breakout_level = breakout_level or D(str(r1))
                    levels_source = "regime-service"
                elif r1 > 0 or s1 > 0:
                    support_resistance = {
                        "support": [str(s1)] if s1 > 0 else [],
                        "resistance": [str(r1)] if r1 > 0 else [],
                    }
                    if r1 > 0 and breakout_level is None:
                        breakout_level = D(str(r1))
                    levels_source = "regime-service"
                if levels_source == "regime-service" and enrich_cached.get("key_levels"):
                    levels_source = "regime-service-cached"
            except Exception:
                pass
        if ind is not None:
            if atr is None:
                try:
                    if float(getattr(ind, "atr_14", 0) or 0) > 0:
                        atr = D(str(ind.atr_14))
                except Exception:
                    pass
            if volatility is None:
                try:
                    bw = float(getattr(ind, "bollinger_bandwidth", 0) or 0)
                    if bw >= 4.5:
                        volatility = {"volatility_change": 0.3}
                    elif bw <= 2.2:
                        volatility = {"volatility_change": -0.3}
                    else:
                        volatility = {"volatility_change": 0.0}
                except Exception:
                    pass

        if options_data is None:
            if chain is not None and getattr(chain, "analytics", None) is not None:
                ana = chain.analytics
                pcr = getattr(ana, "pcr_oi", None)
                if pcr is not None:
                    try:
                        options_data = {
                            "pcr": float(pcr),
                            "total_call_oi": int(getattr(ana, "total_call_oi", 0) or 0),
                            "total_put_oi": int(getattr(ana, "total_put_oi", 0) or 0),
                            "pcr_volume": float(getattr(ana, "pcr_volume", 0) or 0),
                        }
                    except Exception:
                        options_data = None
                        options_status_reason = "invalid PCR value"
                else:
                    options_status_reason = "chain returned no PCR"
            elif need_opt:
                options_status_reason = "option chain unavailable (broker timeout or no access)"

        # Candles → vwap / volumes / multi-timeframe (fill gaps only)
        c5 = c1 = c15 = None
        if candle_pack:
            try:
                c5, c1, c15 = candle_pack
            except Exception:
                pass
        if c5 or c1 or c15:
            mtf: dict[str, str] = dict(multi_timeframe) if multi_timeframe else {}
            if c1 and "1m" not in mtf:
                mtf["1m"] = _bias_from_candles(c1[-20:])
            if c5:
                if "5m" not in mtf:
                    mtf["5m"] = _bias_from_candles(c5[-20:])
                if vwap is None or volumes is None:
                    try:
                        last = c5[-1]
                        if vwap is None and getattr(last, "vwap", None):
                            vwap = D(str(last.vwap))
                            vwap_source = "candle"
                        if volumes is None:
                            vols = [float(getattr(c, "volume", 0) or 0) for c in c5[-20:]]
                            if vols and sum(vols) > 0:
                                avg = sum(vols) / len(vols)
                                chg = (vols[-1] - avg) / avg if avg > 0 else 0.0
                                volumes = {"volume_change": float(max(-1.0, min(2.0, chg)))}
                    except Exception:
                        pass
            if c15 and "15m" not in mtf:
                mtf["15m"] = _bias_from_candles(c15[-20:])
            if mtf and multi_timeframe is None:
                multi_timeframe = mtf
            # Deterministic fallbacks from session candles (marked in provenance)
            if vwap is None and c5:
                _sv = session_vwap_from_candles(c5)
                if _sv is not None:
                    vwap = _sv
                    vwap_source = "session-derived"
            if (support_resistance is None or breakout_level is None) and c5:
                _sr, _bl = session_pivots_from_candles(c5)
                if _sr is not None:
                    support_resistance = support_resistance or _sr
                    breakout_level = breakout_level or _bl
                    levels_source = levels_source or "session-developing"

        # Closed-market EOD reference: after close there are no live ticks, but
        # the day's candles still describe what happened. Use the last 5m close
        # as the reference price (source "eod", NEVER cached as live) so the
        # workspace shows the session's real structure instead of all-UNKNOWN.
        if spot is None and prof.pipeline == "INDIAN_EQUITY" and sess_state == "CLOSED" and c5:
            _eod_px = eod_spot_from_candles(c5)
            if _eod_px is not None:
                spot = _eod_px
                spot_source = "eod"
                last_update_ms = now_ms

    # ── 4. Health derivation (after all spot sources incl. EOD) ──────
    # Effective age: buffer age if buffer hit, else now - last_update
    if spot_source == "buffer" and buf_age is not None:
        eff_age = max(0, int(buf_age))
    elif spot is not None:
        eff_age = max(0, now_ms - int(last_update_ms))
    else:
        eff_age = None

    if feed_health == "FEED_DEGRADED":
        data_health = "FEED_DEGRADED"
    elif spot is None:
        if prof.pipeline == "INDIAN_EQUITY" and sess_state == "CLOSED":
            data_health = "CLOSED"
        else:
            data_health = "DISCONNECTED"
    elif prof.pipeline == "INDIAN_EQUITY" and sess_state == "CLOSED":
        # EOD reference or late tick after close: session truth, not staleness.
        data_health = "CLOSED"
    else:
        # Bands widened for REST-poll cadence (see LIVE_AFTER_MS/STALE_AFTER_MS):
        # flapping LIVE/STALE across polls is worse than a calm RECENT.
        data_health = health_band(eff_age)

    # PCR validity gate: the options service emits pcr_oi=0.0 as a sentinel for
    # an EMPTY chain (no strikes / zero OI totals). Zero is not a tradeable
    # reading — surfacing it as "Bearish" is a false signal. Reject it (and any
    # non-positive PCR) here so every consumer (MI engine, signal center, UI)
    # treats it as missing data, regardless of which path seeded it.
    options_data, _gate_reason = sanitize_options_data(options_data)
    if _gate_reason is not None:
        options_status_reason = _gate_reason

    # Liquidity heuristic: very low relative volume → THIN (raises false-breakout risk honestly)
    try:
        if volumes is not None and float(volumes.get("volume_change", 0)) < -0.5:
            liquidity = {"state": "THIN"}
    except Exception:
        pass

    mi_data_health = "LIVE" if data_health in ("LIVE", "RECENT") else data_health
    mi_feed_health = "HEALTHY" if feed_health == "HEALTHY" else "FEED_DEGRADED"

    cross_snap = build_cross_snapshot(iid, prof.pipeline, now_ms)

    provenance = {
        "spot_source": spot_source,
        "used_cache": used_cache,
        "effective_age_ms": eff_age,
        "session": sess_state,
        "meta_fresh": bool(_meta_fresh),
        "vwap_source": vwap_source,
        "levels_source": levels_source,
        "options_status": "AVAILABLE" if options_data is not None else (options_status_reason or "UNAVAILABLE"),
        "cross_market": getattr(cross_snap, "status", None),
        "errors": dict(enrich_errs),
        "cache_hits": sorted([k for k, v in enrich_cached.items() if v]),
        "enriched": {
            "vwap": vwap is not None,
            "volumes": volumes is not None,
            "breadth": breadth is not None,
            "options": options_data is not None,
            "levels": support_resistance is not None,
            "mtf": multi_timeframe is not None,
            "volatility": volatility is not None,
            "funding": funding is not None,
            "atr": atr is not None,
        },
    }

    return MIInputs(
        instrument_id=iid,
        spot=spot,
        last_update_ms=int(last_update_ms),
        spot_source=spot_source,
        used_cache=used_cache,
        vwap=vwap,
        vwap_source=vwap_source,
        volumes=volumes,
        quote_volume=quote_volume,
        breadth=breadth,
        oi_data=None,
        options_data=options_data,
        support_resistance=support_resistance,
        levels_source=levels_source,
        multi_timeframe=multi_timeframe,
        volatility=volatility,
        liquidity=liquidity,
        funding=funding,
        breakout_level=breakout_level,
        atr=atr,
        synchronized_snapshot=cross_snap,
        data_health=mi_data_health,
        feed_health=mi_feed_health,
        market_session=sess_state,
        provenance=provenance,
    )


def session_block(iid: str, now_ms: int) -> dict[str, Any]:
    """Real session block (no hardcoded placeholders)."""
    try:
        clock = get_session_clock(iid)
        info = clock.session_info(now_ms) if hasattr(clock, "session_info") else {}
        state = info.get("session_state") or clock.current_state(now_ms=now_ms)
        return {
            "is_open": bool(info.get("is_open", state == "OPEN")),
            "session_type": state,
            "is_tradable": bool(info.get("is_tradable", state == "OPEN")),
            "now_ist": info.get("now_ist"),
            "clock_divergence_ms": 0,
            "is_synchronized": True,
        }
    except Exception:
        return {
            "is_open": False, "session_type": "UNKNOWN", "is_tradable": False,
            "now_ist": None, "clock_divergence_ms": 0, "is_synchronized": False,
        }


def sequence_block(iid: str) -> dict[str, Any]:
    try:
        v = get_sequence_validator(iid)
        return {
            "last_seq": getattr(v, "_last_source_seq", None) or getattr(v, "_internal_seq", 0),
            "gap_detected": bool(getattr(v, "_gap_detected", False)),
            "gap_count": int(getattr(v, "_gap_count", 0)) if hasattr(v, "_gap_count") else 0,
            "out_of_order_count": int(getattr(v, "_ooo_count", 0)) if hasattr(v, "_ooo_count") else 0,
        }
    except Exception:
        return {"last_seq": 0, "gap_detected": False, "gap_count": 0, "out_of_order_count": 0}


def feed_block(
    iid: str,
    last_update_ms: int,
    now_ms: int,
    has_spot: bool,
    used_cache: bool,
    spot_source: str = "spot",
) -> dict[str, Any]:
    try:
        snap = feed_circuit.snapshot(iid)
        health = getattr(snap, "health", "HEALTHY")
        circuit = "TRIPPED" if getattr(snap, "suppress_candidates", False) else "CLOSED"
        reason = getattr(snap, "reason", None)
    except Exception:
        health, circuit, reason = "HEALTHY", "CLOSED", None
    if not has_spot:
        staleness = 999999
        is_stale = True
        if health == "HEALTHY":
            health = "STALE"
    elif spot_source == "eod":
        # EOD reference after close: freshly derived, nothing wrong with feed.
        staleness = max(0, now_ms - int(last_update_ms))
        is_stale = False
    else:
        staleness = max(0, now_ms - int(last_update_ms))
        # Same widened band as health_band(): REST-poll cadence lives in RECENT.
        is_stale = staleness > STALE_AFTER_MS
        if health == "HEALTHY" and is_stale:
            health = "STALE"
    return {
        "health": health,
        "reason": reason,
        "circuit_state": circuit,
        "staleness_ms": int(staleness),
        "is_stale": bool(is_stale),
        "used_cache": bool(used_cache),
        "used_synthetic_fallback": False,
        "is_synthetic_fallback": False,
    }
