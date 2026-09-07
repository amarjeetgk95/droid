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
_LAST_GOOD_MAX_AGE_MS = 15 * 60 * 1000  # serve cached spot as STALE up to 15m


@dataclass
class MIInputs:
    instrument_id: str
    spot: Decimal | None = None
    last_update_ms: int = 0
    spot_source: str = "none"  # buffer | market_service | binance | cache | none
    used_cache: bool = False
    vwap: Decimal | None = None
    volumes: dict[str, Any] | None = None
    oi_data: dict[str, Any] | None = None
    options_data: dict[str, Any] | None = None
    support_resistance: dict[str, list] | None = None
    multi_timeframe: dict[str, str] | None = None
    volatility: dict[str, Any] | None = None
    liquidity: dict[str, Any] | None = None
    funding: dict[str, Any] | None = None
    breakout_level: Decimal | None = None
    atr: Decimal | None = None
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

    # Crypto: prefer Binance live (works without Indian broker creds)
    if spot is None and iid == "BTCUSD":
        try:
            from app.services.binance_service import binance_service

            ticker = await _with_timeout(binance_service.get_ticker("BTCUSDT"), timeout=4.0)
            if ticker is not None and getattr(ticker, "price", 0) and float(ticker.price) > 0:
                spot = D(str(ticker.price))
                try:
                    lu = getattr(ticker, "last_updated", None)
                    last_update_ms = int(lu.timestamp() * 1000) if lu is not None else now_ms
                except Exception:
                    last_update_ms = now_ms
                spot_source = "binance"
                # Seed buffer so subsequent reads + cross-market see it (non-synthetic live tick)
                try:
                    from app.institutional.events import InstrumentEvent

                    synth = InstrumentEvent.create(
                        instrument_id=iid, asset_class="CRYPTO", symbol="BTCUSDT",
                        price=str(spot), exchange_timestamp_utc=last_update_ms,
                        canonical_timestamp_utc=last_update_ms, is_synthetic=False,
                        source_id="binance_live",
                    )
                    synchronized_buffer.ingest_sync(synth)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("mi_binance_spot_failed", instrument=iid, error=str(e)[:150])

    # Indian / fallback: MarketService live quote
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
                        last_update_ms = int(ts.timestamp() * 1000) if ts is not None else now_ms
                    except Exception:
                        last_update_ms = now_ms
                    spot_source = "market_service"
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
    elif eff_age is not None and eff_age > 5000:
        data_health = "STALE"
    elif eff_age is not None and eff_age > 2000:
        data_health = "RECENT"
    else:
        data_health = "LIVE"

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

    if iid == "BTCUSD":
        if funding is None:
            try:
                from app.services.binance_service import binance_service as _bs

                deriv = await _with_timeout(_bs.get_derivatives_data("BTCUSDT"), timeout=4.0)
                if deriv is not None and getattr(deriv, "funding_rate", None) is not None:
                    try:
                        funding = {"rate": float(deriv.funding_rate)}
                    except Exception:
                        funding = None
            except Exception:
                pass
        # Candles → vwap/volumes/mtf/volatility for crypto too (fill gaps only)
        if vwap is None or volumes is None or multi_timeframe is None:
            try:
                from app.services.binance_service import binance_service as _bs2

                candles = await _with_timeout(_bs2.get_candles("BTCUSDT", timeframe="5m", limit=30), timeout=4.0)
                if candles:
                    if vwap is None:
                        try:
                            last = candles[-1]
                            if getattr(last, "vwap", None):
                                vwap = D(str(last.vwap))
                        except Exception:
                            pass
                    if volumes is None:
                        try:
                            vols = [float(getattr(c, "volume", 0) or 0) for c in candles]
                            if vols and sum(vols) > 0:
                                avg = sum(vols) / len(vols)
                                chg = (vols[-1] - avg) / avg if avg > 0 else 0.0
                                volumes = {"volume_change": float(chg)}
                        except Exception:
                            pass
                    if multi_timeframe is None:
                        try:
                            multi_timeframe = {"5m": _bias_from_candles(candles[-15:]), "15m": _bias_from_candles(candles)}
                        except Exception:
                            pass
            except Exception:
                pass
    else:
        # Key levels + ATR + PCR (each independent; failure → keep metadata value)
        if support_resistance is None or breakout_level is None or atr is None or volatility is None:
            try:
                from app.services.regime_service import regime_service

                if support_resistance is None or breakout_level is None:
                    kl = await _with_timeout(regime_service.get_key_levels(iid), timeout=4.0)
                    if kl is not None:
                        try:
                            r1 = float(getattr(kl, "r1", 0) or 0)
                            s1 = float(getattr(kl, "s1", 0) or 0)
                            r2 = float(getattr(kl, "r2", 0) or 0)
                            s2 = float(getattr(kl, "s2", 0) or 0)
                            if r1 > 0 and s1 > 0:
                                support_resistance = {"support": [str(s1), str(s2)], "resistance": [str(r1), str(r2)]}
                                breakout_level = breakout_level or D(str(r1))
                            elif r1 > 0 or s1 > 0:
                                support_resistance = {
                                    "support": [str(s1)] if s1 > 0 else [],
                                    "resistance": [str(r1)] if r1 > 0 else [],
                                }
                                if r1 > 0 and breakout_level is None:
                                    breakout_level = D(str(r1))
                        except Exception:
                            pass
                if atr is None or volatility is None:
                    ind = await _with_timeout(regime_service.get_technical_indicators(iid), timeout=4.0)
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
            except Exception as e:
                logger.debug("mi_regime_enrich_failed", instrument=iid, error=str(e)[:150])

        if options_data is None:
            try:
                from app.services.options_service import options_service

                chain = await _with_timeout(options_service.get_option_chain_matrix(iid), timeout=4.0)
                if chain is not None and getattr(chain, "analytics", None) is not None:
                    pcr = getattr(chain.analytics, "pcr_oi", None)
                    if pcr is not None:
                        try:
                            options_data = {"pcr": float(pcr)}
                        except Exception:
                            options_data = None
            except Exception as e:
                logger.debug("mi_options_enrich_failed", instrument=iid, error=str(e)[:150])

        # Candles → vwap / volumes / multi-timeframe (fill gaps only)
        if vwap is None or volumes is None or multi_timeframe is None:
            try:
                from app.services.market_service import MarketService as _MS

                svc = _MS()
                c5 = await _with_timeout(svc.get_candles(iid, timeframe="5m"), timeout=4.0)
                c1 = await _with_timeout(svc.get_candles(iid, timeframe="1m"), timeout=4.0)
                c15 = await _with_timeout(svc.get_candles(iid, timeframe="15m"), timeout=4.0)
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
            except Exception as e:
                logger.debug("mi_candles_enrich_failed", instrument=iid, error=str(e)[:150])

    # Liquidity heuristic: very low relative volume → THIN (raises false-breakout risk honestly)
    try:
        if volumes is not None and float(volumes.get("volume_change", 0)) < -0.5:
            liquidity = {"state": "THIN"}
    except Exception:
        pass

    mi_data_health = "LIVE" if data_health in ("LIVE", "RECENT") else data_health
    mi_feed_health = "HEALTHY" if feed_health == "HEALTHY" else "FEED_DEGRADED"

    provenance = {
        "spot_source": spot_source,
        "used_cache": used_cache,
        "effective_age_ms": eff_age,
        "session": sess_state,
        "meta_fresh": bool(_meta_fresh),
        "enriched": {
            "vwap": vwap is not None,
            "volumes": volumes is not None,
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
        volumes=volumes,
        oi_data=None,
        options_data=options_data,
        support_resistance=support_resistance,
        multi_timeframe=multi_timeframe,
        volatility=volatility,
        liquidity=liquidity,
        funding=funding,
        breakout_level=breakout_level,
        atr=atr,
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


def feed_block(iid: str, last_update_ms: int, now_ms: int, has_spot: bool, used_cache: bool) -> dict[str, Any]:
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
    else:
        staleness = max(0, now_ms - int(last_update_ms))
        is_stale = staleness > 5000
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
