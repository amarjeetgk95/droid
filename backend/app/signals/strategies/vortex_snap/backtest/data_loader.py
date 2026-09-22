"""
Historical Data Loader & Point-In-Time Pipeline (§34).

Provides:
- Parquet historical candle loading (SENSEX, NIFTY, BANKNIFTY)
- High-fidelity synthetic intraday session generator for deterministic research/testing
- Point-in-time session level computation (PDH, PDL, PDC, CDO, cumulative VWAP)
- Resampling 1m -> 5m strictly at bar close boundaries with zero look-ahead bias

DATA-SOURCE CONTRACT (strict real-data default):
- Live HUD paths MUST call load_candles_with_source(..., require_real_data=True).
  When no 1m parquet exists this raises FileNotFoundError (mapped to HTTP 503 by
  the API layer) — it must NEVER silently fall back to the seed-42 generator.
- generate_synthetic_session() is TEST / BACKTEST-ONLY. It is kept solely so the
  deterministic seed-42 session remains available to unit tests, ablation studies,
  and backtests that pass an explicit synthetic flag (allow_synthetic=True /
  require_real_data=False). It must not feed any live-trading or live-HUD path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import polars as pl
import structlog

from app.quant.data.provenance import assert_real_dataset, check_provenance
from app.signals.strategies.vortex_snap.types import Candle
from app.signals.strategies.vortex_snap.session import MarketSessionModel

logger = structlog.get_logger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[5]

_SYNTHETIC_NOTE = (
    "Simulated seed-42 intraday session (no real 1m parquet found). "
    "Levels and gauges do NOT reflect live prices."
)


@dataclass
class CandleSource:
    type: str                       # "parquet" | "synthetic" — storage form
    instrument: str
    path: Optional[str] = None
    #: True when the candles are not verifiable market data. Previously defined
    #: as "type == 'synthetic'", which is why a generated series persisted as
    #: parquet advertised itself as real. Widened to cover provenance failure:
    #:   is_simulated == (type == "synthetic" or not provenance_verified)
    is_simulated: bool = False
    note: str = ""
    #: True only when the dataset's provenance sidecar and statistical screen
    #: both passed. Defaults to False so an unexamined source never claims truth.
    provenance_verified: bool = False

    @property
    def is_real_market_data(self) -> bool:
        return self.provenance_verified and not self.is_simulated

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "instrument": self.instrument, "path": self.path,
                "is_simulated": self.is_simulated, "note": self.note,
                "provenance_verified": self.provenance_verified}


@dataclass
class HistoricalBarContext:
    """Point-in-time context for a single historical 1-minute bar."""
    timestamp_ms: int
    candle_1m: Candle
    history_1m: List[Candle]  # All 1m candles up to and including current
    candles_5m: List[Candle]  # Closed 5m candles strictly prior to/at current
    pdh: Optional[float] = None
    pdl: Optional[float] = None
    pdc: Optional[float] = None
    cdo: Optional[float] = None
    vwap: Optional[float] = None


class HistoricalDataLoader:
    """Manages loading, synthetic generation, and point-in-time feed iteration."""

    def __init__(self, raw_data_dir: Optional[Path | str] = None):
        if raw_data_dir is None:
            self.raw_data_dir = BACKEND_ROOT / "data" / "raw"
        else:
            resolved = Path(raw_data_dir)
            if not resolved.is_absolute():
                resolved = BACKEND_ROOT / resolved
            self.raw_data_dir = resolved
        # All lookup roots derive from raw_data_dir so an overridden root isolates
        # the loader from the repository's real data trees (tests rely on this).
        self._hist_data_root = self.raw_data_dir.parent / "historical" / "parquet"
        self._datasets_root = self.raw_data_dir.parent / "datasets"
        self.session_model = MarketSessionModel()

    def locate_parquet(self, instrument: str, timeframe: str = "1m") -> Optional[Path]:
        """Locate the parquet dataset for an instrument/timeframe, or None if absent."""
        clean_name = instrument.lower().replace(":", "_").replace(" ", "_").replace("-", "_")
        # Check the Historical Data Module path (data/historical/parquet/<instrument>/<timeframe>/candles_v1.parquet).
        hist_dir = self._hist_data_root / clean_name / timeframe
        if hist_dir.exists():
            v1_path = hist_dir / "candles_v1.parquet"
            if v1_path.exists():
                return v1_path
            # Check any candles_*.parquet
            candidates = list(hist_dir.glob("candles_*.parquet"))
            if candidates:
                return sorted(candidates)[-1]

        parquet_path = self.raw_data_dir / clean_name / f"{timeframe}.parquet"
        if parquet_path.exists():
            return parquet_path
        fallback = self._datasets_root / f"{instrument}_{timeframe}.parquet"
        if fallback.exists():
            return fallback
        return None

    def load_parquet(
        self,
        instrument: str,
        timeframe: str = "1m",
        require_real_data: bool = False,
    ) -> List[Candle]:
        """Load historical candles from parquet dataset.

        Args:
            instrument: e.g. 'SENSEX', 'NIFTY', 'BANKNIFTY'
            timeframe: e.g. '1m'
            require_real_data: verify provenance, not merely file presence. A
                parquet written from the seed-42 generator is still a parquet;
                file existence is not evidence of authenticity.

        Returns:
            List of chronological Candle objects.

        Raises:
            FileNotFoundError: If no parquet dataset exists for the instrument.
            SyntheticDataError: If the dataset is a fixture or fails the
                simulation screen and require_real_data is set.
            UnknownProvenanceError: If provenance cannot be established and
                require_real_data is set.
        """
        clean_name = instrument.lower().replace(":", "_").replace(" ", "_")
        parquet_path = self.locate_parquet(instrument, timeframe)
        if parquet_path is None:
            raise FileNotFoundError(
                f"Historical parquet dataset not found at {self.raw_data_dir / clean_name / f'{timeframe}.parquet'}"
            )

        if require_real_data:
            assert_real_dataset(
                parquet_path, label=f"{instrument} {timeframe} candle dataset"
            )
        else:
            report = check_provenance(parquet_path)
            if not report.admissible:
                logger.warning(
                    "backtest_dataset_provenance_unverified",
                    instrument=instrument,
                    timeframe=timeframe,
                    path=str(parquet_path),
                    reasons=list(report.reasons),
                    note="Backtest/test path — results describe this file, not the market.",
                )

        df = pl.read_parquet(parquet_path)
        candles: List[Candle] = []

        # Sort by timestamp
        df = df.sort("timestamp")
        for row in df.iter_rows(named=True):
            ts = row["timestamp"]
            if isinstance(ts, datetime):
                ts_ms = int(ts.replace(tzinfo=timezone.utc).timestamp() * 1000)
            elif isinstance(ts, int):
                ts_ms = ts if ts > 1e11 else ts * 1000
            else:
                ts_ms = int(ts)

            candles.append(
                Candle(
                    timestamp=ts_ms,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0) or 0.0),
                )
            )
        return candles

    def load_candles_with_source(
        self,
        instrument: str,
        timeframe: str = "1m",
        count: Optional[int] = None,
        require_real_data: bool = False,
    ) -> Tuple[List[Candle], CandleSource]:
        """Load candles for an instrument, explicitly reporting the data source.

        Uses the real parquet dataset when available. If absent, either raises
        FileNotFoundError (require_real_data=True — the live-HUD default) or
        generates the deterministic seed-42 synthetic session and marks it as
        simulated (TEST/BACKTEST-ONLY via an explicit synthetic flag).

        NOTE: callers on the live HUD path must pass require_real_data=True so a
        missing parquet surfaces as FileNotFoundError (-> HTTP 503) instead of a
        silent simulated fallback.

        A parquet whose provenance says it was generated is NOT real data. When
        require_real_data is set this raises SyntheticDataError; the caller is
        expected to surface it as a data-source failure, never to fall back.
        """
        path = self.locate_parquet(instrument, timeframe)
        if path is not None:
            if require_real_data:
                report = assert_real_dataset(
                    path, label=f"{instrument} {timeframe} candle dataset"
                )
            else:
                report = check_provenance(path)
            candles = self.load_parquet(instrument, timeframe)
            if count and len(candles) > count:
                candles = candles[-count:]
            return candles, CandleSource(
                type="parquet",
                instrument=instrument,
                path=str(path),
                # A parquet whose provenance is unverified is reported as
                # simulated, so no downstream consumer can mistake it for a market.
                is_simulated=not report.admissible,
                provenance_verified=report.admissible,
                note=(
                    "Real historical 1m parquet dataset (provenance verified)."
                    if report.admissible
                    else "Parquet present but provenance unverified: "
                    + "; ".join(report.reasons)
                ),
            )
        if require_real_data:
            raise FileNotFoundError(f"Historical parquet dataset not found for {instrument} ({timeframe})")
        d = datetime.now(timezone.utc)
        base = 80000.0 if "SENSEX" in instrument.upper() else (50000.0 if "BANK" in instrument.upper() else 24000.0)
        candles = HistoricalDataLoader.generate_synthetic_session(
            date_obj=d,
            start_price=base,
            drift=20.0,
            volatility=10.0,
            add_compression_and_breakout=True,
            seed=42,
        )
        if count and len(candles) > count:
            candles = candles[-count:]
        return candles, CandleSource(
            type="synthetic",
            instrument=instrument,
            path=None,
            is_simulated=True,
            provenance_verified=False,
            note=_SYNTHETIC_NOTE,
        )

    @staticmethod
    def generate_synthetic_session(
        date_obj: datetime,
        start_price: float = 24000.0,
        drift: float = 0.0,
        volatility: float = 12.0,
        add_compression_and_breakout: bool = True,
        seed: int = 42,
    ) -> List[Candle]:
        """Generates a realistic 375-bar 1-minute intraday session (09:15 to 15:30 IST).

        TEST / BACKTEST-ONLY helper (kept for deterministic unit tests, ablation,
        and backtests with an explicit synthetic flag). NEVER use on the live HUD
        path — missing real data there must raise, not synthesize.

        Args:
            date_obj: The calendar date for the session.
            start_price: Opening spot price.
            drift: Overall directional drift in points.
            volatility: Per-minute volatility standard deviation.
            add_compression_and_breakout: If True, injects structured compression and breakout.
            seed: Deterministic random seed.
            
        Returns:
            375 chronological 1-minute candles.
        """
        import random
        rng = random.Random(seed)

        # 09:15 IST is UTC 03:45
        ist_offset = timedelta(hours=5, minutes=30)
        start_ist = datetime(date_obj.year, date_obj.month, date_obj.day, 9, 15, tzinfo=timezone.utc) - ist_offset
        start_ts_ms = int(start_ist.timestamp() * 1000)

        candles: List[Candle] = []
        curr_price = start_price
        total_bars = 375

        # Pre-plan regime structure:
        # Bars 0-30: Opening discovery (moderate range)
        # Bars 30-70: Tight compression range
        # Bar 70-75: Explosive breakout with volume expansion
        # Bars 75-120: Trend acceptance / continuation
        # Bars 120-250: Midday consolidation
        # Bars 250-320: Afternoon drift
        # Bars 320-374: Late session close

        compression_range_mid = curr_price
        breakout_bar = 70 if add_compression_and_breakout else -1

        for i in range(total_bars):
            ts = start_ts_ms + i * 60000
            
            # Intraday volume curve: high at open/close (U-shaped)
            u_curve = 1.0 + 2.5 * ((i - 187.5) / 187.5) ** 2
            base_vol = 1500.0 * u_curve

            if add_compression_and_breakout and 30 <= i < breakout_bar:
                # Tight compression: price oscillates closely around compression_range_mid
                delta = rng.gauss(0, volatility * 0.20)
                o = curr_price
                c = compression_range_mid + delta
                h = max(o, c) + abs(rng.gauss(0, volatility * 0.15))
                l = min(o, c) - abs(rng.gauss(0, volatility * 0.15))
                v = base_vol * 0.40  # Volume dries up in compression
                curr_price = c
            elif add_compression_and_breakout and i == breakout_bar:
                # Breakout candle: strong displacement + heavy volume
                o = curr_price
                c = o + volatility * 3.5  # Strong bullish snap
                h = c + volatility * 0.3
                l = o - volatility * 0.1
                v = base_vol * 3.5  # Volume spike
                curr_price = c
            elif add_compression_and_breakout and i == breakout_bar + 1:
                # Confirmation follow-through bar
                o = curr_price
                c = o + volatility * 1.5
                h = c + volatility * 0.4
                l = o - volatility * 0.2
                v = base_vol * 2.2
                curr_price = c
            else:
                # Normal random walk with drift
                step = (drift / total_bars) + rng.gauss(0, volatility)
                o = curr_price
                c = o + step
                wiggle_h = abs(rng.gauss(0, volatility * 0.4))
                wiggle_l = abs(rng.gauss(0, volatility * 0.4))
                h = max(o, c) + wiggle_h
                l = min(o, c) - wiggle_l
                v = base_vol * (0.8 + rng.random() * 0.4)
                curr_price = c

            candles.append(
                Candle(
                    timestamp=ts,
                    open=round(o, 2),
                    high=round(h, 2),
                    low=round(l, 2),
                    close=round(c, 2),
                    volume=round(v, 1),
                )
            )

        return candles

    @staticmethod
    def resample_5m(candles_1m: List[Candle]) -> List[Candle]:
        """Resample a series of 1m candles into strictly closed 5m candles.
        
        A 5m bar spans minutes 0-4, 5-9, etc., and closes at the end of minute 4, 9.
        """
        if not candles_1m:
            return []

        candles_5m: List[Candle] = []
        current_bucket_ts: Optional[int] = None
        bucket_1m: List[Candle] = []

        for c in candles_1m:
            # 5m bucket start timestamp in ms (aligned to 5 minutes = 300,000 ms)
            bucket_start = (c.timestamp // 300000) * 300000

            if current_bucket_ts is None:
                current_bucket_ts = bucket_start

            if bucket_start != current_bucket_ts:
                # Close out previous 5m candle if it contains 5 bars
                if bucket_1m:
                    candles_5m.append(
                        Candle(
                            timestamp=bucket_1m[-1].timestamp,
                            open=bucket_1m[0].open,
                            high=max(b.high for b in bucket_1m),
                            low=min(b.low for b in bucket_1m),
                            close=bucket_1m[-1].close,
                            volume=sum(b.volume for b in bucket_1m),
                        )
                    )
                bucket_1m = [c]
                current_bucket_ts = bucket_start
            else:
                bucket_1m.append(c)

        # Include completed final 5m candle if it has all 5 bars
        if len(bucket_1m) == 5:
            candles_5m.append(
                Candle(
                    timestamp=bucket_1m[-1].timestamp,
                    open=bucket_1m[0].open,
                    high=max(b.high for b in bucket_1m),
                    low=min(b.low for b in bucket_1m),
                    close=bucket_1m[-1].close,
                    volume=sum(b.volume for b in bucket_1m),
                )
            )

        return candles_5m

    @staticmethod
    def compute_session_levels(
        all_candles_1m: List[Candle]
    ) -> List[HistoricalBarContext]:
        """Point-in-time session level enrichment across the entire candle sequence.
        
        Extracts PDH, PDL, PDC, CDO, and cumulative daily VWAP bar-by-bar
        strictly using past candles.
        """
        if not all_candles_1m:
            return []

        session_model = MarketSessionModel()
        contexts: List[HistoricalBarContext] = []

        # Identify day boundaries using IST day
        # Map: day_str -> list of candles
        day_buckets: Dict[str, List[Candle]] = {}
        for c in all_candles_1m:
            # Convert timestamp to IST string YYYY-MM-DD
            # UTC + 5:30
            dt_utc = datetime.fromtimestamp(c.timestamp / 1000, tz=timezone.utc)
            dt_ist = dt_utc + timedelta(hours=5, minutes=30)
            day_key = dt_ist.strftime("%Y-%m-%d")
            if day_key not in day_buckets:
                day_buckets[day_key] = []
            day_buckets[day_key].append(c)

        ordered_days = sorted(day_buckets.keys())

        # Rolling state
        prior_day_high: Optional[float] = None
        prior_day_low: Optional[float] = None
        prior_day_close: Optional[float] = None

        history_accumulated: List[Candle] = []

        for d_idx, day_key in enumerate(ordered_days):
            day_candles = day_buckets[day_key]
            current_day_open = day_candles[0].open

            # Cumulative daily VWAP tracking
            cum_vol = 0.0
            cum_pv = 0.0

            for bar_idx, c in enumerate(day_candles):
                history_accumulated.append(c)
                typ_price = (c.high + c.low + c.close) / 3.0
                cum_vol += c.volume
                cum_pv += typ_price * c.volume
                rolling_vwap = (cum_pv / cum_vol) if cum_vol > 0 else c.close

                # Closed 5m history up to this point
                # Only include completed 5m bars
                closed_5m = HistoricalDataLoader.resample_5m(history_accumulated)

                ctx = HistoricalBarContext(
                    timestamp_ms=c.timestamp,
                    candle_1m=c,
                    history_1m=list(history_accumulated),  # copy
                    candles_5m=closed_5m,
                    pdh=prior_day_high,
                    pdl=prior_day_low,
                    pdc=prior_day_close,
                    cdo=current_day_open,
                    vwap=round(rolling_vwap, 2),
                )
                contexts.append(ctx)

            # End of day: update prior day stats for next day
            prior_day_high = max(c.high for c in day_candles)
            prior_day_low = min(c.low for c in day_candles)
            prior_day_close = day_candles[-1].close

        return contexts
