"""Tests for dataset provenance enforcement and the simulation screen.

Context: ``data/raw/sensex/1m.json`` in this repository declares
``"source": "synthetic_fixture"``, yet the data loaded as real on every path
that checked only for file presence, and ``DataQualityFirewall`` scored it
100.0. These tests lock in the two properties that were missing: a generated
series is detected from its statistics, and a fixture is refused by name.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from app.quant.data.data_firewall import DataQualityFirewall
from app.quant.data.provenance import (
    DatasetIntegrityError,
    SyntheticDataError,
    UnknownProvenanceError,
    assert_real_dataset,
    check_provenance,
    compute_sha256,
)
from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader

BARS_PER_SESSION = 375


def _timestamps(sessions: int, bars: int = BARS_PER_SESSION) -> list[datetime]:
    """Weekday 09:15-start sessions of 1-minute bars."""
    out: list[datetime] = []
    day = datetime(2025, 1, 1, 9, 15)
    made = 0
    while made < sessions:
        if day.weekday() < 5:
            out.extend(day + timedelta(minutes=i) for i in range(bars))
            made += 1
        day += timedelta(days=1)
    return out


def _generated_frame(sessions: int = 25, bars: int = BARS_PER_SESSION, seed: int = 42) -> pl.DataFrame:
    """Mirrors the signature of the seed-42 style generator found in this repo.

    No intraday gaps, ``open[t] == close[t-1]`` exactly, Gaussian returns,
    every bar carrying both wicks, and fractional volume.
    """
    rng = np.random.default_rng(seed)
    ts = _timestamps(sessions, bars)
    n = len(ts)

    steps = rng.normal(0.0, 0.0004, n)
    closes = 80000.0 * np.exp(np.cumsum(steps))
    opens = np.empty(n)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]  # exact continuation — impossible in a real book

    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 5, n)) + 0.1
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 5, n)) - 0.1
    volume = rng.uniform(100.0, 25_000.0, n)  # fractional

    return pl.DataFrame(
        {
            "timestamp": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volume,
        }
    )


def _realistic_frame(sessions: int = 25, bars: int = BARS_PER_SESSION, seed: int = 7) -> pl.DataFrame:
    """Gappy, fat-tailed, integer-volume, gap-opening, wick-carrying series."""
    rng = np.random.default_rng(seed)
    ts = _timestamps(sessions, bars)
    n = len(ts)

    steps = rng.standard_t(df=4, size=n) * 0.0004  # fat tails
    closes = 80000.0 * np.exp(np.cumsum(steps))

    opens = np.empty(n)
    opens[0] = closes[0] * 1.0005
    opens[1:] = closes[:-1] * (1.0 + rng.normal(0, 0.0003, n - 1))  # real gap opens

    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 6, n)) + 0.5
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 6, n)) - 0.5
    # Quiet bars genuinely have no wick on one side.
    direction = rng.random(n) < 0.5
    for i in np.flatnonzero(rng.random(n) < 0.15):
        if direction[i]:
            lows[i] = min(opens[i], closes[i])
        else:
            highs[i] = max(opens[i], closes[i])

    volume = rng.integers(1_000, 50_000, n).astype(float)

    frame = pl.DataFrame(
        {
            "timestamp": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volume,
        }
    )

    # Missing bars are the norm intraday.
    drop = np.zeros(n, dtype=bool)
    for session in range(sessions):
        drop[session * bars + 100] = True
        drop[session * bars + 250] = True
    return frame.filter(~pl.Series("drop", drop))


def _borderline_frame(sessions: int = 25, bars: int = BARS_PER_SESSION, seed: int = 11) -> pl.DataFrame:
    """A series that trips exactly two signals: continuous opens, Gaussian returns.

    This is the shape a *real* continuous index series can legitimately have — the
    close of one minute is the open of the next, and quiet-regime 1-minute returns
    can look near-Gaussian. Two signals must not be enough to reject real data.
    """
    rng = np.random.default_rng(seed)
    ts = _timestamps(sessions, bars)
    n = len(ts)

    steps = rng.normal(0.0, 0.0004, n)  # Gaussian, not fat-tailed
    closes = 80000.0 * np.exp(np.cumsum(steps))
    opens = np.empty(n)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]  # continuous

    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 6, n)) + 0.5
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 6, n)) - 0.5
    direction = rng.random(n) < 0.5
    for i in np.flatnonzero(rng.random(n) < 0.15):
        if direction[i]:
            lows[i] = min(opens[i], closes[i])
        else:
            highs[i] = max(opens[i], closes[i])
    volume = rng.integers(1_000, 50_000, n).astype(float)

    frame = pl.DataFrame(
        {
            "timestamp": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volume,
        }
    )
    drop = np.zeros(n, dtype=bool)
    for session in range(sessions):
        drop[session * bars + 100] = True
        drop[session * bars + 250] = True
    return frame.filter(~pl.Series("drop", drop))


def _write_dataset(
    root: Path,
    name: str,
    frame: pl.DataFrame,
    source: str,
    *,
    checksum_override: str | None = None,
    write_sidecar: bool = True,
    row_count_override: int | None = None,
) -> Path:
    path = root / f"{name}.parquet"
    frame.write_parquet(path)
    if write_sidecar:
        meta = {
            "dataset_id": f"ds_{name}",
            "instrument": name,
            "timeframe": "1m",
            "row_count": len(frame) if row_count_override is None else row_count_override,
            "start_time": str(frame["timestamp"][0]),
            "end_time": str(frame["timestamp"][-1]),
            "checksum_sha256": checksum_override or compute_sha256(path),
            "created_at_utc": "2026-09-22T00:00:00+00:00",
            "source": source,
            "data_quality_score": 100.0,
        }
        path.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    return path


def _write_hdm_dataset(root: Path, name: str, frame: pl.DataFrame) -> Path:
    """Write a dataset with a Historical Data Module schema sidecar."""
    path = root / f"{name}.parquet"
    frame.write_parquet(path)
    meta = {
        "symbol": "SENSEX",
        "timeframe": "1m",
        "version_tag": "v1",
        "row_count": len(frame),
        "start_time": str(frame["timestamp"][0]),
        "end_time": str(frame["timestamp"][-1]),
        "checksum_sha256": compute_sha256(path),
        "quality_score": 98.83,
        "lineage": {
            "engine_version": "1.0.0",
            "provider_id": "fyers",
            "provider_api_version": "v3",
            "calendar_version": "2026.1",
            "normalizer_version": "1.0.0",
            "validation_ruleset_version": "1.0.0",
            "created_at": "2026-09-22T11:21:46.106241Z",
        },
        "methodology_events": [],
        "saved_at_utc": "2026-09-22T11:21:46.207384+00:00",
    }
    path.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    return path


class TestHdmSidecarTranslation:
    """The Historical Data Module writes a richer sidecar schema; real data
    must be admitted through it, not refused on schema grounds."""

    def test_hdm_sidecar_with_real_provider_is_admissible(self, tmp_path):
        path = _write_hdm_dataset(tmp_path, "candles_v1", _realistic_frame())
        report = check_provenance(path)
        assert report.admissible is True
        assert report.source == "fyers_api_v3"
        assert report.row_count == len(_realistic_frame())

    def test_hdm_sidecar_without_provider_fails_closed(self, tmp_path):
        path = _write_hdm_dataset(tmp_path, "candles_v1", _realistic_frame())
        payload = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        payload["lineage"].pop("provider_id")
        path.with_suffix(".json").write_text(json.dumps(payload), encoding="utf-8")
        report = check_provenance(path)
        assert report.admissible is False
        assert any("provider_id" in r for r in report.reasons)

    def test_hdm_sidecar_with_fixture_provider_is_refused(self, tmp_path):
        path = _write_hdm_dataset(tmp_path, "candles_v1", _generated_frame())
        payload = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        payload["lineage"]["provider_id"] = "synthetic"
        path.with_suffix(".json").write_text(json.dumps(payload), encoding="utf-8")
        report = check_provenance(path)
        assert report.admissible is False
        assert any(r.startswith("fixture_source") for r in report.reasons)

    def test_hdm_checksum_mismatch_is_integrity_error(self, tmp_path):
        path = _write_hdm_dataset(tmp_path, "candles_v1", _realistic_frame())
        payload = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        payload["checksum_sha256"] = "0" * 64
        path.with_suffix(".json").write_text(json.dumps(payload), encoding="utf-8")
        report = check_provenance(path)
        assert report.admissible is False
        assert any(r.startswith("checksum_mismatch") for r in report.reasons)


# --------------------------------------------------------------------------
# Simulation screen
# --------------------------------------------------------------------------


class TestSimulationScreen:
    def test_generated_series_is_detected(self):
        screen = DataQualityFirewall().screen_simulation_signals(_generated_frame())
        assert screen.looks_simulated
        assert "no_intraday_gaps" in screen.signals
        assert "open_equals_prior_close" in screen.signals
        assert "gaussian_returns" in screen.signals
        assert "no_zero_wicks" in screen.signals
        assert "non_integer_volume" in screen.signals

    def test_realistic_series_is_not_flagged(self):
        screen = DataQualityFirewall().screen_simulation_signals(_realistic_frame())
        assert not screen.looks_simulated, screen.signals
        assert screen.signals == []

    def test_screen_refuses_structurally_unusable_frame(self):
        with pytest.raises(ValueError):
            DataQualityFirewall().screen_simulation_signals(
                pl.DataFrame({"timestamp": [datetime(2025, 1, 1)], "open": [1.0]})
            )
        with pytest.raises(ValueError):
            DataQualityFirewall().screen_simulation_signals(pl.DataFrame({"open": []}))

    def test_hygiene_score_alone_cannot_distinguish_a_market(self):
        """The reason provenance could not be inferred from the quality score."""
        firewall = DataQualityFirewall()
        _clean, report = firewall.inspect_and_clean(_generated_frame())
        assert report.score == 100.0
        assert firewall.screen_simulation_signals(_generated_frame()).looks_simulated


# --------------------------------------------------------------------------
# Provenance gate
# --------------------------------------------------------------------------


class TestProvenanceGate:
    def test_fixture_source_is_refused(self, tmp_path):
        path = _write_dataset(tmp_path, "sensex", _generated_frame(), "synthetic_fixture")
        with pytest.raises(SyntheticDataError):
            assert_real_dataset(path)

    def test_unknown_source_is_refused(self, tmp_path):
        path = _write_dataset(tmp_path, "sensex", _realistic_frame(), "some_scraper")
        with pytest.raises(UnknownProvenanceError):
            assert_real_dataset(path)

    def test_missing_sidecar_is_refused(self, tmp_path):
        path = _write_dataset(
            tmp_path, "sensex", _realistic_frame(), "fyers_api_v3", write_sidecar=False
        )
        with pytest.raises(UnknownProvenanceError):
            assert_real_dataset(path)

    def test_corrupt_sidecar_is_refused_not_ignored(self, tmp_path):
        path = _write_dataset(tmp_path, "sensex", _realistic_frame(), "fyers_api_v3")
        path.with_suffix(".json").write_text("{not json", encoding="utf-8")
        with pytest.raises(UnknownProvenanceError):
            assert_real_dataset(path)

    def test_checksum_mismatch_is_refused(self, tmp_path):
        path = _write_dataset(
            tmp_path,
            "sensex",
            _realistic_frame(),
            "fyers_api_v3",
            checksum_override="0" * 64,
        )
        with pytest.raises(DatasetIntegrityError):
            assert_real_dataset(path)

    def test_declared_row_count_mismatch_is_refused(self, tmp_path):
        path = _write_dataset(
            tmp_path,
            "sensex",
            _realistic_frame(),
            "fyers_api_v3",
            row_count_override=12,
        )
        with pytest.raises(DatasetIntegrityError):
            assert_real_dataset(path)

    def test_real_dataset_is_admitted(self, tmp_path):
        path = _write_dataset(tmp_path, "sensex", _realistic_frame(), "fyers_api_v3")
        report = assert_real_dataset(path)
        assert report.admissible
        assert report.source == "fyers_api_v3"
        assert report.reasons == ()

    def test_self_consistent_fixture_with_real_source_is_still_refused(self, tmp_path):
        """The important one.

        A generated file with a *valid* checksum claiming a real broker source is
        exactly the case that defeated presence-based loading. Only the
        statistical screen can catch it, which is why the screen is not optional.
        """
        path = _write_dataset(tmp_path, "sensex", _generated_frame(), "fyers_api_v3")
        report = check_provenance(path)
        assert not report.admissible
        assert any(r.startswith("simulation_screen") for r in report.reasons)
        with pytest.raises(SyntheticDataError):
            assert_real_dataset(path)

    def test_two_signals_do_not_override_admissible_provenance(self, tmp_path):
        """Refusing real data is as damaging as accepting generated data.

        A continuous index series trips ``open_equals_prior_close`` on its own, so
        overriding a broker's provenance takes three signals, not two.
        """
        path = _write_dataset(tmp_path, "sensex", _borderline_frame(), "fyers_api_v3")
        report = assert_real_dataset(path)
        assert report.admissible
        assert len(report.screen.signals) == 2, report.screen.signals

    def test_two_signals_do_refuse_a_fixture_source(self, tmp_path):
        path = _write_dataset(tmp_path, "sensex", _borderline_frame(), "synthetic_fixture")
        report = check_provenance(path)
        assert not report.admissible
        with pytest.raises(SyntheticDataError):
            assert_real_dataset(path)

    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            assert_real_dataset(tmp_path / "absent.parquet")

    def test_explicit_opt_in_admits_fixture_for_fixture_only_harnesses(self, tmp_path):
        path = _write_dataset(tmp_path, "sensex", _generated_frame(), "synthetic_fixture")
        report = assert_real_dataset(path, allow_synthetic=True)
        assert not report.admissible


# --------------------------------------------------------------------------
# Loader enforcement (the promise `require_real_data=True` was not keeping)
# --------------------------------------------------------------------------


class TestLoaderEnforcement:
    def _loader_dataset(self, tmp_path: Path, frame: pl.DataFrame, source: str) -> Path:
        target = tmp_path / "sensex"
        target.mkdir(parents=True, exist_ok=True)
        return _write_dataset(target, "1m", frame, source)

    def _isolated_loader(self, tmp_path: Path) -> "HistoricalDataLoader":
        """Loader rooted at tmp_path/raw with all lookup roots isolated.

        Isolation matters: the repository now holds real data under
        data/historical/parquet, and an unisolated lookup would find (and then
        provenance-check) repo datasets instead of the fixture under test.
        """
        return HistoricalDataLoader(raw_data_dir=tmp_path / "raw")

    def test_require_real_data_refuses_fixture_parquet(self, tmp_path):
        self._loader_dataset(tmp_path / "raw", _generated_frame(), "synthetic_fixture")
        loader = self._isolated_loader(tmp_path)
        with pytest.raises(SyntheticDataError):
            loader.load_candles_with_source("SENSEX", "1m", require_real_data=True)

    def test_require_real_data_refuses_unverified_parquet(self, tmp_path):
        """A generated parquet claiming a real source must not pass as real."""
        self._loader_dataset(tmp_path / "raw", _generated_frame(), "fyers_api_v3")
        loader = self._isolated_loader(tmp_path)
        with pytest.raises(SyntheticDataError):
            loader.load_candles_with_source("SENSEX", "1m", require_real_data=True)

    def test_require_real_data_accepts_real_parquet(self, tmp_path):
        self._loader_dataset(tmp_path / "raw", _realistic_frame(), "fyers_api_v3")
        loader = self._isolated_loader(tmp_path)
        candles, source = loader.load_candles_with_source("SENSEX", "1m", require_real_data=True)
        assert candles
        assert source.type == "parquet"
        assert source.is_simulated is False

    def test_soft_path_marks_unverified_parquet_as_simulated(self, tmp_path):
        """Backtest paths keep working, but must not claim the data is real."""
        self._loader_dataset(tmp_path / "raw", _generated_frame(), "synthetic_fixture")
        loader = self._isolated_loader(tmp_path)
        candles, source = loader.load_candles_with_source("SENSEX", "1m", require_real_data=False)
        assert candles
        assert source.is_simulated is True
        assert "provenance unverified" in source.note
