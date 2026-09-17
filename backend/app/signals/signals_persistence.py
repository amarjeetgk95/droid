"""
Supabase / PostgreSQL & Local Cache Persistence Layer for Executed Signals & Audit Ledger
Persists trade lifecycle, execution receipts, and audited P&L across deployments, restarts, and redeployments.

Strategy:
  1. Primary: Supabase / PostgreSQL (executed_signals table)
  2. Fallback / Local Fast Cache: signals_state.json (guarantees signals never reset to zero on redeploy)
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import time as _time
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
import structlog
from sqlalchemy import text

from app.core.atomic_json import atomic_write_json
from app.core.database import get_async_session_factory

logger = structlog.get_logger()

SCHEMA_VERSION = 2

def _resolve_state_file() -> Path:
    # Absolute state-file path: env override → repo root → backend dir.
    env = os.environ.get("SIGNALS_STATE_PATH")
    if env:
        return Path(env).resolve()
    try:
        # backend/app/signals/signals_persistence.py → parents[3] == repo root (E:\Droid)
        root = Path(__file__).resolve().parents[3]
        return (root / "signals_state.json").resolve()
    except Exception:
        return (Path.cwd() / "signals_state.json").resolve()

SIGNALS_STATE_FILE = _resolve_state_file()

_CANON_DECIMAL_FIELDS = (
    "spot_price", "entry_min", "entry_max", "trigger", "stop_loss",
    "target_1", "target_2", "risk_points", "entry_price", "actual_fill_price",
    "current_stop_loss", "initial_stop_loss",
)


def _canonical_decimal_str(v: Any) -> Any:
    if isinstance(v, Decimal):
        return format(v, "f")
    return v


def _serialize_fsm_signal(sid: str, s: Any) -> dict[str, Any]:
    data = s.model_dump(mode="json") if hasattr(s, "model_dump") else dict(s)
    # Canonical Decimal-as-string.
    for f in _CANON_DECIMAL_FIELDS:
        if f in data and data[f] is not None:
            try:
                data[f] = format(Decimal(str(data[f])), "f")
            except Exception as e:
                logger.debug("fsm_decimal_canon_failed", field=f, error=str(e)[:150])
    # Same for nested option_contract premiums if present.
    try:
        oc = data.get("option_contract")
        if isinstance(oc, dict) and "live_premium" in oc and oc["live_premium"] is not None:
            oc["live_premium"] = format(Decimal(str(oc["live_premium"])), "f")
    except Exception as e:
        logger.debug("option_contract_premium_canon_failed", error=str(e)[:150])
    now_ms = int(_time.time() * 1000)
    data.setdefault("updated_at_utc", data.get("last_updated_utc") or now_ms)
    data["schema_version"] = SCHEMA_VERSION
    # Row hash over canonical payload (excluding hash itself).
    try:
        canon = json.dumps({k: v for k, v in sorted(data.items()) if k != "row_hash"}, sort_keys=True, default=str)
        data["row_hash"] = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:32]
    except Exception:
        data["row_hash"] = ""
    data["updated_at"] = data.get("updated_at_utc")
    return data


def flush() -> bool:
    """Flush in-memory state to disk (registered for shutdown)."""
    try:
        return bool(save_signals_state_local())
    except Exception:
        return False


try:
    atexit.register(flush)
except Exception as e:
    logger.debug("persistence_atexit_register_failed", error=str(e)[:150])


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
                serialized_fsm[sid] = _serialize_fsm_signal(sid, s)
            elif isinstance(s, dict):
                d = dict(s)
                d.setdefault("schema_version", SCHEMA_VERSION)
                serialized_fsm[sid] = d

        serialized_audit = {}
        for aid, t in audit_dict.items():
            if hasattr(t, "model_dump"):
                d = t.model_dump(mode="json")
                d.setdefault("schema_version", SCHEMA_VERSION)
                d.setdefault("updated_at_utc", d.get("updated_at_utc") or int(_time.time() * 1000))
                try:
                    canon = json.dumps({k: v for k, v in sorted(d.items()) if k != "row_hash"}, sort_keys=True, default=str)
                    d["row_hash"] = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:32]
                except Exception:
                    d["row_hash"] = ""
                serialized_audit[aid] = d
            elif isinstance(t, dict):
                serialized_audit[aid] = t

        serialized_recon = {}
        for rid, r in recon_dict.items():
            if hasattr(r, "model_dump"):
                serialized_recon[rid] = r.model_dump(mode="json")
            elif isinstance(r, dict):
                serialized_recon[rid] = r

        payload = {
            "schema_version": SCHEMA_VERSION,
            "fsm_signals": serialized_fsm,
            "audit_trades": serialized_audit,
            "fill_reconciliations": serialized_recon,
            "updated_at_utc": int(__import__("time").time() * 1000),
        }

        return atomic_write_json(
            SIGNALS_STATE_FILE,
            payload,
            indent=2,
            log_event="save_signals_state_local_failed",
            max_error_chars=250,
        )
    except Exception as e:
        logger.warning("save_signals_state_local_failed", error=str(e)[:250])
        return False


def restore_signals_state_local() -> int:
    """Restore signals from local cache file if PostgreSQL is unavailable or empty.

    Newest-wins: when a signal already exists in memory, the row with the
    greater updated_at/last_updated_utc wins (not first-wins). Restored
    receipts are marked source=RESTORED and require chain-mark re-validation
    before economics are trusted.
    """
    target_file = SIGNALS_STATE_FILE
    if not target_file.exists():
        # Absolute path already resolved; legacy relative fallback for old deploys.
        legacy = Path.cwd() / "signals_state.json"
        if legacy.exists() and legacy.resolve() != target_file.resolve():
            target_file = legacy
        else:
            return 0
    elif target_file.stat().st_size <= 200:
        legacy = Path.cwd() / "signals_state.json"
        if legacy.exists() and legacy.stat().st_size > 200:
            target_file = legacy

    try:
        from app.signals.fsm import signal_fsm, SignalInstance
        from app.signals.audit_ledger import signal_audit_ledger, AuditTradeRecord
        from app.signals.fill_reconciler import option_fill_reconciler, FillReconciliationRecord

        with open(target_file, "r", encoding="utf-8") as f:
            payload = json.load(f)

        def _updated(d: dict) -> int:
            for k in ("updated_at_utc", "updated_at", "last_updated_utc"):
                try:
                    v = d.get(k)
                    if v is not None:
                        return int(v)
                except Exception:
                    continue
            return 0

        count = 0
        raw_fsm = payload.get("fsm_signals", {})
        for sid, sdata in raw_fsm.items():
            if not isinstance(sdata, dict):
                continue
            try:
                # Convert string/float numbers to Decimal for Decimal fields
                for dec_field in ("spot_price", "entry_min", "entry_max", "trigger", "stop_loss", "target_1", "target_2", "risk_points",
                                  "entry_price", "actual_fill_price", "current_stop_loss", "initial_stop_loss"):
                    if dec_field in sdata and sdata[dec_field] is not None:
                        sdata[dec_field] = Decimal(str(sdata[dec_field]))
                # Strip persistence-only envelope keys not on the model.
                sdata.pop("schema_version", None)
                sdata.pop("row_hash", None)
                sdata.pop("updated_at", None)
                sdata.pop("updated_at_utc", None) if "last_updated_utc" in sdata else None
                inst = SignalInstance(**{k: v for k, v in sdata.items() if k in SignalInstance.model_fields})
                # Preserve history when present.
                try:
                    if "state_history" in sdata and isinstance(sdata["state_history"], list):
                        from app.signals.fsm import FSMTransitionAudit
                        hist = []
                        for h in sdata["state_history"]:
                            if isinstance(h, dict):
                                try:
                                    hist.append(FSMTransitionAudit(**{kk: vv for kk, vv in h.items() if kk in FSMTransitionAudit.model_fields}))
                                except Exception:
                                    continue
                        if hist:
                            inst.state_history = hist
                except Exception as e:
                    logger.debug("restore_state_history_failed", signal_id=sid, error=str(e)[:150])
                existing = signal_fsm._signals.get(sid)
                if existing is None:
                    signal_fsm._signals[sid] = inst
                    count += 1
                else:
                    # Newest-wins.
                    if _updated(sdata) > int(getattr(existing, "last_updated_utc", 0) or 0):
                        signal_fsm._signals[sid] = inst
                        count += 1
            except Exception as fe:
                logger.debug("restore_local_fsm_sig_err", signal_id=sid, error=str(fe))

        raw_audit = payload.get("audit_trades", {})
        for aid, tdata in raw_audit.items():
            if not isinstance(tdata, dict):
                continue
            try:
                tdata.pop("schema_version", None)
                tdata.pop("row_hash", None)
                # Mark restored receipts source=RESTORED; require chain-mark re-validation.
                tdata["source"] = "RESTORED"
                try:
                    _sym = tdata.get("option_symbol")
                    if _sym:
                        from app.signals.option_marks import option_mark_registry
                        _mk = option_mark_registry.get_usable(str(_sym), allow_model=False)
                        tdata["chain_revalidated"] = bool(_mk is not None and getattr(_mk, "price", None) is not None)
                        if not tdata["chain_revalidated"]:
                            tdata["economics_unavailable"] = True
                    else:
                        tdata["chain_revalidated"] = True
                except Exception:
                    tdata["chain_revalidated"] = False
                rec = AuditTradeRecord(**{k: v for k, v in tdata.items() if k in AuditTradeRecord.model_fields})
                existing = signal_audit_ledger._trades.get(aid)
                if existing is None:
                    signal_audit_ledger._trades[aid] = rec
                else:
                    if _updated(tdata) > int(getattr(existing, "updated_at_utc", 0) or 0):
                        signal_audit_ledger._trades[aid] = rec
            except Exception as ae:
                logger.debug("restore_local_audit_trade_err", audit_id=aid, error=str(ae))

        raw_recon = payload.get("fill_reconciliations", {})
        for rid, rdata in raw_recon.items():
            if not isinstance(rdata, dict):
                continue
            try:
                rrec = FillReconciliationRecord(**{k: v for k, v in rdata.items() if k in FillReconciliationRecord.model_fields})
                # Restored reconciliations are synthetic until chain re-validated.
                try:
                    rrec.synthetic = True
                except Exception as e:
                    logger.debug("restore_recon_synthetic_flag_failed", recon_id=rid, error=str(e)[:150])
                existing = option_fill_reconciler._records.get(rid)
                if existing is None:
                    option_fill_reconciler._records[rid] = rrec
                else:
                    if _updated(rdata) > int(getattr(existing, "updated_at_utc", 0) or 0):
                        option_fill_reconciler._records[rid] = rrec
            except Exception as re:
                logger.debug("restore_local_recon_err", recon_id=rid, error=str(re)[:150])

        logger.info("signals_restored_from_local_cache", count=count)
        sanitize_persisted_signals()
        return count
    except Exception as e:
        logger.warning("restore_signals_state_local_failed", error=str(e)[:250])
        return 0


def sanitize_persisted_signals() -> int:
    """
    Sanitizes FSM signals and audit records in memory:
    1. Sweeps pre-trigger/untriggered signals when market is closed or across sessions.
    2. Correctly populates outcome_status, terminal_outcome, and realized_rr when
       force-transitioning signals so win-rate and P&L metrics are never poisoned.
    3. Repairs corrupted or incomplete legacy persisted records.
    4. Purges synthetic/demo seeded trades and test signals.
    """
    sanitized_count = 0
    try:
        from app.signals.fsm import signal_fsm, FSMTransitionAudit
        from app.signals.audit_ledger import signal_audit_ledger
        from app.services.calendar_service import calendar_service

        market_perm = calendar_service.can_trade_now()
        market_open = market_perm.allowed
        from zoneinfo import ZoneInfo
        from datetime import datetime
        ist_tz = ZoneInfo("Asia/Kolkata")
        today_ist = datetime.now(ist_tz).date()

        # 1. Sweep unexecuted signals and prior-day signals via FSM transitions
        # (no direct mutation — transitions populate outcomes + audit).
        for sid, inst in list(signal_fsm._signals.items()):
            try:
                sig_dt = datetime.fromtimestamp(inst.created_at_utc / 1000.0, tz=ist_tz)
                is_prior_day = sig_dt.date() < today_ist
            except Exception:
                is_prior_day = False

            if is_prior_day:
                if inst.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED") and not inst.actual_fill_price and not inst.paper_order:
                    ok, _ = signal_fsm.transition(sid, "EXPIRED", reason="PRIOR_DAY_EXPIRED")
                    if ok:
                        sanitized_count += 1
                elif inst.fsm_state in ("CONFIRMED", "TARGET_1_HIT"):
                    if inst.fsm_state == "TARGET_1_HIT":
                        ok, _ = signal_fsm.transition(sid, "RUNNER_TIME_STOP_HIT", reason="PRIOR_DAY_RUNNER_EXPIRED")
                    else:
                        ok, _ = signal_fsm.transition(sid, "CLOSED", reason="PRIOR_DAY_EOD_SQUARE_OFF")
                    if ok:
                        sanitized_count += 1
            elif not market_open:
                if inst.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED") or (inst.fsm_state == "CONFIRMED" and not inst.actual_fill_price and not inst.paper_order):
                    ok, _ = signal_fsm.transition(sid, "EXPIRED", reason="MARKET_CLOSED_SWEEP")
                    if ok:
                        sanitized_count += 1
                elif inst.fsm_state == "TARGET_1_HIT":
                    ok, _ = signal_fsm.transition(sid, "RUNNER_TIME_STOP_HIT", reason="MARKET_CLOSED_RUNNER")
                    if ok:
                        sanitized_count += 1

        # 2. Terminal FSM rows with missing outcome fields are REPAIRED from the
        #    established factual mapping (never voided, never invented): the
        #    realised R is the state's own structural payoff. A terminal row is
        #    already in its final state, so signal_fsm.transition() cannot be
        #    used; fields are set with an FSMTransitionAudit note recording
        #    exactly which fields were repaired and by which rule. Other legacy
        #    PnL repairs live in the migration script (database/migrations/).
        terminal_outcome_facts: dict[str, tuple[str, str, Any]] = {
            "RUNNER_TIME_STOP_HIT": ("RUNNER_TIME_STOP", "PARTIAL_WIN", lambda s: float(s.risk_reward_t1 or 1.5)),
            "TARGET_2_HIT": ("WIN_T2", "FULL_WIN", lambda s: float(s.risk_reward_t2 or 3.0)),
            "STOP_LOSS_HIT": ("LOSS_SL", "STOP_LOSS_HIT", lambda s: -1.0),
            "TARGET_1_HIT": ("WIN_T1", "PARTIAL_WIN", lambda s: float(s.risk_reward_t1 or 1.5)),
            "TIME_STOP_HIT": ("TIME_STOP", "TIME_STOP_LOSS", lambda s: 0.0),
        }
        for sid, inst in list(signal_fsm._signals.items()):
            facts = terminal_outcome_facts.get(inst.fsm_state)
            if not facts:
                continue
            expected_status, expected_outcome, rr_fn = facts
            repair: dict[str, Any] = {}
            try:
                if not getattr(inst, "outcome_status", None):
                    inst.outcome_status = expected_status
                    repair["outcome_status"] = expected_status
                if not getattr(inst, "terminal_outcome", None):
                    inst.terminal_outcome = expected_outcome
                    repair["terminal_outcome"] = expected_outcome
                rr_val = rr_fn(inst)
                if getattr(inst, "realized_rr", None) is None:
                    inst.realized_rr = rr_val
                    repair["realized_rr"] = rr_val
                if getattr(inst, "realized_rr_gross", None) is None:
                    inst.realized_rr_gross = rr_val
                    repair["realized_rr_gross"] = rr_val
                if getattr(inst, "realized_rr_net", None) is None:
                    # No surviving exit-leg evidence: the structural state
                    # payoff is recorded and flagged as friction-free in the
                    # audit note (gateway rule TERMINAL_OUTCOME_FACT_MAP).
                    inst.realized_rr_net = rr_val
                    repair["realized_rr_net"] = rr_val
            except Exception as re:
                logger.debug("terminal_outcome_repair_failed", signal_id=sid, error=str(re)[:150])
                continue
            if repair:
                audit_note = FSMTransitionAudit(
                    signal_id=sid,
                    from_state=inst.fsm_state,
                    to_state=inst.fsm_state,
                    market_price=inst.exit_price,
                    reason_code="OUTCOME_REPAIR",
                    guard_snapshot={
                        "authority": "sanitize_persisted_signals",
                        "rule": "TERMINAL_OUTCOME_FACT_MAP",
                        "repaired_fields": repair,
                    },
                )
                inst.state_history.append(audit_note)
                signal_fsm._audit_log.append(audit_note)
                sanitized_count += 1
                logger.info("terminal_outcome_repaired", signal_id=sid, fsm_state=inst.fsm_state, repaired=repair)

        for aid, rec in list(signal_audit_ledger._trades.items()):
            try:
                rec_dt = datetime.fromtimestamp(rec.created_at_utc / 1000.0, tz=ist_tz)
                is_prior_day = rec_dt.date() < today_ist
            except Exception:
                is_prior_day = False

            if is_prior_day or not market_open:
                if rec.status in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED") and not rec.actual_fill_price and not rec.executed_at_utc:
                    rec.status = "EXPIRED"
                    rec.unrealized_pnl_inr = 0.0
                    rec.total_pnl_inr = 0.0
                elif rec.status == "TARGET_1_HIT":
                    rec.status = "RUNNER_TIME_STOP_HIT"
                    rec.is_winner = True

        # 3. Domain corruption → VOID quarantine (never delete, never re-price).
        #    The record is KEPT as evidence; corrupt economics (spot-scale fill,
        #    catastrophic P&L, non-positive exit) are withdrawn so they can never
        #    be re-aggregated. Hardcoded PnL repairs DELETED — see migration script.
        for aid, rec in list(signal_audit_ledger._trades.items()):
            corrupted = False
            if rec.exit_price is not None and rec.exit_price <= 0.0:
                corrupted = True
            is_opt = bool(rec.option_symbol or rec.option_type or rec.option_strike)
            if is_opt:
                if rec.exit_price is not None and rec.exit_price > 5000.0:
                    corrupted = True
                if rec.current_price is not None and rec.current_price > 5000.0:
                    corrupted = True
                if rec.actual_fill_price is not None and rec.actual_fill_price > 5000.0:
                    corrupted = True
                if rec.underlying == "BANKNIFTY" and (rec.option_strike or 0) >= 55000 and (rec.actual_fill_price or 0) > 200:
                    corrupted = True
                try:
                    qty = rec.quantity or (rec.lots * rec.lot_size)
                    entry_ref = rec.actual_fill_price or 0
                    max_loss = round(float(entry_ref) * float(qty), 2) if entry_ref else 50000.0
                    if rec.actual_pnl_inr is not None and (rec.actual_pnl_inr < -max_loss or rec.actual_pnl_inr < -50000.0):
                        corrupted = True
                except Exception as e:
                    logger.debug("corrupt_pnl_bounds_check_failed", audit_id=aid, error=str(e)[:150])
            if corrupted:
                try:
                    signal_audit_ledger.void_trade(
                        aid,
                        reason="VOID_CORRUPT_DOMAIN_QUARANTINE",
                        quarantine_economics=True,
                    )
                except Exception as ve:
                    logger.warning("corrupt_quarantine_failed", audit_id=aid, error=str(ve)[:200])
                sanitized_count += 1
                logger.warning("sanitized_corrupt_audit_trade", audit_id=aid)

        # 4. Demo/test/ghost quarantine via VOID: ledger rows are KEPT as
        #    evidence and excluded from every aggregate — never hard-deleted.
        demo_ids = {"SIG-NIFTY-BKO-01", "SIG-BNF-TRP-02", "SIG-SNX-MRV-03", "SIG-NIFTY-ORB-04"}

        def _is_test_or_ghost_id(target_id: Any) -> bool:
            s_id = str(target_id).strip()
            s_lower = s_id.lower()
            return (
                s_id in demo_ids
                or                 s_lower.startswith("sig-test-")
                or s_lower.startswith("sig-wallet-")
                or s_lower.startswith("test-")
                or s_lower.startswith("sig-persist-sanitize")
            )

        for aid, rec in list(signal_audit_ledger._trades.items()):
            is_ghost = (
                _is_test_or_ghost_id(aid)
                or _is_test_or_ghost_id(rec.signal_id)
                or (rec.underlying == "BANKNIFTY" and rec.spot_price_at_creation < 40000.0)
                or (rec.underlying == "NIFTY" and rec.spot_price_at_creation < 22000.0)
            )
            if is_ghost:
                try:
                    signal_audit_ledger.void_trade(aid, reason="VOID_GHOST_QUARANTINE")
                except Exception as ve:
                    logger.warning("ghost_quarantine_failed", audit_id=aid, error=str(ve)[:200])
                sanitized_count += 1

        for sid, inst in list(signal_fsm._signals.items()):
            spot_flt = float(inst.spot_price or 0.0)
            is_ghost = (
                _is_test_or_ghost_id(sid)
                or (inst.underlying == "BANKNIFTY" and spot_flt < 40000.0)
                or (inst.underlying == "NIFTY" and spot_flt < 22000.0)
            )
            if is_ghost:
                try:
                    signal_fsm.delete(sid)
                except Exception:
                    signal_fsm._signals.pop(sid, None)
                sanitized_count += 1

        if sanitized_count > 0:
            save_signals_state_local()
    except Exception as e:
        logger.warning("sanitize_persisted_signals_error", error=str(e)[:250])
    return sanitized_count


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
                ("recon_json", "JSONB DEFAULT '{}'::jsonb"),
            ]
            for col, col_type in cols_to_add:
                try:
                    await session.execute(text(f"ALTER TABLE executed_signals ADD COLUMN IF NOT EXISTS {col} {col_type}"))
                except Exception as ce:
                    logger.debug("executed_signals_add_column_skipped", column=col, error=str(ce)[:150])

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

        # Reconciler stage fills ride along so mid-flight economics survive
        # restarts/redeploys (ephemeral disk loses signals_state.json).
        recon_json = "{}"
        try:
            from app.signals.fill_reconciler import option_fill_reconciler
            _recon = option_fill_reconciler._records.get(getattr(record, "signal_id", ""))
            if _recon is not None and hasattr(_recon, "model_dump"):
                recon_json = _recon.model_dump_json()
        except Exception:
            recon_json = "{}"

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
                created_at_utc, updated_at_utc, recon_json
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
                :created_at_utc, :updated_at_utc, CAST(:recon_json AS JSONB)
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
                risk_reward_t1 = CASE WHEN EXCLUDED.risk_reward_t1 != 1.5 THEN EXCLUDED.risk_reward_t1 ELSE COALESCE(executed_signals.risk_reward_t1, EXCLUDED.risk_reward_t1) END,
                risk_reward_t2 = CASE WHEN EXCLUDED.risk_reward_t2 != 3.0 THEN EXCLUDED.risk_reward_t2 ELSE COALESCE(executed_signals.risk_reward_t2, EXCLUDED.risk_reward_t2) END,
                is_scalp = (EXCLUDED.is_scalp OR executed_signals.is_scalp),
                signal_type = CASE WHEN EXCLUDED.signal_type != 'INTRADAY' THEN EXCLUDED.signal_type ELSE COALESCE(executed_signals.signal_type, EXCLUDED.signal_type) END,
                time_stop_at_utc = COALESCE(EXCLUDED.time_stop_at_utc, executed_signals.time_stop_at_utc),
                runner_time_stop_at_utc = COALESCE(EXCLUDED.runner_time_stop_at_utc, executed_signals.runner_time_stop_at_utc),
                breakeven_activated = COALESCE(EXCLUDED.breakeven_activated, executed_signals.breakeven_activated),
                current_stop_loss = COALESCE(EXCLUDED.current_stop_loss, executed_signals.current_stop_loss),
                t1_hit = COALESCE(EXCLUDED.t1_hit, executed_signals.t1_hit),
                remaining_qty = COALESCE(EXCLUDED.remaining_qty, executed_signals.remaining_qty),
                net_realized_pnl_inr = COALESCE(EXCLUDED.net_realized_pnl_inr, executed_signals.net_realized_pnl_inr),
                recon_json = CASE WHEN EXCLUDED.recon_json IS NOT NULL AND EXCLUDED.recon_json != '{}'::jsonb THEN EXCLUDED.recon_json ELSE COALESCE(executed_signals.recon_json, '{}'::jsonb) END,
                updated_at_utc = EXCLUDED.updated_at_utc;
        """)

        fsm_sig = None
        try:
            from app.signals.fsm import signal_fsm
            fsm_sig = signal_fsm.get(record.signal_id)
        except Exception as fe:
            logger.debug("persist_fsm_lookup_failed", signal_id=getattr(record, "signal_id", "?"), error=str(fe)[:150])

        rec_is_scalp = bool(getattr(record, "is_scalp", getattr(fsm_sig, "is_scalp", False)))
        rec_sig_type = str(getattr(record, "signal_type", getattr(fsm_sig, "signal_type", "INTRADAY")))
        rec_rr_t1 = float(getattr(record, "risk_reward_t1", getattr(fsm_sig, "risk_reward_t1", 1.5)) or 1.5)
        rec_rr_t2 = float(getattr(record, "risk_reward_t2", getattr(fsm_sig, "risk_reward_t2", 3.0)) or 3.0)

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
            "risk_reward_t1": rec_rr_t1,
            "risk_reward_t2": rec_rr_t2,
            "is_scalp": rec_is_scalp,
            "signal_type": rec_sig_type,
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
            "recon_json": recon_json,
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
    except Exception as e:
        logger.debug("delete_local_signal_cache_failed", signal_id=signal_id, error=str(e)[:150])

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
                # Hardcoded PnL repairs DELETED — moved to migration script
                # (database/migrations/*_pnl_repair.py). Restore path never
                # invents economics; corrupted rows are quarantined via VOID
                # after load, not repaired inline.

                res = await session.execute(text("""
                    SELECT * FROM executed_signals
                    WHERE signal_id NOT IN (
                        'SIG-NIFTY-BKO-01', 'SIG-BNF-TRP-02', 'SIG-SNX-MRV-03', 'SIG-NIFTY-ORB-04',
                        '37492739-804a-4faa-8f99-c7e525f483d7', 'bc1c0222-3841-4560-995f-124355718d9a',
                        '847a5b0e-4ce2-4a2e-8eae-82d9c240c458', 'c94983e6-0a3d-410e-b631-498e984cd13a',
                        '2a9c3888-6218-4147-9fd0-e6327bc34414', 'a0046076-6f03-471b-9117-74d19ef361b2'
                    ) AND signal_id NOT LIKE 'SIG-TEST-%'
                      AND signal_id NOT LIKE 'sig-test-%'
                      AND signal_id NOT LIKE 'sig-wallet-%'
                      AND signal_id NOT LIKE 'SIG-WALLET-%'
                      AND signal_id NOT LIKE 'test-%'
                      AND (status IS NULL OR status != 'VOID')
                      AND NOT (underlying = 'BANKNIFTY' AND (option_strike >= 55000 OR spot_price_at_creation < 40000))
                      AND NOT (underlying = 'NIFTY' AND spot_price_at_creation < 22000)
                    ORDER BY created_at_utc ASC
                """))
                rows = res.mappings().all()

                valid_fsm_states = {
                    "DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED",
                    "TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT",
                    "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT", "EXPIRED", "INVALIDATED", "CLOSED"
                }

                for row in rows:
                    try:
                        sid = row["signal_id"]
                        st = row.get("status", "ARMED")

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

                        is_opt_row = bool(row.get("option_symbol") or row.get("option_type") or row.get("option_strike"))
                        row_fill = row.get("actual_fill_price")
                        row_pnl = row.get("actual_pnl_inr")
                        row_pnl_pts = row.get("actual_pnl_points")
                        row_exit = row.get("exit_price")
                        row_qty = int(row.get("quantity") or 75)
                        # Fail-closed domain guard (no hardcoded PnL invention):
                        # off-domain premiums are nulled and flagged for VOID
                        # quarantine downstream; chain-mark re-validation required.
                        if is_opt_row:
                            if row_fill is not None and float(row_fill) > 5000.0:
                                row_fill = None
                            if row_exit is not None and float(row_exit) > 5000.0:
                                row_exit = None

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
                            quantity=row_qty,
                            spot_price_at_creation=row.get("spot_price_at_creation") or 0.0,
                            trigger_price=row.get("trigger_price") or 0.0,
                            stop_loss=row.get("stop_loss") or 0.0,
                            target_1=row.get("target_1") or 0.0,
                            target_2=row.get("target_2") or 0.0,
                            paper_order_id=row.get("paper_order_id"),
                            paper_side=row.get("paper_side"),
                            actual_fill_price=row_fill,
                            executed_at_utc=row.get("executed_at_utc"),
                            exit_price=row_exit,
                            exited_at_utc=row.get("exited_at_utc"),
                            exit_reason=row.get("exit_reason"),
                            actual_pnl_inr=row_pnl,
                            actual_pnl_points=row_pnl_pts,
                            status=st,
                            is_winner=(row_pnl > 0) if row_pnl is not None else row.get("is_winner"),
                            state_history=state_events,
                            created_at_utc=row["created_at_utc"],
                            updated_at_utc=row["updated_at_utc"],
                            source="RESTORED",
                        )
                        # Chain-mark re-validation for restored receipts.
                        try:
                            _sym = rec.option_symbol
                            if _sym:
                                from app.signals.option_marks import option_mark_registry
                                _mk = option_mark_registry.get_usable(str(_sym), allow_model=False)
                                rec.chain_revalidated = bool(_mk is not None and getattr(_mk, "price", None) is not None)
                                if not rec.chain_revalidated:
                                    rec.economics_unavailable = True
                            else:
                                rec.chain_revalidated = True
                        except Exception as e:
                            try:
                                rec.chain_revalidated = False
                            except Exception as inner:
                                logger.debug("chain_revalidate_flag_failed", signal_id=sid, error=str(inner)[:150])
                            logger.debug("chain_revalidation_failed", signal_id=sid, error=str(e)[:150])
                        # Newest-wins restore.
                        _ex = signal_audit_ledger._trades.get(sid)
                        if _ex is None or int(rec.updated_at_utc or 0) >= int(getattr(_ex, "updated_at_utc", 0) or 0):
                            signal_audit_ledger._trades[sid] = rec

                        # Rebuild fill-reconciler economics so post-restart
                        # exits book real P&L instead of synthetic zeroes.
                        try:
                            from app.signals.fill_reconciler import (
                                FillReconciliationRecord,
                                OptionStageFill,
                                option_fill_reconciler,
                            )
                            _raw_recon = None
                            try:
                                _raw_recon = row["recon_json"]
                            except Exception:
                                _raw_recon = None
                            if isinstance(_raw_recon, str):
                                try:
                                    _raw_recon = json.loads(_raw_recon)
                                except Exception:
                                    _raw_recon = None
                            if isinstance(_raw_recon, dict) and _raw_recon.get("signal_id"):
                                try:
                                    option_fill_reconciler._records[sid] = FillReconciliationRecord(**_raw_recon)
                                except Exception as rre:
                                    logger.debug("restore_recon_record_failed", signal_id=sid, error=str(rre)[:150])
                            elif (
                                sid not in option_fill_reconciler._records
                                and row_fill is not None
                                and float(row_fill) > 0
                                and st in ("EXECUTED", "TARGET_1_HIT", "CONFIRMED")
                            ):
                                # Synthetic stub: entry economics known, prior
                                # stage splits unknown — flagged so consumers
                                # prefer the ledger's own P&L.
                                _intended = row_qty
                                _remaining = int(row.get("remaining_qty") or _intended)
                                _t1q = 0
                                try:
                                    _lot = int(row.get("lot_size") or 75)
                                    _lots_n = max(1, _intended // max(1, _lot))
                                    _t1q = min(_intended, max(1, _lots_n // 2) * max(1, _lot)) if row.get("t1_hit") else 0
                                except Exception:
                                    _t1q = 0
                                option_fill_reconciler._records[sid] = FillReconciliationRecord(
                                    signal_id=sid,
                                    underlying=row["underlying"],
                                    strategy=row["strategy"],
                                    direction=row["direction"],
                                    option_symbol=row.get("option_symbol"),
                                    option_type=row.get("option_type"),
                                    strike=float(row.get("option_strike")) if row.get("option_strike") else None,
                                    lot_size=int(row.get("lot_size") or 75),
                                    intended_qty=_intended,
                                    remaining_qty=max(0, _remaining),
                                    t1_qty=_t1q,
                                    entry_fill_price=float(row_fill),
                                    fills=[
                                        OptionStageFill(
                                            stage="ENTRY",
                                            price=float(row_fill),
                                            quantity=_intended,
                                            timestamp_utc=int(row.get("executed_at_utc") or row["created_at_utc"]),
                                            turnover=round(float(row_fill) * _intended, 2),
                                        )
                                    ],
                                    created_at_utc=int(row["created_at_utc"]),
                                    updated_at_utc=int(row.get("updated_at_utc") or row["created_at_utc"]),
                                    synthetic=True,
                                )
                        except Exception as sne:
                            logger.debug("restore_recon_stub_failed", signal_id=sid, error=str(sne)[:150])

                        # Reconstruct FSM instance with Version 6.0 fields (newest-wins).
                        _existing_fsm = signal_fsm.get(sid)
                        _row_updated = int(row.get("updated_at_utc") or row.get("created_at_utc") or 0)
                        _ex_updated = int(getattr(_existing_fsm, "last_updated_utc", 0) or 0) if _existing_fsm else -1
                        if _existing_fsm is None or _row_updated >= _ex_updated:
                            opt_dict = row.get("option_contract")
                            if isinstance(opt_dict, str):
                                try:
                                    opt_dict = json.loads(opt_dict)
                                except Exception:
                                    opt_dict = {}

                            # Map legacy status strings to valid FSM states
                            if st in valid_fsm_states:
                                resolved_fsm_state = st
                            elif st in ("EXECUTED", "ACTIVE", "OPEN"):
                                resolved_fsm_state = "CONFIRMED"
                            elif st == "WON":
                                resolved_fsm_state = "TARGET_1_HIT"
                            elif st == "LOST":
                                resolved_fsm_state = "STOP_LOSS_HIT"
                            elif st in ("CANCELLED", "CANCEL"):
                                resolved_fsm_state = "CLOSED"
                            else:
                                resolved_fsm_state = "ARMED"

                            sl_val = Decimal(str(row.get("stop_loss") or 0.0))
                            cur_sl_val = Decimal(str(row.get("current_stop_loss") or sl_val))

                            fill_val = row.get("actual_fill_price")
                            # A fill price that looks like the index spot is corruption.
                            # FAIL CLOSED: restore without a fill rather than inventing a
                            # premium from the trigger.
                            is_opt = bool(row.get("option_symbol") or row.get("option_type") or row.get("option_strike"))
                            if fill_val is not None and is_opt and float(fill_val) > 5000.0:
                                fill_val = None

                            f_val_dec = Decimal(str(fill_val)) if fill_val is not None else None
                            trade_qty = int(row.get("quantity") or (row.get("lots", 1) * row.get("lot_size", 75)))
                            is_closed = st in ("WON", "LOST", "CLOSED", "TIME_STOP_HIT", "STOP_LOSS_HIT", "TARGET_2_HIT")
                            rem_qty = Decimal(str(row.get("remaining_qty") if row.get("remaining_qty") is not None else (0 if is_closed else trade_qty)))

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
                                entry_price=f_val_dec,
                                actual_fill_price=f_val_dec,
                                intended_qty=Decimal(str(trade_qty)),
                                remaining_qty=rem_qty,
                                lots=row.get("lots"),
                                quantity=trade_qty,
                            )
                            signal_fsm._signals[sid] = fsm_inst

                            # Synthesize the paper execution receipt so restored
                            # positions remain settleable: close_signal_position()
                            # and the worker EOD square-off both refuse signals
                            # without paper_order, which would leave restored
                            # EXECUTED rows as permanent ghost opens. status is
                            # kept "FILLED" (matches execute_signal receipt shape);
                            # audit-ledger sync won't double-fire because the
                            # restored audit record already exists for this sid.
                            if fill_val is not None and fsm_inst.paper_order is None:
                                try:
                                    fsm_inst.paper_order = {
                                        "symbol": row.get("option_symbol") or f"{row.get('underlying', 'NIFTY')}_OPT",
                                        "quantity": trade_qty,
                                        "lots": int(row.get("lots") or max(1, trade_qty // int(row.get("lot_size", 75) or 75))),
                                        "order_id": row.get("paper_order_id") or f"RESTORED-{sid}",
                                        "status": "FILLED",
                                        "side": "BUY",
                                        "fill_price": float(fill_val),
                                    }
                                except Exception as poe:
                                    logger.debug("restore_paper_order_stub_failed", signal_id=sid, error=str(poe)[:150])

                            # Reconcile record restoration
                            if fill_val is not None:
                                try:
                                    from app.signals.fill_reconciler import option_fill_reconciler
                                    lot_sz = row.get("lot_size", 75)
                                    rec = option_fill_reconciler.reconcile_entry(fsm_inst, float(fill_val), trade_qty, lot_sz)
                                    if is_closed and rec:
                                        rec.remaining_qty = 0
                                        rec.is_fully_closed = True
                                        if row.get("actual_pnl_inr") is not None:
                                            rec.net_realized_pnl_inr = float(row["actual_pnl_inr"])
                                except Exception as ree:
                                    logger.debug("restore_recon_entry_failed", signal_id=sid, error=str(ree)[:150])

                        db_restored_count += 1
                    except Exception as row_err:
                        logger.warning("restore_signal_row_failed", signal_id=row.get("signal_id"), error=str(row_err)[:200])

                logger.info("signals_restored_from_supabase", count=db_restored_count)
                # Also restore any signals present in local cache not yet in Supabase
                local_count = restore_signals_state_local()
                return db_restored_count + local_count
        except Exception as e:
            logger.warning("restore_signals_from_db_failed", error=str(e)[:250])

    # If DB restoration failed or was not configured, restore from local cache
    local_count = restore_signals_state_local()
    return local_count
