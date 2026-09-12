"""Manual signal generation service — the business logic behind POST /api/v1/signals/generate.

Extracted from ``app/api/signals.py`` so the risk-critical level math is
unit-testable without HTTP plumbing. The router keeps only request parsing and
the ``InvalidManualSignal`` → ``HTTPException`` mapping.

Pipeline (fail-closed at every step):
  1. Validate underlying / timeframe / direction                (422)
  2. Resolve spot: manual price > live quote (6s timeout) > trigger level (503)
  3. Spot plausibility corridor per index                        (400)
  4. Live-quote drift guard (max 5%)                             (400)
  5. Derive entry/trigger/SL/T1/T2 levels (tick-normalized)
  6. Level coherence (SL/entry/T1/T2 ordering per direction)     (400)
  7. Resolve ATM option contract                                 (422)
  8. Strategy normalization + scalp classification               (422)
  9. Trigger-integrity gate                                      (400)
 10. Register into FSM, audit ledger, Supabase persistence
 11. Optional paper execution + Telegram dispatch + SSE broadcast
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import structlog

from app.signals.audit_ledger import signal_audit_ledger
from app.signals.contract_resolver import (
    normalize_price,
    resolve_option_contract,
    validate_underlying,
)
from app.signals.fsm import SignalInstance, signal_fsm
from app.signals.paper_engine import signal_paper_engine
from app.signals.sse import signal_sse_hub
from app.signals.strategies import SCALP_STRATEGY_NAMES, STRATEGY_REGISTRY

logger = structlog.get_logger()

TICK = Decimal("0.05")
MAX_QUOTE_DRIFT = Decimal("0.05")  # 5% deviation from live LTP is rejected
QUOTE_TIMEOUT_S = 6.0

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


def _quote_is_fallback(quote: object) -> bool:
    try:
        status = str(getattr(quote, "status", "") or "").upper()
        provider = str(getattr(quote, "provider", "") or "").lower()
        return "OFFLINE" in status or provider in ("fallback", "synthetic", "mock")
    except Exception:
        return False


def _quote_is_live(quote: object) -> bool:
    return quote is not None and getattr(quote, "ltp", None) is not None and not _quote_is_fallback(quote)


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


async def _resolve_spot(req, u: str) -> tuple[Decimal, bool, object]:
    """Spot = manual price > live quote > trigger level. Returns (spot, quote_ok, quote)."""
    from app.services.market_service import MarketService

    try:
        quote = await asyncio.wait_for(MarketService().get_quote(u), timeout=QUOTE_TIMEOUT_S)
    except Exception:
        quote = None
    quote_ok = _quote_is_live(quote)

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
    """Plausibility corridor + drift guard."""
    if u in INDEX_PLAUSIBLE_RANGES:
        min_p, max_p = INDEX_PLAUSIBLE_RANGES[u]
        if not (min_p <= spot <= max_p):
            _fail(
                400,
                f"Spot price {spot} for {u} is invalid/implausible. Must be within realistic corridor [{min_p}, {max_p}].",
            )
    if quote_ok and float(quote.ltp) > 0:
        quote_p = Decimal(str(quote.ltp))
        drift_pct = abs(spot - quote_p) / quote_p
        if drift_pct > MAX_QUOTE_DRIFT:
            _fail(
                400,
                f"Price {spot} deviates by {float(drift_pct * 100):.1f}% from live market LTP {quote_p}. "
                f"Max allowed drift is {float(MAX_QUOTE_DRIFT * 100):.1f}%.",
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


async def generate(req) -> dict:
    """Full manual-generation pipeline. Raises :class:`InvalidManualSignal` on rejection."""
    u, tf, dir_val = _validate_context(req)
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
        contract = resolve_option_contract(u, spot, opt_type, strike_offset=0)
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

    instance = _register_instance(req, u, tf, dir_val, spot, strat_val, is_scalp_setup, levels, contract)
    await _persist_and_audit(req, instance)
    paper_result = await _maybe_execute_paper(req, instance)
    telegram_res = await _maybe_notify_telegram(req, instance, dir_val, tf, paper_result)

    await signal_sse_hub.broadcast("signal_created", instance.model_dump(), priority="P0")

    sig_dump = instance.model_dump()
    sig_dump["instrument_id"] = instance.underlying
    sig_dump["direction"] = "BULLISH" if "CALL" in instance.direction else "BEARISH"
    sig_dump["created_at_utc"] = instance.created_at_utc

    paper_order_dict = None
    if paper_result:
        paper_order_dict = {
            "order_id": paper_result.order_id,
            "status": paper_result.status,
            "side": "BUY" if "CALL" in instance.direction else "SELL",
            "quantity": paper_result.quantity,
            "underlying": instance.underlying,
            "fill_price": paper_result.fill_price,
        }

    return {
        "success": True,
        "signal": sig_dump,
        "paper_order": paper_order_dict,
        "telegram": telegram_res,
    }


def _register_instance(req, u, tf, dir_val, spot, strat_val, is_scalp_setup, levels, contract) -> SignalInstance:
    fsm_st = "CONFIRMED" if (req.execute_paper or req.status == "CONFIRMED") else "ARMED"
    sig_type = "SCALP" if is_scalp_setup else (req.signal_type or "INTRADAY")
    ttl_s = req.time_stop_seconds or (180 if is_scalp_setup else 300)

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
        confidence=req.confidence or 80.0,
        confluence_breakdown={"technical": 80.0, "mtf": 75.0, "fno": 75.0, "regime": 80.0, "ai": 75.0},
        rationale=req.rationale or [f"Manual {req.strategy} setup on {u}"],
        option_contract=contract.model_dump(),
        fsm_state=fsm_st,
    )
    signal_fsm.register(instance)
    return instance


async def _persist_and_audit(req, instance: SignalInstance) -> None:
    try:
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
            confidence=float(instance.confidence),
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
    if not req.execute_paper:
        return None
    from app.services.calendar_service import calendar_service

    perm = calendar_service.can_trade_now()
    if not perm.allowed:
        logger.warning("generate_signal_paper_auto_blocked_market_closed", reason=perm.reason)
        return None
    try:
        return await signal_paper_engine.execute_signal(instance.signal_id, lots_override=req.lots or 1)
    except Exception as pe:
        logger.warning("generate_signal_paper_auto_failed", error=str(pe))
        return None


async def _maybe_notify_telegram(req, instance: SignalInstance, dir_val: str, tf: str, paper_result) -> dict:
    telegram_res = {"enqueued": 0}
    if not req.notify_telegram:
        return telegram_res
    is_real_fill = paper_result and paper_result.success and paper_result.status != "REJECTED"
    ev_type = "SIGNAL_CONFIRMED" if is_real_fill else "POSSIBLE_SETUP"
    try:
        from app.institutional.telegram_notifications import SignalEvent, telegram_notification_queue

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
            confidence=float(instance.confidence),
            paper_order_id=paper_result.order_id if is_real_fill else None,
            paper_fill_price=paper_result.fill_price if is_real_fill else None,
            paper_filled_qty=paper_result.quantity if is_real_fill else None,
            paper_status=paper_result.status if is_real_fill else None,
            paper_side="BUY" if "CALL" in dir_val else "SELL",
        )
        ids = await telegram_notification_queue.publish_signal_event(ev)
        telegram_res["enqueued"] = len(ids)
    except Exception as te:
        logger.warning("generate_telegram_dispatch_failed", error=str(te))
    return telegram_res


async def resolve_live_spot(u: str) -> Decimal | None:
    """Live spot for auto-detect baseline levels. None when feed is degraded/fallback."""
    from app.services.market_service import MarketService

    try:
        quote = await MarketService().get_quote(u)
    except Exception:
        return None
    if not _quote_is_live(quote):
        return None
    return Decimal(str(quote.ltp))


def build_baseline_candidate(u: str, strategy: str, timeframe: str, spot: Decimal) -> dict:
    """Baseline (detected=False) pre-fill levels from a live spot price."""
    contract = resolve_option_contract(u, spot, "CE", strike_offset=0)
    entry = normalize_price(spot, TICK)
    sl = normalize_price(spot * Decimal("0.995"), TICK)
    t1 = normalize_price(spot + ((entry - sl) * Decimal("1.5")), TICK)
    t2 = normalize_price(spot + ((entry - sl) * Decimal("3.0")), TICK)
    return {
        "underlying": u,
        "strategy": strategy,
        "direction": "LONG_CALL",
        "timeframe": timeframe,
        "spot_price": float(spot),
        "entry_min": float(entry),
        "entry_max": float(entry + Decimal("10.0")),
        "trigger": float(entry + TICK),
        "stop_loss": float(sl),
        "target_1": float(t1),
        "target_2": float(t2),
        "confidence": 75.0,
        "option_contract": contract.model_dump(),
    }
