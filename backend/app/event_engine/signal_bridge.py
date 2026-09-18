from __future__ import annotations

import uuid
import time
from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, Field
import structlog

from app.core.atomic_json import atomic_write_json
from app.event_engine.models import CanonicalEvent

logger = structlog.get_logger()


# P0-5: versioned event-context schema. Bump on any field/semantics change so
# consumers can detect stale writers. Single source for this module.
EVENT_CONTEXT_VERSION = "v3.1.0"
SHADOW_RATIONALE_PREFIX = "[SHADOW·no-trade]"
# Shadow records are forward-test artefacts, not trades: 7-day TTL, file-backed
# (DB mirror via event_shadow_signals when DATABASE_URL is configured).
SHADOW_TTL_SECONDS = 7 * 24 * 3600


class EventSignalContext(BaseModel):
    event_id: str
    event_type: str
    event_phase: str
    importance_score: float
    market_impact_score: Optional[float] = None
    opportunity_score: float
    affected_instrument: str
    event_context_version: str = EVENT_CONTEXT_VERSION
    execution_mode: str = "SHADOW_MODE"


class ShadowSignalRecord(BaseModel):
    shadow_signal_id: str = Field(default_factory=lambda: f"SHADOW-{uuid.uuid4().hex[:8].upper()}")
    canonical_event_id: str
    base_signal_id: str
    underlying: str
    strategy: str
    direction: str
    execution_mode: str = "SHADOW_MODE"
    event_importance_score: float
    event_market_impact_score: Optional[float] = None
    event_opportunity_score: float
    suggested_sizing_factor: float = 1.0
    simulated_entry_price: Optional[float] = None
    simulated_exit_price: Optional[float] = None
    simulated_pnl_pct: Optional[float] = None
    shadow_status: str = "TRACKING"  # TRACKING | COMPLETED | INVALIDATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventSignalBridge:
    """Event → Signal Integration Engine (§3, §27).
    
    Guarantees:
      1. Operates strictly in SHADOW_MODE (§3) — zero automatic real capital execution.
      2. Attaches comprehensive event context (§27) to existing SignalInstances.
      3. Records auditable shadow executions for forward-testing validation.
    """

    def __init__(self, persist_path: str | None = None):
        self._shadow_records: dict[str, ShadowSignalRecord] = {}
        self._persist_path = persist_path
        self._load_shadow_records()

    # ── persistence (file-backed with TTL; DB mirror best-effort) ──
    def _persist_file(self) -> str:
        if self._persist_path:
            return self._persist_path
        try:
            from pathlib import Path
            base = Path(__file__).resolve().parents[2] / "data"
            base.mkdir(parents=True, exist_ok=True)
            return str(base / "event_shadow_records.json")
        except Exception:
            return "/tmp/event_shadow_records.json"

    def _load_shadow_records(self) -> None:
        try:
            import json
            from pathlib import Path
            p = Path(self._persist_file())
            if not p.exists():
                return
            raw = json.loads(p.read_text(encoding="utf-8") or "{}")
            now = datetime.now(timezone.utc).timestamp()
            for sid, payload in (raw or {}).items():
                try:
                    rec = ShadowSignalRecord.model_validate(payload)
                    created = rec.created_at.timestamp() if rec.created_at else now
                    if now - created > SHADOW_TTL_SECONDS:
                        continue
                    self._shadow_records[sid] = rec
                except Exception:
                    continue
        except Exception as e:
            logger.debug("shadow_records_load_failed", error=str(e)[:150])

    def _save_shadow_records(self) -> None:
        try:
            from pathlib import Path
            now = datetime.now(timezone.utc).timestamp()
            live: dict[str, dict] = {}
            for sid, rec in list(self._shadow_records.items()):
                try:
                    created = rec.created_at.timestamp() if rec.created_at else now
                    if now - created > SHADOW_TTL_SECONDS:
                        continue
                    live[sid] = rec.model_dump(mode="json")
                except Exception:
                    continue
            # Prune expired from memory too.
            for sid in list(self._shadow_records.keys()):
                if sid not in live:
                    self._shadow_records.pop(sid, None)
            atomic_write_json(
                Path(self._persist_file()),
                live,
                default=str,
                log_event="shadow_records_persist_failed",
                log_level="debug",
                max_error_chars=150,
            )
        except Exception as e:
            logger.debug("shadow_records_persist_failed", error=str(e)[:150])

    def _prune_expired(self) -> None:
        try:
            now = datetime.now(timezone.utc).timestamp()
            for sid, rec in list(self._shadow_records.items()):
                try:
                    created = rec.created_at.timestamp() if rec.created_at else now
                    if now - created > SHADOW_TTL_SECONDS:
                        self._shadow_records.pop(sid, None)
                except Exception:
                    continue
        except Exception:
            pass

    def create_event_context(self, event: CanonicalEvent, underlying: str) -> EventSignalContext:
        """Construct normalized EventContext payload (§27)."""
        importance = event.scores.importance.final_score if event.scores else 80.0
        impact = event.scores.market_impact.final_score if event.scores else None
        opportunity = event.scores.opportunity.final_score if (event.scores and event.scores.opportunity.final_score is not None) else 70.0

        return EventSignalContext(
            event_id=event.canonical_event_id,
            event_type=event.event_type,
            event_phase=event.temporal_phase,
            importance_score=importance,
            market_impact_score=impact,
            opportunity_score=opportunity,
            affected_instrument=underlying,
            event_context_version=EVENT_CONTEXT_VERSION,
            execution_mode="SHADOW_MODE",
        )

    @staticmethod
    def is_shadow_rationale(line: Any) -> bool:
        """P0-5: shadow rationale lines are prefixed and MUST be excluded from any
        signal counting / scoring / P&L aggregation."""
        try:
            return str(line or "").strip().startswith(SHADOW_RATIONALE_PREFIX)
        except Exception:
            return False

    @staticmethod
    def validate_confluence_breakdown(cb: Any) -> tuple[bool, str | None]:
        """P0-5: validate confluence_breakdown schema before mutating it."""
        if cb is None:
            return True, None  # caller will init to {}
        if not isinstance(cb, dict):
            return False, f"confluence_breakdown must be dict, got {type(cb).__name__}"
        # Known numeric domains must stay numeric when present.
        for k in ("technical", "mtf", "fno", "regime", "ai"):
            if k in cb and cb[k] is not None:
                try:
                    float(cb[k])
                except Exception:
                    return False, f"confluence_breakdown[{k!r}] must be numeric"
        if "event_context" in cb and cb["event_context"] is not None and not isinstance(cb["event_context"], dict):
            return False, "confluence_breakdown[event_context] must be dict"
        return True, None

    def enrich_signal(self, signal: Any, event: CanonicalEvent) -> Any:
        """Attach event context to existing SignalInstance or candidate dict.

        P0-5: validates confluence_breakdown schema before mutate; rationale uses
        the `[SHADOW·no-trade]` prefix and is excluded from counting.
        """
        underlying = str(getattr(signal, "underlying", getattr(signal, "instrument_id", "BANKNIFTY") or "BANKNIFTY"))
        ctx = self.create_event_context(event, underlying)

        if hasattr(signal, "confluence_breakdown"):
            try:
                cb = getattr(signal, "confluence_breakdown", None)
                ok, err = self.validate_confluence_breakdown(cb)
                if not ok:
                    logger.warning("event_enrich_breakdown_invalid", error=err)
                else:
                    if cb is None:
                        try:
                            setattr(signal, "confluence_breakdown", {})
                            cb = signal.confluence_breakdown
                        except Exception:
                            cb = {}
                    if isinstance(cb, dict):
                        cb["event_context"] = ctx.model_dump()
            except Exception as e:
                logger.debug("event_enrich_breakdown_failed", error=str(e)[:150])
        if hasattr(signal, "rationale") and isinstance(signal.rationale, list):
            # Idempotent: don't stack duplicate shadow lines for the same event.
            try:
                if not any(event.canonical_event_id in str(x or "") for x in signal.rationale):
                    signal.rationale.append(
                        f"{SHADOW_RATIONALE_PREFIX} Event Context: {event.title} "
                        f"({event.temporal_phase}, Opp: {ctx.opportunity_score}) — "
                        f"excluded from signal counting, no trade"
                    )
            except Exception:
                pass

        return signal

    def record_shadow_execution(
        self,
        signal_id: str,
        event: CanonicalEvent,
        underlying: str,
        strategy: str,
        direction: str,
        simulated_entry_price: float,
    ) -> ShadowSignalRecord:
        """Record shadow execution for paper forward-testing without touching real capital.

        Sizing: opportunity-weighted advisory factor in [0.25, 1.0]:
          base 1.0 → scaled by opportunity/100, penalized by importance (high importance
          = high uncertainty → smaller). Consumers (risk_engine) multiply lots by this.
        """
        ctx = self.create_event_context(event, underlying)
        try:
            opp = float(ctx.opportunity_score or 70.0) / 100.0
            imp = float(ctx.event_importance_score or 80.0) / 100.0
            sizing = max(0.25, min(1.0, round(opp * (1.15 - 0.4 * imp), 2)))
        except Exception:
            sizing = 1.0
        record = ShadowSignalRecord(
            canonical_event_id=event.canonical_event_id,
            base_signal_id=signal_id,
            underlying=underlying,
            strategy=strategy,
            direction=direction,
            execution_mode="SHADOW_MODE",
            event_importance_score=ctx.importance_score,
            event_market_impact_score=ctx.market_impact_score,
            event_opportunity_score=ctx.opportunity_score,
            suggested_sizing_factor=sizing,
            simulated_entry_price=simulated_entry_price,
            shadow_status="TRACKING",
        )

        self._shadow_records[record.shadow_signal_id] = record
        # P0-5: persist to DB/file with TTL (file always; DB best-effort mirror).
        try:
            self._save_shadow_records()
        except Exception:
            pass
        try:
            self._mirror_shadow_to_db(record)
        except Exception as e:
            logger.debug("shadow_db_mirror_failed", error=str(e)[:150])
        logger.info(
            "event_shadow_execution_recorded",
            shadow_id=record.shadow_signal_id,
            event_id=event.canonical_event_id,
            signal_id=signal_id,
            underlying=underlying,
        )
        return record

    def _mirror_shadow_to_db(self, record: ShadowSignalRecord) -> None:
        """Best-effort DB mirror into event_shadow_signals. Never raises; file is
        the source of truth when DB is unavailable (tests, local dev)."""
        try:
            import asyncio

            async def _insert() -> None:
                try:
                    from app.core.database import get_async_session_factory
                    from app.models.event_engine import EventShadowSignalDB
                except Exception:
                    return
                factory = get_async_session_factory()
                if factory is None:
                    return
                async with factory() as session:
                    async with session.begin():
                        session.add(EventShadowSignalDB(
                            shadow_signal_id=record.shadow_signal_id,
                            canonical_event_id=record.canonical_event_id,
                            base_signal_id=record.base_signal_id,
                            underlying=record.underlying,
                            strategy=record.strategy,
                            direction=record.direction,
                            execution_mode=record.execution_mode,
                            event_importance_score=record.event_importance_score,
                            event_market_impact_score=record.event_market_impact_score,
                            event_opportunity_score=record.event_opportunity_score,
                            suggested_sizing_factor=record.suggested_sizing_factor,
                            simulated_entry_price=record.simulated_entry_price,
                            simulated_exit_price=record.simulated_exit_price,
                            simulated_pnl_pct=record.simulated_pnl_pct,
                            shadow_status=record.shadow_status,
                        ))
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(_insert())
                    return
            except RuntimeError:
                pass
            try:
                asyncio.run(_insert())
            except Exception:
                pass
        except Exception:
            pass

    def get_shadow_records(self, limit: int = 50) -> list[ShadowSignalRecord]:
        self._prune_expired()
        return list(self._shadow_records.values())[:limit]

    def complete_shadow_execution(
        self,
        shadow_signal_id: str,
        simulated_exit_price: float,
    ) -> ShadowSignalRecord | None:
        """Close the loop: record exit + simulated PnL% for calibration."""
        rec = self._shadow_records.get(shadow_signal_id)
        if rec is None or rec.simulated_entry_price is None or rec.simulated_entry_price <= 0:
            return rec
        try:
            entry = float(rec.simulated_entry_price)
            exit_px = float(simulated_exit_price)
            direction_mult = -1.0 if "PUT" in rec.direction.upper() or "SHORT" in rec.direction.upper() or "BEAR" in rec.direction.upper() else 1.0
            rec.simulated_exit_price = exit_px
            rec.simulated_pnl_pct = round((exit_px - entry) / entry * 100.0 * direction_mult, 2)
            rec.shadow_status = "COMPLETED"
        except Exception:
            pass
        try:
            self._save_shadow_records()
        except Exception:
            pass
        return rec

    # ── P0-5: risk-engine sizing guard ──────────────────────────────────
    @staticmethod
    def resolve_live_sizing_factor(
        suggested_sizing_factor: float,
        execution_mode: str,
    ) -> float:
        """Return the live sizing multiplier ONLY when execution_mode == LIVE.

        Shadow/paper contexts must NEVER apply the advisory sizing_factor to real
        capital. risk_engine MUST call this (or equivalent assert) before applying
        any event-driven sizing_factor:

            factor = event_signal_bridge.resolve_live_sizing_factor(
                shadow.suggested_sizing_factor, execution_mode)
        """
        if execution_mode != "LIVE":
            raise AssertionError(
                f"REFUSE_SHADOW_SIZING: execution_mode={execution_mode!r} != 'LIVE' — "
                "shadow sizing_factor must not size live capital"
            )
        try:
            v = float(suggested_sizing_factor)
        except Exception:
            v = 1.0
        return float(max(0.25, min(1.0, v)))


event_signal_bridge = EventSignalBridge()
