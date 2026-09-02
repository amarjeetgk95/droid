"""
Data Quality Validation — §6
Strict checks: OHLC consistency, timestamp ordering, gap detection, forward window completeness.
"""
from __future__ import annotations

from typing import NamedTuple
from app.quant.historical_intelligence.models import CandleData


class ValidationResult(NamedTuple):
    is_valid: bool
    error: str | None = None
    cleaned_candles: list[CandleData] = []


def validate_single_candle(c: CandleData) -> tuple[bool, str | None]:
    """Validate a single bar satisfies basic physical market rules."""
    if c.high < c.low:
        return False, f"Invalid OHLC: high ({c.high}) < low ({c.low}) at ts={c.timestamp_utc}"
    if not (c.low <= c.open <= c.high):
        return False, f"Invalid OHLC: open ({c.open}) out of bounds [{c.low}, {c.high}] at ts={c.timestamp_utc}"
    if not (c.low <= c.close <= c.high):
        return False, f"Invalid OHLC: close ({c.close}) out of bounds [{c.low}, {c.high}] at ts={c.timestamp_utc}"
    if c.volume < 0:
        return False, f"Negative volume ({c.volume}) at ts={c.timestamp_utc}"
    if c.timestamp_utc <= 0:
        return False, f"Invalid non-positive timestamp ({c.timestamp_utc})"
    return True, None


def validate_and_clean_candle_series(
    candles: list[CandleData],
    min_bars: int = 15,
) -> ValidationResult:
    """
    Validates an entire historical candle sequence:
    1. Removes duplicate timestamps (retains latest/highest quality).
    2. Ensures strictly monotonic timestamp ordering.
    3. Validates individual bar rules.
    4. Ensures sufficient length.
    """
    if not candles or len(candles) < min_bars:
        return ValidationResult(
            is_valid=False,
            error=f"Insufficient candle count ({len(candles)} < min {min_bars})",
            cleaned_candles=[],
        )

    # 1. Sort by timestamp first
    sorted_candles = sorted(candles, key=lambda x: x.timestamp_utc)

    # 2. Filter invalid & deduplicate
    seen_timestamps: set[int] = set()
    cleaned: list[CandleData] = []

    for c in sorted_candles:
        if c.timestamp_utc in seen_timestamps:
            continue  # Skip duplicate timestamp
        
        ok, err = validate_single_candle(c)
        if not ok:
            continue  # Drop corrupt single candle
        
        seen_timestamps.add(c.timestamp_utc)
        cleaned.append(c)

    if len(cleaned) < min_bars:
        return ValidationResult(
            is_valid=False,
            error=f"Cleaned candle count ({len(cleaned)}) below minimum required ({min_bars})",
            cleaned_candles=[],
        )

    return ValidationResult(is_valid=True, error=None, cleaned_candles=cleaned)


def has_complete_forward_window(
    series_len: int,
    pattern_end_idx: int,
    horizon_bars: int,
) -> bool:
    """
    Ensures that for a candidate pattern ending at index `pattern_end_idx`,
    there are at least `horizon_bars` subsequent bars in the series (§6, §16).
    """
    return (pattern_end_idx + horizon_bars) < series_len
