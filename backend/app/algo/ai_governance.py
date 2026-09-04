"""
AI Governance — §20-25

Provider/model/prompt versioned, shadow/canary, drift detection, rollback, failure policy.
AI never calls OrderManager/BrokerAdapter, never modifies risk/kill/reconciliation (§20).
"""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Any
import uuid
import structlog
import statistics

logger = structlog.get_logger()

ModelStatus = Literal["CURRENT","CANDIDATE","CANARY","RETIRED","ROLLED_BACK","SHADOW"]
DriftState = Literal["NORMAL","DRIFT_WARNING","DRIFT_CRITICAL","ROLLBACK_REQUIRED"]
AIMode = Literal["AI_REQUIRED","AI_OPTIONAL","AI_DISABLED"]


@dataclass
class AIModelIdentity:
    provider: str
    model_id: str
    model_version: str
    prompt_version: str
    config_version: str | None = None
    status: ModelStatus = "CANDIDATE"
    is_last_known_good: bool = False
    canary_pct: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AIDecision:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    provider: str = ""
    model_id: str = ""
    model_version: str = ""
    prompt_version: str = ""
    config_version: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    market_snapshot_id: str | None = None
    output: dict = field(default_factory=dict)
    confidence: Decimal | None = None
    latency_ms: int | None = None
    schema_valid: bool = True

    def to_audit(self) -> dict:
        return {
            "provider": self.provider, "model_id": self.model_id, "model_version": self.model_version,
            "prompt_version": self.prompt_version, "output": self.output,
            "confidence": str(self.confidence) if self.confidence else None,
            "latency_ms": self.latency_ms, "schema_valid": self.schema_valid,
        }


class AIModelGovernance:
    """Governs current/candidate/canary/shadow lifecycle."""

    def __init__(self):
        self._models: dict[str, AIModelIdentity] = {}
        self._decisions: list[AIDecision] = []
        self._last_known_good_id: str | None = None

    def register(self, identity: AIModelIdentity) -> AIModelIdentity:
        key = f"{identity.provider}:{identity.model_id}:{identity.model_version}"
        self._models[key] = identity
        if identity.is_last_known_good:
            self._last_known_good_id = key
        logger.info("ai_model_registered", key=key, status=identity.status)
        return identity

    def get_current(self) -> AIModelIdentity | None:
        for m in self._models.values():
            if m.status == "CURRENT":
                return m
        return None

    def get_canary(self) -> AIModelIdentity | None:
        for m in self._models.values():
            if m.status == "CANARY":
                return m
        return None

    def get_last_known_good(self) -> AIModelIdentity | None:
        if self._last_known_good_id and self._last_known_good_id in self._models:
            return self._models[self._last_known_good_id]
        for m in self._models.values():
            if m.is_last_known_good:
                return m
        return self.get_current()

    def promote_to_current(self, key: str) -> None:
        # demote existing
        for m in self._models.values():
            if m.status == "CURRENT":
                m.status = "RETIRED"
        if key in self._models:
            self._models[key].status = "CURRENT"
            self._models[key].is_last_known_good = True
            self._last_known_good_id = key

    def start_shadow(self, candidate_key: str) -> None:
        if candidate_key in self._models:
            self._models[candidate_key].status = "SHADOW"

    def start_canary(self, candidate_key: str, pct: Decimal = Decimal("5")) -> None:
        if candidate_key in self._models:
            self._models[candidate_key].status = "CANARY"
            self._models[candidate_key].canary_pct = pct

    def should_use_canary(self, account_hash: int | None = None) -> bool:
        """5% canary routing: CURRENT 95 / CANDIDATE 5 §22."""
        canary = self.get_canary()
        if not canary:
            return False
        import random
        return random.random() * 100 < float(canary.canary_pct)

    def record_decision(self, decision: AIDecision) -> None:
        self._decisions.append(decision)
        if len(self._decisions) > 5000:
            self._decisions = self._decisions[-5000:]

    # ── Drift Detection §23 ──
    def detect_drift(self, window: int = 100) -> dict:
        """
        Compare recent vs baseline distributions for:
        confidence shift, bias shift, LONG/SHORT imbalance, NO_TRADE shift, etc.
        Returns drift metrics + state.
        """
        if len(self._decisions) < window * 2:
            return {"drift_state": "NORMAL", "reason": "INSUFFICIENT_DATA"}

        recent = self._decisions[-window:]
        baseline = self._decisions[-window*2:-window]

        def bias_dist(decisions):
            counts: dict[str, int] = {}
            for d in decisions:
                b = d.output.get("bias", "NO_TRADE")
                counts[b] = counts.get(b, 0) + 1
            total = len(decisions) or 1
            return {k: v/total for k, v in counts.items()}

        recent_conf = [float(d.confidence) for d in recent if d.confidence is not None]
        base_conf = [float(d.confidence) for d in baseline if d.confidence is not None]

        metrics: dict[str, Any] = {}
        drift_flags: list[str] = []

        if recent_conf and base_conf:
            recent_mean = statistics.mean(recent_conf)
            base_mean = statistics.mean(base_conf)
            shift = abs(recent_mean - base_mean)
            metrics["confidence_shift"] = shift
            if shift > 0.15:
                drift_flags.append("CONFIDENCE_SHIFT")
            metrics["recent_conf_mean"] = recent_mean
            metrics["baseline_conf_mean"] = base_mean

        r_bias = bias_dist(recent)
        b_bias = bias_dist(baseline)
        for bias in set(list(r_bias.keys()) + list(b_bias.keys())):
            diff = abs(r_bias.get(bias, 0) - b_bias.get(bias, 0))
            metrics[f"bias_shift_{bias}"] = diff
            if diff > 0.15:
                drift_flags.append(f"BIAS_SHIFT_{bias}")

        # NO_TRADE rate shift
        nt_recent = r_bias.get("NO_TRADE", 0)
        nt_base = b_bias.get("NO_TRADE", 0)
        if abs(nt_recent - nt_base) > 0.15:
            drift_flags.append("NO_TRADE_SHIFT")

        # Schema failures
        recent_schema_fail = sum(1 for d in recent if not d.schema_valid) / len(recent)
        metrics["schema_failure_rate"] = recent_schema_fail
        if recent_schema_fail > 0.05:
            drift_flags.append("SCHEMA_FAILURE_INCREASE")

        # Latency degradation
        recent_lat = [d.latency_ms for d in recent if d.latency_ms]
        base_lat = [d.latency_ms for d in baseline if d.latency_ms]
        if recent_lat and base_lat:
            if statistics.mean(recent_lat) > statistics.mean(base_lat) * 1.5:
                drift_flags.append("LATENCY_DEGRADATION")

        # Determine state
        if len(drift_flags) >= 3 or "CONFIDENCE_SHIFT" in drift_flags and recent_schema_fail > 0.05:
            state: DriftState = "ROLLBACK_REQUIRED"
        elif len(drift_flags) >= 2:
            state = "DRIFT_CRITICAL"
        elif len(drift_flags) >= 1:
            state = "DRIFT_WARNING"
        else:
            state = "NORMAL"

        metrics["drift_flags"] = drift_flags
        metrics["drift_state"] = state
        return metrics

    def rollback(self, candidate_key: str) -> AIModelIdentity | None:
        """
        §24 Stop candidate, restore last-known-good, mark rolled_back, alert, preserve evidence.
        """
        # Mark candidate
        if candidate_key in self._models:
            self._models[candidate_key].status = "ROLLED_BACK"
        lkg = self.get_last_known_good()
        if lkg:
            # Ensure at least one CURRENT
            has_current = any(m.status == "CURRENT" for m in self._models.values())
            if not has_current:
                lkg.status = "CURRENT"
        logger.critical("ai_rollback_executed", candidate=candidate_key, lkg=str(lkg))
        return lkg

    # ── Failure Policy §25 ──
    def handle_failure(self, strategy_ai_mode: AIMode, error: str) -> Literal["NO_NEW_ENTRY", "FALLBACK_ALLOWED"]:
        if strategy_ai_mode == "AI_REQUIRED":
            return "NO_NEW_ENTRY"
        if strategy_ai_mode == "AI_DISABLED":
            return "FALLBACK_ALLOWED"
        # AI_OPTIONAL — deterministic fallback only if explicitly configured & tested
        # Caller must check if fallback configured; default NO_NEW_ENTRY unless allowed
        return "NO_NEW_ENTRY"

    def canary_allowed(self, system_state: str) -> bool:
        """§80 / §37: canary has zero influence during critical states."""
        blocked = {"FULL_EXECUTION_STOP", "ORPHANED_ALERT", "CRITICAL_RECONCILIATION_FAILURE", "CRITICAL_DATA_FAILURE", "CRITICAL_BROKER_FAILURE", "GLOBAL_KILL_SWITCH"}
        return system_state not in blocked


ai_governance = AIModelGovernance()
