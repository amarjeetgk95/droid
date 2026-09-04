"""
Supabase / PostgreSQL Persistence Layer for Executed Signals & Audit Ledger
Persists trade lifecycle, execution receipts, and audited P&L across deployments and restarts.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Optional
import structlog
from sqlalchemy import text

from app.core.database import get_async_session_factory

logger = structlog.get_logger()


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
            await session.execute(text("ALTER TABLE executed_signals ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION DEFAULT 80.0"))
            await session.execute(text("ALTER TABLE executed_signals ADD COLUMN IF NOT EXISTS risk_points DOUBLE PRECISION"))
            await session.execute(text("ALTER TABLE executed_signals ADD COLUMN IF NOT EXISTS risk_reward_t1 DOUBLE PRECISION DEFAULT 1.5"))
            await session.execute(text("ALTER TABLE executed_signals ADD COLUMN IF NOT EXISTS risk_reward_t2 DOUBLE PRECISION DEFAULT 3.0"))
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
    """Upsert executed signal record into Supabase PostgreSQL."""
    factory = get_async_session_factory()
    if factory is None:
        return False

    try:
        opt_json = json.dumps(record.option_contract if hasattr(record, "option_contract") else {}, default=str)
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
                created_at_utc, updated_at_utc
            ) VALUES (
                :signal_id, :audit_id, :underlying, :strategy, :direction, :timeframe,
                :option_symbol, :option_type, :option_strike, :lot_size, :lots, :quantity,
                :spot_price_at_creation, :trigger_price, :stop_loss, :target_1, :target_2,
                :paper_order_id, :paper_side, :actual_fill_price, :executed_at_utc,
                :exit_price, :exited_at_utc, :exit_reason, :actual_pnl_inr, :actual_pnl_points,
                :status, :is_winner, CAST(:option_contract AS JSONB), CAST(:state_history AS JSONB),
                :confidence, :risk_points, :risk_reward_t1, :risk_reward_t2,
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
                updated_at_utc = EXCLUDED.updated_at_utc;
        """)

        trig = float(getattr(record, "trigger_price", getattr(record, "trigger", 0.0)) or 0.0)
        sl = float(getattr(record, "stop_loss", 0.0) or 0.0)
        rp = float(getattr(record, "risk_points", abs(trig - sl)) or abs(trig - sl))

        params = {
            "signal_id": record.signal_id,
            "audit_id": getattr(record, "audit_id", f"AUD-{record.signal_id[:8]}"),
            "underlying": record.underlying,
            "strategy": record.strategy,
            "direction": record.direction,
            "timeframe": getattr(record, "timeframe", "5M"),
            "option_symbol": getattr(record, "option_symbol", None),
            "option_type": getattr(record, "option_type", None),
            "option_strike": getattr(record, "option_strike", None),
            "lot_size": getattr(record, "lot_size", 75),
            "lots": getattr(record, "lots", 1),
            "quantity": getattr(record, "quantity", 75),
            "spot_price_at_creation": getattr(record, "spot_price_at_creation", getattr(record, "spot_price", 0.0)),
            "trigger_price": trig,
            "stop_loss": sl,
            "target_1": getattr(record, "target_1", 0.0),
            "target_2": getattr(record, "target_2", 0.0),
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
    """Delete a signal from Supabase PostgreSQL."""
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
    """Hydrate persisted executed signals from Supabase into memory."""
    factory = get_async_session_factory()
    if factory is None:
        return 0

    try:
        from app.signals.audit_ledger import signal_audit_ledger, AuditTradeRecord, AuditStateEvent
        from app.signals.fsm import signal_fsm, SignalInstance

        async with factory() as session:
            res = await session.execute(text("SELECT * FROM executed_signals ORDER BY created_at_utc ASC"))
            rows = res.mappings().all()
            count = 0

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

                # Mirror into FSM if not present
                if not signal_fsm.get(sid):
                    opt_dict = row.get("option_contract")
                    if isinstance(opt_dict, str):
                        try:
                            opt_dict = json.loads(opt_dict)
                        except Exception:
                            opt_dict = {}

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
                        stop_loss=Decimal(str(row.get("stop_loss") or 0.0)),
                        target_1=Decimal(str(row.get("target_1") or 0.0)),
                        target_2=Decimal(str(row.get("target_2") or 0.0)),
                        risk_points=Decimal(str(row.get("risk_points") or abs((row.get("trigger_price") or 0) - (row.get("stop_loss") or 0)))),
                        risk_reward_t1=float(row.get("risk_reward_t1") or 1.5),
                        risk_reward_t2=float(row.get("risk_reward_t2") or 3.0),
                        confidence=float(row.get("confidence") or 80.0),
                        option_contract=opt_dict,
                        fsm_state=st if st in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED", "EXECUTED", "TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT", "EXPIRED", "INVALIDATED", "CLOSED") else ("TARGET_1_HIT" if st == "WON" else ("STOP_LOSS_HIT" if st == "LOST" else "ARMED")),
                        created_at_utc=row["created_at_utc"],
                    )
                    signal_fsm._signals[sid] = fsm_inst

                count += 1

            logger.info("signals_restored_from_supabase", count=count)
            return count
    except Exception as e:
        logger.warning("restore_signals_from_db_failed", error=str(e)[:250])
        return 0
