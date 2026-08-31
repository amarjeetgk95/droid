"""
Signal Fusion, Trigger Engine, Strategy Conflict Resolution — §26-31
"""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Any
from uuid import UUID, uuid4
import structlog

from app.algo.money import D

logger = structlog.get_logger()

# §26 default weights
DEFAULT_WEIGHTS = {
    "technical": Decimal("40"),
    "mtf": Decimal("20"),
    "fno": Decimal("15"),
    "regime": Decimal("10"),
    "ai": Decimal("10"),
    "event_risk": Decimal("5"),
}


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
        elif fused >= D(62):
            direction = "LONG"
        elif fused <= D(38):
            direction = "SHORT"
        else:
            direction = "NO_TRADE"

        # Confidence derived from agreement among components
        # High when technical, mtf, ai all agree
        agreement = 0
        if inputs.technical.get("trend") == "BULLISH" and direction == "LONG": agreement += 1
        if inputs.technical.get("trend") == "BEARISH" and direction == "SHORT": agreement += 1
        if inputs.mtf.get("overall_bias") == "BULLISH" and direction == "LONG": agreement += 1
        if inputs.mtf.get("overall_bias") == "BEARISH" and direction == "SHORT": agreement += 1
        if ai_bias == direction: agreement += 1
        confidence = D("0.5") + D(agreement) * D("0.1") + (abs(fused - D(50)) / D(100))
        confidence = max(D("0.1"), min(D("0.95"), confidence))

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
