"""Data Quality Firewall for Market Data (Tier 0).

Ground truth validation of historical and live candle streams:
- Monotonic timestamp ordering
- Duplicate detection & deduplication
- OHLC price geometric validity (low <= open, close <= high)
- Price jump anomaly detection
- Trading session boundary validation (09:15 - 15:30 IST)
- Intraday gap detection & missing bar accounting
- Data Quality Score (0 - 100) and failure gating
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone, timedelta
from typing import Literal, Optional, List, Dict, Any
import numpy as np
import polars as pl
import structlog

logger = structlog.get_logger(__name__)

# Indian Market Session (IST = UTC + 5:30)
IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TIMEZONE = timezone(IST_OFFSET)

SESSION_START_IST = time(9, 15)
SESSION_END_IST = time(15, 30)

DataQualityStatus = Literal["PASSED", "DEGRADED", "FAILED"]

#: Minimum sessions before gap-based signals are considered meaningful.
MIN_SESSIONS_FOR_SIMULATION_SCREEN = 20

#: Signals required to call a series generated when provenance is already
#: suspect (or absent).
MIN_SIMULATION_SIGNALS = 2

#: Signals required to *override* an admissible real-broker provenance. Refusing
#: real data is as damaging as accepting generated data, and one signal —
#: ``open_equals_prior_close`` — is expected for a continuous index series, where
#: the close of one minute is the open of the next. Confirming suspicion is cheap;
#: contradicting a broker's provenance should not be.
STRONG_SIMULATION_SIGNALS = 3

#: IST offset in minutes, for session grouping in the simulation screen.
IST_OFFSET_MINUTES = 5 * 60 + 30


@dataclass
class SimulationScreen:
    """Statistical fingerprints of a *generated* (non-market) price series.

    ``inspect_and_clean`` measures hygiene: ordering, duplicates, OHLC geometry,
    gaps, jumps. A perfect simulator scores 100.0 on all of it, because a
    simulator has none of those defects. This screen measures authenticity
    instead, and is a separate axis on purpose.

    Individually each signal is weak. Two or more together across >= 20 sessions
    is not a market: real index candles have gaps, gap opens, fat tails, and
    integer volume, and they produce none of these signals.

    Caveat carried deliberately: ``open_equals_prior_close`` is *expected* for a
    continuous index series, so on its own it is weak evidence and callers that
    already hold admissible provenance should require
    :data:`STRONG_SIMULATION_SIGNALS` before overriding it.
    """

    sessions: int
    gap_free_sessions: int
    open_equals_prior_close_frac: float
    excess_kurtosis: float
    zero_wick_frac: float
    integer_volume_frac: float
    signals: list[str] = field(default_factory=list)

    @property
    def looks_simulated(self) -> bool:
        return self.is_simulated_with(MIN_SIMULATION_SIGNALS)

    def is_simulated_with(self, min_signals: int) -> bool:
        """Whether at least ``min_signals`` signals fired."""
        return len(self.signals) >= int(min_signals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": self.sessions,
            "gap_free_sessions": self.gap_free_sessions,
            "open_equals_prior_close_frac": round(self.open_equals_prior_close_frac, 6),
            "excess_kurtosis": round(self.excess_kurtosis, 6),
            "zero_wick_frac": round(self.zero_wick_frac, 6),
            "integer_volume_frac": round(self.integer_volume_frac, 6),
            "signals": self.signals,
            "looks_simulated": self.looks_simulated,
        }


@dataclass
class DataQualityReport:
    status: DataQualityStatus
    score: float
    total_input_bars: int
    valid_bars: int
    duplicates_removed: int
    invalid_ohlc_bars: int
    anomalous_jumps: int
    missing_bars_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": round(self.score, 2),
            "total_input_bars": self.total_input_bars,
            "valid_bars": self.valid_bars,
            "duplicates_removed": self.duplicates_removed,
            "invalid_ohlc_bars": self.invalid_ohlc_bars,
            "anomalous_jumps": self.anomalous_jumps,
            "missing_bars_count": self.missing_bars_count,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class DataQualityFirewall:
    """Validates, sanitizes, and scores historical and live OHLCV datasets."""

    def __init__(
        self,
        max_jump_pct: float = 0.08,  # 8% 1-minute jump threshold for index
        session_only: bool = True,
        strict_monotonic: bool = True,
    ):
        self.max_jump_pct = max_jump_pct
        self.session_only = session_only
        self.strict_monotonic = strict_monotonic

    def inspect_and_clean(
        self,
        df: pl.DataFrame,
        instrument: str = "SENSEX",
    ) -> tuple[pl.DataFrame, DataQualityReport]:
        """Validate and clean OHLCV Polars DataFrame.
        
        Expected columns: timestamp (datetime or int epoch ms/s), open, high, low, close, volume.
        Returns cleaned DataFrame and DataQualityReport.
        """
        errors: list[str] = []
        warnings: list[str] = []
        total_input = len(df)

        if total_input == 0:
            return df, DataQualityReport(
                status="FAILED",
                score=0.0,
                total_input_bars=0,
                valid_bars=0,
                duplicates_removed=0,
                invalid_ohlc_bars=0,
                anomalous_jumps=0,
                missing_bars_count=0,
                errors=["Dataset is completely empty."],
            )

        # 1. Normalize schema and column names (lowercase)
        rename_map = {col: col.lower().strip() for col in df.columns}
        df = df.rename(rename_map)

        required_cols = {"timestamp", "open", "high", "low", "close"}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            errors.append(f"Missing required columns: {missing_cols}")
            return df, DataQualityReport(
                status="FAILED",
                score=0.0,
                total_input_bars=total_input,
                valid_bars=0,
                duplicates_removed=0,
                invalid_ohlc_bars=0,
                anomalous_jumps=0,
                missing_bars_count=0,
                errors=errors,
            )

        if "volume" not in df.columns:
            df = df.with_columns(pl.lit(0.0).alias("volume"))

        # Cast to standard types
        try:
            # Ensure timestamp is datetime (UTC)
            if df["timestamp"].dtype in (pl.Int64, pl.Int32, pl.Float64):
                # Check if epoch in seconds vs milliseconds
                first_val = df["timestamp"][0]
                if first_val > 1e11:  # ms
                    df = df.with_columns(pl.from_epoch(pl.col("timestamp"), time_unit="ms").alias("timestamp"))
                else:  # seconds
                    df = df.with_columns(pl.from_epoch(pl.col("timestamp"), time_unit="s").alias("timestamp"))
            elif df["timestamp"].dtype == pl.String:
                df = df.with_columns(pl.col("timestamp").str.to_datetime().alias("timestamp"))
            
            # Cast prices and volume to float64
            df = df.with_columns([
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
            ])
        except Exception as e:
            errors.append(f"Type casting error: {e}")
            return df, DataQualityReport(
                status="FAILED",
                score=0.0,
                total_input_bars=total_input,
                valid_bars=0,
                duplicates_removed=0,
                invalid_ohlc_bars=0,
                anomalous_jumps=0,
                missing_bars_count=0,
                errors=errors,
            )

        # 2. Deduplicate timestamps (keep first)
        pre_dedup = len(df)
        df = df.unique(subset=["timestamp"], keep="first")
        duplicates_removed = pre_dedup - len(df)
        if duplicates_removed > 0:
            warnings.append(f"Deduplicated {duplicates_removed} repeated timestamp bars.")

        # 3. Sort strictly by timestamp
        df = df.sort("timestamp")

        # 4. Filter to market session (09:15 to 15:30 IST) if requested
        if self.session_only:
            # Convert timestamp to IST for time check
            # pl.col("timestamp").dt.convert_time_zone("Asia/Kolkata")
            # If naive, assume UTC or apply offset
            df = df.with_columns([
                (pl.col("timestamp") + pl.duration(hours=5, minutes=30)).alias("timestamp_ist")
            ])
            
            # Cast hour and minute to Int32 to prevent Int8 overflow (e.g. 9 * 60 = 540 overflows Int8)
            hour_expr = pl.col("timestamp_ist").dt.hour().cast(pl.Int32)
            min_expr = pl.col("timestamp_ist").dt.minute().cast(pl.Int32)
            total_minutes = hour_expr * 60 + min_expr

            session_mask = (total_minutes >= (9 * 60 + 15)) & (total_minutes <= (15 * 60 + 30))
            
            # Weekday filter (Monday=1 ... Friday=5)
            weekday_mask = pl.col("timestamp_ist").dt.weekday() <= 5
            
            df = df.filter(session_mask & weekday_mask)
            df = df.drop("timestamp_ist")

        # 5. Validate OHLC geometric coherence:
        # low <= min(open, close) and high >= max(open, close) and low > 0 and high >= low
        ohlc_valid_mask = (
            (pl.col("low") <= pl.col("open")) &
            (pl.col("low") <= pl.col("close")) &
            (pl.col("high") >= pl.col("open")) &
            (pl.col("high") >= pl.col("close")) &
            (pl.col("high") >= pl.col("low")) &
            (pl.col("low") > 0.0)
        )
        invalid_ohlc_bars = len(df.filter(~ohlc_valid_mask))
        if invalid_ohlc_bars > 0:
            errors.append(f"Found {invalid_ohlc_bars} bars with invalid OHLC geometry (e.g. low > open or high < close).")
            df = df.filter(ohlc_valid_mask)

        # 6. Check for anomalous price jumps (close to next open or close to close)
        if len(df) > 1:
            df = df.with_columns([
                ((pl.col("close") - pl.col("close").shift(1)).abs() / pl.col("close").shift(1)).alias("jump_ratio")
            ])
            anomalous_mask = pl.col("jump_ratio") > self.max_jump_pct
            anomalous_jumps = len(df.filter(anomalous_mask))
            if anomalous_jumps > 0:
                warnings.append(f"Detected {anomalous_jumps} bars with price jump > {self.max_jump_pct*100:.1f}%.")
            df = df.drop("jump_ratio")
        else:
            anomalous_jumps = 0

        # 7. Calculate missing bars count in intraday sequence (for 1m timeframe, expected delta is 1 min)
        missing_bars_count = 0
        if len(df) > 1:
            diffs = df.select(
                (pl.col("timestamp") - pl.col("timestamp").shift(1)).dt.total_seconds().alias("diff_s")
            )["diff_s"].drop_nulls()
            
            # Expected 1m is 60s. For jumps between 60s and session gap (e.g. 120s to 300s during market hours)
            # Diffs between 61s and 1800s (30m) within same day count as missing bars
            missing_bars_series = diffs.filter((diffs > 60) & (diffs <= 18000))
            if len(missing_bars_series) > 0:
                missing_bars_count = int((missing_bars_series / 60 - 1).sum())
                if missing_bars_count > 0:
                    warnings.append(f"Identified approximately {missing_bars_count} missing 1-minute bars within trading sessions.")

        valid_bars = len(df)
        
        # Calculate quality score
        score = 100.0
        score -= min(30.0, (duplicates_removed / max(1, total_input)) * 100.0 * 2.0)
        score -= min(40.0, (invalid_ohlc_bars / max(1, total_input)) * 100.0 * 10.0)
        score -= min(20.0, (anomalous_jumps / max(1, total_input)) * 100.0 * 5.0)
        score -= min(20.0, (missing_bars_count / max(1, total_input)) * 100.0 * 1.0)
        score = max(0.0, round(score, 2))

        status: DataQualityStatus = "PASSED"
        if score < 70.0 or invalid_ohlc_bars > (0.01 * total_input):
            status = "FAILED"
        elif score < 95.0 or missing_bars_count > 10 or anomalous_jumps > 0:
            status = "DEGRADED"

        report = DataQualityReport(
            status=status,
            score=score,
            total_input_bars=total_input,
            valid_bars=valid_bars,
            duplicates_removed=duplicates_removed,
            invalid_ohlc_bars=invalid_ohlc_bars,
            anomalous_jumps=anomalous_jumps,
            missing_bars_count=missing_bars_count,
            errors=errors,
            warnings=warnings,
        )

        return df, report

    def screen_simulation_signals(self, df: pl.DataFrame) -> SimulationScreen:
        """Detect generated/simulated candle data from its statistical signature.

        Returns a :class:`SimulationScreen`. Never mutates ``df``. Raises
        ``ValueError`` only for a structurally unusable frame (missing columns or
        too few bars) — an unusable frame is not a clean frame, and this method
        must never report "looks real" for data it could not examine.
        """
        if len(df) < 2:
            raise ValueError(
                f"Simulation screen needs >= 2 bars to examine, got {len(df)}"
            )

        frame = df.rename({col: col.lower().strip() for col in df.columns})
        required = {"timestamp", "open", "high", "low", "close"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Simulation screen missing required columns: {sorted(missing)}")
        if "volume" not in frame.columns:
            frame = frame.with_columns(pl.lit(0.0).alias("volume"))

        frame = frame.sort("timestamp")

        ts = np.asarray(frame["timestamp"].to_numpy())
        if ts.dtype.kind != "M":
            raise ValueError(
                f"Simulation screen requires a datetime timestamp column, got {ts.dtype}"
            )
        o = frame["open"].cast(pl.Float64).to_numpy()
        h = frame["high"].cast(pl.Float64).to_numpy()
        lo = frame["low"].cast(pl.Float64).to_numpy()
        c = frame["close"].cast(pl.Float64).to_numpy()
        v = frame["volume"].cast(pl.Float64).to_numpy()

        # Session key in IST, so a single trading day groups together.
        ts_ist = ts + np.timedelta64(IST_OFFSET_MINUTES, "m")
        session_days = ts_ist.astype("datetime64[D]")
        _unique_days, day_codes = np.unique(session_days, return_inverse=True)
        sessions = int(_unique_days.size)

        # Only intra-session transitions carry signal; the overnight gap is expected.
        same_session = session_days[1:] == session_days[:-1]
        delta_seconds = (ts[1:] - ts[:-1]) / np.timedelta64(1, "s")
        gaps = same_session & (np.abs(delta_seconds - 60.0) > 1e-6)

        gaps_per_session = np.bincount(day_codes[1:][gaps], minlength=sessions)
        gap_free_sessions = int((gaps_per_session == 0).sum())

        if same_session.any():
            prior_close = c[:-1][same_session]
            open_equals_prior_close_frac = float(
                np.isclose(o[1:][same_session], prior_close, rtol=0.0, atol=1e-8).mean()
            )
        else:
            open_equals_prior_close_frac = 0.0

        with np.errstate(divide="ignore", invalid="ignore"):
            log_ret = np.log(c / o)
        log_ret = log_ret[np.isfinite(log_ret)]
        if log_ret.size >= 2:
            centred = log_ret - log_ret.mean()
            variance = float((centred ** 2).mean())
            excess_kurtosis = (
                float((centred ** 4).mean() / variance ** 2) - 3.0 if variance > 0 else 0.0
            )
        else:
            excess_kurtosis = 0.0

        zero_wick = np.isclose(h, np.maximum(o, c), rtol=0.0, atol=1e-9) | np.isclose(
            lo, np.minimum(o, c), rtol=0.0, atol=1e-9
        )
        integer_volume_frac = float(np.isclose(v, np.round(v), rtol=0.0, atol=1e-9).mean())

        signals: list[str] = []
        if sessions >= MIN_SESSIONS_FOR_SIMULATION_SCREEN and gap_free_sessions >= MIN_SESSIONS_FOR_SIMULATION_SCREEN:
            signals.append("no_intraday_gaps")
        if open_equals_prior_close_frac > 0.90:
            signals.append("open_equals_prior_close")
        if excess_kurtosis < 0.5:
            signals.append("gaussian_returns")
        if float(zero_wick.mean()) < 0.001:
            signals.append("no_zero_wicks")
        if integer_volume_frac < 0.5:
            signals.append("non_integer_volume")

        return SimulationScreen(
            sessions=sessions,
            gap_free_sessions=gap_free_sessions,
            open_equals_prior_close_frac=open_equals_prior_close_frac,
            excess_kurtosis=excess_kurtosis,
            zero_wick_frac=float(zero_wick.mean()),
            integer_volume_frac=integer_volume_frac,
            signals=signals,
        )
