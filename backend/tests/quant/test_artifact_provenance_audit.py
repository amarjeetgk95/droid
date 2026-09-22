"""Tests for the artifact provenance audit's verdict logic.

The audit exists because trained artifacts in this repository trace back to a
100% synthetic candidate dataset, and the drift monitor certified it as STABLE.
Its verdicts must therefore be conservative: an unresolved artifact is
UNVERIFIABLE, never OK.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.audit_artifact_provenance import (  # noqa: E402
    V_OK,
    V_SYNTHETIC,
    V_UNVERIFIABLE,
    ArtifactRecord,
    DatasetRecord,
    _match,
    _verdict,
    _markdown,
)


def _dataset(**kwargs) -> DatasetRecord:
    base = dict(path="data/ml_datasets/candidates_v3.parquet", rows=1669)
    base.update(kwargs)
    return DatasetRecord(**base)


class TestSyntheticDetection:
    def test_fidelity_column_alone_is_enough(self):
        d = _dataset(fidelity={"SYNTHETIC": 1669}, admissible=False, source="unknown")
        assert d.synthetic

    def test_fixture_source_is_enough(self):
        d = _dataset(source="synthetic_fixture", reasons=("fixture_source: synthetic_fixture",))
        assert d.synthetic

    def test_missing_sidecar_counts_as_synthetic_for_matching(self):
        """Unknown provenance cannot be treated as clean when resolving coverage."""
        d = _dataset(reasons=("no_sidecar",))
        assert d.synthetic

    def test_real_data_with_only_a_screen_reason_is_not_called_synthetic(self):
        """A screen hit alone does not override an admissible broker source."""
        d = _dataset(source="fyers_api_v3", admissible=False, reasons=("simulation_screen(3/3): x",))
        assert not d.synthetic


class TestMatching:
    def test_unique_row_count_match_resolves(self):
        datasets = [_dataset(rows=1669), _dataset(path="other.parquet", rows=500)]
        assert _match(1669, datasets).path == "data/ml_datasets/candidates_v3.parquet"

    def test_ambiguous_row_count_is_not_evidence(self):
        datasets = [_dataset(rows=100), _dataset(path="other.parquet", rows=100)]
        assert _match(100, datasets) is None

    def test_absent_row_count_and_no_match_resolve_to_none(self):
        assert _match(None, [_dataset()]) is None
        assert _match(120, [_dataset(rows=1669)]) is None


class TestVerdicts:
    def test_synthetic_dataset_yields_synthetic(self):
        artifact = ArtifactRecord(path="meta.json", n_samples=1669)
        assert _verdict(artifact, _dataset(fidelity={"SYNTHETIC": 1669})) == V_SYNTHETIC

    def test_admissible_dataset_yields_ok(self):
        artifact = ArtifactRecord(path="meta.json", n_samples=100)
        dataset = _dataset(rows=100, admissible=True, source="fyers_api_v3")
        assert _verdict(artifact, dataset) == V_OK

    def test_unresolved_artifact_is_never_ok(self):
        artifact = ArtifactRecord(path="meta_h60.json", n_samples=120)
        assert _verdict(artifact, None) == V_UNVERIFIABLE

    def test_unverifiable_dataset_provenance_is_not_ok(self):
        artifact = ArtifactRecord(path="meta.json", n_samples=100)
        dataset = _dataset(rows=100, admissible=False, reasons=("checksum_mismatch",))
        assert _verdict(artifact, dataset) == V_UNVERIFIABLE


def test_markdown_renders_verdicts_and_disclaims_unverifiable():
    report = {
        "generated_by": "scripts/audit_artifact_provenance.py",
        "verdict_counts": {V_SYNTHETIC: 1, V_UNVERIFIABLE: 1},
        "artifacts": [
            {
                "artifact": "meta.json",
                "n_samples": 1669,
                "verdict": V_SYNTHETIC,
                "resolved_dataset": "data/ml_datasets/candidates_v3.parquet",
                "dataset_fidelity": {"SYNTHETIC": 1669},
            }
        ],
        "datasets": [
            {
                "path": "data/ml_datasets/candidates_v3.parquet",
                "rows": 1669,
                "admissible": False,
                "source": "unknown",
                "reasons": ["no_sidecar"],
            }
        ],
        "note": "not a clean bill of health",
    }
    rendered = _markdown(report)
    assert "**SYNTHETIC**: 1" in rendered
    assert "not a clean bill of health" in rendered
    assert "candidates_v3.parquet" in rendered


def test_audit_runs_against_the_repository_without_raising():
    """The audit is a diagnostic; it must survive missing or unreadable inputs."""
    from scripts.audit_artifact_provenance import audit

    report = audit()
    assert "artifacts" in report and "datasets" in report
    for row in report["artifacts"]:
        assert row["verdict"] in (V_SYNTHETIC, V_UNVERIFIABLE, V_OK)
