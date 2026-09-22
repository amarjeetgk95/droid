"""Dataset provenance enforcement for research and backtest entry points.

Why this module exists
----------------------
``DatasetManager.save_dataset`` already records honest provenance — ``source``,
``checksum_sha256``, ``row_count``, time range — in a sidecar ``<name>.json``.
Nothing enforced it. The result, found in this repository:

* ``data/raw/sensex/1m.json`` declares ``"source": "synthetic_fixture"``,
* yet ``HistoricalDataLoader.load_candles_with_source(..., require_real_data=True)``
  returns that same parquet with ``is_simulated=False``, because file *presence*
  was treated as proof of authenticity,
* and ``DataQualityFirewall`` scored it ``100.0``, because a simulator has no
  gaps, no duplicate bars, valid OHLC geometry and no jump anomalies. Hygiene
  and authenticity are different axes; only the first was measured.

Consequence: a Gaussian random walk was admissible as *real market data* on any
path that checked only for a file, including the VORTEX-SNAP live HUD path. Any
research conclusion drawn from it is a conclusion about a random number
generator.

Two layers, deliberately separate
---------------------------------
* ``DataQualityFirewall.screen_simulation_signals`` — *measurement*: does this
  candle series carry the statistical fingerprint of a generated series?
* this module — *policy*: was this dataset legitimately sourced, and is it
  therefore admissible for research, backtest, or live use?

Fail-closed rules
-----------------
A substituted value is never acceptable. Missing sidecar, unknown source,
checksum mismatch, metadata/data disagreement or a simulated screen all raise.
There is no global escape hatch and no environment variable: ``allow_synthetic``
is an explicit per-call argument, so every bypass is greppable at its call site.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import polars as pl
import structlog

from app.quant.data.data_firewall import (
    MIN_SIMULATION_SIGNALS,
    STRONG_SIMULATION_SIGNALS,
    DataQualityFirewall,
    SimulationScreen,
)
from app.quant.data.dataset_manager import DatasetMetadata
from app.signals.quote_quality import SYNTHETIC_PROVIDERS

logger = structlog.get_logger(__name__)

#: Sources admitted for research, backtest, and live use.
ALLOWED_RESEARCH_SOURCES = frozenset(
    {
        "fyers_api_v3",
        "fyers_api",
        "fyers_api_v2",
        "nse_bhavcopy",
        "vendor_export",
        "upstox_api_v2",
        "zerodha_kite_v3",
    }
)

#: Sources that are known not to be market data. The quote-side vocabulary in
#: ``app.signals.quote_quality.SYNTHETIC_PROVIDERS`` is the canonical set; the
#: dataset-ingest vocabulary (``save_dataset(source=...)``) adds the rest.
FIXTURE_SOURCES = SYNTHETIC_PROVIDERS | frozenset(
    {
        "synthetic_fixture",
        "fixture",
        "seed42",
        "gbm",
        "generated",
    }
)


class ProvenanceError(RuntimeError):
    """Base class for all dataset provenance failures."""


class SyntheticDataError(ProvenanceError):
    """The dataset is a fixture or simulator output, not market data."""


class UnknownProvenanceError(ProvenanceError):
    """Provenance is absent or unrecognised, so authenticity cannot be claimed."""


class DatasetIntegrityError(ProvenanceError):
    """The file disagrees with its own declared metadata."""


@dataclass(frozen=True)
class ProvenanceReport:
    """Outcome of a provenance check. Travels with experiment results."""

    path: str
    source: str
    dataset_id: Optional[str]
    checksum_sha256: Optional[str]
    row_count: Optional[int]
    admissible: bool
    reasons: tuple[str, ...]
    screen: Optional[SimulationScreen] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "source": self.source,
            "dataset_id": self.dataset_id,
            "checksum_sha256": self.checksum_sha256,
            "row_count": self.row_count,
            "admissible": self.admissible,
            "reasons": list(self.reasons),
            "screen": self.screen.to_dict() if self.screen is not None else None,
        }


#: Simulation screens are pure functions of file contents; cache by checksum so
#: a hot research loop pays for the screen once per dataset, not once per load.
_SCREEN_CACHE: dict[str, SimulationScreen] = {}


def sidecar_path(path: Path | str) -> Path:
    """Sidecar location for a parquet dataset (mirrors DatasetManager)."""
    return Path(path).with_suffix(".json")


def compute_sha256(path: Path | str, chunk_size: int = 65536) -> str:
    """SHA-256 of a file, matching DatasetManager's digest."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _dataset_metadata_from_hdm(payload: dict) -> Optional[DatasetMetadata]:
    """Translate a Historical Data Module sidecar into ``DatasetMetadata``.

    The HDM ingestion pipeline (``data/historical/parquet/<inst>/<tf>/candles_*.parquet``)
    writes a richer record — ``symbol``/``lineage``/``quality_score`` instead of the
    Tier-0 DatasetManager fields. Recognize it explicitly: refusing genuinely real
    data on sidecar-schema grounds is as damaging as accepting generated data.
    Returns None when the payload does not match the HDM shape; raises
    ``UnknownProvenanceError`` when it matches the shape but cannot establish
    provenance (e.g. no provider in lineage).
    """
    required = {"symbol", "timeframe", "row_count", "checksum_sha256", "lineage"}
    if not required.issubset(payload.keys()):
        return None
    lineage = payload.get("lineage") or {}
    if not isinstance(lineage, dict):
        raise UnknownProvenanceError(
            "Historical Data Module sidecar has a non-object 'lineage'; provenance cannot be established."
        )
    provider = str(lineage.get("provider_id") or "").strip().lower()
    api_version = str(lineage.get("provider_api_version") or "").strip().lower()
    if not provider:
        raise UnknownProvenanceError(
            "Historical Data Module sidecar lacks lineage.provider_id; provenance cannot be established."
        )
    if provider in SYNTHETIC_PROVIDERS:
        # Keep simulator vocabulary bare so it lands in FIXTURE_SOURCES; only
        # real brokers get the versioned ``<provider>_api_<v>`` form.
        source = provider
    else:
        source = f"{provider}_api_{api_version}" if api_version else provider
    version_tag = str(payload.get("version_tag") or "v1")
    return DatasetMetadata(
        dataset_id=f"{payload['symbol']}_{payload['timeframe']}_{version_tag}",
        instrument=str(payload["symbol"]),
        timeframe=str(payload["timeframe"]),
        row_count=int(payload["row_count"]),
        start_time=str(payload.get("start_time") or ""),
        end_time=str(payload.get("end_time") or ""),
        checksum_sha256=str(payload["checksum_sha256"]),
        created_at_utc=str(payload.get("saved_at_utc") or lineage.get("created_at") or ""),
        source=source,
        data_quality_score=float(payload.get("quality_score") or 0.0),
    )


def read_sidecar(path: Path | str) -> Optional[DatasetMetadata]:
    """Parse the provenance sidecar, or None when it does not exist.

    Understands both the Tier-0 DatasetManager schema and the richer Historical
    Data Module schema. Raises ``UnknownProvenanceError`` when the sidecar exists
    but is unreadable or incomplete — a corrupt provenance record cannot be
    treated as absent.
    """
    meta_path = sidecar_path(path)
    if not meta_path.exists():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - re-raised with provenance context
        raise UnknownProvenanceError(
            f"Provenance sidecar {meta_path} exists but is unreadable: {exc}"
        ) from exc
    hdm_meta = _dataset_metadata_from_hdm(payload)
    if hdm_meta is not None:
        return hdm_meta
    try:
        return DatasetMetadata(**payload)
    except TypeError as exc:
        raise UnknownProvenanceError(
            f"Provenance sidecar {meta_path} is incomplete ({exc}). "
            "A partial provenance record cannot establish authenticity."
        ) from exc


def screen_dataset(
    path: Path | str,
    frame: Optional[pl.DataFrame] = None,
    *,
    checksum: Optional[str] = None,
) -> SimulationScreen:
    """Run the simulation screen over a dataset, cached by content checksum."""
    key = checksum or compute_sha256(path)
    cached = _SCREEN_CACHE.get(key)
    if cached is not None:
        return cached

    data = frame if frame is not None else pl.read_parquet(path)
    result = DataQualityFirewall().screen_simulation_signals(data)
    _SCREEN_CACHE[key] = result
    return result


def _as_utc(value: Any) -> Optional[Any]:
    """Normalise a datetime to aware UTC so naive and aware compare safely."""
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _declared_range_reasons(frame: pl.DataFrame, metadata: DatasetMetadata) -> list[str]:
    """Compare the dataset's declared time range against what it actually holds."""
    try:
        declared_start = _as_utc(datetime.fromisoformat(str(metadata.start_time).replace("Z", "+00:00")))
        declared_end = _as_utc(datetime.fromisoformat(str(metadata.end_time).replace("Z", "+00:00")))
    except Exception:  # noqa: BLE001 - unparsable provenance is not a pass
        return ["unparsable_declared_time_range"]

    if declared_start is None or declared_end is None:
        return ["unparsable_declared_time_range"]

    try:
        actual_start = _as_utc(frame["timestamp"].min())
        actual_end = _as_utc(frame["timestamp"].max())
    except Exception as exc:  # noqa: BLE001
        return [f"unreadable_timestamp_column: {exc}"]

    reasons: list[str] = []
    if actual_start != declared_start or actual_end != declared_end:
        reasons.append(
            f"time_range_mismatch: declared {declared_start}..{declared_end}, "
            f"found {actual_start}..{actual_end}"
        )
    return reasons


def check_provenance(
    path: Path | str,
    *,
    screen: bool = True,
    frame: Optional[pl.DataFrame] = None,
) -> ProvenanceReport:
    """Inspect a dataset's provenance without raising.

    Used by soft paths (backtest/test loaders) that must warn rather than fail.
    Strict paths must call :func:`assert_real_dataset` instead.
    """
    dataset_path = Path(path)
    reasons: list[str] = []
    source = "unknown"
    metadata: Optional[DatasetMetadata] = None
    checksum: Optional[str] = None
    sim: Optional[SimulationScreen] = None
    source_admissible = False

    if not dataset_path.exists():
        return ProvenanceReport(
            path=str(dataset_path),
            source=source,
            dataset_id=None,
            checksum_sha256=None,
            row_count=None,
            admissible=False,
            reasons=("dataset_missing",),
        )

    try:
        metadata = read_sidecar(dataset_path)
    except UnknownProvenanceError as exc:
        reasons.append(f"sidecar_unreadable: {exc}")

    if metadata is None:
        reasons.append("no_sidecar")
    else:
        source = metadata.source
        if source in FIXTURE_SOURCES:
            reasons.append(f"fixture_source: {source}")
        elif source not in ALLOWED_RESEARCH_SOURCES:
            reasons.append(f"unknown_source: {source}")
        else:
            source_admissible = True

        checksum = compute_sha256(dataset_path)
        if checksum != metadata.checksum_sha256:
            reasons.append("checksum_mismatch")

    if screen:
        try:
            data = frame if frame is not None else pl.read_parquet(dataset_path)
            sim = screen_dataset(dataset_path, data, checksum=checksum)
            if metadata is not None:
                if len(data) != metadata.row_count:
                    reasons.append(
                        f"row_count_mismatch: declared {metadata.row_count}, found {len(data)}"
                    )
                reasons.extend(_declared_range_reasons(data, metadata))
            # Confirming suspicion is cheap; contradicting an admissible broker
            # provenance requires stronger evidence, so that real index data is
            # not rejected on the one signal a continuous series always triggers.
            needed = (
                STRONG_SIMULATION_SIGNALS
                if source_admissible
                else MIN_SIMULATION_SIGNALS
            )
            if sim.is_simulated_with(needed):
                reasons.append(
                    f"simulation_screen({len(sim.signals)}/{needed}): "
                    f"{','.join(sim.signals)}"
                )
        except Exception as exc:  # noqa: BLE001 - screening failure is not a pass
            reasons.append(f"screen_failed: {exc}")

    return ProvenanceReport(
        path=str(dataset_path),
        source=source,
        dataset_id=metadata.dataset_id if metadata else None,
        checksum_sha256=checksum,
        row_count=metadata.row_count if metadata else None,
        admissible=not reasons,
        reasons=tuple(reasons),
        screen=sim,
    )


def assert_real_dataset(
    path: Path | str,
    *,
    screen: bool = True,
    frame: Optional[pl.DataFrame] = None,
    allow_synthetic: bool = False,
    label: str = "dataset",
) -> ProvenanceReport:
    """Fail closed unless ``path`` is verifiably real market data.

    Args:
        screen: run the statistical simulation screen (default True).
        allow_synthetic: explicit, per-call opt-in for fixtures. Intended only
            for tests and deliberately-synthetic research harnesses. Passed by
            name at the call site so every bypass is greppable.
        label: human-readable role, used in error messages.

    Raises:
        SyntheticDataError: fixture/simulator source, or a simulated screen.
        UnknownProvenanceError: no sidecar, unreadable sidecar, or unknown source.
        DatasetIntegrityError: metadata disagreeing with the file on disk.
        FileNotFoundError: no such dataset.
    """
    report = check_provenance(path, screen=screen, frame=frame)

    if report.admissible:
        return report

    if allow_synthetic:
        logger.warning(
            "synthetic_data_admitted",
            label=label,
            path=report.path,
            source=report.source,
            reasons=list(report.reasons),
        )
        return report

    detail = "; ".join(report.reasons)
    is_fixture = any(
        reason.startswith("fixture_source") or reason.startswith("simulation_screen")
        for reason in report.reasons
    )
    if is_fixture:
        raise SyntheticDataError(
            f"Refusing to use {label} at {report.path} as market data: {detail}. "
            "Simulated or fixture series carry no market structure, so any "
            "research result computed from them is a result about the generator. "
            "Supply a dataset with a real provenance source."
        )
    if "no_sidecar" in report.reasons or any(
        r.startswith("sidecar_unreadable") or r.startswith("unknown_source") for r in report.reasons
    ):
        raise UnknownProvenanceError(
            f"Cannot establish provenance for {label} at {report.path}: {detail}. "
            "Datasets must be written through DatasetManager.save_dataset so the "
            f"sidecar {sidecar_path(report.path)} records an admissible source."
        )
    if "dataset_missing" in report.reasons:
        raise FileNotFoundError(f"No {label} dataset at {report.path}")
    raise DatasetIntegrityError(
        f"{label} at {report.path} failed provenance verification: {detail}"
    )


def provenance_block(path: Path | str, **kwargs: Any) -> dict[str, Any]:
    """Provenance dict for embedding in an experiment report."""
    return check_provenance(path, **kwargs).to_dict()
