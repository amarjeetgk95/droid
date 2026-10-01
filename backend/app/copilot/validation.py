"""Signal Validation / Gate Engine (spec §30).

The quantitative gate engine is AUTHORITATIVE. The LLM never decides whether a
hard rule passed — it only explains the gate table this module produces.

Gates reuse DROID's existing machinery:
  * live signal geometry from `app.signals.fsm.signal_fsm`
  * RISK_GATE delegates to `app.signals.risk_engine.CentralRiskEngine`
  * regime/trend/momentum/volatility/options/flow gates read the copilot
    MarketContext + fused factors (same values the rest of the analysis uses).
"""
from __future__ import annotations

from decimal import Decimal

import structlog

from app.copilot.enums import GATE_ENGINE_VERSION
from app.copilot.models import (
    ConfluenceResult,
    Factor,
    GateCheck,
    LevelsBlock,
    MarketContext,
    SignalUnderReview,
    SignalValidationResult,
)

logger = structlog.get_logger()

HARD_GATES = ("REGIME_GATE", "TREND_GATE", "RISK_GATE")
GATE_ORDER = (
    "REGIME_GATE",
    "TREND_GATE",
    "MOMENTUM_GATE",
    "VOLATILITY_GATE",
    "OPTIONS_GATE",
    "FLOW_GATE",
    "RISK_GATE",
)

_LONG_TOKENS = ("LONG", "BUY", "CALL", "BULL")
_SHORT_TOKENS = ("SHORT", "SELL", "PUT", "BEAR")


def normalize_direction(value: str | None) -> str | None:
    if not value:
        return None
    token = str(value).strip().upper()
    if any(t in token for t in _LONG_TOKENS):
        return "LONG"
    if any(t in token for t in _SHORT_TOKENS):
        return "SHORT"
    return None


class SignalValidationEngine:
    """Deterministic gate evaluation for a LONG/SHORT signal."""

    # ------------------------------------------------------------------ #
    def resolve_signal(
        self,
        symbol: str,
        signal_id: str | None = None,
        direction: str | None = None,
        entry: float | None = None,
        stop: float | None = None,
        target: float | None = None,
    ) -> SignalUnderReview:
        """Resolve a live DROID signal by id, else use the supplied geometry."""
        if signal_id:
            try:
                from app.signals.fsm import signal_fsm

                instance = signal_fsm.get(signal_id)
                if instance is not None:
                    return self._from_instance(instance)
            except Exception as exc:  # noqa: BLE001 — fall back to explicit geometry
                logger.info("copilot_signal_lookup_failed", signal_id=signal_id, error=str(exc)[:160])

        return SignalUnderReview(
            signal_id=signal_id,
            symbol=symbol,
            direction=normalize_direction(direction) or (str(direction).upper() if direction else None),
            entry=entry,
            stop=stop,
            target_1=target,
            source="REQUEST" if signal_id is None else "REQUEST_UNRESOLVED",
        )

    @staticmethod
    def _from_instance(instance: object) -> SignalUnderReview:
        def as_float(value: object) -> float | None:
            try:
                return float(value) if value is not None else None
            except Exception:
                return None

        created = as_float(getattr(instance, "created_at_utc", None))
        created_iso = None
        if created is not None:
            from datetime import datetime, timezone

            created_iso = datetime.fromtimestamp(created / 1000.0, tz=timezone.utc).isoformat()
        return SignalUnderReview(
            signal_id=str(getattr(instance, "signal_id", "") or "") or None,
            symbol=str(getattr(instance, "underlying", "") or "").upper(),
            direction=normalize_direction(getattr(instance, "direction", None)),
            strategy=getattr(instance, "strategy", None),
            timeframe=getattr(instance, "timeframe", None),
            fsm_state=getattr(instance, "fsm_state", None),
            created_at=created_iso,
            entry=as_float(getattr(instance, "trigger", None)),
            stop=as_float(getattr(instance, "stop_loss", None)),
            target_1=as_float(getattr(instance, "target_1", None)),
            target_2=as_float(getattr(instance, "target_2", None)),
            source="LIVE_SIGNAL",
        )

    # ------------------------------------------------------------------ #
    # Gates
    # ------------------------------------------------------------------ #
    def evaluate(
        self,
        ctx: MarketContext,
        factors: dict[str, Factor],
        confluence: ConfluenceResult,
        signal: SignalUnderReview,
        levels: LevelsBlock,
    ) -> SignalValidationResult:
        direction = normalize_direction(signal.direction)
        gates: list[GateCheck] = [
            self._regime_gate(ctx, direction),
            self._trend_gate(factors, direction, ctx),
            self._momentum_gate(factors, direction),
            self._volatility_gate(ctx, signal),
            self._options_gate(ctx, signal, direction),
            self._flow_gate(ctx),
            self._risk_gate(ctx, signal, direction),
        ]
        by_name = {gate.gate: gate for gate in gates}
        ordered = [by_name[name] for name in GATE_ORDER if name in by_name]
        verdict, reasons = self._verdict(ordered, direction)
        return SignalValidationResult(
            verdict=verdict,  # type: ignore[arg-type]
            signal=signal,
            gates=ordered,
            reasons=reasons,
            engine_version=GATE_ENGINE_VERSION,
            authoritative=True,
        )

    @staticmethod
    def _regime_gate(ctx: MarketContext, direction: str | None) -> GateCheck:
        regime = ctx.regime.name
        evidence = [f"Regime {regime}"]
        if regime == "UNKNOWN":
            return GateCheck(
                gate="REGIME_GATE",
                status="FAIL",
                reason="Regime classification unavailable (fail-closed).",
                evidence=evidence,
            )
        if direction == "LONG" and regime == "TRENDING_BEARISH":
            return GateCheck(
                gate="REGIME_GATE",
                status="FAIL",
                reason="LONG signal against a TRENDING_BEARISH regime.",
                evidence=evidence,
            )
        if direction == "SHORT" and regime == "TRENDING_BULLISH":
            return GateCheck(
                gate="REGIME_GATE",
                status="FAIL",
                reason="SHORT signal against a TRENDING_BULLISH regime.",
                evidence=evidence,
            )
        return GateCheck(gate="REGIME_GATE", status="PASS", reason=f"Regime {regime} permits a {direction or 'n/a'} signal.", evidence=evidence)

    @staticmethod
    def _trend_gate(factors: dict[str, Factor], direction: str | None, ctx: MarketContext) -> GateCheck:
        trend = factors.get("trend")
        if trend is None or trend.state == "UNKNOWN":
            return GateCheck(
                gate="TREND_GATE",
                status="FAIL",
                reason="Trend evidence unavailable (fail-closed).",
                evidence=[],
            )
        evidence = list(trend.evidence[:3])
        if trend.state == "NEUTRAL":
            return GateCheck(
                gate="TREND_GATE",
                status="FAIL",
                reason="Trend is non-directional — trend gate is not confirmatory.",
                evidence=evidence,
            )
        if direction and trend.state != ("BULLISH" if direction == "LONG" else "BEARISH"):
            return GateCheck(
                gate="TREND_GATE",
                status="FAIL",
                reason=f"Trend is {trend.state} for a {direction} signal.",
                evidence=evidence,
            )
        return GateCheck(
            gate="TREND_GATE",
            status="PASS",
            reason=f"Trend {trend.state} agrees with a {direction or 'n/a'} signal.",
            evidence=evidence,
        )

    @staticmethod
    def _momentum_gate(factors: dict[str, Factor], direction: str | None) -> GateCheck:
        momentum = factors.get("momentum")
        if momentum is None or momentum.state == "UNKNOWN":
            return GateCheck(gate="MOMENTUM_GATE", status="SKIPPED", reason="Momentum evidence unavailable.", evidence=[])
        evidence = list(momentum.evidence[:3])
        expected = "BULLISH" if direction == "LONG" else "BEARISH"
        if direction and momentum.state != expected and momentum.strength >= 0.4:
            return GateCheck(
                gate="MOMENTUM_GATE",
                status="FAIL",
                reason=f"Momentum is {momentum.state} ({momentum.strength:.2f}) against the {direction} signal.",
                evidence=evidence,
            )
        if momentum.state == "NEUTRAL":
            return GateCheck(gate="MOMENTUM_GATE", status="SKIPPED", reason="Momentum is neutral.", evidence=evidence)
        return GateCheck(gate="MOMENTUM_GATE", status="PASS", reason=f"Momentum {momentum.state}.", evidence=evidence)

    @staticmethod
    def _volatility_gate(ctx: MarketContext, signal: SignalUnderReview) -> GateCheck:
        atr = ctx.technicals.atr
        if atr is None or atr <= 0:
            return GateCheck(gate="VOLATILITY_GATE", status="SKIPPED", reason="ATR unavailable.", evidence=[])
        evidence = [f"ATR {atr:,.2f}"]
        entry, stop = signal.entry, signal.stop
        if entry is None or stop is None:
            if ctx.regime.name == "VOLATILE_EXPANSION":
                return GateCheck(
                    gate="VOLATILITY_GATE",
                    status="FAIL",
                    reason="VOLATILE_EXPANSION regime with no stop geometry to size the risk against.",
                    evidence=evidence + ["Regime VOLATILE_EXPANSION"],
                )
            return GateCheck(
                gate="VOLATILITY_GATE",
                status="SKIPPED",
                reason="No entry/stop supplied, so stop distance cannot be compared with ATR.",
                evidence=evidence,
            )
        stop_distance = abs(entry - stop)
        evidence.append(f"Stop distance {stop_distance:,.2f} pts ({stop_distance / atr:.2f}×ATR)")
        if stop_distance < 0.5 * atr:
            return GateCheck(
                gate="VOLATILITY_GATE",
                status="FAIL",
                reason=f"Stop distance {stop_distance:,.2f} sits inside the {0.5 * atr:,.2f} (0.5×ATR) noise band.",
                evidence=evidence,
            )
        if ctx.regime.name == "VOLATILE_EXPANSION" and stop_distance < atr:
            return GateCheck(
                gate="VOLATILITY_GATE",
                status="FAIL",
                reason="VOLATILE_EXPANSION regime requires a stop distance of at least 1×ATR.",
                evidence=evidence,
            )
        return GateCheck(
            gate="VOLATILITY_GATE",
            status="PASS",
            reason="Stop distance is consistent with current volatility.",
            evidence=evidence,
        )

    @staticmethod
    def _options_gate(ctx: MarketContext, signal: SignalUnderReview, direction: str | None) -> GateCheck:
        o = ctx.options
        if o.pcr_oi is None and o.call_wall is None and o.put_wall is None:
            return GateCheck(
                gate="OPTIONS_GATE",
                status="SKIPPED",
                reason="Options positioning unavailable.",
                evidence=[],
            )
        evidence: list[str] = []
        if o.pcr_oi is not None:
            evidence.append(f"PCR(OI) {o.pcr_oi:.2f}")
        if o.call_wall is not None:
            evidence.append(f"Call wall {o.call_wall:,.0f}")
        if o.put_wall is not None:
            evidence.append(f"Put wall {o.put_wall:,.0f}")
        target = signal.target_1
        if direction == "LONG" and o.call_wall is not None and target is not None and o.call_wall < target:
            return GateCheck(
                gate="OPTIONS_GATE",
                status="FAIL",
                reason=(
                    f"Call wall {o.call_wall:,.0f} sits below the {target:,.0f} target — option writers "
                    "cap the move before the target."
                ),
                evidence=evidence,
            )
        if direction == "SHORT" and o.put_wall is not None and target is not None and o.put_wall > target:
            return GateCheck(
                gate="OPTIONS_GATE",
                status="FAIL",
                reason=(
                    f"Put wall {o.put_wall:,.0f} sits above the {target:,.0f} target — option writers "
                    "support the move before the target."
                ),
                evidence=evidence,
            )
        return GateCheck(
            gate="OPTIONS_GATE",
            status="PASS",
            reason="Option positioning does not block the signal levels.",
            evidence=evidence,
        )

    @staticmethod
    def _flow_gate(ctx: MarketContext) -> GateCheck:
        flow = ctx.institutional_flow
        if not flow.live or flow.net_flow is None:
            return GateCheck(
                gate="FLOW_GATE",
                status="SKIPPED",
                reason="No live institutional flow feed is wired — this gate cannot be evaluated.",
                evidence=["Flow source is a static daily snapshot."] if flow.sentiment else [],
            )
        evidence = [f"Net flow {flow.net_flow:+,.0f} cr on {flow.as_of or '—'}"]
        return GateCheck(
            gate="FLOW_GATE", status="PASS", reason="Live flow available; no veto triggered.", evidence=evidence
        )



    @staticmethod
    def _risk_gate(ctx: MarketContext, signal: SignalUnderReview, direction: str | None) -> GateCheck:
        if signal.entry is None or signal.stop is None or signal.target_1 is None:
            return GateCheck(
                gate="RISK_GATE",
                status="SKIPPED",
                reason="Signal geometry incomplete (entry/stop/target required for a risk audit).",
                evidence=[],
            )
        if direction is None:
            return GateCheck(
                gate="RISK_GATE",
                status="FAIL",
                reason="Signal direction is unresolved — failing closed.",
                evidence=[],
            )
        try:
            from app.signals.risk_engine import CentralRiskEngine, StrategySetup

            setup = StrategySetup(
                strategy_name=signal.strategy or "COPILOT_AUDIT",
                underlying=signal.symbol if signal.symbol in ("NIFTY", "BANKNIFTY", "SENSEX") else "NIFTY",
                direction="LONG_CALL" if direction == "LONG" else "LONG_PUT",
                timeframe=signal.timeframe if signal.timeframe in ("1M", "3M", "5M", "15M", "1H", "1D") else "5M",
                spot_price=Decimal(str(ctx.price.ltp or signal.entry)),
                entry_trigger=Decimal(str(signal.entry)),
                raw_structural_stop=Decimal(str(signal.stop)),
                structural_target_candidates=[Decimal(str(signal.target_1))],
                atr_5m=Decimal(str(ctx.technicals.atr or 1.0)),
                confidence=float(ctx.regime.classification_confidence or 60.0),
            )
            decision = CentralRiskEngine().evaluate(setup, allow_closed_market=True)
            if decision.accepted:
                return GateCheck(
                    gate="RISK_GATE",
                    status="PASS",
                    reason=(
                        f"CentralRiskEngine accepted: R:R(T1) {decision.risk_reward_t1:.2f}, "
                        f"risk {decision.risk_points:.2f} pts."
                    ),
                    evidence=[f"risk {decision.risk_points:.2f} pts", f"R:R(T1) {decision.risk_reward_t1:.2f}"],
                )
            return GateCheck(
                gate="RISK_GATE",
                status="FAIL",
                reason=f"CentralRiskEngine rejected: {decision.rejection_reason}.",
                evidence=[],
            )
        except Exception as exc:  # fail closed — an unevaluable hard gate is never a pass
            logger.info("copilot_risk_gate_unavailable", error=str(exc)[:200])
            return GateCheck(
                gate="RISK_GATE",
                status="FAIL",
                reason=f"Risk engine could not evaluate the geometry (fail-closed): {str(exc)[:160]}",
                evidence=[],
            )

    @staticmethod
    def _verdict(gates: list[GateCheck], direction: str | None) -> tuple[str, list[str]]:
        if direction is None:
            return "CONDITIONAL", ["Signal direction could not be resolved from the supplied context."]
        reasons: list[str] = []
        hard_failures = [g for g in gates if g.gate in HARD_GATES and g.status == "FAIL"]
        soft_failures = [g for g in gates if g.gate not in HARD_GATES and g.status == "FAIL"]
        skipped = [g for g in gates if g.status == "SKIPPED"]
        for gate in hard_failures:
            reasons.append(f"{gate.gate}: {gate.reason}")
        if hard_failures:
            return "REJECTED", reasons
        for gate in soft_failures:
            reasons.append(f"{gate.gate}: {gate.reason}")
        for gate in skipped:
            reasons.append(f"{gate.gate}: {gate.reason}")
        if soft_failures or skipped:
            return "CONDITIONAL", reasons
        reasons.append("All gates passed on live quantitative evidence.")
        return "APPROVED", reasons


signal_validation_engine = SignalValidationEngine()
