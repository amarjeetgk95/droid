"""
Confirmation Gates & Gate Chain for Signal Processing (Phase 3)
Provides modular, independently testable confirmation gates:
  - KillSwitchGate
  - FeedCircuitGate
  - FNOIntegrityGate
  - DeskConcurrencyGate
  - PortfolioConcurrencyGate
  - CrossDeskArbiterGate
  - RSIGate
  - MarketStructureGate
  - TriggerIntegrityGate
  - OptionViabilityGate
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol
import structlog
from pydantic import BaseModel, Field

from app.signals.fsm import signal_fsm
from app.signals.risk.cross_desk_arbiter import cross_desk_arbiter
from app.signals.safety.feed_circuit import feed_circuit
from app.signals.safety.kill_switch import kill_switch
from app.signals.strategies.base import SignalCandidate
from app.signals.trigger_gate import check_trigger_integrity

logger = structlog.get_logger()


class GateResult(BaseModel):
    passed: bool
    gate_name: str
    reason_code: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Gate(Protocol):
    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> GateResult:
        ...


class KillSwitchGate:
    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> GateResult:
        if kill_switch.is_active():
            return GateResult(passed=False, gate_name="KillSwitchGate", reason_code="GLOBAL_KILL_SWITCH_ACTIVE")
        return GateResult(passed=True, gate_name="KillSwitchGate")


class FeedCircuitGate:
    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> GateResult:
        if feed_circuit.is_degraded(candidate.underlying):
            return GateResult(passed=False, gate_name="FeedCircuitGate", reason_code="FEED_DEGRADED_CIRCUIT_BREAKER")
        return GateResult(passed=True, gate_name="FeedCircuitGate")


class FNOIntegrityGate:
    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> GateResult:
        if getattr(candidate, "fno_degraded", False):
            # Flagged in candidate, does not necessarily drop if can be validated, but records rejection code for ARMED
            return GateResult(passed=True, gate_name="FNOIntegrityGate", reason_code="ARMED_BLOCKED_FNO_DEGRADED")
        return GateResult(passed=True, gate_name="FNOIntegrityGate")


class DeskConcurrencyGate:
    def evaluate(self, candidate: SignalCandidate, registered_in_flight: list[Any] | None = None, **kwargs: Any) -> GateResult:
        cand_is_scalp = bool(getattr(candidate, "is_scalp", False) or candidate.timeframe in ("1M", "3M"))
        active_underlying_all = signal_fsm.list_active(underlying=candidate.underlying)
        in_flight_underlying = [
            s for s in active_underlying_all
            if s.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED", "TARGET_1_HIT")
            and not s.is_expired()
        ] + [s for s in (registered_in_flight or []) if s.underlying == candidate.underlying]

        same_desk_in_flight = [
            s for s in in_flight_underlying
            if bool(getattr(s, "is_scalp", False) or s.timeframe in ("1M", "3M")) == cand_is_scalp
        ]

        active_same_desk_trades = [s for s in same_desk_in_flight if s.fsm_state in ("CONFIRMED", "TARGET_1_HIT")]
        if active_same_desk_trades:
            desk_lbl = "SCALP" if cand_is_scalp else "INTRADAY"
            reason = f"UNDERLYING_HAS_ACTIVE_TRADE_{desk_lbl}_{active_same_desk_trades[0].strategy}"
            return GateResult(passed=False, gate_name="DeskConcurrencyGate", reason_code=reason)

        same_dir_stacked = [
            s for s in same_desk_in_flight
            if s.direction == candidate.direction
            and s.fsm_state in ("ARMED", "TRIGGERED", "CONFIRMED", "TARGET_1_HIT")
        ]
        if same_dir_stacked:
            reason = f"STACKING_BLOCKED_EXISTING_{same_dir_stacked[0].strategy}_{same_dir_stacked[0].direction}"
            return GateResult(passed=False, gate_name="DeskConcurrencyGate", reason_code=reason)

        cross_desk_stacked = [
            s for s in in_flight_underlying
            if s.direction == candidate.direction
            and s.strategy == candidate.strategy
            and s.fsm_state in ("ARMED", "TRIGGERED", "CONFIRMED", "TARGET_1_HIT")
        ]
        if cross_desk_stacked:
            blocker = cross_desk_stacked[0]
            reason = f"CROSS_DESK_STACKING_BLOCKED_{blocker.strategy}_{blocker.direction}"
            return GateResult(passed=False, gate_name="DeskConcurrencyGate", reason_code=reason)

        return GateResult(passed=True, gate_name="DeskConcurrencyGate")


class PortfolioConcurrencyGate:
    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> GateResult:
        all_active = signal_fsm.list_active()
        portfolio_open_trades = [
            s for s in all_active
            if s.fsm_state in ("CONFIRMED", "TARGET_1_HIT")
            and not s.is_expired()
        ]
        if len(portfolio_open_trades) >= 4:
            return GateResult(passed=False, gate_name="PortfolioConcurrencyGate", reason_code="PORTFOLIO_CONCURRENCY_LIMIT_REACHED")
        return GateResult(passed=True, gate_name="PortfolioConcurrencyGate")


class CrossDeskArbiterGate:
    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> GateResult:
        cand_is_scalp = bool(getattr(candidate, "is_scalp", False) or candidate.timeframe in ("1M", "3M"))
        all_active = signal_fsm.list_active()
        arb_dec = cross_desk_arbiter.arbitrate(
            candidate_is_scalp=cand_is_scalp,
            candidate_underlying=candidate.underlying,
            candidate_direction=candidate.direction,
            active_trades=all_active,
        )
        if not arb_dec.passed:
            return GateResult(passed=False, gate_name="CrossDeskArbiterGate", reason_code=arb_dec.reason)
        return GateResult(passed=True, gate_name="CrossDeskArbiterGate")


class RSIGate:
    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> GateResult:
        indicators_snap = getattr(candidate, "context_snapshot", {}).get("indicators", {}) or {}
        rsi_explicit = indicators_snap.get("rsi") or indicators_snap.get("momentum", {}).get("rsi")
        if rsi_explicit is not None:
            rsi_val = float(rsi_explicit)
            is_call = "CALL" in candidate.direction
            strat = candidate.strategy.upper()

            if strat == "MEAN_REVERSION":
                rsi_ok = (is_call and rsi_val <= 38.0) or (not is_call and rsi_val >= 62.0)
            elif strat in ("BREAKOUT", "MICRO_MOMENTUM", "GAMMA_SQUEEZE", "GAMMA_SPIKE"):
                rsi_ok = (is_call and 52.0 <= rsi_val <= 82.0) or (not is_call and 18.0 <= rsi_val <= 48.0)
            elif strat in ("TREND_PULLBACK", "EMA_RIBBON", "ORB", "VWAP_SCALP"):
                rsi_ok = (is_call and 40.0 <= rsi_val <= 70.0) or (not is_call and 30.0 <= rsi_val <= 60.0)
            else:
                rsi_ok = (is_call and 35.0 <= rsi_val <= 80.0) or (not is_call and 20.0 <= rsi_val <= 65.0)

            if not rsi_ok:
                return GateResult(passed=False, gate_name="RSIGate", reason_code=f"RSI_REJECTION_{rsi_val:.1f}")
        return GateResult(passed=True, gate_name="RSIGate")


class MarketStructureGate:
    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> GateResult:
        strat = candidate.strategy.upper()
        if strat in ("BREAKOUT", "MEAN_REVERSION", "VWAP_SCALP"):
            return GateResult(passed=True, gate_name="MarketStructureGate")

        indicators_snap = getattr(candidate, "context_snapshot", {}).get("indicators", {}) or {}
        atr_val = Decimal(str(indicators_snap.get("volatility", {}).get("atr") or float(candidate.risk_points or 20.0)))
        sr_data = indicators_snap.get("support_resistance", {})
        is_call = "CALL" in candidate.direction

        if is_call and sr_data.get("resistance"):
            raw_res = sr_data.get("resistance")
            res_items = raw_res if isinstance(raw_res, (list, tuple, set)) else [raw_res] if raw_res is not None else []
            res_levels = []
            for r in res_items:
                try:
                    dec_r = Decimal(str(r))
                    if dec_r > candidate.spot_price:
                        res_levels.append(dec_r)
                except Exception:
                    pass
            if res_levels:
                dist_to_overhead = min(lvl - candidate.spot_price for lvl in res_levels)
                if dist_to_overhead < (atr_val * Decimal("0.25")):
                    return GateResult(passed=False, gate_name="MarketStructureGate", reason_code=f"BLOCKED_BY_RESISTANCE_{float(dist_to_overhead):.1f}pts")
        elif (not is_call) and sr_data.get("support"):
            raw_sup = sr_data.get("support")
            sup_items = raw_sup if isinstance(raw_sup, (list, tuple, set)) else [raw_sup] if raw_sup is not None else []
            sup_levels = []
            for s in sup_items:
                try:
                    dec_s = Decimal(str(s))
                    if dec_s < candidate.spot_price:
                        sup_levels.append(dec_s)
                except Exception:
                    pass
            if sup_levels:
                dist_to_floor = min(candidate.spot_price - lvl for lvl in sup_levels)
                if dist_to_floor < (atr_val * Decimal("0.25")):
                    return GateResult(passed=False, gate_name="MarketStructureGate", reason_code=f"BLOCKED_BY_SUPPORT_{float(dist_to_floor):.1f}pts")

        return GateResult(passed=True, gate_name="MarketStructureGate")


class TriggerIntegrityGate:
    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> GateResult:
        gate = check_trigger_integrity(
            underlying=candidate.underlying,
            strategy=candidate.strategy,
            direction=candidate.direction,
            spot_price=candidate.spot_price,
            entry_min=candidate.entry_min,
            entry_max=candidate.entry_max,
            trigger=candidate.trigger,
            stop_loss=candidate.stop_loss,
            target_1=candidate.target_1,
            target_2=candidate.target_2,
            risk_points=candidate.risk_points,
            risk_reward_t1=candidate.risk_reward_t1,
            risk_reward_t2=candidate.risk_reward_t2,
            is_scalp=getattr(candidate, "is_scalp", False),
            timeframe=getattr(candidate, "timeframe", "5M"),
        )
        if not gate.passed:
            return GateResult(passed=False, gate_name="TriggerIntegrityGate", reason_code=gate.reason_code, message=gate.message)
        return GateResult(passed=True, gate_name="TriggerIntegrityGate")


class OptionViabilityGate:
    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> GateResult:
        if candidate.path_simulation and not candidate.path_simulation.get("is_economically_viable", True):
            viab_reasons = candidate.path_simulation.get("viability_rationale") or ["OPTION_NOT_ECONOMICALLY_VIABLE"]
            rejection_lbl = viab_reasons[0][:40].replace(" ", "_").upper()
            return GateResult(passed=False, gate_name="OptionViabilityGate", reason_code=rejection_lbl)
        return GateResult(passed=True, gate_name="OptionViabilityGate")


class GateChain:
    """Evaluates candidates through an ordered chain of gates."""
    def __init__(self, gates: list[Gate] | None = None):
        self.gates: list[Gate] = gates or [
            KillSwitchGate(),
            FeedCircuitGate(),
            FNOIntegrityGate(),
            DeskConcurrencyGate(),
            PortfolioConcurrencyGate(),
            CrossDeskArbiterGate(),
            RSIGate(),
            MarketStructureGate(),
            TriggerIntegrityGate(),
            OptionViabilityGate(),
        ]

    def evaluate(self, candidate: SignalCandidate, **kwargs: Any) -> tuple[bool, list[GateResult]]:
        results = []
        for gate in self.gates:
            res = gate.evaluate(candidate, **kwargs)
            results.append(res)
            if not res.passed:
                return False, results
        return True, results
