"""
Deterministic Trade Validator — §2, §7, §21

Single validator, shared by both AI paths (not duplicated per-path logic).
Pure function, no I/O. Must complete in <10ms p95.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Literal
import structlog

from app.ai.schemas import (
    AISignal,
    Decision,
    Regime,
    ValidationStatus,
    ExecutionDecision,
    RejectionReason,
    LatencyBreakdown,
)

logger = structlog.get_logger()

MIN_RISK_REWARD = 1.5
DEFAULT_CONFIDENCE_THRESHOLD = 60
DEFAULT_MAX_POSITION_SIZE = 100
DEFAULT_MAX_DAILY_LOSS = 50000.0


class DeterministicTradeValidator:
    """
    Unified deterministic validator for both AI paths.

    Per §7: Single validator, shared by both paths.
    Per §2: Pure function, no I/O. Must complete in <10ms p95.
    """

    def validate(
        self,
        signal: AISignal,
        market_state: dict,
        risk_state: dict,
        config: Optional[dict] = None,
    ) -> ExecutionDecision:
        """
        Deterministic validation of AI signal against market and risk state.

        Args:
            signal: Validated AI signal from output validator
            market_state: Current market state dict with keys:
                - is_market_open: bool
                - is_trading_day: bool
                - data_fresh: bool
                - current_price: float
                - spread_pct: float
                - max_spread_pct: float
                - circuit_breaker: bool
                - kill_switch: bool
                - symbol: str
                - existing_position: dict (optional)
            risk_state: Current risk state dict with keys:
                - capital_available: float
                - margin_available: float
                - position_size: int
                - daily_loss: float
                - daily_loss_limit: float
                - max_position_size: int
                - existing_exposure: dict
            config: Optional config overrides

        Returns:
            ExecutionDecision with PASS or REJECT + reason code
        """
        cfg = config or {}

        if signal.decision == Decision.NO_TRADE:
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.INVALID_SIGNAL,
                reason_detail="Signal decision is NO_TRADE",
                signal_id=signal.signal_id,
            )

        if err := self._validate_market_hours(market_state):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.MARKET_CLOSED,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_trading_day(market_state):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.MARKET_CLOSED,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_stale_data(market_state):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.STALE_DATA,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_price_sanity(signal, market_state):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.INVALID_STOP_TARGET,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_max_spread(signal, market_state, cfg):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.SPREAD_TOO_WIDE,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_stop_validity(signal):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.INVALID_STOP_TARGET,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_risk_reward(signal, cfg):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.RISK_VIOLATION,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_max_position_size(signal, risk_state, cfg):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.POSITION_SIZE_EXCEEDED,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_max_daily_loss(signal, risk_state, cfg):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.MAX_DAILY_LOSS_HIT,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_existing_exposure(signal, risk_state):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.RISK_VIOLATION,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_duplicate_signal(signal, market_state):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.DUPLICATE_SIGNAL,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_position_limits(signal, risk_state):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.RISK_VIOLATION,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_circuit_breaker(market_state):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.CIRCUIT_BREAKER,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_kill_switch(market_state):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.KILL_SWITCH,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_confidence_threshold(signal, cfg):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.RISK_VIOLATION,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_regime(signal):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.UNKNOWN_REGIME,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        if err := self._validate_signal_expiry(signal):
            return ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.EXPIRED_SIGNAL,
                reason_detail=err,
                signal_id=signal.signal_id,
            )

        return ExecutionDecision(
            decision="PASS",
            signal_id=signal.signal_id,
            order_request={
                "signal_id": signal.signal_id,
                "symbol": signal.symbol,
                "side": "BUY" if signal.decision == Decision.LONG else "SELL",
                "entry": signal.entry,
                "stop_loss": signal.stop_loss,
                "target": signal.target,
                "quantity": risk_state.get("calculated_quantity", 0),
            },
        )

    def _validate_market_hours(self, market_state: dict) -> Optional[str]:
        if not market_state.get("is_market_open", True):
            return "Market is closed"
        return None

    def _validate_trading_day(self, market_state: dict) -> Optional[str]:
        if not market_state.get("is_trading_day", True):
            return "Not a trading day"
        return None

    def _validate_stale_data(self, market_state: dict) -> Optional[str]:
        if not market_state.get("data_fresh", True):
            return "Market data is stale"
        return None

    def _validate_price_sanity(self, signal: AISignal, market_state: dict) -> Optional[str]:
        current_price = market_state.get("current_price", 0)
        if current_price <= 0:
            return f"Invalid current price: {current_price}"
        entry = signal.entry
        if entry <= 0:
            return f"Invalid entry price: {entry}"
        deviation_pct = abs(entry - current_price) / current_price * 100
        max_deviation = market_state.get("max_price_deviation_pct", 5.0)
        if deviation_pct > max_deviation:
            return f"Entry price deviation {deviation_pct:.2f}% exceeds max {max_deviation}%"
        return None

    def _validate_max_spread(self, signal: AISignal, market_state: dict, config: dict) -> Optional[str]:
        spread_pct = market_state.get("spread_pct", 0)
        max_spread = config.get("max_spread_pct", market_state.get("max_spread_pct", 0.5))
        if spread_pct > max_spread:
            return f"Spread {spread_pct:.3f}% exceeds max {max_spread}%"
        return None

    def _validate_stop_validity(self, signal: AISignal) -> Optional[str]:
        entry = signal.entry
        stop = signal.stop_loss
        target = signal.target

        if signal.decision == Decision.LONG:
            if stop >= entry:
                return f"LONG: stop_loss ({stop}) must be < entry ({entry})"
            if target <= entry:
                return f"LONG: target ({target}) must be > entry ({entry})"
        elif signal.decision == Decision.SHORT:
            if stop <= entry:
                return f"SHORT: stop_loss ({stop}) must be > entry ({entry})"
            if target >= entry:
                return f"SHORT: target ({target}) must be < entry ({entry})"
        return None

    def _validate_risk_reward(self, signal: AISignal, config: dict) -> Optional[str]:
        entry = signal.entry
        stop = signal.stop_loss
        target = signal.target

        risk = abs(entry - stop)
        reward = abs(target - entry)
        if risk <= 0:
            return "Risk is zero or negative"
        rr = reward / risk
        min_rr = config.get("min_risk_reward", MIN_RISK_REWARD)
        if rr < min_rr:
            return f"Risk/reward {rr:.2f} < minimum {min_rr}"
        return None

    def _validate_max_position_size(self, signal: AISignal, risk_state: dict, config: dict) -> Optional[str]:
        position_size = risk_state.get("position_size", 0)
        max_size = config.get("max_position_size", risk_state.get("max_position_size", DEFAULT_MAX_POSITION_SIZE))
        if position_size >= max_size:
            return f"Position size {position_size} >= max {max_size}"
        return None

    def _validate_max_daily_loss(self, signal: AISignal, risk_state: dict, config: dict) -> Optional[str]:
        daily_loss = risk_state.get("daily_loss", 0)
        daily_limit = config.get("daily_loss_limit", risk_state.get("daily_loss_limit", DEFAULT_MAX_DAILY_LOSS))
        if daily_loss <= -daily_limit:
            return f"Daily loss {daily_loss} exceeds limit {daily_limit}"
        return None

    def _validate_existing_exposure(self, signal: AISignal, risk_state: dict) -> Optional[str]:
        existing = risk_state.get("existing_exposure", {})
        symbol_exposure = existing.get(signal.symbol, 0)
        if symbol_exposure > 0 and signal.decision != Decision.NO_TRADE:
            same_direction = risk_state.get("existing_position_direction") == signal.decision.value
            if same_direction:
                return f"Already have {signal.decision.value} position on {signal.symbol}"
        return None

    def _validate_duplicate_signal(self, signal: AISignal, market_state: dict) -> Optional[str]:
        last_signal = market_state.get("last_signal")
        if last_signal is None:
            return None
        if signal.signal_id == last_signal.get("signal_id"):
            return "Duplicate signal: same signal_id"
        time_bucket = signal.timestamp.strftime("%Y%m%d%H%M")
        last_bucket = last_signal.get("time_bucket")
        if last_bucket == time_bucket:
            same_setup = (
                signal.symbol == last_signal.get("symbol")
                and signal.decision == last_signal.get("decision")
                and signal.setup_type == last_signal.get("setup_type")
            )
            if same_setup:
                return "Duplicate signal: same setup in time bucket"
        return None

    def _validate_position_limits(self, signal: AISignal, risk_state: dict) -> Optional[str]:
        return None

    def _validate_circuit_breaker(self, market_state: dict) -> Optional[str]:
        if market_state.get("circuit_breaker", False):
            return "Circuit breaker is active"
        return None

    def _validate_kill_switch(self, market_state: dict) -> Optional[str]:
        if market_state.get("kill_switch", False):
            return "Kill switch is active"
        return None

    def _validate_confidence_threshold(self, signal: AISignal, config: dict) -> Optional[str]:
        threshold = config.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
        calibrated = signal.calibrated_confidence or signal.raw_confidence
        if calibrated < threshold:
            return f"Calibrated confidence {calibrated} < threshold {threshold}"
        return None

    def _validate_regime(self, signal: AISignal) -> Optional[str]:
        if signal.regime == Regime.UNKNOWN and signal.decision != Decision.NO_TRADE:
            return "UNKNOWN regime with non-NO_TRADE decision"
        return None

    def _validate_signal_expiry(self, signal: AISignal) -> Optional[str]:
        now = datetime.now(timezone.utc)
        if signal.expires_at and now > signal.expires_at:
            return f"Signal expired at {signal.expires_at.isoformat()}"
        return None


deterministic_trade_validator = DeterministicTradeValidator()
