"""
VORTEX-SNAP Strategy Adapter for DROID Signal Engine.

Implements the Strategy protocol:
    detect(ctx: StrategyContext) -> Optional[SignalCandidate]
Integrates with the full VORTEX-SNAP microstructure engine, FSM, and risk gates.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.strategies.candidate import make_candidate
from app.signals.strategies.vortex_snap.types import (
    Candle,
    EventType,
    VortexFeatureSnapshot,
    VortexState,
)
from app.signals.strategies.vortex_snap.config import VortexSnapConfig
from app.signals.strategies.vortex_snap.session import MarketSessionModel
from app.signals.strategies.vortex_snap.feature_engine import VortexFeatureEngine
from app.signals.strategies.vortex_snap.signals.event_classifier import EventClassifier
from app.signals.strategies.vortex_snap.signals.confirmation import ConfirmationEngine
from app.signals.strategies.vortex_snap.signals.no_trade import NoTradeGate
from app.signals.strategies.vortex_snap.signals.exit_engine import DynamicExitEngine
from app.signals.strategies.vortex_snap.signals.signal_score import SignalScoreEngine
from app.signals.strategies.vortex_snap.signals.cooldown import CooldownManager, SignalDeduplicator
from app.signals.strategies.vortex_snap.risk.data_quality import DataQualityGate
from app.signals.strategies.vortex_snap.risk.daily_gates import DailyRiskGate
from app.signals.strategies.vortex_snap.ml.validator import VortexMLValidator
from app.signals.strategies.vortex_snap.signals.state_machine import VortexSnapFSM


def dict_to_candle(c: dict, default_ts: int = 0) -> Candle:
    """Safely parse candle dictionary into typed Candle."""
    ts = c.get("timestamp") or c.get("time") or default_ts
    if isinstance(ts, str):
        try:
            ts = int(ts)
        except ValueError:
            ts = default_ts
    return Candle(
        timestamp=int(ts),
        open=float(c.get("open", 0.0)),
        high=float(c.get("high", 0.0)),
        low=float(c.get("low", 0.0)),
        close=float(c.get("close", 0.0)),
        volume=float(c.get("volume", 0.0)),
    )


class VortexSnapStrategy(Strategy):
    """Institutional Microstructure Scalping Strategy (§1 - §56)."""

    name = "VORTEX_SNAP"

    def __init__(
        self,
        config: Optional[VortexSnapConfig] = None,
        feature_engine: Optional[VortexFeatureEngine] = None,
        ablation_overrides: Optional[Dict[str, bool]] = None,
        ml_validator: Optional[VortexMLValidator] = None,
    ) -> None:
        self.config = config or VortexSnapConfig.default()
        self.feature_engine = feature_engine or VortexFeatureEngine(self.config)
        self.ablation_overrides = ablation_overrides
        self.ml_validator = ml_validator or VortexMLValidator(enabled=True)
        self.session_model = MarketSessionModel(self.config.session)
        self.classifier = EventClassifier()
        self.confirmation_engine = ConfirmationEngine()
        self.no_trade_gate = NoTradeGate()
        self.exit_engine = DynamicExitEngine()
        self.score_engine = SignalScoreEngine()
        self.cooldown_mgr = CooldownManager()
        self.deduplicator = SignalDeduplicator()
        self.data_quality_gate = DataQualityGate()
        self.daily_risk_gate = DailyRiskGate()
        self.fsm = VortexSnapFSM()

    def reset(self) -> None:
        """Reset internal state across sequential backtest runs or new trading sessions."""
        self.feature_engine.reset_state()
        self.cooldown_mgr.reset()
        self.deduplicator.reset()
        self.daily_risk_gate.reset()
        self.fsm = VortexSnapFSM()

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        """Evaluate market state and emit deterministic candidate signal.

        Args:
            ctx: Point-in-time StrategyContext.

        Returns:
            SignalCandidate if all microstructure, FSM, and risk gates pass, else None.
        """
        # Fail closed on insufficient candles
        candles_raw = getattr(ctx, "candles", None)
        if not candles_raw or len(candles_raw) < self.config.compression.atr_long_period:
            return None

        spot_dec = ctx.spot_price
        if spot_dec <= Decimal("0"):
            return None
        spot = float(spot_dec)

        # 1. Parse candle history
        candles_1m: List[Candle] = []
        for i, c in enumerate(candles_raw):
            try:
                candles_1m.append(dict_to_candle(c, default_ts=ctx.timestamp_ms - (len(candles_raw) - i) * 60000))
            except Exception:
                return None  # Fail closed on malformed candle

        # 2. Data Quality Gate (§40)
        dq_res = self.data_quality_gate.validate(candles_1m, system_time_ms=ctx.timestamp_ms)
        if not dq_res.is_valid:
            return None

        # 3. Extract Macro Reference Levels from context
        ind = ctx.indicators or {}
        pdh = float(ind.get("pdh", 0.0)) or None
        pdl = float(ind.get("pdl", 0.0)) or None
        pdc = float(ind.get("pdc", 0.0)) or None
        cdo = float(ind.get("cdo", 0.0)) or None
        vwap = float(getattr(ctx, "vwap", 0.0) or ind.get("vwap", 0.0)) or None

        # 4. Compute Point-In-Time Microstructure Feature Snapshot
        try:
            snapshot: VortexFeatureSnapshot = self.feature_engine.compute_snapshot(
                instrument=ctx.underlying,
                candles_1m=candles_1m,
                timestamp_ms=ctx.timestamp_ms,
                spot_price=spot,
                pdh=pdh,
                pdl=pdl,
                pdc=pdc,
                cdo=cdo,
                vwap=vwap,
                ablation_overrides=self.ablation_overrides,
            )
            # Step the FSM state machine
            self.fsm.step(snapshot, candles_1m)
        except Exception:
            return None  # Fail closed

        # 5. Global Risk & No-Trade Gate (§18, §39)
        risk_ok, risk_reason = self.daily_risk_gate.can_open_position()
        if not risk_ok:
            return None

        is_cooling = self.cooldown_mgr.is_in_cooldown(ctx.underlying, ctx.timestamp_ms)
        no_trade_res = self.no_trade_gate.evaluate(
            snapshot=snapshot,
            cooldown_active=is_cooling,
            daily_loss_limit_breached=not risk_ok,
        )
        if no_trade_res.is_no_trade:
            return None

        # 6. Event Classification (§12)
        event = self.classifier.classify(snapshot, candles_1m)
        trigger_candle = candles_1m[-2] if len(candles_1m) >= 2 else candles_1m[-1]
        confirm_candle = candles_1m[-1]

        if not event and len(candles_1m) >= 2:
            # Check if event was initiated on candle t-1 and candle t is the confirmation bar
            prior_snapshot = self.feature_engine.compute_snapshot(
                instrument=ctx.underlying,
                candles_1m=candles_1m[:-1],
                timestamp_ms=candles_1m[-2].timestamp,
                spot_price=candles_1m[-2].close,
                pdh=pdh,
                pdl=pdl,
                pdc=pdc,
                cdo=cdo,
                vwap=vwap,
                ablation_overrides=self.ablation_overrides,
            )
            event = self.classifier.classify(prior_snapshot, candles_1m[:-1])
            if event:
                trigger_candle = candles_1m[-2]
                confirm_candle = candles_1m[-1]

        if not event:
            return None

        # 7. Deduplication Check (§36)
        if self.deduplicator.is_duplicate(
            instrument=ctx.underlying,
            level_price=event.interacted_level.price,
            direction=event.direction,
            timestamp_ms=ctx.timestamp_ms,
        ):
            return None

        # 8. Confirmation Engine (§17)
        conf_res = self.confirmation_engine.evaluate(
            event=event,
            trigger_candle=trigger_candle,
            confirm_candle=confirm_candle,
            snapshot=snapshot,
        )
        if not conf_res.is_confirmed:
            return None

        # 8b. Machine Learning Validator Gate (§25-§27)
        session_info = self.session_model.evaluate(ctx.timestamp_ms)
        ml_decision = self.ml_validator.validate(
            snapshot=snapshot,
            current_candle=confirm_candle,
            session_info=session_info,
            interacted_level=event.interacted_level,
            event_type=event.event_type,
            direction=event.direction,
        )
        if not ml_decision.is_accepted:
            return None

        # 9. Dynamic Exit & Trade Parameters (§20, §21)
        targets = self.exit_engine.calculate_trade_envelope(
            direction=event.direction,
            entry_price=spot,
            snapshot=snapshot,
            interacted_level=event.interacted_level,
        )

        # 10. Multi-Factor Scoring (§24)
        base_confidence = self.score_engine.compute_score(
            snapshot=snapshot,
            interacted_level=event.interacted_level,
            ml_probability=ml_decision.calibrated_probability,
        )
        total_boost = conf_res.confidence_boost + ml_decision.confidence_boost
        final_confidence = min(round((base_confidence + total_boost) * 100.0, 1), 95.0)

        # 11. Option Selection Contract Resolution (§28)
        direction_tag = "LONG_CALL" if event.direction > 0 else "LONG_PUT"
        opt_type = "CE" if event.direction > 0 else "PE"
        opt = resolve_option_contract(
            ctx.underlying,
            spot_dec,
            opt_type,
            strike_offset=0,
        )

        # 12. Build Candidate Signal
        reasons = [r.value for r in event.reason_codes]
        if conf_res.reason_code:
            reasons.append(conf_res.reason_code.value)
        reasons.append(f"Regime={snapshot.regime.regime.value}")
        reasons.append(f"TranslationRatio={snapshot.translation.translation_ratio:.2f}")
        reasons.append(f"ML_Prob={ml_decision.calibrated_probability:.2f}")

        entry_dec = Decimal(str(targets.entry_price))
        stop_dec = Decimal(str(targets.stop_price))
        t1_dec = Decimal(str(targets.target_1))
        t2_dec = Decimal(str(targets.target_2))

        entry_buffer = Decimal(str(round(targets.expected_move * 0.05, 2)))

        return make_candidate(
            ctx,
            strategy=self.name,
            direction=direction_tag,
            entry_min=entry_dec - entry_buffer,
            entry_max=entry_dec + entry_buffer,
            trigger=entry_dec,
            stop_loss=stop_dec,
            target_1=t1_dec,
            target_2=t2_dec,
            risk_points=Decimal(str(round(targets.risk_points, 2))),
            risk_reward_t1=targets.reward_risk_ratio,
            risk_reward_t2=round(targets.reward_risk_ratio * 1.6, 2),
            signal_type="SCALP",
            is_scalp=True,
            overall_confidence=final_confidence,
            option_contract=opt,
            rationale=reasons,
        )
