from datetime import datetime
from typing import NamedTuple, Any
from app.models.contracts import TickEvent
from app.models.market import NormalizedCandle
import structlog

logger = structlog.get_logger()


class ValidationResult(NamedTuple):
    is_valid: bool
    quarantine: bool
    reason: str | None
    gap_detected: bool
    sanitized: Any | None


class DataQualityEngine:
    """Data Quality Validation and Gap Detection Engine.
    
    Adheres strictly to Section 14 (Gap Detection) and Section 75 (Data Quality Validation).
    """

    def __init__(self):
        self._last_sequences: dict[str, int] = {}
        self._last_timestamps: dict[str, datetime] = {}
        self._quarantined_count: int = 0
        self._dropped_count: int = 0
        self._gap_count: int = 0

    def validate_tick(self, tick: TickEvent) -> ValidationResult:
        """Validate an incoming high-frequency tick event."""
        symbol = tick.symbol

        # 1. Price checks
        if tick.ltp <= 0.0:
            self._quarantined_count += 1
            return ValidationResult(
                is_valid=False,
                quarantine=True,
                reason=f"Invalid non-positive LTP: {tick.ltp}",
                gap_detected=False,
                sanitized=None,
            )

        # 2. Open Interest checks
        if tick.open_interest is not None and tick.open_interest < 0:
            self._quarantined_count += 1
            return ValidationResult(
                is_valid=False,
                quarantine=True,
                reason=f"Invalid negative Open Interest: {tick.open_interest}",
                gap_detected=False,
                sanitized=None,
            )

        # 3. Bid-Ask Inversion check
        if tick.bid is not None and tick.ask is not None:
            if tick.bid > 0 and tick.ask > 0 and tick.bid > tick.ask:
                self._quarantined_count += 1
                return ValidationResult(
                    is_valid=False,
                    quarantine=True,
                    reason=f"Inverted orderbook: bid ({tick.bid}) > ask ({tick.ask})",
                    gap_detected=False,
                    sanitized=None,
                )

        # 4. Volume check
        if tick.volume < 0:
            self._quarantined_count += 1
            return ValidationResult(
                is_valid=False,
                quarantine=True,
                reason=f"Negative volume: {tick.volume}",
                gap_detected=False,
                sanitized=None,
            )

        # 5. Sequence Gap & Out-of-Order Check
        gap_detected = False
        if tick.sequence_number is not None:
            last_seq = self._last_sequences.get(symbol)
            if last_seq is not None:
                expected_seq = last_seq + 1
                if tick.sequence_number > expected_seq:
                    gap_detected = True
                    self._gap_count += 1
                    logger.warning(
                        "sequence_gap_detected",
                        symbol=symbol,
                        expected=expected_seq,
                        received=tick.sequence_number,
                    )
                elif tick.sequence_number < last_seq:
                    # Out of order packet
                    self._dropped_count += 1
                    return ValidationResult(
                        is_valid=False,
                        quarantine=False,
                        reason=f"Out of order sequence: {tick.sequence_number} < {last_seq}",
                        gap_detected=False,
                        sanitized=None,
                    )
            self._last_sequences[symbol] = tick.sequence_number

        # 6. Timestamp sanity check
        last_ts = self._last_timestamps.get(symbol)
        if last_ts and tick.timestamp < last_ts:
            # Out of order timestamp
            self._dropped_count += 1
            return ValidationResult(
                is_valid=False,
                quarantine=False,
                reason=f"Out of order timestamp: {tick.timestamp} < {last_ts}",
                gap_detected=False,
                sanitized=None,
            )
        self._last_timestamps[symbol] = tick.timestamp

        return ValidationResult(
            is_valid=True,
            quarantine=False,
            reason=None,
            gap_detected=gap_detected,
            sanitized=tick,
        )

    def validate_candle(self, candle: NormalizedCandle) -> ValidationResult:
        """Validate historical or completed candle."""
        if candle.high < max(candle.open, candle.close):
            return ValidationResult(
                is_valid=False,
                quarantine=True,
                reason=f"High {candle.high} < max(Open={candle.open}, Close={candle.close})",
                gap_detected=False,
                sanitized=None,
            )
        if candle.low > min(candle.open, candle.close):
            return ValidationResult(
                is_valid=False,
                quarantine=True,
                reason=f"Low {candle.low} > min(Open={candle.open}, Close={candle.close})",
                gap_detected=False,
                sanitized=None,
            )
        if candle.volume < 0:
            return ValidationResult(
                is_valid=False,
                quarantine=True,
                reason=f"Negative candle volume: {candle.volume}",
                gap_detected=False,
                sanitized=None,
            )
        return ValidationResult(
            is_valid=True,
            quarantine=False,
            reason=None,
            gap_detected=False,
            sanitized=candle,
        )

    def get_metrics(self) -> dict:
        """Return data quality engine telemetry."""
        return {
            "quarantined_events": self._quarantined_count,
            "dropped_events": self._dropped_count,
            "detected_gaps": self._gap_count,
        }


data_quality_engine = DataQualityEngine()
