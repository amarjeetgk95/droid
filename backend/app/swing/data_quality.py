"""
Data Quality Firewall and Point-in-Time Integrity Gate (v5.0).
Guarantees:
  1. No unfinalized daily candles are treated as complete history (§3).
  2. Strict OHLC relationship validation (§6).
  3. De-duplication and chronological ordering.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field


class DataQualityResult(BaseModel):
    is_valid: bool
    status: Literal["VALID", "DEGRADED", "STALE", "INVALID"]
    cleaned_candles: list[dict[str, Any]] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    sample_count: int = 0
    start_timestamp: int | None = None
    end_timestamp: int | None = None


def validate_and_clean_daily_candles(
    raw_candles: list[dict[str, Any] | Any],
    min_required_bars: int = 30,
    ensure_finalized_only: bool = True,
    current_time_utc: datetime | None = None,
) -> DataQualityResult:
    """
    Validates a sequence of daily candles for swing setup analysis.
    - Strips invalid OHLC values.
    - Ensures sorted order.
    - Discards incomplete current-day bars if running before 15:30 IST.
    """
    reasons: list[str] = []
    if not raw_candles:
        return DataQualityResult(
            is_valid=False,
            status="INVALID",
            reasons=["No candle data provided."],
        )

    now_utc = current_time_utc or datetime.now(timezone.utc)
    parsed: list[dict[str, Any]] = []

    for idx, c in enumerate(raw_candles):
        # Support dict or NormalizedCandle pydantic object
        if hasattr(c, "model_dump"):
            d = c.model_dump()
        elif isinstance(c, dict):
            d = dict(c)
        else:
            d = {
                "timestamp": getattr(c, "timestamp", None),
                "open": getattr(c, "open", 0.0),
                "high": getattr(c, "high", 0.0),
                "low": getattr(c, "low", 0.0),
                "close": getattr(c, "close", 0.0),
                "volume": getattr(c, "volume", 0),
            }

        ts = d.get("timestamp")
        if isinstance(ts, (int, float)):
            ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, str):
            try:
                ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                ts_dt = now_utc
        elif isinstance(ts, datetime):
            ts_dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        else:
            ts_dt = now_utc

        d["timestamp_dt"] = ts_dt
        d["timestamp_epoch"] = int(ts_dt.timestamp())

        # Validate OHLC logic
        o = float(d.get("open", 0.0) or 0.0)
        h = float(d.get("high", 0.0) or 0.0)
        l = float(d.get("low", 0.0) or 0.0)
        c_price = float(d.get("close", 0.0) or 0.0)
        v = int(d.get("volume", 0) or 0)

        if o <= 0 or h <= 0 or l <= 0 or c_price <= 0:
            continue
        if h < l or h < o or h < c_price or l > o or l > c_price:
            continue

        d["open"] = o
        d["high"] = h
        d["low"] = l
        d["close"] = c_price
        d["volume"] = max(0, v)
        parsed.append(d)

    if not parsed:
        return DataQualityResult(
            is_valid=False,
            status="INVALID",
            reasons=["All candles failed basic OHLC validation."],
        )

    # Sort chronologically & deduplicate by epoch
    parsed.sort(key=lambda x: x["timestamp_epoch"])
    deduped: list[dict[str, Any]] = []
    seen_epochs = set()
    for item in parsed:
        ep = item["timestamp_epoch"]
        if ep not in seen_epochs:
            seen_epochs.add(ep)
            deduped.append(item)

    # Point-in-time check: if the latest bar is from today and market is still open (< 15:30 IST)
    # in UTC: 15:30 IST = 10:00 UTC.
    if ensure_finalized_only and deduped:
        latest = deduped[-1]
        latest_dt = latest["timestamp_dt"]
        if latest_dt.date() == now_utc.date():
            # If current UTC time is before 10:00 UTC (15:30 IST), today's candle is unfinalized!
            if now_utc.hour < 10:
                reasons.append("Today's unfinalized daily candle was excluded to prevent lookahead bias.")
                deduped.pop()

    count = len(deduped)
    if count < min_required_bars:
        return DataQualityResult(
            is_valid=False,
            status="INCOMPLETE",
            cleaned_candles=deduped,
            reasons=[f"Candle count {count} is below minimum requirement of {min_required_bars} bars."],
            sample_count=count,
        )

    status = "VALID"
    if count < 150:
        status = "DEGRADED"
        reasons.append(f"Candle count {count} is sufficient for 20/50 MA but insufficient for 200 SMA.")

    return DataQualityResult(
        is_valid=True,
        status=status,
        cleaned_candles=deduped,
        reasons=reasons,
        sample_count=count,
        start_timestamp=deduped[0]["timestamp_epoch"] if deduped else None,
        end_timestamp=deduped[-1]["timestamp_epoch"] if deduped else None,
    )
