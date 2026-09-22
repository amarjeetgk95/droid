"""Manual signal generation service — the business logic behind POST /api/v1/signals/generate.

Extracted from ``app/api/signals.py`` so the risk-critical level math is
unit-testable without HTTP plumbing. The router keeps only request parsing and
the ``InvalidManualSignal`` → ``HTTPException`` mapping.

Pipeline (fail-closed at every step):
  1. Validate underlying / timeframe / direction                (422)
  2. Reject new signals after 15:15 IST                         (400)
  3. Resolve spot: manual price > live quote (6s timeout) > trigger level (503)
  4. Spot plausibility corridor per index                        (400)
  5. Live-quote drift guard vs live LTP or last-known-good LTP   (400/503)
  6. Derive entry/trigger/SL/T1/T2 levels (tick-normalized)
  7. Level coherence (SL/entry/T1/T2 ordering per direction)     (400)
  8. Resolve ATM option contract (formula allowed, inactive)     (422)
  9. Strategy normalization + scalp classification               (422)
 10. Trigger-integrity gate                                      (400)
 11. Idempotency dedupe (Idempotency-Key → existing signal)
 12. Register into FSM as ARMED, audit ledger, Supabase persistence
 13. Optional paper execution (only receipt promotes to CONFIRMED) +
      Telegram dispatch + SSE broadcast (never fail the response)

P0-4 rewiring notes:
  * Quote trust comes from :mod:`app.signals.quote_quality` — LIVE only.
    DEGRADED / STALE / CLOSED / INVALID / OFFLINE / synthetic providers are
    all rejected for generation. Quote age beyond ``MAX_QUOTE_AGE_MS``
    (5s) is stale.
  * Drift is enforced against the live LTP when available, else against the
    last-known-good LTP cache — a manual price with neither is 503.
  * Manual signals register ARMED always; only a paper receipt promotes to
    CONFIRMED. Manual confidence is capped at 60 and flagged MANUAL_UNRATED.
  * Long options are always BUY (calls and puts alike).
"""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

import structlog

from app.signals.audit_ledger import signal_audit_ledger
from app.signals.contract_resolver import (
    normalize_price,
    resolve_option_contract,
    resolve_sizing_for_contract,
    validate_underlying,
)
from app.signals.fsm import SignalInstance, signal_fsm
from app.signals.paper_engine import signal_paper_engine
from app.signals.quote_quality import (
    LIVE,
    classify_quote,
    is_fallback_quote,
    require_generation_usable,
)
from app.signals.sse import signal_sse_hub
from app.signals.strategies import SCALP_STRATEGY_NAMES, STRATEGY_REGISTRY

logger = structlog.get_logger()

TICK = Decimal("0.05")
#: Max quote age for generation use (ms). Older quotes are stale.
MAX_QUOTE_AGE_MS = 5000
#: Index-spot drift tolerance floor: |manual - live| / live <= 0.3%.
INDEX_SPOT_DRIFT_TOL = Decimal("0.003")
#: Option-premium drift tolerance (chain mark vs fill domain): 2%.
OPTION_PREMIUM_DRIFT_TOL = Decimal("0.02")
#: Legacy 5% ceiling — kept for backwards-compat imports only. Live decisions
#: use the dynamic threshold (max(0.3%, 2*ATR%)); this constant is not consulted.
MAX_QUOTE_DRIFT = Decimal("0.05")
QUOTE_TIMEOUT_S = 6.0
#: Manual setups are unrated by construction — never echo caller confidence.
MANUAL_CONFIDENCE_CAP = 60.0
MANUAL_CONFLUENCE_SOURCE = "MANUAL_UNRATED"
#: No new manual signals after this IST wall-clock (square-off regime).
NEW_SIGNAL_CUTOFF_HOUR_IST = 15
NEW_SIGNAL_CUTOFF_MIN_IST = 15
#: Fixed pre-trigger TTLs (market-close-unaware): scalp 180s, intraday 300s.
SCALP_TTL_S = 180
INTRADAY_TTL_S = 300

VALID_TIMEFRAMES = ("1M", "3M", "5M", "15M", "1H", "1D")

# Realistic spot corridors per index — guards against fat-finger or stale-feed prices.
INDEX_PLAUSIBLE_RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "NIFTY": (Decimal("22000.0"), Decimal("35000.0")),
    "BANKNIFTY": (Decimal("40000.0"), Decimal("75000.0")),
    "SENSEX": (Decimal("70000.0"), Decimal("120000.0")),
}


class InvalidManualSignal(Exception):
    """Request rejected — carries the HTTP status the router should surface."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _fail(status_code: int, detail: str) -> None:
    raise InvalidManualSignal(status_code, detail)


# ── Quote trust (delegates to quote_quality) ──────────────────────────

def _quote_is_fallback(quote: object) -> bool:
    """Back-compat alias — delegates to the unified quote-quality policy."""
    try:
        return is_fallback_quote(quote)
    except Exception:
        return False


def _quote_age_ms(quote: object) -> int | None:
    """Age of a quote in ms, or None when indeterminable."""
    try:
        now_ms = int(time.time() * 1000)
        ts = getattr(quote, "timestamp", None)
        if ts is not None:
            if isinstance(ts, datetime):
                q = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
                return max(0, int((datetime.now(timezone.utc) - q).total_seconds() * 1000))
            if isinstance(ts, (int, float)) and float(ts) > 0:
                v = float(ts)
                # Heuristic: epoch-ms vs epoch-s.
                q_ms = int(v) if v > 1e12 else int(v * 1000)
                return max(0, now_ms - q_ms)
        for attr in ("fetched_at_ms", "as_of_utc", "timestamp_ms", "updated_at_ms"):
            v = getattr(quote, attr, None)
            if v is not None:
                try:
                    return max(0, now_ms - int(float(v)))
                except Exception:
                    continue
        upd = getattr(quote, "updated_at", None)
        if isinstance(upd, datetime):
            q = upd if upd.tzinfo is not None else upd.replace(tzinfo=timezone.utc)
            return max(0, int((datetime.now(timezone.utc) - q).total_seconds() * 1000))
    except Exception:
        return None
    return None


def _quote_is_live(quote: object, max_quote_age_ms: int = MAX_QUOTE_AGE_MS) -> bool:
    """Strict generation gate: LIVE classification + positive LTP + fresh."""
    if quote is None:
        return False
    try:
        ltp = getattr(quote, "ltp", None)
        if ltp is None or float(ltp) <= 0:
            return False
    except Exception:
        return False
    try:
        if classify_quote(quote) != LIVE:
            return False
    except Exception:
        return False
    age = _quote_age_ms(quote)
    if age is not None and age > max_quote_age_ms:
        return False
    return True


# ── Last-known-good LTP cache (drift reference when live fails) ───────

_LAST_GOOD_LTP: dict[str, dict] = {}
_LAST_GOOD_LOCK = threading.RLock()


def record_last_good_ltp(underlying: str, ltp: float) -> None:
    """Remember the latest verified LIVE LTP for drift fallback."""
    try:
        v = float(ltp)
        if v <= 0:
            return
        with _LAST_GOOD_LOCK:
            _LAST_GOOD_LTP[str(underlying).upper()] = {"ltp": v, "ts_ms": int(time.time() * 1000)}
    except Exception:
        pass


def get_last_good_ltp(underlying: str) -> tuple[float, int] | None:
    """(ltp, age_ms) of the last verified LIVE print, or None."""
    try:
        with _LAST_GOOD_LOCK:
            rec = _LAST_GOOD_LTP.get(str(underlying).upper())
        if not rec:
            return None
        ltp = float(rec["ltp"])
        if ltp <= 0:
            return None
        return ltp, max(0, int(time.time() * 1000) - int(rec["ts_ms"]))
    except Exception:
        return None


def clear_last_good_ltp_cache() -> None:
    with _LAST_GOOD_LOCK:
        _LAST_GOOD_LTP.clear()


# ── Idempotency registry (Idempotency-Key → signal_id) ────────────────

_IDEMPOTENCY_MAP: dict[str, str] = {}
_IDEMPOTENCY_LOCK = threading.RLock()


def _extract_idempotency_key(req: object, explicit: str | None = None) -> str | None:
    if explicit:
        k = str(explicit).strip()
        if k:
            return k
    try:
        for attr in ("idempotency_key", "idempotencyKey", "Idempotency_Key", "idempotency-key"):
            v = getattr(req, attr, None)
            if v:
                k = str(v).strip()
                if k:
                    return k
        if isinstance(req, dict):
            for f in ("idempotency_key", "idempotencyKey", "Idempotency-Key"):
                v = req.get(f)
                if v:
                    k = str(v).strip()
                    if k:
                        return k
    except Exception:
        return None
    return None


def lookup_idempotent_signal(idempotency_key: str) -> SignalInstance | None:
    try:
        with _IDEMPOTENCY_LOCK:
            sid = _IDEMPOTENCY_MAP.get(str(idempotency_key).strip())
        if not sid:
            return None
        return signal_fsm.get(sid)
    except Exception:
        return None


def remember_idempotent_signal(idempotency_key: str, signal_id: str) -> None:
    try:
        k = str(idempotency_key).strip()
        if not k or not signal_id:
            return
        with _IDEMPOTENCY_LOCK:
            _IDEMPOTENCY_MAP.setdefault(k, str(signal_id))
    except Exception:
        pass


def clear_idempotency_registry() -> None:
    with _IDEMPOTENCY_LOCK:
        _IDEMPOTENCY_MAP.clear()


# ── Drift threshold (index-spot 0.3% floor, ATR-adaptive) ─────────────

def drift_threshold_for(underlying: str, spot: Decimal, kind: str = "index_spot") -> Decimal:
    """Allowed relative drift for a price domain.

    * ``index_spot`` → max(0.3%, 2 × ATR%) — tight because levels price off spot.
    * ``option_premium`` → 2% floor (premiums are noisier tick-for-tick).
    """
    base = OPTION_PREMIUM_DRIFT_TOL if kind == "option_premium" else INDEX_SPOT_DRIFT_TOL
    if kind == "option_premium":
        return base
    try:
        from app.signals.risk_engine import resolve_realistic_atr

        spot_d = Decimal(str(spot))
        atr = resolve_realistic_atr(str(underlying), spot_d, None)
        if spot_d > 0 and atr is not None and Decimal(str(atr)) > 0:
            atr_pct = Decimal(str(atr)) / spot_d
            dyn = Decimal("2") * atr_pct
            return max(base, dyn)
    except Exception:
        pass
    return base


def _validate_context(req) -> tuple[str, str, str]:
    """Validate underlying/timeframe/direction → (underlying, timeframe, direction)."""
    raw_u = req.underlying or req.instrument_id or "NIFTY"
    try:
        u = validate_underlying(raw_u)
    except ValueError as ve:
        _fail(422, str(ve))

    tf = (req.timeframe or req.candle_timeframe or "5M").upper()
    if tf not in VALID_TIMEFRAMES:
        _fail(422, f"Unknown timeframe '{tf}'. Use 1M, 3M, 5M, 15M, 1H, or 1D.")

    raw_dir = (req.direction or "LONG_CALL").upper()
    if raw_dir in ("BULLISH", "LONG", "BUY"):
        dir_val = "LONG_CALL"
    elif raw_dir in ("BEARISH", "SHORT", "SELL"):
        dir_val = "LONG_PUT"
    elif raw_dir not in ("LONG_CALL", "LONG_PUT"):
        _fail(422, f"Unknown direction '{req.direction}'. Use LONG_CALL / LONG_PUT (or BULLISH / BEARISH).")
    else:
        dir_val = raw_dir
    return u, tf, dir_val


def _enforce_new_signal_cutoff() -> None:
    """No new manual signals after 15:15 IST (square-off regime)."""
    try:
        from app.services.calendar_service import calendar_service

        perm = calendar_service.can_trade_now()
        ts = getattr(perm, "timestamp_ist", None)
        if ts is None:
            return
        # Mock-friendly: tests pin timestamp_ist to 11:00; prod carries real IST.
        hh, mm = int(getattr(ts, "hour", 0)), int(getattr(ts, "minute", 0))
        if (hh, mm) >= (NEW_SIGNAL_CUTOFF_HOUR_IST, NEW_SIGNAL_CUTOFF_MIN_IST):
            _fail(
                400,
                "NO_NEW_SIGNALS_AFTER_1515_IST: manual signal creation is closed after "
                "15:15 IST (square-off regime). Existing positions continue to be managed.",
            )
    except InvalidManualSignal:
        raise
    except Exception:
        return


async def _resolve_spot(req, u: str) -> tuple[Decimal, bool, object]:
    """Spot = manual price > live quote > trigger level. Returns (spot, quote_ok, quote)."""
    from app.services.market_service import MarketService

    try:
        quote = await asyncio.wait_for(MarketService().get_quote(u), timeout=QUOTE_TIMEOUT_S)
    except Exception:
        quote = None
    # Unified policy: only a fresh LIVE broker quote counts.
    quote_ok = _quote_is_live(quote)
    if quote_ok:
        try:
            require_generation_usable(quote, u)
        except Exception:
            quote_ok = False
    if quote_ok:
        try:
            record_last_good_ltp(u, float(quote.ltp))
        except Exception:
            pass

    if req.current_price:
        spot = Decimal(str(req.current_price))
    elif quote_ok:
        spot = Decimal(str(quote.ltp))
    elif req.trigger or req.trigger_level:
        spot = Decimal(str(req.trigger or req.trigger_level))
    else:
        _fail(
            503,
            f"Live price for {u} is unavailable (feed degraded) and no manual price was supplied. Retry when LIVE.",
        )
    return spot, quote_ok, quote


def _validate_spot(u: str, spot: Decimal, quote_ok: bool, quote: object) -> None:
    """Plausibility corridor + drift guard (live LTP, else last-known-good)."""
    if u in INDEX_PLAUSIBLE_RANGES:
        min_p, max_p = INDEX_PLAUSIBLE_RANGES[u]
        if not (min_p <= spot <= max_p):
            _fail(
                400,
                f"Spot price {spot} for {u} is invalid/implausible. Must be within realistic corridor [{min_p}, {max_p}].",
            )
    threshold = drift_threshold_for(u, spot, kind="index_spot")
    if quote_ok:
        try:
            ref = Decimal(str(quote.ltp))
        except Exception:
            _fail(503, f"Live price for {u} is unavailable (feed degraded). Retry when LIVE.")
        if ref <= 0:
            _fail(503, f"Live price for {u} is unavailable (feed degraded). Retry when LIVE.")
        age_ms = _quote_age_ms(quote)
        age_ms = int(age_ms) if age_ms is not None else 0
    else:
        # Live failed: the manual price must still prove itself against the
        # last-known-good LIVE print — else fail closed with 503.
        cached = get_last_good_ltp(u)
        if cached is None:
            _fail(
                503,
                f"Live price for {u} is unavailable (feed degraded) and no last-known-good "
                f"LTP is cached to validate the manual price {spot}. Retry when LIVE.",
            )
        ref_v, age_ms = cached
        ref = Decimal(str(ref_v))
    if ref > 0:
        drift_pct = abs(spot - ref) / ref
        if drift_pct > threshold:
            _fail(
                400,
                f"DRIFT_EXCEEDED: manual price {spot} deviates by {float(drift_pct * 100):.2f}% "
                f"from reference LTP {ref} for {u} (max {float(threshold * 100):.2f}%). "
                f"detail={{'spot': {float(spot)}, 'age_ms': {int(age_ms)}, "
                f"'drift_pct': {round(float(drift_pct * 100), 3)}, "
                f"'threshold_pct': {round(float(threshold * 100), 3)}}}",
            )


def derive_levels(
    *,
    is_put: bool,
    spot: Decimal,
    trigger: Decimal | None,
    entry_min: Decimal | None,
    entry_max: Decimal | None,
    stop_loss: Decimal | None,
    target_1: Decimal | None,
    target_2: Decimal | None,
) -> dict[str, Decimal]:
    """Derive tick-normalized signal levels, filling gaps from spot/trigger.

    Pure function — unit-test the level math here.
    """
    trig_val = trigger
    min_gap = normalize_price(max(spot * Decimal("0.001"), Decimal("15.0")), TICK)
    trigger = normalize_price(trig_val or (spot - min_gap if is_put else spot + min_gap), TICK)
    entry_min = normalize_price(entry_min or (trigger - Decimal("5.0") if is_put else trigger), TICK)
    entry_max = normalize_price(entry_max or (trigger if is_put else trigger + Decimal("5.0")), TICK)

    if is_put:
        stop_loss = normalize_price(stop_loss or (spot * Decimal("1.005")), TICK)
        risk_pts = abs(stop_loss - entry_max)
        t1 = normalize_price(target_1 or (entry_min - (risk_pts * Decimal("1.5"))), TICK)
        t2 = normalize_price(target_2 or (entry_min - (risk_pts * Decimal("3.0"))), TICK)
    else:
        stop_loss = normalize_price(stop_loss or (spot * Decimal("0.995")), TICK)
        risk_pts = abs(entry_min - stop_loss)
        t1 = normalize_price(target_1 or (entry_max + (risk_pts * Decimal("1.5"))), TICK)
        t2 = normalize_price(target_2 or (entry_max + (risk_pts * Decimal("3.0"))), TICK)

    exit_ref = entry_min if is_put else entry_max
    rr_t1 = float((abs(t1 - exit_ref) / risk_pts).quantize(Decimal("0.1"))) if risk_pts > 0 else 1.5
    rr_t2 = float((abs(t2 - exit_ref) / risk_pts).quantize(Decimal("0.1"))) if risk_pts > 0 else 3.0

    return {
        "trigger": trigger,
        "entry_min": entry_min,
        "entry_max": entry_max,
        "stop_loss": stop_loss,
        "target_1": t1,
        "target_2": t2,
        "risk_points": risk_pts,
        "risk_reward_t1": rr_t1,
        "risk_reward_t2": rr_t2,
    }


def _validate_levels(is_put: bool, levels: dict[str, Decimal]) -> None:
    """Reject incoherent manuals instead of registering doomed signals."""
    if levels["risk_points"] <= 0:
        _fail(400, "Stop-loss must differ from entry (zero risk points).")
    if is_put:
        coherent = levels["stop_loss"] > levels["entry_max"] and levels["target_1"] < levels["entry_min"] and levels["target_2"] < levels["target_1"]
        if not coherent:
            _fail(400, "PUT levels incoherent: need SL > entry > T1 > T2.")
    else:
        coherent = levels["stop_loss"] < levels["entry_min"] and levels["target_1"] > levels["entry_max"] and levels["target_2"] > levels["target_1"]
        if not coherent:
            _fail(400, "CALL levels incoherent: need SL < entry < T1 < T2.")


def _resolve_strategy_and_scalp(req, u: str, tf: str) -> tuple[str, bool]:
    strat_val = req.strategy.upper()
    if strat_val in ("VWAP_REJECTION", "VWAP"):
        strat_val = "VWAP_SCALP"
    if strat_val not in STRATEGY_REGISTRY:
        _fail(422, f"Unknown strategy '{req.strategy}'. Valid: {sorted(STRATEGY_REGISTRY.keys())}")
    is_scalp_setup = req.is_scalp or (req.signal_type == "SCALP") or (tf in ("1M", "3M")) or (strat_val in SCALP_STRATEGY_NAMES)
    return strat_val, is_scalp_setup


def _signal_response_dump(instance: SignalInstance) -> dict:
    sig_dump = instance.model_dump()
    sig_dump["instrument_id"] = instance.underlying
    sig_dump["direction"] = "BULLISH" if "CALL" in instance.direction else "BEARISH"
    sig_dump["created_at_utc"] = instance.created_at_utc
    return sig_dump


async def generate(req, idempotency_key: str | None = None) -> dict:
    """Full manual-generation pipeline. Raises :class:`InvalidManualSignal` on rejection."""
    u, tf, dir_val = _validate_context(req)
    _enforce_new_signal_cutoff()
    spot, quote_ok, quote = await _resolve_spot(req, u)
    _validate_spot(u, spot, quote_ok, quote)

    is_put = "PUT" in dir_val or "BEARISH" in dir_val
    levels = derive_levels(
        is_put=is_put,
        spot=spot,
        trigger=req.trigger or req.trigger_level,
        entry_min=Decimal(str(req.entry_min)) if req.entry_min else None,
        entry_max=Decimal(str(req.entry_max)) if req.entry_max else None,
        stop_loss=Decimal(str(req.stop_loss)) if req.stop_loss else None,
        target_1=Decimal(str(req.target_1)) if req.target_1 else None,
        target_2=Decimal(str(req.target_2)) if req.target_2 else None,
    )
    _validate_levels(is_put, levels)

    try:
        opt_type = "CE" if "CALL" in dir_val else "PE"
        # Manual registration tolerates a formula contract (marked inactive);
        # only the paper receipt may promote the signal to CONFIRMED.
        contract = resolve_option_contract(u, spot, opt_type, strike_offset=0, require_chain_mark=False)
    except ValueError as ve:
        _fail(422, str(ve))

    strat_val, is_scalp_setup = _resolve_strategy_and_scalp(req, u, tf)

    from app.signals.trigger_gate import check_trigger_integrity

    gate = check_trigger_integrity(
        underlying=u,
        strategy=strat_val,
        direction=dir_val,
        spot_price=spot,
        entry_min=levels["entry_min"],
        entry_max=levels["entry_max"],
        trigger=levels["trigger"],
        stop_loss=levels["stop_loss"],
        target_1=levels["target_1"],
        target_2=levels["target_2"],
        risk_points=levels["risk_points"],
        risk_reward_t1=levels["risk_reward_t1"],
        risk_reward_t2=levels["risk_reward_t2"],
        is_scalp=is_scalp_setup,
        timeframe=tf,
    )
    if not gate.passed:
        _fail(400, f"{gate.reason_code}: {gate.message}")

    # Idempotency: a retried Idempotency-Key returns the original signal —
    # never a duplicate registration or a double paper fill.
    idem_key = _extract_idempotency_key(req, idempotency_key)
    if idem_key:
        existing = lookup_idempotent_signal(idem_key)
        if existing is not None:
            sig_dump = _signal_response_dump(existing)
            return {
                "success": True,
                "signal": sig_dump,
                "paper_order": (existing.paper_order or None),
                "paper_status": "SKIPPED",
                "paper_error": None,
                "telegram": {"enqueued": 0, "status": "SKIPPED"},
                "sse": {"status": "SKIPPED"},
                "deduplicated": True,
                "idempotency_key": idem_key,
            }

    instance = _register_instance(req, u, tf, dir_val, spot, strat_val, is_scalp_setup, levels, contract)
    if idem_key:
        remember_idempotent_signal(idem_key, instance.signal_id)

    try:
        await _persist_and_audit(req, instance)
    except Exception as pe:
        logger.warning("generate_signal_persist_failed_non_fatal", error=str(pe))

    paper_result, paper_status, paper_error = await _maybe_execute_paper(req, instance)
    telegram_res = await _maybe_notify_telegram(req, instance, dir_val, tf, paper_result)

    try:
        await signal_sse_hub.broadcast("signal_created", instance.model_dump(), priority="P0")
        sse_res: dict = {"status": "SENT"}
    except Exception as se:
        logger.warning("generate_sse_broadcast_failed_non_fatal", error=str(se))
        sse_res = {"status": "FAILED", "error": str(se)[:200]}

    sig_dump = _signal_response_dump(instance)

    paper_order_dict = None
    if paper_result is not None and getattr(paper_result, "order_id", None):
        # Long options are ALWAYS bought — calls and puts alike.
        paper_order_dict = {
            "order_id": paper_result.order_id,
            "status": paper_result.status,
            "side": "BUY",
            "quantity": paper_result.quantity,
            "underlying": instance.underlying,
            "fill_price": paper_result.fill_price,
        }
    elif instance.paper_order:
        try:
            po = instance.paper_order if isinstance(instance.paper_order, dict) else {}
            paper_order_dict = {
                "order_id": po.get("order_id", ""),
                "status": po.get("status", paper_status),
                "side": "BUY",
                "quantity": po.get("quantity", 0),
                "underlying": instance.underlying,
                "fill_price": po.get("fill_price", 0.0),
            }
        except Exception:
            paper_order_dict = None

    # Sizing evidence: options size off premium (buyer sizing is the default),
    # never off index-spot points.
    sizing_evidence: dict | None = None
    try:
        opt = instance.option_contract or {}
        prem = opt.get("live_premium") if isinstance(opt, dict) else None
        if prem is not None and float(prem) > 0:
            sizing_evidence = resolve_sizing_for_contract(
                opt,
                available_capital=1000000.0,
                risk_percent=2.0,
                option_entry_premium=float(prem),
            )
    except Exception:
        sizing_evidence = None

    return {
        "success": True,
        "signal": sig_dump,
        "paper_order": paper_order_dict,
        "paper_status": paper_status,
        "paper_error": paper_error,
        "telegram": telegram_res,
        "sse": sse_res,
        "sizing": sizing_evidence,
        "deduplicated": False,
        **({"idempotency_key": idem_key} if idem_key else {}),
    }


def _register_instance(req, u, tf, dir_val, spot, strat_val, is_scalp_setup, levels, contract) -> SignalInstance:
    # P0-4: manual signals register ARMED always — never CONFIRMED pre-paper.
    # Only a paper receipt (paper_engine fill) promotes to CONFIRMED.
    fsm_st = "ARMED"
    sig_type = "SCALP" if is_scalp_setup else (req.signal_type or "INTRADAY")
    # Fixed pre-trigger TTLs (not market-close-aware by request): scalp 180s, intraday 300s.
    ttl_s = SCALP_TTL_S if is_scalp_setup else INTRADAY_TTL_S

    # Manual setups are unrated: cap confidence at 60 and null the breakdown.
    # Missing caller confidence is explicit UNVETTED (never a silent 80.0);
    # provided confidence is capped and flagged MANUAL_UNRATED.
    try:
        if req.confidence is None:
            confidence: float | None = MANUAL_CONFIDENCE_CAP  # type: ignore[annotation-unchecked]
            _conf_status = "UNVETTED"
        else:
            asked = float(req.confidence)
            confidence = min(asked, MANUAL_CONFIDENCE_CAP)
            _conf_status = "MANUAL_UNRATED"
    except Exception:
        confidence = MANUAL_CONFIDENCE_CAP  # type: ignore[assignment]
        _conf_status = "UNVETTED"

    instance = SignalInstance(
        underlying=u,
        strategy=strat_val,
        direction=dir_val,
        timeframe=tf,
        spot_price=spot,
        signal_type=sig_type,
        is_scalp=is_scalp_setup,
        entry_min=levels["entry_min"],
        entry_max=levels["entry_max"],
        trigger=levels["trigger"],
        stop_loss=levels["stop_loss"],
        initial_stop_loss=levels["stop_loss"],
        current_stop_loss=levels["stop_loss"],
        target_1=levels["target_1"],
        target_2=levels["target_2"],
        t1_price=levels["target_1"],
        t2_price=levels["target_2"],
        risk_points=levels["risk_points"],
        risk_reward_t1=levels["risk_reward_t1"],
        risk_reward_t2=levels["risk_reward_t2"],
        ttl_seconds=ttl_s,
        runner_ttl_seconds=req.runner_ttl_seconds,
        confidence=confidence,
        confluence_breakdown={
            "technical": None,
            "mtf": None,
            "fno": None,
            "regime": None,
            "ai": None,
            "confluence_source": MANUAL_CONFLUENCE_SOURCE,
            "unrated": True,
            "confidence_status": _conf_status,
        },
        rationale=req.rationale or [f"Manual {req.strategy} setup on {u}"],
        option_contract=contract.model_dump(),
        fsm_state=fsm_st,
    )
    signal_fsm.register(instance)
    return instance


async def _persist_and_audit(req, instance: SignalInstance) -> None:
    try:
        _audit_conf = float(instance.confidence) if getattr(instance, "confidence", None) is not None else None
        signal_audit_ledger.record_signal_created(
            signal_id=instance.signal_id,
            underlying=instance.underlying,
            strategy=instance.strategy,
            direction=instance.direction,
            timeframe=instance.timeframe,
            spot_price=float(instance.spot_price),
            trigger=float(instance.trigger),
            stop_loss=float(instance.stop_loss),
            target_1=float(instance.target_1),
            target_2=float(instance.target_2),
            confidence=_audit_conf if _audit_conf is not None else 60.0,
            option_contract=instance.option_contract,
            lots=req.lots or 1,
            status=instance.fsm_state,
        )
    except Exception as ae:
        logger.warning("audit_record_created_failed", error=str(ae))

    try:
        from app.signals.signals_persistence import persist_executed_signal

        await persist_executed_signal(instance)
    except Exception as se:
        logger.warning("generate_signal_supabase_persist_failed", signal_id=instance.signal_id, error=str(se))


async def _maybe_execute_paper(req, instance: SignalInstance):
    """Execute paper when requested. Returns (result|None, status, error).

    Status is never None: SKIPPED (not requested / blocked), the broker
    status on fill (e.g. FILLED), or FAILED with evidence. Exceptions never
    propagate — the signal response still returns success=True.
    """
    if not req.execute_paper:
        return None, "SKIPPED", None
    from app.services.calendar_service import calendar_service

    try:
        perm = calendar_service.can_trade_now()
    except Exception as ce:
        logger.warning("generate_signal_paper_calendar_failed", error=str(ce))
        return None, "FAILED", f"calendar check failed: {ce!s}"[:200]
    if not perm.allowed:
        logger.warning("generate_signal_paper_auto_blocked_market_closed", reason=perm.reason)
        return None, "SKIPPED", f"MARKET_CLOSED: {perm.reason}"

    # Execution lots: explicit request wins, else a single-lot default. Option
    # legs are PRICED off premium-domain buyer sizing (see the `sizing`
    # evidence on the response, wired via resolve_sizing_for_contract), while
    # the fill itself stays a 1-lot default unless the desk pins lots — the
    # paper engine prices the fill from the live chain mark either way.
    lots_override = req.lots or 1
    try:
        result = await signal_paper_engine.execute_signal(instance.signal_id, lots_override=lots_override)
    except Exception as pe:
        logger.warning("generate_signal_paper_auto_failed", error=str(pe))
        return None, "FAILED", str(pe)[:300]
    try:
        if result is not None and getattr(result, "success", False) and getattr(result, "status", "") != "REJECTED":
            return result, (getattr(result, "status", None) or "FILLED"), None
        msg = getattr(result, "message", None) if result is not None else "no receipt"
        return result, "FAILED", str(msg)[:300]
    except Exception as se:
        logger.warning("generate_signal_paper_status_failed", error=str(se))
        return result, "FAILED", str(se)[:200]


async def _maybe_notify_telegram(req, instance: SignalInstance, dir_val: str, tf: str, paper_result) -> dict:
    """Telegram dispatch — best-effort with explicit SKIPPED/FAILED status."""
    if not req.notify_telegram:
        return {"enqueued": 0, "status": "SKIPPED"}
    is_real_fill = paper_result is not None and getattr(paper_result, "success", False) and getattr(paper_result, "status", "") != "REJECTED"
    ev_type = "SIGNAL_CONFIRMED" if is_real_fill else "POSSIBLE_SETUP"
    try:
        from app.institutional.telegram_notifications import SignalEvent, telegram_notification_queue

        _tg_conf = float(instance.confidence) if getattr(instance, "confidence", None) is not None else None
        ev = SignalEvent(
            event_type=ev_type,
            signal_id=instance.signal_id,
            instrument=instance.underlying,
            candle_timeframe=tf,
            setup_type=req.strategy,
            direction="BULLISH" if "CALL" in dir_val else "BEARISH",
            status=instance.fsm_state,
            trigger_level=float(instance.trigger),
            current_price=float(instance.spot_price),
            stop_loss=float(instance.stop_loss),
            confidence=_tg_conf if _tg_conf is not None else 0.0,
            paper_order_id=paper_result.order_id if is_real_fill else None,
            paper_fill_price=paper_result.fill_price if is_real_fill else None,
            paper_filled_qty=paper_result.quantity if is_real_fill else None,
            paper_status=(paper_result.status if is_real_fill else "SKIPPED"),
            # Long options are always bought — puts included.
            paper_side="BUY",
        )
        ids = await telegram_notification_queue.publish_signal_event(ev)
        n = len(ids or [])
        return {"enqueued": n, "status": "SENT" if n > 0 else "SKIPPED"}
    except Exception as te:
        logger.warning("generate_telegram_dispatch_failed", error=str(te))
        return {"enqueued": 0, "status": "FAILED", "error": str(te)[:200]}


async def resolve_live_spot(u: str) -> Decimal | None:
    """Live spot for auto-detect baseline levels. None when feed is degraded/fallback."""
    from app.services.market_service import MarketService

    try:
        quote = await MarketService().get_quote(u)
    except Exception:
        return None
    if not _quote_is_live(quote):
        return None
    try:
        record_last_good_ltp(u, float(quote.ltp))
    except Exception:
        pass
    return Decimal(str(quote.ltp))


def build_baseline_candidate(u: str, strategy: str, timeframe: str, spot: Decimal) -> dict:
    """Fail-closed baseline for detected=False: no tradable levels.

    Returns spot context only — entry/stop/target are None, confidence is None
    with INSUFFICIENT_DATA, option_contract is None, tradable=False. Callers
    must not enter/stop/target off an undetected baseline.
    """
    return {
        "underlying": u,
        "strategy": strategy,
        "direction": "NO_TRADE",
        "timeframe": timeframe,
        "spot_price": float(spot),
        "entry_min": None,
        "entry_max": None,
        "trigger": None,
        "stop_loss": None,
        "target_1": None,
        "target_2": None,
        "confidence": None,
        "confidence_status": "INSUFFICIENT_DATA",
        "option_contract": None,
        "tradable": False,
        "status": "UNVETTED",
    }
