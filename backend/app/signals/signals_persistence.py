"""
Supabase / PostgreSQL & Local Cache Persistence Layer for Executed Signals & Audit Ledger
Persists trade lifecycle, execution receipts, and audited P&L across deployments, restarts, and redeployments.

Strategy:
  1. Primary: Supabase / PostgreSQL (executed_signals table)
  2. Fallback / Local Fast Cache: signals_state.json (guarantees signals never reset to zero on redeploy)
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
import structlog
from sqlalchemy import text

from app.core.database import get_async_session_factory

logger = structlog.get_logger()

SIGNALS_STATE_FILE = Path("signals_state.json")


def save_signals_state_local(
    fsm_signals: Optional[dict[str, Any]] = None,
    audit_trades: Optional[dict[str, Any]] = None,
) -> bool:
    """Safely persist active FSM signals and audit trades to local cache file."""
    try:
        from app.signals.fsm import signal_fsm
        from app.signals.audit_ledger import signal_audit_ledger
        from app.signals.fill_reconciler import option_fill_reconciler

        fsm_dict = fsm_signals if fsm_signals is not None else signal_fsm._signals
        audit_dict = audit_trades if audit_trades is not None else signal_audit_ledger._trades
        recon_dict = getattr(option_fill_reconciler, "_records", {})

        serialized_fsm = {}
        for sid, s in fsm_dict.items():
            if hasattr(s, "model_dump"):
                data = s.model_dump(mode="json")
                serialized_fsm[sid] = data
            elif isinstance(s, dict):
                serialized_fsm[sid] = s

        serialized_audit = {}
        for aid, t in audit_dict.items():
            if hasattr(t, "model_dump"):
                serialized_audit[aid] = t.model_dump(mode="json")
            elif isinstance(t, dict):
                serialized_audit[aid] = t

        serialized_recon = {}
        for rid, r in recon_dict.items():
            if hasattr(r, "model_dump"):
                serialized_recon[rid] = r.model_dump(mode="json")
            elif isinstance(r, dict):
                serialized_recon[rid] = r

        payload = {
            "fsm_signals": serialized_fsm,
            "audit_trades": serialized_audit,
            "fill_reconciliations": serialized_recon,
            "updated_at_utc": int(__import__("time").time() * 1000),
        }

        tmp_file = SIGNALS_STATE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        tmp_file.replace(SIGNALS_STATE_FILE)
        return True
    except Exception as e:
        logger.warning("save_signals_state_local_failed", error=str(e)[:250])
        return False


def restore_signals_state_local() -> int:
    """Restore signals from local cache file if PostgreSQL is unavailable or empty."""
    if not SIGNALS_STATE_FILE.exists():
        return 0

    try:
        from app.signals.fsm import signal_fsm, SignalInstance
        from app.signals.audit_ledger import signal_audit_ledger, AuditTradeRecord, AuditStateEvent
        from app.signals.fill_reconciler import option_fill_reconciler, FillReconciliationRecord

        with open(SIGNALS_STATE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)

        count = 0
        raw_fsm = payload.get("fsm_signals", {})
        for sid, sdata in raw_fsm.items():
            if sid not in signal_fsm._signals and isinstance(sdata, dict):
                try:
                    # Convert string/float numbers to Decimal for Decimal fields
                    for dec_field in ("spot_price", "entry_min", "entry_max", "trigger", "stop_loss", "target_1", "target_2", "risk_points"):
                        if dec_field in sdata and sdata[dec_field] is not None:
                            sdata[dec_field] = Decimal(str(sdata[dec_field]))
                    inst = SignalInstance(**sdata)
                    signal_fsm._signals[sid] = inst
                    count += 1
                except Exception as fe:
                    logger.debug("restore_local_fsm_sig_err", signal_id=sid, error=str(fe))

        raw_audit = payload.get("audit_trades", {})
        for aid, tdata in raw_audit.items():
            if aid not in signal_audit_ledger._trades and isinstance(tdata, dict):
                try:
                    rec = AuditTradeRecord(**tdata)
                    signal_audit_ledger._trades[aid] = rec
                except Exception as ae:
                    logger.debug("restore_local_audit_trade_err", audit_id=aid, error=str(ae))

        raw_recon = payload.get("fill_reconciliations", {})
        for rid, rdata in raw_recon.items():
            if rid not in option_fill_reconciler._records and isinstance(rdata, dict):
                try:
                    rrec = FillReconciliationRecord(**rdata)
                    option_fill_reconciler._records[rid] = rrec
                except Exception:
                    pass

        logger.info("signals_restored_from_local_cache", count=count)
        return count
    except Exception as e:
        logger.warning("restore_signals_state_local_failed", error=str(e)[:250])
        return 0


async def ensure_signals_tables() -> bool:
    """Auto-provision executed_signals table in Supabase PostgreSQL if not present."""
    factory = get_async_session_factory()
    if factory is None:
        logger.debug("signals_persistence_no_db_factory")
        return False
    try:
        async with factory() as session:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS executed_signals (
                    signal_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    timeframe TEXT NOT NULL DEFAULT '5M',
                    option_symbol TEXT,
                    option_type TEXT,
                    option_strike DOUBLE PRECISION,
                    lot_size INT NOT NULL DEFAULT 75,
                    lots INT NOT NULL DEFAULT 1,
                    quantity INT NOT NULL DEFAULT 75,
                    spot_price_at_creation DOUBLE PRECISION,
                    trigger_price DOUBLE PRECISION,
                    stop_loss DOUBLE PRECISION,
                    target_1 DOUBLE PRECISION,
                    target_2 DOUBLE PRECISION,
                    paper_order_id TEXT,
                    paper_side TEXT,
                    actual_fill_price DOUBLE PRECISION,
                    executed_at_utc BIGINT,
                    exit_price DOUBLE PRECISION,
                    exited_at_utc BIGINT,
                    exit_reason TEXT,
                    actual_pnl_inr DOUBLE PRECISION,
                    actual_pnl_points DOUBLE PRECISION,
                    status TEXT NOT NULL DEFAULT 'ARMED',
                    is_winner BOOLEAN,
                    option_contract JSONB DEFAULT '{}'::jsonb,
                    state_history JSONB DEFAULT '[]'::jsonb,
                    confidence DOUBLE PRECISION DEFAULT 80.0,
                    risk_points DOUBLE PRECISION,
                    risk_reward_t1 DOUBLE PRECISION DEFAULT 1.5,
                    risk_reward_t2 DOUBLE PRECISION DEFAULT 3.0,
                    created_at_utc BIGINT NOT NULL,
                    updated_at_utc BIGINT NOT NULL
                )
            """))
            # Schema migrations for v6.0 dual-cadence scalping engine
            cols_to_add = [
                ("confidence", "DOUBLE PRECISION DEFAULT 80.0"),
                ("risk_points", "DOUBLE PRECISION"),
                ("risk_reward_t1", "DOUBLE PRECISION DEFAULT 1.5"),
                ("risk_reward_t2", "DOUBLE PRECISION DEFAULT 3.0"),
                ("is_scalp", "BOOLEAN DEFAULT FALSE"),
                ("signal_type", "TEXT DEFAULT 'INTRADAY'"),
                ("time_stop_seconds", "INT"),
                ("runner_ttl_seconds", "INT"),
                ("time_stop_at_utc", "BIGINT"),
                ("runner_time_stop_at_utc", "BIGINT"),
                ("breakeven_activated", "BOOLEAN DEFAULT FALSE"),
                ("current_stop_loss", "DOUBLE PRECISION"),
                ("t1_hit", "BOOLEAN DEFAULT FALSE"),
                ("remaining_qty", "INT"),
                ("intended_qty", "INT"),
                ("net_realized_pnl_inr", "DOUBLE PRECISION"),
            ]
            for col, col_type in cols_to_add:
                try:
                    await session.execute(text(f"ALTER TABLE executed_signals ADD COLUMN IF NOT EXISTS {col} {col_type}"))
                except Exception:
                    pass

            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_executed_signals_underlying ON executed_signals (underlying)"))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_executed_signals_status ON executed_signals (status)"))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_executed_signals_created ON executed_signals (created_at_utc DESC)"))
            await session.commit()
            logger.info("executed_signals_table_ensured")
            return True
    except Exception as e:
        logger.warning("ensure_signals_tables_failed", error=str(e)[:250])
        return False


async def persist_executed_signal(record: Any) -> bool:
    """Upsert executed signal record into PostgreSQL and sync to local state cache."""
    # Always write to local file cache first
    save_signals_state_local()

    factory = get_async_session_factory()
    if factory is None:
        return False

    try:
        opt_data = record.option_contract if hasattr(record, "option_contract") else {}
        if isinstance(opt_data, str):
            try:
                opt_data = json.loads(opt_data)
            except Exception:
                opt_data = {}
        opt_json = json.dumps(opt_data or {}, default=str)

        hist_json = json.dumps([h.model_dump() if hasattr(h, "model_dump") else h for h in getattr(record, "state_history", [])], default=str)

        query = text("""
            INSERT INTO executed_signals (
                signal_id, audit_id, underlying, strategy, direction, timeframe,
                option_symbol, option_type, option_strike, lot_size, lots, quantity,
                spot_price_at_creation, trigger_price, stop_loss, target_1, target_2,
                paper_order_id, paper_side, actual_fill_price, executed_at_utc,
                exit_price, exited_at_utc, exit_reason, actual_pnl_inr, actual_pnl_points,
                status, is_winner, option_contract, state_history,
                confidence, risk_points, risk_reward_t1, risk_reward_t2,
                is_scalp, signal_type, time_stop_seconds, runner_ttl_seconds,
                time_stop_at_utc, runner_time_stop_at_utc, breakeven_activated,
                current_stop_loss, t1_hit, remaining_qty, intended_qty, net_realized_pnl_inr,
                created_at_utc, updated_at_utc
            ) VALUES (
                :signal_id, :audit_id, :underlying, :strategy, :direction, :timeframe,
                :option_symbol, :option_type, :option_strike, :lot_size, :lots, :quantity,
                :spot_price_at_creation, :trigger_price, :stop_loss, :target_1, :target_2,
                :paper_order_id, :paper_side, :actual_fill_price, :executed_at_utc,
                :exit_price, :exited_at_utc, :exit_reason, :actual_pnl_inr, :actual_pnl_points,
                :status, :is_winner, CAST(:option_contract AS JSONB), CAST(:state_history AS JSONB),
                :confidence, :risk_points, :risk_reward_t1, :risk_reward_t2,
                :is_scalp, :signal_type, :time_stop_seconds, :runner_ttl_seconds,
                :time_stop_at_utc, :runner_time_stop_at_utc, :breakeven_activated,
                :current_stop_loss, :t1_hit, :remaining_qty, :intended_qty, :net_realized_pnl_inr,
                :created_at_utc, :updated_at_utc
            )
            ON CONFLICT (signal_id) DO UPDATE SET
                status = EXCLUDED.status,
                paper_order_id = COALESCE(EXCLUDED.paper_order_id, executed_signals.paper_order_id),
                paper_side = COALESCE(EXCLUDED.paper_side, executed_signals.paper_side),
                actual_fill_price = COALESCE(EXCLUDED.actual_fill_price, executed_signals.actual_fill_price),
                executed_at_utc = COALESCE(EXCLUDED.executed_at_utc, executed_signals.executed_at_utc),
                exit_price = COALESCE(EXCLUDED.exit_price, executed_signals.exit_price),
                exited_at_utc = COALESCE(EXCLUDED.exited_at_utc, executed_signals.exited_at_utc),
                exit_reason = COALESCE(EXCLUDED.exit_reason, executed_signals.exit_reason),
                actual_pnl_inr = COALESCE(EXCLUDED.actual_pnl_inr, executed_signals.actual_pnl_inr),
                actual_pnl_points = COALESCE(EXCLUDED.actual_pnl_points, executed_signals.actual_pnl_points),
                is_winner = COALESCE(EXCLUDED.is_winner, executed_signals.is_winner),
                state_history = EXCLUDED.state_history,
                confidence = COALESCE(EXCLUDED.confidence, executed_signals.confidence),
                risk_points = COALESCE(EXCLUDED.risk_points, executed_signals.risk_points),
                risk_reward_t1 = COALESCE(EXCLUDED.risk_reward_t1, executed_signals.risk_reward_t1),
                risk_reward_t2 = COALESCE(EXCLUDED.risk_reward_t2, executed_signals.risk_reward_t2),
                is_scalp = COALESCE(EXCLUDED.is_scalp, executed_signals.is_scalp),
                signal_type = COALESCE(EXCLUDED.signal_type, executed_signals.signal_type),
                time_stop_at_utc = COALESCE(EXCLUDED.time_stop_at_utc, executed_signals.time_stop_at_utc),
                runner_time_stop_at_utc = COALESCE(EXCLUDED.runner_time_stop_at_utc, executed_signals.runner_time_stop_at_utc),
                breakeven_activated = COALESCE(EXCLUDED.breakeven_activated, executed_signals.breakeven_activated),
                current_stop_loss = COALESCE(EXCLUDED.current_stop_loss, executed_signals.current_stop_loss),
                t1_hit = COALESCE(EXCLUDED.t1_hit, executed_signals.t1_hit),
                remaining_qty = COALESCE(EXCLUDED.remaining_qty, executed_signals.remaining_qty),
                net_realized_pnl_inr = COALESCE(EXCLUDED.net_realized_pnl_inr, executed_signals.net_realized_pnl_inr),
                updated_at_utc = EXCLUDED.updated_at_utc;
        """)

        trig = float(getattr(record, "trigger_price", getattr(record, "trigger", 0.0)) or 0.0)
        sl = float(getattr(record, "stop_loss", 0.0) or 0.0)
        cur_sl = float(getattr(record, "current_stop_loss", sl) or sl)
        rp = float(getattr(record, "risk_points", abs(trig - sl)) or abs(trig - sl))

        opt_sym = getattr(record, "option_symbol", None) or (opt_data.get("broker_symbol") if isinstance(opt_data, dict) else None)
        opt_type = getattr(record, "option_type", None) or (opt_data.get("option_type") if isinstance(opt_data, dict) else None)
        opt_strike = getattr(record, "option_strike", None) or (opt_data.get("strike") if isinstance(opt_data, dict) else None)
        lot_sz = getattr(record, "lot_size", None) or (opt_data.get("lot_size", 75) if isinstance(opt_data, dict) else 75)

        params = {
            "signal_id": record.signal_id,
            "audit_id": getattr(record, "audit_id", f"AUD-{record.signal_id[:8]}"),
            "underlying": record.underlying,
            "strategy": record.strategy,
            "direction": record.direction,
            "timeframe": getattr(record, "timeframe", "5M"),
            "option_symbol": opt_sym,
            "option_type": opt_type,
            "option_strike": float(opt_strike) if opt_strike else None,
            "lot_size": int(lot_sz or 75),
            "lots": int(getattr(record, "lots", 1) or 1),
            "quantity": int(getattr(record, "quantity", 75) or 75),
            "spot_price_at_creation": float(getattr(record, "spot_price_at_creation", getattr(record, "spot_price", 0.0)) or 0.0),
            "trigger_price": trig,
            "stop_loss": sl,
            "target_1": float(getattr(record, "target_1", 0.0) or 0.0),
            "target_2": float(getattr(record, "target_2", 0.0) or 0.0),
            "paper_order_id": getattr(record, "paper_order_id", None),
            "paper_side": getattr(record, "paper_side", None),
            "actual_fill_price": getattr(record, "actual_fill_price", None),
            "executed_at_utc": getattr(record, "executed_at_utc", None),
            "exit_price": getattr(record, "exit_price", None),
            "exited_at_utc": getattr(record, "exited_at_utc", None),
            "exit_reason": getattr(record, "exit_reason", None),
            "actual_pnl_inr": getattr(record, "actual_pnl_inr", None),
            "actual_pnl_points": getattr(record, "actual_pnl_points", None),
            "status": getattr(record, "status", getattr(record, "fsm_state", "ARMED")),
            "is_winner": getattr(record, "is_winner", None),
            "option_contract": opt_json,
            "state_history": hist_json,
            "confidence": float(getattr(record, "confidence", 80.0) or 80.0),
            "risk_points": rp,
            "risk_reward_t1": float(getattr(record, "risk_reward_t1", 1.5) or 1.5),
            "risk_reward_t2": float(getattr(record, "risk_reward_t2", 3.0) or 3.0),
            "is_scalp": bool(getattr(record, "is_scalp", False)),
            "signal_type": str(getattr(record, "signal_type", "INTRADAY")),
            "time_stop_seconds": getattr(record, "time_stop_seconds", None),
            "runner_ttl_seconds": getattr(record, "runner_ttl_seconds", None),
            "time_stop_at_utc": getattr(record, "time_stop_at_utc", None),
            "runner_time_stop_at_utc": getattr(record, "runner_time_stop_at_utc", None),
            "breakeven_activated": bool(getattr(record, "breakeven_activated", False)),
            "current_stop_loss": cur_sl,
            "t1_hit": bool(getattr(record, "t1_hit", False)),
            "remaining_qty": int(getattr(record, "remaining_qty", 0) or 0),
            "intended_qty": int(getattr(record, "intended_qty", 0) or 0),
            "net_realized_pnl_inr": getattr(record, "net_realized_pnl_inr", None),
            "created_at_utc": getattr(record, "created_at_utc", int(__import__("time").time() * 1000)),
            "updated_at_utc": getattr(record, "updated_at_utc", int(__import__("time").time() * 1000)),
        }

        async with factory() as session:
            await session.execute(query, params)
            await session.commit()
            logger.info("executed_signal_persisted_to_supabase", signal_id=record.signal_id, status=params["status"])
            return True
    except Exception as e:
        logger.warning("persist_executed_signal_failed", signal_id=getattr(record, "signal_id", "unknown"), error=str(e)[:250])
        return False


async def delete_persisted_signal(signal_id: str) -> bool:
    """Delete a signal from PostgreSQL and local cache."""
    # Delete from local state cache
    try:
        from app.signals.fsm import signal_fsm
        from app.signals.audit_ledger import signal_audit_ledger
        signal_fsm._signals.pop(signal_id, None)
        signal_audit_ledger._trades.pop(signal_id, None)
        save_signals_state_local()
    except Exception:
        pass

    factory = get_async_session_factory()
    if factory is None:
        return False
    try:
        async with factory() as session:
            await session.execute(
                text("DELETE FROM executed_signals WHERE signal_id = :signal_id"),
                {"signal_id": signal_id},
            )
            await session.commit()
            logger.info("executed_signal_deleted_from_supabase", signal_id=signal_id)
            return True
    except Exception as e:
        logger.warning("delete_persisted_signal_failed", signal_id=signal_id, error=str(e)[:250])
        return False


async def restore_signals_from_db() -> int:
    """
    Hydrates persisted signals from PostgreSQL or local cache.
    Ensures signals and audit records NEVER start from zero on server restart or redeployment.
    """
    factory = get_async_session_factory()
    db_restored_count = 0

    if factory is not None:
        try:
            from app.signals.audit_ledger import signal_audit_ledger, AuditTradeRecord, AuditStateEvent
            from app.signals.fsm import signal_fsm, SignalInstance

            async with factory() as session:
                res = await session.execute(text("SELECT * FROM executed_signals ORDER BY created_at_utc ASC"))
                rows = res.mappings().all()

                for row in rows:
                    sid = row["signal_id"]
                    st = row["status"]

                    # Reconstitute state history
                    raw_hist = row.get("state_history") or []
                    if isinstance(raw_hist, str):
                        try:
                            raw_hist = json.loads(raw_hist)
                        except Exception:
                            raw_hist = []

                    state_events = []
                    for h in raw_hist:
                        if isinstance(h, dict):
                            state_events.append(
                                AuditStateEvent(
                                    timestamp_utc=h.get("timestamp_utc", row["created_at_utc"]),
                                    from_state=h.get("from_state", "DETECTED"),
                                    to_state=h.get("to_state", st),
                                    market_price=h.get("market_price"),
                                    reason=h.get("reason", "RESTORED"),
                                )
                            )

                    rec = AuditTradeRecord(
                        audit_id=row["audit_id"],
                        signal_id=sid,
                        underlying=row["underlying"],
                        strategy=row["strategy"],
                        direction=row["direction"],
                        timeframe=row.get("timeframe", "5M"),
                        option_symbol=row.get("option_symbol"),
                        option_type=row.get("option_type"),
                        option_strike=row.get("option_strike"),
                        lot_size=row.get("lot_size", 75),
                        lots=row.get("lots", 1),
                        quantity=row.get("quantity", 75),
                        spot_price_at_creation=row.get("spot_price_at_creation") or 0.0,
                        trigger_price=row.get("trigger_price") or 0.0,
                        stop_loss=row.get("stop_loss") or 0.0,
                        target_1=row.get("target_1") or 0.0,
                        target_2=row.get("target_2") or 0.0,
                        paper_order_id=row.get("paper_order_id"),
                        paper_side=row.get("paper_side"),
                        actual_fill_price=row.get("actual_fill_price"),
                        executed_at_utc=row.get("executed_at_utc"),
                        exit_price=row.get("exit_price"),
                        exited_at_utc=row.get("exited_at_utc"),
                        exit_reason=row.get("exit_reason"),
                        actual_pnl_inr=row.get("actual_pnl_inr"),
                        actual_pnl_points=row.get("actual_pnl_points"),
                        status=st,
                        is_winner=row.get("is_winner"),
                        state_history=state_events,
                        created_at_utc=row["created_at_utc"],
                        updated_at_utc=row["updated_at_utc"],
                    )
                    signal_audit_ledger._trades[sid] = rec

                    # Reconstruct FSM instance with Version 6.0 fields
                    if not signal_fsm.get(sid):
                        opt_dict = row.get("option_contract")
                        if isinstance(opt_dict, str):
                            try:
                                opt_dict = json.loads(opt_dict)
                            except Exception:
                                opt_dict = {}

                        valid_fsm_states = (
                            "DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED",
                            "EXECUTED", "TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT",
                            "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT", "EXPIRED", "INVALIDATED", "CLOSED"
                        )
                        resolved_fsm_state = st if st in valid_fsm_states else (
                            "TARGET_1_HIT" if st == "WON" else ("STOP_LOSS_HIT" if st == "LOST" else "ARMED")
                        )

                        sl_val = Decimal(str(row.get("stop_loss") or 0.0))
                        cur_sl_val = Decimal(str(row.get("current_stop_loss") or sl_val))

                        fsm_inst = SignalInstance(
                            signal_id=sid,
                            underlying=row["underlying"],
                            strategy=row["strategy"],
                            direction=row["direction"],
                            timeframe=row.get("timeframe", "5M"),
                            spot_price=Decimal(str(row.get("spot_price_at_creation") or 0.0)),
                            entry_min=Decimal(str(row.get("trigger_price") or 0.0)),
                            entry_max=Decimal(str(row.get("trigger_price") or 0.0)),
                            trigger=Decimal(str(row.get("trigger_price") or 0.0)),
                            stop_loss=sl_val,
                            initial_stop_loss=sl_val,
                            current_stop_loss=cur_sl_val,
                            target_1=Decimal(str(row.get("target_1") or 0.0)),
                            target_2=Decimal(str(row.get("target_2") or 0.0)),
                            risk_points=Decimal(str(row.get("risk_points") or abs((row.get("trigger_price") or 0) - (row.get("stop_loss") or 0)))),
                            risk_reward_t1=float(row.get("risk_reward_t1") or 1.5),
                            risk_reward_t2=float(row.get("risk_reward_t2") or 3.0),
                            confidence=float(row.get("confidence") or 80.0),
                            option_contract=opt_dict,
                            signal_type=str(row.get("signal_type") or "INTRADAY"),
                            is_scalp=bool(row.get("is_scalp") or False),
                            time_stop_seconds=row.get("time_stop_seconds"),
                            runner_ttl_seconds=row.get("runner_ttl_seconds"),
                            time_stop_at_utc=row.get("time_stop_at_utc"),
                            runner_time_stop_at_utc=row.get("runner_time_stop_at_utc"),
                            breakeven_activated=bool(row.get("breakeven_activated") or False),
                            t1_hit=bool(row.get("t1_hit") or False),
                            fsm_state=resolved_fsm_state,
                            created_at_utc=row["created_at_utc"],
                        )
                        signal_fsm._signals[sid] = fsm_inst

                    db_restored_count += 1

                logger.info("signals_restored_from_supabase", count=db_restored_count)
                # Synchronize to local backup cache
                if db_restored_count > 0:
                    save_signals_state_local()
                return db_restored_count
        except Exception as e:
            logger.warning("restore_signals_from_db_failed", error=str(e)[:250])

    # If DB restoration yielded 0 records or failed, restore from local cache
    local_count = restore_signals_state_local()
    return local_count
