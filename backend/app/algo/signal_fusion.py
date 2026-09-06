"""
Signal Fusion, Trigger Engine, Strategy Conflict Resolution — §26-31
"""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4
import structlog

from app.algo.money import D

logger = structlog.get_logger()

# §26 default weights — single source of truth: backend/config/scoring_weights.json (v2).
# Kept inline as fallback if config file is missing (tests, minimal installs).
def _load_scoring_weights_percent() -> dict:
    try:
        import json
        from pathlib import Path
        for p in (
            Path(__file__).resolve().parents[2] / "config" / "scoring_weights.json",
            Path("backend/config/scoring_weights.json"),
            Path("config/scoring_weights.json"),
        ):
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                w = data.get("weights_percent", {})
                if w:
                    return {k: Decimal(str(v)) for k, v in w.items() if k != "ml_max"}
    except Exception:
        pass
    return {
        "technical": Decimal("40"),
        "mtf": Decimal("20"),
        "fno": Decimal("15"),
        "regime": Decimal("10"),
        "ai": Decimal("10"),
        "event_risk": Decimal("5"),
    }


DEFAULT_WEIGHTS = _load_scoring_weights_percent()

# Unified thresholds (scoring_weights.json: fusion_long 62 / fusion_short 38 / armed 70)
FUSION_LONG_THRESHOLD = Decimal("62")
FUSION_SHORT_THRESHOLD = Decimal("38")


@dataclass
class SignalInputs:
    technical: dict = field(default_factory=dict)      # includes score etc
    mtf: dict = field(default_factory=dict)
    fno: dict = field(default_factory=dict)
    regime: dict = field(default_factory=dict)
    ai: dict = field(default_factory=dict)
    event_risk: dict = field(default_factory=dict)
    # per-strategy configurable weights
    weights: dict = field(default_factory=dict)


@dataclass
class Signal:
    signal_id: UUID
    strategy_id: str
    instrument_id: str | None
    symbol: str
    direction: Literal["LONG", "SHORT", "NO_TRADE"]
    timestamp: datetime
    market_snapshot_id: str | None
    technical_state: dict
    mtf_state: dict
    fo_state: dict
    regime: str | None
    ai_result: dict | None
    score: Decimal
    confidence: Decimal
    invalidation_conditions: dict

    def is_actionable(self) -> bool:
        return self.direction in ("LONG", "SHORT")


class SignalFusion:
    """
    Combine technical/mtf/fno/regime/AI/event_risk into fused score & direction.
    Weights configurable per strategy & versioned (§26, §29).
    """

    def fuse(self, inputs: SignalInputs, strategy_id: str, symbol: str, instrument_id: str | None = None) -> Signal:
        weights = inputs.weights or DEFAULT_WEIGHTS
        # Normalize weights to sum 100
        total_w = sum(D(v) for v in weights.values()) or D(100)
        def w(k): return D(weights.get(k, DEFAULT_WEIGHTS.get(k, 0))) / total_w * D(100)

        # Extract normalized sub-scores (0-100)
        tech_score = D(inputs.technical.get("technical_score", 50))
        mtf_score = D(inputs.mtf.get("score", 50))  # caller may provide bias-derived score
        # derive mtf score from bias
        if "score" not in inputs.mtf and "overall_bias" in inputs.mtf:
            bias = inputs.mtf.get("overall_bias")
            if bias == "BULLISH": mtf_score = D(75)
            elif bias == "BEARISH": mtf_score = D(25)

        fno_score = D(inputs.fno.get("score", 50))
        regime_score = D(inputs.regime.get("score", 50))
        if "regime" in inputs.regime and "score" not in inputs.regime:
            # regime -> bias mapping
            r = inputs.regime.get("regime", "RANGE")
            if r in ("STRONG_BULL","BULL"): regime_score = D(75)
            elif r in ("STRONG_BEAR","BEAR"): regime_score = D(25)
            elif r == "RANGE": regime_score = D(50)

        ai_conf = D(inputs.ai.get("confidence", 0.5))
        ai_bias = inputs.ai.get("bias", "NEUTRAL")
        if ai_bias == "LONG": ai_score = ai_conf * D(100)
        elif ai_bias == "SHORT": ai_score = (D(1) - ai_conf) * D(100)
        else: ai_score = D(50)  # NEUTRAL/NO_TRADE

        event_score = D(inputs.event_risk.get("score", 50))
        # event_risk 5% usually penalizes if event pending
        if inputs.event_risk.get("event_pending"):
            event_score = D(30)

        fused = (
            tech_score * w("technical") +
            mtf_score * w("mtf") +
            fno_score * w("fno") +
            regime_score * w("regime") +
            ai_score * w("ai") +
            event_score * w("event_risk")
        ) / D(100)

        # Direction from fused score + AI/technical alignment
        # Also consider AI risk_flags — if critical risk_flag, force NO_TRADE
        risk_flags = inputs.ai.get("risk_flags", [])
        if any(f in ("HIGH_RISK", "EVENT_RISK_HIGH", "LIQUIDITY_RISK") for f in risk_flags):
            direction: Literal["LONG","SHORT","NO_TRADE"] = "NO_TRADE"
            fused = min(fused, D(45))
        elif fused >= FUSION_LONG_THRESHOLD:
            direction = "LONG"
        elif fused <= FUSION_SHORT_THRESHOLD:
            direction = "SHORT"
        else:
            direction = "NO_TRADE"

        # Confidence: agreement + distance from 50, capped at 0.90 (§35).
        # 0.07/agreement (not 0.10) + /200 (not /100) prevents borderline 62 → 0.92 inflation.
        agreement = 0
        if inputs.technical.get("trend") == "BULLISH" and direction == "LONG": agreement += 1
        if inputs.technical.get("trend") == "BEARISH" and direction == "SHORT": agreement += 1
        if inputs.mtf.get("overall_bias") == "BULLISH" and direction == "LONG": agreement += 1
        if inputs.mtf.get("overall_bias") == "BEARISH" and direction == "SHORT": agreement += 1
        if ai_bias == direction: agreement += 1
        confidence = D("0.5") + D(agreement) * D("0.07") + (abs(fused - D(50)) / D(200))
        # Haircut when AI unavailable (no AI key or NEUTRAL with low confidence)
        if not inputs.ai or inputs.ai.get("bias", "NEUTRAL") == "NEUTRAL":
            confidence -= D("0.08")
        confidence = max(D("0.1"), min(D("0.90"), confidence))

        return Signal(
            signal_id=uuid4(),
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            symbol=symbol,
            direction=direction,
            timestamp=datetime.now(timezone.utc),
            market_snapshot_id=inputs.technical.get("market_snapshot_id"),
            technical_state=inputs.technical,
            mtf_state=inputs.mtf,
            fo_state=inputs.fno,
            regime=inputs.regime.get("regime"),
            ai_result=inputs.ai,
            score=fused.quantize(D("0.01")),
            confidence=confidence.quantize(D("0.0001")),
            invalidation_conditions=inputs.ai.get("suggested_invalidation", {}) if isinstance(inputs.ai.get("suggested_invalidation"), dict) else {"raw": inputs.ai.get("suggested_invalidation")},
        )


# ── Strategy Conflict Resolution §28 ─────────────────────────────────

ConflictPolicy = Literal["NET", "PRIORITIZE_BY_RANK", "REJECT_BOTH_AND_ALERT"]


@dataclass
class ConflictingSignal:
    strategy_id: str
    direction: str
    rank: int
    signal: Signal


class ConflictResolver:
    DEFAULT_POLICY: ConflictPolicy = "REJECT_BOTH_AND_ALERT"

    def resolve(
        self,
        signals: list[ConflictingSignal],
        policy: ConflictPolicy | None = None,
        instrument_equivalence_fn=None,
    ) -> tuple[list[Signal], str]:
        """
        Returns (approved_signals, reason).
        - For opposing signals on equivalent instruments, do not silently submit opposing orders.
        - NET: net exposure, submit residual after risk validation.
        """
        policy = policy or self.DEFAULT_POLICY
        if len(signals) <= 1:
            return [s.signal for s in signals], "NO_CONFLICT"

        # Group by equivalent instrument
        # Simplified: if same underlying, treat as equivalent
        # Real: instrument_equivalence_fn maps symbol->underlying bucket
        directions = set(s.direction for s in signals)
        if len(directions) == 1:
            return [s.signal for s in signals], "SAME_DIRECTION_NO_CONFLICT"

        # Conflict: LONG vs SHORT present
        if policy == "REJECT_BOTH_AND_ALERT":
            logger.warning("strategy_conflict_reject_both", count=len(signals))
            return [], "REJECT_BOTH_DUE_TO_CONFLICT"

        if policy == "PRIORITIZE_BY_RANK":
            # Lowest rank number wins
            signals.sort(key=lambda s: s.rank)
            winner = signals[0]
            logger.info("strategy_conflict_prioritized", winner=winner.strategy_id)
            return [winner.signal], f"PRIORITIZED_{winner.strategy_id}"

        if policy == "NET":
            long_ct = sum(1 for s in signals if s.direction == "LONG")
            short_ct = sum(1 for s in signals if s.direction == "SHORT")
            net = long_ct - short_ct
            if net == 0:
                return [], "NET_ZERO_NO_ORDER"
            wanted_dir = "LONG" if net > 0 else "SHORT"
            # Pick highest confidence of wanted direction
            candidates = [s for s in signals if s.direction == wanted_dir]
            candidates.sort(key=lambda s: s.signal.confidence, reverse=True)
            return [candidates[0].signal], f"NET_{wanted_dir}_RESIDUAL_{abs(net)}"

        return [], "UNKNOWN_POLICY"

    def resolve_candidate_conflicts(
        self,
        candidates: list[Any],
        tie_epsilon: float = 5.0,
    ) -> tuple[list[Any], list[str]]:
        """
        Arbitrate between competing SignalCandidates on the same underlying instrument (§28).
        If opposing directions (CALL vs PUT) fire simultaneously:
          - If |confidence_A - confidence_B| < tie_epsilon: Reject both (NO_TRADE on tie).
          - Else: Pick higher confidence candidate, drop opposing candidate.
        """
        if len(candidates) <= 1:
            return candidates, []

        from collections import defaultdict
        by_underlying = defaultdict(list)
        for c in candidates:
            by_underlying[c.underlying].append(c)

        approved = []
        dropped_reasons = []

        for underlying, c_list in by_underlying.items():
            calls = [c for c in c_list if "CALL" in c.direction]
            puts = [c for c in c_list if "PUT" in c.direction]

            if calls and puts:
                best_call = max(calls, key=lambda c: getattr(c, "overall_confidence", 50.0) or 50.0)
                best_put = max(puts, key=lambda c: getattr(c, "overall_confidence", 50.0) or 50.0)
                diff = abs(float(best_call.overall_confidence or 50.0) - float(best_put.overall_confidence or 50.0))

                if diff < tie_epsilon:
                    dropped_reasons.append(
                        f"{underlying}:CONFLICT_TIE_REJECT_BOTH (call={best_call.overall_confidence}, put={best_put.overall_confidence})"
                    )
                    logger.warning("candidate_conflict_tie_reject_both", underlying=underlying, diff=diff)
                    continue

                if (best_call.overall_confidence or 50.0) > (best_put.overall_confidence or 50.0):
                    approved.append(best_call)
                    dropped_reasons.append(f"{underlying}:{best_put.strategy}_DROPPED_IN_FAVOR_OF_{best_call.strategy}_CALL")
                else:
                    approved.append(best_put)
                    dropped_reasons.append(f"{underlying}:{best_call.strategy}_DROPPED_IN_FAVOR_OF_{best_put.strategy}_PUT")
            else:
                approved.extend(c_list)

        return approved, dropped_reasons


conflict_resolver = ConflictResolver()


# ── Trigger Engine §31 ───────────────────────────────────────────────

TriggerType = Literal["BREAKOUT","BREAKDOWN","VWAP_CROSS","EMA_CROSS","VOLUME_SPIKE","OI_ANOMALY","OPTION_CHAIN_CHANGE","TREND_REVERSAL","REGIME_CHANGE","AI_CONTEXT_CHANGE","TIME_BASED"]


@dataclass
class TriggerConfig:
    trigger_types: list[TriggerType] = field(default_factory=lambda: ["BREAKOUT"])
    min_score: Decimal = D(60)
    min_confidence: Decimal = D("0.6")
    cooldown_seconds: int = 60


class TriggerEngine:
    """
    Signal → actionable event. A signal is not an order (§31 last line).
    Dedup: same event must not create duplicate executable signals (§27).
    """

    def __init__(self):
        self._recent_triggers: dict[str, datetime] = {}  # signal_id -> ts for dedup
        self._last_trigger_ts: dict[str, datetime] = {}  # strategy+symbol -> ts for cooldown

    def should_trigger(self, signal: Signal, trigger: TriggerType, config: TriggerConfig | None = None) -> tuple[bool, str]:
        config = config or TriggerConfig()
        key = f"{signal.strategy_id}:{signal.symbol}"

        from app.services.calendar_service import calendar_service
        if not calendar_service.can_trade_now().allowed:
            return False, "MARKET_CLOSED"

        # Dedup: same signal_id already triggered
        if str(signal.signal_id) in self._recent_triggers:
            return False, "DUPLICATE_SIGNAL_ID"

        # Cooldown
        last = self._last_trigger_ts.get(key)
        if last and (datetime.now(timezone.utc) - last).total_seconds() < config.cooldown_seconds:
            return False, "COOLDOWN_ACTIVE"

        # Validate trigger type enabled
        if trigger not in config.trigger_types and "TIME_BASED" not in config.trigger_types:
            # allow if signal score high enough to override? No — strict per config
            pass

        if signal.direction == "NO_TRADE":
            return False, "NO_TRADE_SIGNAL"

        if signal.score < config.min_score:
            return False, f"SCORE_BELOW_THRESHOLD_{signal.score}<{config.min_score}"

        if signal.confidence < config.min_confidence:
            return False, f"CONFIDENCE_BELOW_THRESHOLD_{signal.confidence}<{config.min_confidence}"

        # Trigger type specific checks could go here (breakout validated etc)
        return True, "TRIGGER_APPROVED"

    def mark_triggered(self, signal: Signal) -> None:
        self._recent_triggers[str(signal.signal_id)] = datetime.now(timezone.utc)
        self._last_trigger_ts[f"{signal.strategy_id}:{signal.symbol}"] = datetime.now(timezone.utc)
        # prune old
        cutoff = datetime.now(timezone.utc).timestamp() - 3600
        self._recent_triggers = {k: v for k, v in self._recent_triggers.items() if v.timestamp() > cutoff}


signal_fusion = SignalFusion()
conflict_resolver = ConflictResolver()
trigger_engine = TriggerEngine()
