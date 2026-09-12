"""
Automated Dual-Cadence Signal Engine & High-Frequency Outcome Worker (Version 6.0)

Architecture:
  1. Priority 1: Open-Position Risk Management Loop (3-second cadence, 2500ms budget).
     - Dedicated exclusively to open-risk management, stops, ratchets, and staged exits.
     - NEVER creates or scans new candidates.
     - Cycle-overrun protection with latency telemetry.
  2. Priority 2: Dual-Cadence Candidate Scanner Loop.
     - Fast Scalp Desk (1M): Scans every 10 seconds on confirmed candle closes.
     - Core Intraday Desk (5M): Scans every 30 seconds on 5M candles.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
import structlog

from app.signals.contract_resolver import APPROVED_UNDERLYINGS
from app.signals.scanner import scanner_engine
from app.signals.outcome_tracker import outcome_tracker
from app.signals.fsm import signal_fsm
from app.services.market_service import MarketService
from app.services.calendar_service import calendar_service
from app.models.market import DataStatus

logger = structlog.get_logger()

MAX_QUOTE_AGE_SECONDS: float = 15.0


class AutomatedSignalWorker:
    """
    Decoupled dual-cadence worker:
      - Risk Management Loop (3s, budget: 2500ms)
      - Scalp Scanner Loop (10s)
      - Intraday Scanner Loop (30s)
    """

    def __init__(
        self,
        risk_interval_seconds: float = 3.0,
        scalp_scan_interval_seconds: float = 10.0,
        intraday_scan_interval_seconds: float = 30.0,
        max_risk_cycle_budget_ms: float = 2500.0,
    ):
        self._risk_interval = risk_interval_seconds
        self._scalp_interval = scalp_scan_interval_seconds
        self._intraday_interval = intraday_scan_interval_seconds
        self._budget_ms = max_risk_cycle_budget_ms

        self._running = False
        self._risk_task: asyncio.Task | None = None
        self._scanner_task: asyncio.Task | None = None
        self._market_svc = MarketService()
        self._last_market_open: bool | None = None
        self._last_risk_closed_log_ts: float = 0.0
        self._last_scanner_closed_log_ts: float = 0.0
        self._bg_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._risk_task = asyncio.create_task(self._run_position_risk_loop())
        self._scanner_task = asyncio.create_task(self._run_scanner_loop())
        logger.info(
            "automated_signal_worker_started",
            risk_interval=self._risk_interval,
            scalp_interval=self._scalp_interval,
            intraday_interval=self._intraday_interval,
        )

    async def stop(self) -> None:
        self._running = False
        for t in (self._risk_task, self._scanner_task):
            if t:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        for t in list(self._bg_tasks):
            t.cancel()
        self._bg_tasks.clear()
        self._risk_task = None
        self._scanner_task = None
        logger.info("automated_signal_worker_stopped")

    async def _run_position_risk_loop(self) -> None:
        """
        Dedicated 3-second open-position risk management loop (§14).
        Enforces Market Session Permission & Quote Freshness Invariants.
        """
        while self._running:
            cycle_start = time.perf_counter()
            try:
                # ── Centralized Market Session Check ──
                perm = calendar_service.can_trade_now()
                if not perm.allowed:
                    # Session transition check: trigger idempotent market-close sweep
                    if self._last_market_open is not False:
                        self._last_market_open = False
                        sweep_res = signal_fsm.sweep_expired()
                        logger.info("market_closed_idempotent_sweep_executed", reason=perm.reason, sweep=sweep_res)
                        # EOD square-off: the FSM sweep alone never books P&L —
                        # without this, open paper positions and EXECUTED audit
                        # rows survive overnight with frozen MTM (ghost opens).
                        eod_task = asyncio.create_task(self._settle_eod_positions())
                        self._bg_tasks.add(eod_task)
                        eod_task.add_done_callback(self._bg_tasks.discard)

                    now_wall = time.time()
                    if now_wall - self._last_risk_closed_log_ts >= 60.0:
                        self._last_risk_closed_log_ts = now_wall
                        logger.info("worker_risk_loop_paused_market_closed", reason=perm.reason, session=perm.session)

                    await asyncio.sleep(max(1.0, self._risk_interval))
                    continue

                self._last_market_open = True

                # Iterate approved instruments and manage open risk
                for u in list(APPROVED_UNDERLYINGS):
                    try:
                        quote = await self._market_svc.get_quote(u)
                        if not quote or getattr(quote, "ltp", None) is None:
                            continue

                        ltp = float(quote.ltp)
                        if ltp <= 0:
                            logger.debug("worker_risk_tick_rejected_non_positive", underlying=u, ltp=ltp)
                            continue

                        status = getattr(quote, "status", None)
                        if status != DataStatus.LIVE and str(status).upper() != "LIVE":
                            logger.debug("worker_risk_tick_rejected_not_live", underlying=u, status=str(status))
                            continue

                        # Quote freshness validation (15s ceiling)
                        if getattr(quote, "timestamp", None):
                            q_ts = quote.timestamp
                            if q_ts.tzinfo is None:
                                q_ts = q_ts.replace(tzinfo=timezone.utc)
                            age_sec = (datetime.now(timezone.utc) - q_ts).total_seconds()
                            if age_sec > MAX_QUOTE_AGE_SECONDS:
                                logger.debug("worker_risk_tick_rejected_stale", underlying=u, age_sec=round(age_sec, 2))
                                continue

                        # Feed Circuit Breaker Check
                        from app.signals.safety.feed_circuit import feed_circuit
                        if feed_circuit.is_degraded(u):
                            logger.warning("worker_risk_tick_skipped_feed_degraded", underlying=u)
                            continue

                        curr_p = Decimal(str(ltp))
                        # Process price updates (triggers, ratchets, staged exits, time stops)
                        await outcome_tracker.process_price_update_async(u, curr_p)

                        # Non-critical telemetry & audit MTM update: offload to background task to protect 2500ms cycle budget
                        async def _bg_audit_and_sse(sym: str, price_val: Decimal):
                            try:
                                import time as _time

                                from app.signals.audit_ledger import signal_audit_ledger
                                from app.signals.sse import signal_sse_hub
                                updated_recs = signal_audit_ledger.update_live_quote(sym, float(price_val))
                                if updated_recs:
                                    # Include per-trade MTM deltas so the P&L ledger can
                                    # apply SSE updates incrementally without a full
                                    # /audit refetch every 3s. Cap payload size.
                                    try:
                                        deltas = [r.model_dump() for r in updated_recs[:50]]
                                    except Exception:
                                        deltas = []
                                    await signal_sse_hub.broadcast(
                                        "audit_pnl_update",
                                        {
                                            "underlying": sym,
                                            "ltp": float(price_val),
                                            "summary": signal_audit_ledger.get_summary_metrics(),
                                            "trades": deltas,
                                            "count": len(updated_recs),
                                            "timestamp_ms": int(_time.time() * 1000),
                                        },
                                        priority="P1",
                                    )
                            except Exception as te_err:
                                logger.debug("worker_bg_audit_telemetry_error", underlying=sym, error=str(te_err))

                        bg_task = asyncio.create_task(_bg_audit_and_sse(u, curr_p))
                        self._bg_tasks.add(bg_task)
                        bg_task.add_done_callback(self._bg_tasks.discard)
                    except Exception as pe:
                        logger.debug("worker_risk_tick_err", underlying=u, error=str(pe))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("risk_management_cycle_error", error=str(e))

            cycle_duration_ms = (time.perf_counter() - cycle_start) * 1000.0
            if cycle_duration_ms > self._budget_ms:
                logger.warning(
                    "risk_management_cycle_overrun",
                    duration_ms=round(cycle_duration_ms, 2),
                    budget_ms=self._budget_ms,
                )

            # Sleep remaining budget
            sleep_sec = max(0.1, self._risk_interval - (cycle_duration_ms / 1000.0))
            try:
                await asyncio.sleep(sleep_sec)
            except asyncio.CancelledError:
                break

    async def _settle_eod_positions(self) -> None:
        """EOD session square-off: close open paper positions and settle the audit
        ledger so no ghost EXECUTED rows (frozen MTM, no exit) survive overnight.
        Idempotent — signals without paper orders or already settled are skipped."""
        try:
            from app.signals.paper_engine import signal_paper_engine
            settled = 0
            for sig in signal_fsm.list_active(include_terminal=True):
                # RUNNER_TIME_STOP_HIT / TIME_STOP_HIT must be included: the
                # sweep executed moments earlier on this same market-close edge
                # converts TARGET_1_HIT/CONFIRMED into those terminal states
                # without squaring off the paper position — skipping them here
                # would leave exactly the ghost opens this task exists to clear.
                if sig.fsm_state not in ("CONFIRMED", "TARGET_1_HIT", "RUNNER_TIME_STOP_HIT", "TIME_STOP_HIT"):
                    continue
                if not getattr(sig, "paper_order", None):
                    continue
                try:
                    await signal_paper_engine.close_signal_position(
                        sig.signal_id,
                        exit_price=None,
                        reason="EOD_SQUAREOFF",
                        allow_closed_market=True,
                    )
                    settled += 1
                except Exception as ce:
                    logger.debug("eod_square_off_failed", signal_id=sig.signal_id, error=str(ce)[:150])
                    continue
                try:
                    signal_fsm.transition(sig.signal_id, "CLOSED", market_price=None, reason="EOD_SESSION_SQUARE_OFF")
                except Exception:
                    pass
            if settled:
                logger.info("eod_positions_settled", count=settled)
        except Exception as e:
            logger.warning("eod_settle_error", error=str(e)[:200])

    async def _run_scanner_loop(self) -> None:
        """
        Dual-cadence candidate scanning loop:
          - Scalp Desk: every 10 seconds
          - Intraday Desk: every 30 seconds
        Enforces Market Session Permission: never scans stale/post-market candles.
        """
        last_scalp_ts = 0.0
        last_intraday_ts = 0.0

        while self._running:
            try:
                # ── Centralized Market Session Check ──
                perm = calendar_service.can_trade_now()
                if not perm.allowed:
                    now_wall = time.time()
                    if now_wall - self._last_scanner_closed_log_ts >= 60.0:
                        self._last_scanner_closed_log_ts = now_wall
                        logger.info("worker_scanner_loop_paused_market_closed", reason=perm.reason, session=perm.session)

                    await asyncio.sleep(5.0)
                    continue

                now = time.time()

                # 0. Live contract symbols (FYERS chain truth, 60s cadence).
                # Keeps broker_symbol/premium exact; resolver falls back to
                # formula when the chain is unreachable.
                try:
                    from app.signals.live_contract_cache import live_contract_cache
                    live_contract_cache.schedule_refresh(self._market_svc)
                except Exception:
                    pass

                # 1. Fast Scalp Scanning (1M)
                if now - last_scalp_ts >= self._scalp_interval:
                    last_scalp_ts = now
                    try:
                        await scanner_engine.scan_scalp()
                    except Exception as se:
                        logger.debug("scalp_scanner_error", error=str(se))

                # 2. Core Intraday Scanning (5M)
                if now - last_intraday_ts >= self._intraday_interval:
                    last_intraday_ts = now
                    try:
                        await scanner_engine.scan_intraday()
                    except Exception as ie:
                        logger.debug("intraday_scanner_error", error=str(ie))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("scanner_loop_error", error=str(e))

            try:
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                break


automated_signal_worker = AutomatedSignalWorker()

