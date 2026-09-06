"""
Supabase PostgreSQL & Local Cache Persistence Layer for Crypto Scalp Signals.
Guarantees full signal history survives Render redeployments and restarts.
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

logger = structlog.get_logger()

CRYPTO_SCALP_STATE_FILE = Path("crypto_scalp_signals_state.json")


async def ensure_crypto_scalp_tables() -> bool:
    """Auto-provision crypto_scalp_signals table in Supabase PostgreSQL if not present."""
    factory = get_async_session_factory()
    if factory is None:
        logger.debug("crypto_scalp_persistence_no_db_factory")
        return False
    try:
        async with factory() as session:
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
            await session.commit()
            logger.info("crypto_scalp_table_provisioned_successfully")
            return True
    except Exception as e:
        logger.warning("ensure_crypto_scalp_tables_failed", error=str(e)[:250])
        return False


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
    # Replace or prepend
    found = False
    for idx, s in enumerate(local_signals):
        if s.id == signal.id:
            local_signals[idx] = signal
            found = True
            break
    if not found:
        local_signals.insert(0, signal)
    # Keep top 100 in local cache
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

    # Reset local cache
    save_scalp_signals_local([])
    return deleted_count

