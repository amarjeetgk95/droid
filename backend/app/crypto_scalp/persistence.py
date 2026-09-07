"""
Supabase PostgreSQL & Local Cache Persistence Layer for Crypto Scalp Signals & Execution Track Record.
Guarantees full signal history and execution ledger survive Render redeployments and restarts.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
import structlog
from sqlalchemy import text

from app.core.database import get_async_session_factory
from app.models.crypto import CryptoScalpSignal, SignalDirection, CryptoSignalStatus
from app.crypto_scalp.models_execution import (
    CryptoScalpExecutionRecord,
    CryptoScalpExecutionEvent,
    CryptoScalpPositionState,
    CryptoScalpExitEventType,
    CryptoScalpExecutionMode,
    format_detailed_exit_reason,
)

logger = structlog.get_logger()

CRYPTO_SCALP_STATE_FILE = Path("crypto_scalp_signals_state.json")
CRYPTO_SCALP_EXECUTIONS_FILE = Path("crypto_scalp_executions_state.json")
CRYPTO_SCALP_EVENTS_FILE = Path("crypto_scalp_events_state.json")


async def ensure_crypto_scalp_tables() -> bool:
    """Auto-provision crypto_scalp tables in Supabase PostgreSQL if not present."""
    factory = get_async_session_factory()
    if factory is None:
        logger.debug("crypto_scalp_persistence_no_db_factory")
        return False
    try:
        async with factory() as session:
            # 1. Signals Table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS crypto_scalp_signals (
                    signal_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    timeframe TEXT NOT NULL DEFAULT '1m',
                    entry_price DOUBLE PRECISION NOT NULL,
                    stop_loss DOUBLE PRECISION NOT NULL,
                    target_1 DOUBLE PRECISION NOT NULL,
                    target_2 DOUBLE PRECISION NOT NULL,
                    current_price DOUBLE PRECISION NOT NULL,
                    risk_points DOUBLE PRECISION NOT NULL,
                    risk_percent DOUBLE PRECISION NOT NULL,
                    risk_reward_ratio DOUBLE PRECISION NOT NULL,
                    confidence DOUBLE PRECISION NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    confluence_factors JSONB DEFAULT '[]'::jsonb,
                    rationale TEXT,
                    atr_value DOUBLE PRECISION,
                    volume_ratio DOUBLE PRECISION,
                    funding_rate DOUBLE PRECISION,
                    depth_imbalance DOUBLE PRECISION,
                    telegram_dispatched BOOLEAN DEFAULT FALSE,
                    created_at_utc BIGINT NOT NULL,
                    updated_at_utc BIGINT NOT NULL
                )
            """))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_crypto_scalp_symbol ON crypto_scalp_signals(symbol)"))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_crypto_scalp_created ON crypto_scalp_signals(created_at_utc DESC)"))

            # 2. Executions Table (Consolidated trade ledger)
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS crypto_scalp_executions (
                    trade_id TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    execution_mode TEXT NOT NULL DEFAULT 'PAPER',
                    position_state TEXT NOT NULL DEFAULT 'ACTIVE',
                    signal_price DOUBLE PRECISION NOT NULL,
                    entry_fill_price DOUBLE PRECISION NOT NULL,
                    initial_stop_price DOUBLE PRECISION NOT NULL,
                    current_stop_price DOUBLE PRECISION NOT NULL,
                    target_1_price DOUBLE PRECISION NOT NULL,
                    target_2_price DOUBLE PRECISION NOT NULL,
                    exit_price DOUBLE PRECISION,
                    exit_reason TEXT,
                    quantity_initial DOUBLE PRECISION NOT NULL,
                    quantity_closed_t1 DOUBLE PRECISION DEFAULT 0.0,
                    quantity_closed_final DOUBLE PRECISION DEFAULT 0.0,
                    quantity_remaining DOUBLE PRECISION NOT NULL,
                    notional_usd DOUBLE PRECISION DEFAULT 0.0,
                    initial_risk_usd DOUBLE PRECISION DEFAULT 0.0,
                    gross_pnl_usd DOUBLE PRECISION DEFAULT 0.0,
                    fees_usd DOUBLE PRECISION DEFAULT 0.0,
                    slippage_usd DOUBLE PRECISION DEFAULT 0.0,
                    net_pnl_usd DOUBLE PRECISION DEFAULT 0.0,
                    net_return_pct DOUBLE PRECISION DEFAULT 0.0,
                    r_multiple DOUBLE PRECISION DEFAULT 0.0,
                    theoretical_r DOUBLE PRECISION DEFAULT 0.0,
                    execution_drag_r DOUBLE PRECISION DEFAULT 0.0,
                    t1_hit_at BIGINT,
                    t2_hit_at BIGINT,
                    stop_hit_at BIGINT,
                    duration_seconds INTEGER DEFAULT 0,
                    duration_str TEXT DEFAULT '0s',
                    created_at_utc BIGINT NOT NULL,
                    closed_at_utc BIGINT
                )
            """))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_crypto_scalp_exec_symbol ON crypto_scalp_executions(symbol)"))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_crypto_scalp_exec_state ON crypto_scalp_executions(position_state)"))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_crypto_scalp_exec_strategy ON crypto_scalp_executions(strategy)"))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_crypto_scalp_exec_created ON crypto_scalp_executions(created_at_utc DESC)"))

            # 3. Execution Events Table (Immutable audit trail)
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS crypto_scalp_execution_events (
                    event_id TEXT PRIMARY KEY,
                    trade_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    timestamp_ms BIGINT NOT NULL,
                    market_price DOUBLE PRECISION NOT NULL,
                    fill_price DOUBLE PRECISION NOT NULL,
                    quantity DOUBLE PRECISION NOT NULL,
                    fee_usd DOUBLE PRECISION DEFAULT 0.0,
                    slippage_usd DOUBLE PRECISION DEFAULT 0.0,
                    gross_pnl_usd DOUBLE PRECISION DEFAULT 0.0,
                    net_pnl_usd DOUBLE PRECISION DEFAULT 0.0,
                    r_multiple DOUBLE PRECISION DEFAULT 0.0,
                    state_before TEXT NOT NULL,
                    state_after TEXT NOT NULL,
                    metadata_json JSONB DEFAULT '{}'::jsonb
                )
            """))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_crypto_scalp_events_trade ON crypto_scalp_execution_events(trade_id)"))
            await session.execute(text("CREATE INDEX IF NOT EXISTS idx_crypto_scalp_events_time ON crypto_scalp_execution_events(timestamp_ms DESC)"))

            await session.commit()
            logger.info("crypto_scalp_tables_provisioned_successfully")
            return True
    except Exception as e:
        logger.warning("ensure_crypto_scalp_tables_failed", error=str(e)[:250])
        return False


# ==============================================================================
# Signals Persistence
# ==============================================================================

def save_scalp_signals_local(signals: list[CryptoScalpSignal]) -> bool:
    """Safely persist scalp signals to local JSON cache file."""
    try:
        payload = {
            "signals": [s.model_dump(mode="json") for s in signals],
            "updated_at_utc": int(time.time() * 1000),
        }
        tmp_file = CRYPTO_SCALP_STATE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        tmp_file.replace(CRYPTO_SCALP_STATE_FILE)
        return True
    except Exception as e:
        logger.warning("save_scalp_signals_local_failed", error=str(e)[:250])
        return False


def restore_scalp_signals_local() -> list[CryptoScalpSignal]:
    """Restore scalp signals from local JSON file."""
    if not CRYPTO_SCALP_STATE_FILE.exists():
        return []
    try:
        with open(CRYPTO_SCALP_STATE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        raw_list = payload.get("signals", [])
        signals = [CryptoScalpSignal(**item) for item in raw_list if isinstance(item, dict)]
        return signals
    except Exception as e:
        logger.warning("restore_scalp_signals_local_failed", error=str(e)[:250])
        return []


async def persist_scalp_signal(signal: CryptoScalpSignal) -> bool:
    """
    Persist a new or updated scalp signal to Supabase PostgreSQL,
    with automatic local JSON cache backup.
    """
    now_ms = int(time.time() * 1000)
    persisted_to_db = False

    factory = get_async_session_factory()
    if factory is not None:
        try:
            async with factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO crypto_scalp_signals (
                            signal_id, symbol, asset, direction, strategy, strategy_name,
                            timeframe, entry_price, stop_loss, target_1, target_2,
                            current_price, risk_points, risk_percent, risk_reward_ratio,
                            confidence, status, confluence_factors, rationale,
                            atr_value, volume_ratio, funding_rate, depth_imbalance,
                            telegram_dispatched, created_at_utc, updated_at_utc
                        ) VALUES (
                            :signal_id, :symbol, :asset, :direction, :strategy, :strategy_name,
                            :timeframe, :entry_price, :stop_loss, :target_1, :target_2,
                            :current_price, :risk_points, :risk_percent, :risk_reward_ratio,
                            :confidence, :status, :confluence_factors, :rationale,
                            :atr_value, :volume_ratio, :funding_rate, :depth_imbalance,
                            :telegram_dispatched, :created_at_utc, :updated_at_utc
                        )
                        ON CONFLICT (signal_id) DO UPDATE SET
                            current_price = EXCLUDED.current_price,
                            status = EXCLUDED.status,
                            telegram_dispatched = EXCLUDED.telegram_dispatched,
                            updated_at_utc = EXCLUDED.updated_at_utc;
                    """),
                    {
                        "signal_id": signal.id,
                        "symbol": signal.symbol,
                        "asset": signal.asset,
                        "direction": signal.direction.value,
                        "strategy": signal.strategy,
                        "strategy_name": signal.strategy_name,
                        "timeframe": signal.timeframe,
                        "entry_price": float(signal.entry_price),
                        "stop_loss": float(signal.stop_loss),
                        "target_1": float(signal.target_1),
                        "target_2": float(signal.target_2),
                        "current_price": float(signal.current_price),
                        "risk_points": float(signal.risk_points),
                        "risk_percent": float(signal.risk_percent),
                        "risk_reward_ratio": float(signal.risk_reward_ratio),
                        "confidence": float(signal.confidence),
                        "status": signal.status.value,
                        "confluence_factors": json.dumps(signal.confluence_factors),
                        "rationale": signal.rationale,
                        "atr_value": float(signal.atr_value) if signal.atr_value is not None else None,
                        "volume_ratio": float(signal.volume_ratio) if signal.volume_ratio is not None else None,
                        "funding_rate": float(signal.funding_rate) if signal.funding_rate is not None else None,
                        "depth_imbalance": float(signal.depth_imbalance) if signal.depth_imbalance is not None else None,
                        "telegram_dispatched": bool(signal.telegram_dispatched),
                        "created_at_utc": signal.created_at_utc or now_ms,
                        "updated_at_utc": now_ms,
                    }
                )
                await session.commit()
                persisted_to_db = True
                signal.persisted_to_supabase = True
                logger.info("crypto_scalp_signal_persisted_supabase", signal_id=signal.id)
        except Exception as e:
            logger.warning("crypto_scalp_signal_db_persist_failed", signal_id=signal.id, error=str(e)[:200])

    # Also update local backup cache
    local_signals = restore_scalp_signals_local()
    found = False
    for idx, s in enumerate(local_signals):
        if s.id == signal.id:
            local_signals[idx] = signal
            found = True
            break
    if not found:
        local_signals.insert(0, signal)
    save_scalp_signals_local(local_signals[:100])

    return persisted_to_db


async def fetch_persisted_scalp_signals(limit: int = 50, symbol: str | None = None) -> list[CryptoScalpSignal]:
    """Fetch historical crypto scalp signals from Supabase PostgreSQL with local cache fallback."""
    factory = get_async_session_factory()
    if factory is not None:
        try:
            query = "SELECT * FROM crypto_scalp_signals"
            params: dict[str, Any] = {"limit": limit}
            if symbol:
                query += " WHERE symbol = :symbol"
                params["symbol"] = symbol.upper()
            query += " ORDER BY created_at_utc DESC LIMIT :limit"

            async with factory() as session:
                result = await session.execute(text(query), params)
                rows = result.mappings().all()

                signals: list[CryptoScalpSignal] = []
                for row in rows:
                    confluences = row.get("confluence_factors")
                    if isinstance(confluences, str):
                        try:
                            confluences = json.loads(confluences)
                        except Exception:
                            confluences = []
                    elif not isinstance(confluences, list):
                        confluences = []

                    sig = CryptoScalpSignal(
                        id=row["signal_id"],
                        symbol=row["symbol"],
                        asset=row["asset"],
                        direction=SignalDirection(row["direction"]),
                        strategy=row["strategy"],
                        strategy_name=row["strategy_name"],
                        entry_price=float(row["entry_price"]),
                        stop_loss=float(row["stop_loss"]),
                        target_1=float(row["target_1"]),
                        target_2=float(row["target_2"]),
                        current_price=float(row["current_price"]),
                        risk_points=float(row.get("risk_points", 0.0)),
                        risk_percent=float(row.get("risk_percent", 0.0)),
                        risk_reward_ratio=float(row.get("risk_reward_ratio", 1.5)),
                        confidence=float(row.get("confidence", 75.0)),
                        timeframe=row.get("timeframe", "1m"),
                        status=CryptoSignalStatus(row.get("status", "ACTIVE")),
                        confluence_factors=confluences,
                        rationale=row.get("rationale", ""),
                        atr_value=float(row["atr_value"]) if row.get("atr_value") is not None else None,
                        volume_ratio=float(row["volume_ratio"]) if row.get("volume_ratio") is not None else None,
                        funding_rate=float(row["funding_rate"]) if row.get("funding_rate") is not None else None,
                        depth_imbalance=float(row["depth_imbalance"]) if row.get("depth_imbalance") is not None else None,
                        persisted_to_supabase=True,
                        telegram_dispatched=bool(row.get("telegram_dispatched", False)),
                        created_at_utc=int(row.get("created_at_utc", 0)),
                    )
                    signals.append(sig)

                if signals:
                    return signals
        except Exception as e:
            logger.warning("fetch_crypto_scalp_supabase_failed", error=str(e)[:200])

    # Fallback to local cache
    local = restore_scalp_signals_local()
    if symbol:
        local = [s for s in local if s.symbol.upper() == symbol.upper()]
    return local[:limit]


async def purge_stale_spam_signals(older_than_seconds: int = 1800) -> int:
    """Purge stale scalp signals older than older_than_seconds from Supabase and local cache."""
    factory = get_async_session_factory()
    deleted_count = 0
    cutoff_ms = int((time.time() - older_than_seconds) * 1000)
    if factory is not None:
        try:
            async with factory() as session:
                res = await session.execute(
                    text("DELETE FROM crypto_scalp_signals WHERE created_at_utc < :cutoff_ms"),
                    {"cutoff_ms": cutoff_ms},
                )
                await session.commit()
                deleted_count = res.rowcount or 0
                logger.info("purged_stale_scalp_signals_supabase", deleted=deleted_count)
        except Exception as e:
            logger.warning("purge_stale_scalp_signals_failed", error=str(e)[:200])

    save_scalp_signals_local([])
    return deleted_count


# ==============================================================================
# Executions & Ledger Persistence
# ==============================================================================

def save_executions_local(executions: list[CryptoScalpExecutionRecord]) -> bool:
    """Persist execution records to local JSON cache."""
    try:
        payload = {
            "executions": [rec.model_dump(mode="json") for rec in executions],
            "updated_at_utc": int(time.time() * 1000),
        }
        tmp = CRYPTO_SCALP_EXECUTIONS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        tmp.replace(CRYPTO_SCALP_EXECUTIONS_FILE)
        return True
    except Exception as e:
        logger.warning("save_executions_local_failed", error=str(e)[:200])
        return False


def restore_executions_local() -> list[CryptoScalpExecutionRecord]:
    """Restore execution records from local JSON cache."""
    if not CRYPTO_SCALP_EXECUTIONS_FILE.exists():
        return []
    try:
        with open(CRYPTO_SCALP_EXECUTIONS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        raw_list = payload.get("executions", [])
        return [CryptoScalpExecutionRecord(**item) for item in raw_list if isinstance(item, dict)]
    except Exception as e:
        logger.warning("restore_executions_local_failed", error=str(e)[:200])
        return []


def save_events_local(events: list[CryptoScalpExecutionEvent]) -> bool:
    """Persist execution events to local JSON cache."""
    try:
        payload = {
            "events": [ev.model_dump(mode="json") for ev in events],
            "updated_at_utc": int(time.time() * 1000),
        }
        tmp = CRYPTO_SCALP_EVENTS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        tmp.replace(CRYPTO_SCALP_EVENTS_FILE)
        return True
    except Exception as e:
        logger.warning("save_events_local_failed", error=str(e)[:200])
        return False


def restore_events_local() -> list[CryptoScalpExecutionEvent]:
    """Restore execution events from local JSON cache."""
    if not CRYPTO_SCALP_EVENTS_FILE.exists():
        return []
    try:
        with open(CRYPTO_SCALP_EVENTS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        raw_list = payload.get("events", [])
        return [CryptoScalpExecutionEvent(**item) for item in raw_list if isinstance(item, dict)]
    except Exception as e:
        logger.warning("restore_events_local_failed", error=str(e)[:200])
        return []


async def save_execution_event(event: CryptoScalpExecutionEvent) -> bool:
    """Persist an immutable execution event to Supabase and local cache."""
    factory = get_async_session_factory()
    persisted = False
    if factory is not None:
        try:
            async with factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO crypto_scalp_execution_events (
                            event_id, trade_id, signal_id, event_type, symbol, direction,
                            strategy, timestamp_ms, market_price, fill_price, quantity,
                            fee_usd, slippage_usd, gross_pnl_usd, net_pnl_usd, r_multiple,
                            state_before, state_after, metadata_json
                        ) VALUES (
                            :event_id, :trade_id, :signal_id, :event_type, :symbol, :direction,
                            :strategy, :timestamp_ms, :market_price, :fill_price, :quantity,
                            :fee_usd, :slippage_usd, :gross_pnl_usd, :net_pnl_usd, :r_multiple,
                            :state_before, :state_after, :metadata_json
                        )
                        ON CONFLICT (event_id) DO NOTHING;
                    """),
                    {
                        "event_id": event.event_id,
                        "trade_id": event.trade_id,
                        "signal_id": event.signal_id,
                        "event_type": event.event_type.value,
                        "symbol": event.symbol,
                        "direction": event.direction.value,
                        "strategy": event.strategy,
                        "timestamp_ms": event.timestamp_ms,
                        "market_price": float(event.market_price),
                        "fill_price": float(event.fill_price),
                        "quantity": float(event.quantity),
                        "fee_usd": float(event.fee_usd),
                        "slippage_usd": float(event.slippage_usd),
                        "gross_pnl_usd": float(event.gross_pnl_usd),
                        "net_pnl_usd": float(event.net_pnl_usd),
                        "r_multiple": float(event.r_multiple),
                        "state_before": event.state_before.value,
                        "state_after": event.state_after.value,
                        "metadata_json": json.dumps(event.metadata_json),
                    }
                )
                await session.commit()
                persisted = True
        except Exception as e:
            logger.warning("save_execution_event_failed", event_id=event.event_id, error=str(e)[:200])

    # Local fallback
    local_evs = restore_events_local()
    local_evs.append(event)
    save_events_local(local_evs[-200:])
    return persisted


async def save_execution_record(record: CryptoScalpExecutionRecord) -> bool:
    """Upsert consolidated execution record to Supabase and local cache."""
    factory = get_async_session_factory()
    persisted = False
    if factory is not None:
        try:
            async with factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO crypto_scalp_executions (
                            trade_id, signal_id, symbol, asset, direction, strategy, strategy_name,
                            execution_mode, position_state, signal_price, entry_fill_price,
                            initial_stop_price, current_stop_price, target_1_price, target_2_price,
                            exit_price, exit_reason, quantity_initial, quantity_closed_t1,
                            quantity_closed_final, quantity_remaining, notional_usd, initial_risk_usd,
                            gross_pnl_usd, fees_usd, slippage_usd, net_pnl_usd, net_return_pct,
                            r_multiple, theoretical_r, execution_drag_r, t1_hit_at, t2_hit_at,
                            stop_hit_at, duration_seconds, duration_str, created_at_utc, closed_at_utc
                        ) VALUES (
                            :trade_id, :signal_id, :symbol, :asset, :direction, :strategy, :strategy_name,
                            :execution_mode, :position_state, :signal_price, :entry_fill_price,
                            :initial_stop_price, :current_stop_price, :target_1_price, :target_2_price,
                            :exit_price, :exit_reason, :quantity_initial, :quantity_closed_t1,
                            :quantity_closed_final, :quantity_remaining, :notional_usd, :initial_risk_usd,
                            :gross_pnl_usd, :fees_usd, :slippage_usd, :net_pnl_usd, :net_return_pct,
                            :r_multiple, :theoretical_r, :execution_drag_r, :t1_hit_at, :t2_hit_at,
                            :stop_hit_at, :duration_seconds, :duration_str, :created_at_utc, :closed_at_utc
                        )
                        ON CONFLICT (trade_id) DO UPDATE SET
                            position_state = EXCLUDED.position_state,
                            current_stop_price = EXCLUDED.current_stop_price,
                            exit_price = EXCLUDED.exit_price,
                            exit_reason = EXCLUDED.exit_reason,
                            quantity_closed_t1 = EXCLUDED.quantity_closed_t1,
                            quantity_closed_final = EXCLUDED.quantity_closed_final,
                            quantity_remaining = EXCLUDED.quantity_remaining,
                            gross_pnl_usd = EXCLUDED.gross_pnl_usd,
                            fees_usd = EXCLUDED.fees_usd,
                            slippage_usd = EXCLUDED.slippage_usd,
                            net_pnl_usd = EXCLUDED.net_pnl_usd,
                            net_return_pct = EXCLUDED.net_return_pct,
                            r_multiple = EXCLUDED.r_multiple,
                            theoretical_r = EXCLUDED.theoretical_r,
                            execution_drag_r = EXCLUDED.execution_drag_r,
                            t1_hit_at = EXCLUDED.t1_hit_at,
                            t2_hit_at = EXCLUDED.t2_hit_at,
                            stop_hit_at = EXCLUDED.stop_hit_at,
                            duration_seconds = EXCLUDED.duration_seconds,
                            duration_str = EXCLUDED.duration_str,
                            closed_at_utc = EXCLUDED.closed_at_utc;
                    """),
                    {
                        "trade_id": record.trade_id,
                        "signal_id": record.signal_id,
                        "symbol": record.symbol,
                        "asset": record.asset,
                        "direction": record.direction.value,
                        "strategy": record.strategy,
                        "strategy_name": record.strategy_name,
                        "execution_mode": record.execution_mode.value,
                        "position_state": record.position_state.value,
                        "signal_price": float(record.signal_price),
                        "entry_fill_price": float(record.entry_fill_price),
                        "initial_stop_price": float(record.initial_stop_price),
                        "current_stop_price": float(record.current_stop_price),
                        "target_1_price": float(record.target_1_price),
                        "target_2_price": float(record.target_2_price),
                        "exit_price": float(record.exit_price) if record.exit_price is not None else None,
                        "exit_reason": record.exit_reason.value if record.exit_reason is not None else None,
                        "quantity_initial": float(record.quantity_initial),
                        "quantity_closed_t1": float(record.quantity_closed_t1),
                        "quantity_closed_final": float(record.quantity_closed_final),
                        "quantity_remaining": float(record.quantity_remaining),
                        "notional_usd": float(record.notional_usd),
                        "initial_risk_usd": float(record.initial_risk_usd),
                        "gross_pnl_usd": float(record.gross_pnl_usd),
                        "fees_usd": float(record.fees_usd),
                        "slippage_usd": float(record.slippage_usd),
                        "net_pnl_usd": float(record.net_pnl_usd),
                        "net_return_pct": float(record.net_return_pct),
                        "r_multiple": float(record.r_multiple),
                        "theoretical_r": float(record.theoretical_r),
                        "execution_drag_r": float(record.execution_drag_r),
                        "t1_hit_at": record.t1_hit_at,
                        "t2_hit_at": record.t2_hit_at,
                        "stop_hit_at": record.stop_hit_at,
                        "duration_seconds": record.duration_seconds,
                        "duration_str": record.duration_str,
                        "created_at_utc": record.created_at_utc,
                        "closed_at_utc": record.closed_at_utc,
                    }
                )
                await session.commit()
                persisted = True
        except Exception as e:
            logger.warning("save_execution_record_failed", trade_id=record.trade_id, error=str(e)[:200])

    # Local cache
    local_recs = restore_executions_local()
    idx_found = -1
    for idx, r in enumerate(local_recs):
        if r.trade_id == record.trade_id:
            idx_found = idx
            break
    if idx_found >= 0:
        local_recs[idx_found] = record
    else:
        local_recs.insert(0, record)
    save_executions_local(local_recs[:150])
    return persisted


async def fetch_execution_records(
    limit: int = 100,
    symbol: str | None = None,
    state: CryptoScalpPositionState | None = None,
) -> list[CryptoScalpExecutionRecord]:
    """Fetch execution trade records from DB or local cache."""
    factory = get_async_session_factory()
    if factory is not None:
        try:
            query = "SELECT * FROM crypto_scalp_executions"
            clauses = []
            params: dict[str, Any] = {"limit": limit}
            if symbol:
                clauses.append("symbol = :symbol")
                params["symbol"] = symbol.upper()
            if state:
                clauses.append("position_state = :state")
                params["state"] = state.value

            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at_utc DESC LIMIT :limit"

            async with factory() as session:
                result = await session.execute(text(query), params)
                rows = result.mappings().all()
                records: list[CryptoScalpExecutionRecord] = []
                for row in rows:
                    rec = CryptoScalpExecutionRecord(
                        trade_id=row["trade_id"],
                        signal_id=row["signal_id"],
                        symbol=row["symbol"],
                        asset=row["asset"],
                        direction=SignalDirection(row["direction"]),
                        strategy=row["strategy"],
                        strategy_name=row["strategy_name"],
                        execution_mode=CryptoScalpExecutionMode(row.get("execution_mode", "PAPER")),
                        position_state=CryptoScalpPositionState(row["position_state"]),
                        signal_price=float(row["signal_price"]),
                        entry_fill_price=float(row["entry_fill_price"]),
                        initial_stop_price=float(row["initial_stop_price"]),
                        current_stop_price=float(row["current_stop_price"]),
                        target_1_price=float(row["target_1_price"]),
                        target_2_price=float(row["target_2_price"]),
                        exit_price=float(row["exit_price"]) if row.get("exit_price") is not None else None,
                        exit_reason=CryptoScalpExitEventType(row["exit_reason"]) if row.get("exit_reason") else None,
                        quantity_initial=float(row["quantity_initial"]),
                        quantity_closed_t1=float(row.get("quantity_closed_t1", 0.0)),
                        quantity_closed_final=float(row.get("quantity_closed_final", 0.0)),
                        quantity_remaining=float(row["quantity_remaining"]),
                        notional_usd=float(row.get("notional_usd", 0.0)),
                        initial_risk_usd=float(row.get("initial_risk_usd", 0.0)),
                        gross_pnl_usd=float(row.get("gross_pnl_usd", 0.0)),
                        fees_usd=float(row.get("fees_usd", 0.0)),
                        slippage_usd=float(row.get("slippage_usd", 0.0)),
                        net_pnl_usd=float(row.get("net_pnl_usd", 0.0)),
                        net_return_pct=float(row.get("net_return_pct", 0.0)),
                        r_multiple=float(row.get("r_multiple", 0.0)),
                        theoretical_r=float(row.get("theoretical_r", 0.0)),
                        execution_drag_r=float(row.get("execution_drag_r", 0.0)),
                        t1_hit_at=row.get("t1_hit_at"),
                        t2_hit_at=row.get("t2_hit_at"),
                        stop_hit_at=row.get("stop_hit_at"),
                        duration_seconds=int(row.get("duration_seconds", 0)),
                        duration_str=row.get("duration_str", "0s"),
                        created_at_utc=int(row.get("created_at_utc", 0)),
                        closed_at_utc=row.get("closed_at_utc"),
                        exit_reason_detail=row.get("exit_reason_detail") or format_detailed_exit_reason(
                            reason=row.get("exit_reason"),
                            symbol=row["symbol"],
                            entry_fill=float(row["entry_fill_price"]),
                            exit_price=float(row["exit_price"]) if row.get("exit_price") is not None else None,
                            target_1=float(row["target_1_price"]),
                            target_2=float(row["target_2_price"]),
                            stop_loss=float(row["initial_stop_price"]),
                            r_multiple=float(row.get("r_multiple", 0.0)),
                            duration_str=row.get("duration_str", "0s"),
                        ),
                    )
                    records.append(rec)
                if records:
                    return records
        except Exception as e:
            logger.warning("fetch_execution_records_failed", error=str(e)[:200])

    # Fallback to local
    local = restore_executions_local()
    for r in local:
        if not r.exit_reason_detail and r.exit_reason:
            r.exit_reason_detail = format_detailed_exit_reason(
                reason=r.exit_reason,
                symbol=r.symbol,
                entry_fill=r.entry_fill_price,
                exit_price=r.exit_price,
                target_1=r.target_1_price,
                target_2=r.target_2_price,
                stop_loss=r.initial_stop_price,
                r_multiple=r.r_multiple,
                duration_str=r.duration_str,
            )
    if symbol:
        local = [r for r in local if r.symbol.upper() == symbol.upper()]
    if state:
        local = [r for r in local if r.position_state == state]
    return local[:limit]


async def fetch_execution_record_by_id(trade_id: str) -> CryptoScalpExecutionRecord | None:
    """Fetch single trade execution record with its event trail."""
    recs = await fetch_execution_records(limit=100)
    for r in recs:
        if r.trade_id == trade_id:
            r.events = await fetch_events_for_trade(trade_id)
            return r
    return None


async def fetch_events_for_trade(trade_id: str) -> list[CryptoScalpExecutionEvent]:
    """Fetch all chronological audit events for a trade."""
    factory = get_async_session_factory()
    if factory is not None:
        try:
            async with factory() as session:
                result = await session.execute(
                    text("SELECT * FROM crypto_scalp_execution_events WHERE trade_id = :trade_id ORDER BY timestamp_ms ASC"),
                    {"trade_id": trade_id},
                )
                rows = result.mappings().all()
                events: list[CryptoScalpExecutionEvent] = []
                for row in rows:
                    meta = row.get("metadata_json")
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except Exception:
                            meta = {}
                    elif not isinstance(meta, dict):
                        meta = {}

                    ev = CryptoScalpExecutionEvent(
                        event_id=row["event_id"],
                        trade_id=row["trade_id"],
                        signal_id=row["signal_id"],
                        event_type=CryptoScalpExitEventType(row["event_type"]),
                        symbol=row["symbol"],
                        direction=SignalDirection(row["direction"]),
                        strategy=row["strategy"],
                        timestamp_ms=int(row["timestamp_ms"]),
                        market_price=float(row["market_price"]),
                        fill_price=float(row["fill_price"]),
                        quantity=float(row["quantity"]),
                        fee_usd=float(row.get("fee_usd", 0.0)),
                        slippage_usd=float(row.get("slippage_usd", 0.0)),
                        gross_pnl_usd=float(row.get("gross_pnl_usd", 0.0)),
                        net_pnl_usd=float(row.get("net_pnl_usd", 0.0)),
                        r_multiple=float(row.get("r_multiple", 0.0)),
                        state_before=CryptoScalpPositionState(row["state_before"]),
                        state_after=CryptoScalpPositionState(row["state_after"]),
                        metadata_json=meta,
                    )
                    events.append(ev)
                if events:
                    return events
        except Exception as e:
            logger.warning("fetch_events_for_trade_failed", trade_id=trade_id, error=str(e)[:200])

    # Fallback to local
    local_evs = restore_events_local()
    return [ev for ev in local_evs if ev.trade_id == trade_id]


async def load_unclosed_execution_records() -> list[CryptoScalpExecutionRecord]:
    """Retrieve all open/active/partially closed positions for restart recovery."""
    all_recs = await fetch_execution_records(limit=200)
    return [r for r in all_recs if r.position_state in (CryptoScalpPositionState.ACTIVE, CryptoScalpPositionState.PARTIALLY_CLOSED)]


async def delete_execution_record(trade_id: str) -> bool:
    """Delete a trade execution record and its audit events from database and local cache."""
    try:
        from app.crypto_scalp.outcome_tracker import crypto_scalp_outcome_tracker
        crypto_scalp_outcome_tracker.active_positions.pop(trade_id, None)
    except Exception:
        pass

    # Remove from local cache
    try:
        local_recs = restore_executions_local()
        new_recs = [r for r in local_recs if r.trade_id != trade_id]
        save_executions_local(new_recs)

        local_evs = restore_events_local()
        new_evs = [ev for ev in local_evs if ev.trade_id != trade_id]
        save_events_local(new_evs)
    except Exception as e:
        logger.warning("delete_execution_record_local_failed", trade_id=trade_id, error=str(e)[:200])

    # Remove from DB if connected
    factory = get_async_session_factory()
    if factory is not None:
        try:
            async with factory() as session:
                await session.execute(
                    text("DELETE FROM crypto_scalp_execution_events WHERE trade_id = :trade_id"),
                    {"trade_id": trade_id},
                )
                await session.execute(
                    text("DELETE FROM crypto_scalp_executions WHERE trade_id = :trade_id"),
                    {"trade_id": trade_id},
                )
                await session.commit()
                return True
        except Exception as e:
            logger.warning("delete_execution_record_db_failed", trade_id=trade_id, error=str(e)[:200])
    return True


# ── Full Crypto FSM & Fill Reconciler Local Cache Layer ──

CRYPTO_FSM_STATE_FILE = Path("crypto_signals_fsm_state.json")

# Max audit entries retained in the local snapshot (append-only in memory).
AUDIT_LOG_SNAPSHOT_LIMIT = 500


async def save_execution_record_from_reconciliation(
    sig: Any,
    rec: Any,
    exit_reason: str,
) -> bool:
    """
    Synthesize a consolidated CryptoScalpExecutionRecord from the FSM + fill
    reconciler ledger and persist it (Supabase + local cache). This bridges the
    production signal path into the executions ledger so the performance API
    reports real completed trades instead of an empty book.
    """
    try:
        from app.models.crypto import SignalDirection
        now_ms = int(time.time() * 1000)

        if sig.t1_hit:
            if exit_reason in ("TARGET_2", "TARGET_2_HIT"):
                exit_ev = CryptoScalpExitEventType.T2_HIT
                theoretical_r = round(0.5 * float(sig.risk_reward_t1) + 0.5 * float(sig.risk_reward_t2), 2)
            elif exit_reason == "RUNNER_TIME_STOP_HIT":
                exit_ev = CryptoScalpExitEventType.TIME_STOP
                theoretical_r = round(0.5 * float(sig.risk_reward_t1), 2)
            else:
                exit_ev = CryptoScalpExitEventType.BREAKEVEN_STOP
                theoretical_r = round(0.5 * float(sig.risk_reward_t1), 2)
        else:
            exit_ev = CryptoScalpExitEventType.TIME_STOP if "TIME_STOP" in str(exit_reason) else CryptoScalpExitEventType.INITIAL_STOP
            theoretical_r = -1.0 if exit_ev == CryptoScalpExitEventType.INITIAL_STOP else 0.0

        duration = max(0, int((now_ms - sig.created_at_utc) / 1000))
        risk_base = rec.initial_risk_usd if rec.initial_risk_usd > 0 else max(1.0, abs(rec.entry_fill_price) * rec.initial_qty * 0.001)
        final_qty = round(rec.initial_qty - rec.t1_qty, 6) if rec.t1_qty else rec.initial_qty

        record = CryptoScalpExecutionRecord(
            trade_id=f"trade_{sig.signal_id}",
            signal_id=sig.signal_id,
            symbol=sig.symbol,
            asset=sig.asset,
            direction=SignalDirection.LONG if sig.direction == "LONG" else SignalDirection.SHORT,
            strategy=sig.strategy,
            strategy_name=sig.strategy_name or sig.strategy,
            position_state=CryptoScalpPositionState.CLOSED,
            signal_price=float(sig.trigger),
            entry_fill_price=rec.entry_fill_price,
            initial_stop_price=float(sig.initial_stop_loss or sig.stop_loss),
            current_stop_price=float(sig.current_stop_loss or sig.stop_loss),
            target_1_price=float(sig.target_1),
            target_2_price=float(sig.target_2),
            exit_price=rec.final_fill_price,
            exit_reason=exit_ev,
            quantity_initial=rec.initial_qty,
            quantity_closed_t1=rec.t1_qty,
            quantity_closed_final=final_qty,
            quantity_remaining=0.0,
            notional_usd=round(rec.entry_fill_price * rec.initial_qty, 2),
            initial_risk_usd=rec.initial_risk_usd,
            gross_pnl_usd=rec.total_gross_pnl_usd,
            fees_usd=rec.total_fees_usd,
            slippage_usd=rec.total_slippage_usd,
            net_pnl_usd=rec.total_net_pnl_usd,
            net_return_pct=round((rec.total_net_pnl_usd / risk_base) * 100.0, 2),
            r_multiple=rec.realized_rr_net,
            theoretical_r=theoretical_r,
            execution_drag_r=round(theoretical_r - rec.realized_rr_net, 2),
            t1_hit_at=sig.t1_fill_timestamp,
            t2_hit_at=now_ms if exit_ev == CryptoScalpExitEventType.T2_HIT else None,
            stop_hit_at=now_ms if exit_ev in (CryptoScalpExitEventType.INITIAL_STOP, CryptoScalpExitEventType.BREAKEVEN_STOP) else None,
            duration_seconds=duration,
            duration_str=f"{duration // 60}m {duration % 60}s" if duration >= 60 else f"{duration}s",
            created_at_utc=sig.created_at_utc,
            closed_at_utc=now_ms,
            exit_reason_detail=format_detailed_exit_reason(
                reason=exit_ev,
                symbol=sig.symbol,
                entry_fill=rec.entry_fill_price,
                exit_price=rec.final_fill_price,
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                stop_loss=float(sig.initial_stop_loss or sig.stop_loss),
                r_multiple=rec.realized_rr_net,
                duration_str=f"{duration // 60}m {duration % 60}s" if duration >= 60 else f"{duration}s",
            ),
        )
        return await save_execution_record(record)
    except Exception as e:
        logger.warning(
            "crypto_reconciliation_record_persist_failed",
            signal_id=getattr(sig, "signal_id", "?"),
            error=str(e)[:200],
        )
        return False


def save_crypto_signals_state_local() -> bool:
    """Safely persist active crypto FSM signals and fill reconciliation records to local cache file."""
    try:
        from app.crypto_scalp.fsm import crypto_signal_fsm
        from app.crypto_scalp.fill_reconciler import crypto_fill_reconciler

        fsm_dict = crypto_signal_fsm._signals
        recon_dict = getattr(crypto_fill_reconciler, "_records", {})

        serialized_fsm = {}
        for sid, s in fsm_dict.items():
            if hasattr(s, "model_dump"):
                serialized_fsm[sid] = s.model_dump(mode="json")
            elif isinstance(s, dict):
                serialized_fsm[sid] = s

        serialized_recon = {}
        for rid, r in recon_dict.items():
            if hasattr(r, "model_dump"):
                serialized_recon[rid] = r.model_dump(mode="json")
            elif isinstance(r, dict):
                serialized_recon[rid] = r

        payload = {
            "fsm_signals": serialized_fsm,
            "fill_reconciliations": serialized_recon,
            # Append-only transition audit log survives restarts too.
            "audit_log": [
                a.model_dump(mode="json")
                for a in list(crypto_signal_fsm._audit_log)[-AUDIT_LOG_SNAPSHOT_LIMIT:]
            ],
            "updated_at_utc": int(time.time() * 1000),
        }

        tmp_file = CRYPTO_FSM_STATE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        tmp_file.replace(CRYPTO_FSM_STATE_FILE)
        return True
    except Exception as e:
        logger.warning("save_crypto_signals_state_local_failed", error=str(e)[:250])
        return False


def restore_crypto_signals_state_local() -> int:
    """Restore crypto FSM signals and fill reconciliations from local cache file."""
    if not CRYPTO_FSM_STATE_FILE.exists():
        return 0

    try:
        from app.crypto_scalp.fsm import crypto_signal_fsm, CryptoSignalInstance
        from app.crypto_scalp.fill_reconciler import crypto_fill_reconciler, CryptoFillReconciliationRecord
        from decimal import Decimal

        with open(CRYPTO_FSM_STATE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)

        count = 0
        raw_fsm = payload.get("fsm_signals", {})
        for sid, sdata in raw_fsm.items():
            if sid not in crypto_signal_fsm._signals and isinstance(sdata, dict):
                try:
                    for dec_field in ("spot_price", "trigger", "stop_loss", "initial_stop_loss", "current_stop_loss", "target_1", "target_2", "t1_price", "t2_price", "risk_points", "risk_r"):
                        if dec_field in sdata and sdata[dec_field] is not None:
                            sdata[dec_field] = Decimal(str(sdata[dec_field]))
                    inst = CryptoSignalInstance(**sdata)
                    crypto_signal_fsm._signals[sid] = inst
                    count += 1
                except Exception as ex:
                    logger.debug("restore_crypto_fsm_instance_failed", signal_id=sid, error=str(ex))

        raw_recon = payload.get("fill_reconciliations", {})
        for rid, rdata in raw_recon.items():
            if rid not in crypto_fill_reconciler._records and isinstance(rdata, dict):
                try:
                    rec = CryptoFillReconciliationRecord(**rdata)
                    crypto_fill_reconciler._records[rid] = rec
                except Exception:
                    pass

        # Restore the append-only transition audit log.
        from app.crypto_scalp.fsm import CryptoFSMTransitionAudit as _Audit
        existing_audit_ids = {a.transition_id for a in crypto_signal_fsm._audit_log}
        for adata in payload.get("audit_log", []):
            if isinstance(adata, dict) and adata.get("transition_id") not in existing_audit_ids:
                try:
                    crypto_signal_fsm._audit_log.append(_Audit(**adata))
                except Exception:
                    pass

        if count:
            logger.info("crypto_fsm_signals_restored_from_local_cache", count=count)
        return count
    except Exception as e:
        logger.warning("restore_crypto_signals_state_local_failed", error=str(e)[:250])
        return 0

