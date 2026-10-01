"""Historical candle adapter for the research module (§2, §7).

Reads the existing canonical historical store; it does not acquire data and it
never synthesises a candle. If a dataset is missing, empty for the requested
range, or unreadable, the caller receives an explicit availability value and a
human-readable reason — never a silently shortened or fabricated series.

That matters more than it sounds: a research engine that quietly returns 40
synthetic bars where the user asked for two years of NIFTY will produce a
confident, wrong number. The UI shows the reason instead.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import structlog

from app.indicator_research.enums import DataAvailability, OrderFlowProvenance

logger = structlog.get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")

#: Instruments the research UI offers by default.
SUPPORTED_INSTRUMENTS: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "SENSEX")

#: Timeframes offered initially; the loader accepts any that exists on disk.
SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "30m", "1h", "1D")

#: Free-text instrument labels mapped onto dataset symbols.
_SYMBOL_ALIASES: dict[str, str] = {
    "NIFTY": "NIFTY",
    "NIFTY50": "NIFTY",
    "NIFTY 50": "NIFTY",
    "NIFTY_50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "BANK NIFTY": "BANKNIFTY",
    "NIFTY BANK": "BANKNIFTY",
    "NIFTYBANK": "BANKNIFTY",
    "SENSEX": "SENSEX",
    "BSE SENSEX": "SENSEX",
    "BSESENSEX": "SENSEX",
}

#: Hard ceiling on bars pulled into one research run (memory guard).
DEFAULT_MAX_BARS = 250_000

#: Bars below this make the causality check meaningless.
MIN_USEFUL_BARS = 30


def resolve_symbol(instrument: str) -> str:
    """Map a user-facing instrument label to a dataset symbol."""
    key = (instrument or "").strip().upper()
    if key in _SYMBOL_ALIASES:
        return _SYMBOL_ALIASES[key]
    compact = key.replace("_", " ")
    return _SYMBOL_ALIASES.get(compact, key)


def normalize_timeframe(timeframe: str) -> str:
    tf = (timeframe or "5m").strip()
    if tf.upper() in ("1D", "1D", "D", "DAY"):
        return "1D"
    return tf.lower()


@dataclass
class CandleSeries:
    """A loaded (or failed-to-load) candle series plus its provenance."""

    instrument: str
    dataset_symbol: str
    timeframe: str
    availability: str
    candles: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None
    source: str = "historical_parquet"
    version: str | None = None
    requested_start: str | None = None
    requested_end: str | None = None
    data_start: str | None = None
    data_end: str | None = None
    truncated: bool = False
    order_flow_provenance: str = OrderFlowProvenance.UNAVAILABLE.value
    warnings: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.availability == DataAvailability.AVAILABLE.value

    @property
    def bars(self) -> int:
        return len(self.candles)

    def to_dict(self, *, include_candles: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "instrument": self.instrument,
            "dataset_symbol": self.dataset_symbol,
            "timeframe": self.timeframe,
            "available": self.available,
            "availability": self.availability,
            "reason": self.reason,
            "source": self.source,
            "version": self.version,
            "requested_start": self.requested_start,
            "requested_end": self.requested_end,
            "data_start": self.data_start,
            "data_end": self.data_end,
            "bars": self.bars,
            "truncated": self.truncated,
            "order_flow_provenance": self.order_flow_provenance,
            "warnings": list(self.warnings),
        }
        if include_candles:
            payload["candles"] = list(self.candles)
        return payload


def _ist_day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=IST).astimezone(timezone.utc)


def _ist_day_end_exclusive(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=IST).astimezone(
        timezone.utc
    )


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _normalize_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce stored rows into the engine's candle shape."""
    out: list[dict[str, Any]] = []
    for row in rows:
        ts = row.get("timestamp")
        item: dict[str, Any] = {
            "timestamp": _iso(ts),
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "volume": row.get("volume"),
        }
        for k in (
            "trades",
            "buy_volume",
            "sell_volume",
            "bids",
            "asks",
            "vwap",
            "open_interest",
            "spread",
        ):
            if k in row and row[k] is not None:
                item[k] = row[k]
        out.append(item)
    return out


def _versions_on_disk(parquet_repo: Any, dataset_symbol: str, timeframe: str) -> list[str]:
    """Every version tag present on disk, oldest first.

    Guards against the silent-staleness failure mode: if the catalogue lookup
    is unavailable and the loader defaulted to ``v1``, a research run would read
    months-old bars and report a confident result from them.
    """
    try:
        directory = parquet_repo.get_parquet_path(dataset_symbol, timeframe, "v1").parent
    except Exception:
        return []
    if not directory.exists():
        return []

    def sort_key(tag: str) -> tuple[int, str]:
        digits = tag[1:] if tag.startswith("v") else tag
        return (int(digits), tag) if digits.isdigit() else (-1, tag)

    tags = [
        path.stem.rsplit("_", 1)[-1]
        for path in directory.glob("candles_*.parquet")
        if path.stem.startswith("candles_")
    ]
    return sorted(set(tags), key=sort_key)


async def _resolve_version(dataset_symbol: str, timeframe: str) -> str | None:
    """Current version tag for a dataset from the catalogue, if reachable."""
    try:
        from app.historical_data.storage.db_repository import db_repo

        dataset = await db_repo.get_dataset(f"{dataset_symbol}_{timeframe.upper()}")
        if dataset and dataset.current_version_id:
            tag = str(dataset.current_version_id).rsplit("_", 1)[-1]
            if tag:
                return tag
    except Exception as e:
        logger.debug(
            "indicator_research_version_lookup_failed",
            symbol=dataset_symbol,
            error=str(e)[:200],
        )
    return None


def load_candles_sync(
    instrument: str,
    timeframe: str,
    start: date | None = None,
    end: date | None = None,
    *,
    version: str | None = None,
    max_bars: int = DEFAULT_MAX_BARS,
) -> CandleSeries:
    """Blocking read from the canonical historical store."""
    dataset_symbol = resolve_symbol(instrument)
    tf = normalize_timeframe(timeframe)
    series = CandleSeries(
        instrument=instrument,
        dataset_symbol=dataset_symbol,
        timeframe=tf,
        availability=DataAvailability.PROVIDER_ERROR.value,
        requested_start=start.isoformat() if start else None,
        requested_end=end.isoformat() if end else None,
        version=version,
    )

    try:
        from app.historical_data.storage.parquet_repository import parquet_repo
    except Exception as e:
        series.reason = (
            "The historical data store is unavailable in this environment "
            f"({type(e).__name__}: {e}). No candles could be loaded."
        )
        return series

    start_dt = _ist_day_start(start) if start else None
    end_dt = _ist_day_end_exclusive(end) if end else None

    # Version selection. A catalogue hint is used only if its file exists; the
    # newest version actually on disk wins otherwise, so a DB outage degrades to
    # the freshest available bars instead of the oldest.
    available = _versions_on_disk(parquet_repo, dataset_symbol, tf)
    version_tag: str | None = version
    if version_tag and version not in available and available:
        series.warnings.append(
            f"Requested version '{version}' is not on disk; using '{available[-1]}' instead."
        )
        version_tag = available[-1]
    if not version_tag:
        version_tag = available[-1] if available else "v1"
    series.version = version_tag

    try:
        frame = parquet_repo.load_candles(
            dataset_symbol,
            tf,
            version_tag=version_tag,
            start_time=start_dt,
            end_time=end_dt,
        )
    except FileNotFoundError as e:
        series.availability = DataAvailability.DATASET_MISSING.value
        known = ", ".join(available) if available else "none"
        series.reason = (
            f"No stored {dataset_symbol} {tf} dataset was found for version "
            f"{version_tag} (versions on disk: {known}). Download it from Historical "
            f"Data first. Detail: {e}"
        )
        return series
    except Exception as e:
        series.reason = (
            f"Reading the {dataset_symbol} {tf} dataset failed "
            f"({type(e).__name__}: {str(e)[:200]})."
        )
        return series

    try:
        rows = frame.to_dicts()
    except Exception as e:
        series.reason = f"Stored dataset could not be decoded ({e})."
        return series

    if not rows:
        series.availability = DataAvailability.EMPTY_RANGE.value
        series.reason = (
            f"The {dataset_symbol} {tf} dataset holds no candles in "
            f"{series.requested_start or 'the beginning'} → "
            f"{series.requested_end or 'now'}."
        )
        return series

    if len(rows) > max_bars:
        series.truncated = True
        series.warnings.append(
            f"Requested range has {len(rows)} bars; the most recent {max_bars} were used."
        )
        rows = rows[-max_bars:]

    series.candles = _normalize_rows(rows)
    series.availability = DataAvailability.AVAILABLE.value
    series.data_start = series.candles[0]["timestamp"]
    series.data_end = series.candles[-1]["timestamp"]

    # Determine order-flow provenance
    sample_candles = series.candles[:100]
    has_real_flow = any(
        c.get("trades") or (c.get("buy_volume") is not None and c.get("sell_volume") is not None) or (c.get("bids") and c.get("asks"))
        for c in sample_candles
    )
    if has_real_flow:
        series.order_flow_provenance = OrderFlowProvenance.REAL.value
    elif any(c.get("volume") is not None and float(c.get("volume") or 0) > 0 for c in sample_candles):
        series.order_flow_provenance = OrderFlowProvenance.PROXY.value
    else:
        series.order_flow_provenance = OrderFlowProvenance.UNAVAILABLE.value

    if len(series.candles) < MIN_USEFUL_BARS:
        series.warnings.append(
            f"Only {len(series.candles)} bars were loaded; results below "
            f"{MIN_USEFUL_BARS} bars are not statistically meaningful and causality "
            "cannot be verified."
        )
    return series


async def load_candles(
    instrument: str,
    timeframe: str,
    start: date | None = None,
    end: date | None = None,
    *,
    version: str | None = None,
    max_bars: int = DEFAULT_MAX_BARS,
) -> CandleSeries:
    """Async wrapper. Resolves the current dataset version, then reads off-thread."""
    dataset_symbol = resolve_symbol(instrument)
    tf = normalize_timeframe(timeframe)
    hint = version
    if hint is None:
        hint = await _resolve_version(dataset_symbol, tf)
    return await asyncio.to_thread(
        load_candles_sync, instrument, tf, start, end, version=hint, max_bars=max_bars
    )


async def dataset_catalog() -> dict[str, Any]:
    """Availability of every instrument/timeframe the UI offers.

    Lets the research page state what data actually exists before a user spends
    time configuring an experiment that cannot run.
    """
    entries: list[dict[str, Any]] = []
    known: dict[str, Any] = {}
    catalogue_reachable = True
    try:
        from app.historical_data.storage.db_repository import db_repo

        datasets = await db_repo.list_datasets()
        known = {d.id: d for d in datasets}
    except Exception as e:
        logger.debug("indicator_research_catalog_failed", error=str(e)[:200])
        catalogue_reachable = False

    parquet_repo = None
    try:
        from app.historical_data.storage.parquet_repository import parquet_repo as _repo

        parquet_repo = _repo
    except Exception:  # pragma: no cover - storage always importable in app
        parquet_repo = None

    for instrument in SUPPORTED_INSTRUMENTS:
        symbol = resolve_symbol(instrument)
        for timeframe in SUPPORTED_TIMEFRAMES:
            dataset = known.get(f"{symbol}_{timeframe.upper()}")
            versions = (
                _versions_on_disk(parquet_repo, symbol, timeframe) if parquet_repo else []
            )
            # The catalogue is the richer source, but a disk scan keeps the
            # availability report honest when the database is unreachable —
            # otherwise the UI would claim nothing exists while the files sit
            # right there on disk.
            entry: dict[str, Any] = {
                "instrument": instrument,
                "dataset_symbol": symbol,
                "timeframe": timeframe,
                "available": bool(versions) or dataset is not None,
                "source": "catalogue+disk" if dataset is not None else "disk",
                "versions_on_disk": versions,
                "dataset_id": dataset.id if dataset else f"{symbol}_{timeframe.upper()}",
                "status": getattr(dataset, "status", None) if dataset else None,
                "total_candles": getattr(dataset, "total_candles", 0) if dataset else 0,
                "earliest_available_ts": (
                    _iso(getattr(dataset, "earliest_available_ts", None)) if dataset else None
                ),
                "latest_available_ts": (
                    _iso(getattr(dataset, "latest_available_ts", None)) if dataset else None
                ),
                "quality_score": (
                    getattr(dataset, "latest_quality_score", None) if dataset else None
                ),
            }
            entries.append(entry)
    return {
        "instruments": list(SUPPORTED_INSTRUMENTS),
        "timeframes": list(SUPPORTED_TIMEFRAMES),
        "entries": entries,
        "catalogue_reachable": catalogue_reachable,
        "note": (
            "Research runs read the canonical historical store. Nothing is "
            "downloaded or synthesised on demand."
            + (
                ""
                if catalogue_reachable
                else " The dataset catalogue was unreachable, so availability was "
                "determined by scanning stored files; candle counts and date ranges "
                "are not reported."
            )
        ),
    }


__all__ = [
    "DEFAULT_MAX_BARS",
    "MIN_USEFUL_BARS",
    "SUPPORTED_INSTRUMENTS",
    "SUPPORTED_TIMEFRAMES",
    "CandleSeries",
    "dataset_catalog",
    "load_candles",
    "load_candles_sync",
    "normalize_timeframe",
    "resolve_symbol",
]
