"""Resolve trained artifacts to their datasets and report whether those datasets are real.

Why this exists
---------------
Every model under ``app/ml/artifacts`` was trained before dataset provenance was
enforced. In this repository that matters concretely:

* ``data/ml_datasets/candidates_v3.parquet`` is 100% ``data_fidelity == 'SYNTHETIC'``;
* ``app/ml/artifacts/meta.json`` records ``n_samples: 1669``, exactly that file's
  row count, and reports 3-class accuracy 0.3892;
* ``app/ml/artifacts/daily_settlement_report.json`` reports
  ``total_records_evaluated: 1669``, ``status: STABLE``, ``retrain_recommended:
  false`` — the drift monitor certified a simulator as healthy;
* ``promotion_audit.jsonl`` records two promotions of models built this way.

Recording provenance is not enough. This audit *resolves* artifact → dataset and
states a verdict, so a prior result can be trusted, flagged, or withdrawn rather
than silently inherited.

Usage:
    python scripts/audit_artifact_provenance.py

Writes ``data/experiments/artifact_provenance_audit.json`` and ``.md``.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.quant.data.provenance import check_provenance  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parent.parent

DATASET_GLOBS = (
    "data/datasets/*.parquet",
    "data/raw/*/*.parquet",
    "data/ml_datasets/*.parquet",
    "data/fixtures/*/*.parquet",
)
ARTIFACT_DIR = BACKEND_ROOT / "app" / "ml" / "artifacts"

#: Verdicts, ordered by severity.
V_SYNTHETIC = "SYNTHETIC"
V_UNVERIFIABLE = "UNVERIFIABLE"
V_OK = "OK"


@dataclass
class DatasetRecord:
    path: str
    rows: int
    fidelity: dict[str, int] = field(default_factory=dict)
    admissible: bool = False
    source: str = "unknown"
    reasons: tuple[str, ...] = ()

    @property
    def synthetic(self) -> bool:
        if self.reasons_except_screen:
            return True
        return bool(self.fidelity) and set(self.fidelity) <= {"SYNTHETIC", "SIMULATED"}

    @property
    def reasons_except_screen(self) -> tuple[str, ...]:
        return tuple(
            r for r in self.reasons if r.startswith(("fixture_source", "no_sidecar", "unknown_source"))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "rows": self.rows,
            "fidelity": self.fidelity,
            "admissible": self.admissible,
            "source": self.source,
            "reasons": list(self.reasons),
            "synthetic": self.synthetic,
        }


@dataclass
class ArtifactRecord:
    path: str
    trained_at: Optional[str] = None
    n_samples: Optional[int] = None
    model_version: Optional[str] = None
    target_spec_version: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


def iter_datasets() -> Iterator[DatasetRecord]:
    seen: set[Path] = set()
    for pattern in DATASET_GLOBS:
        for path in sorted(BACKEND_ROOT.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            yield _inspect_dataset(path)


def _inspect_dataset(path: Path) -> DatasetRecord:
    report = check_provenance(path)
    rows = 0
    fidelity: dict[str, int] = {}
    try:
        frame = pl.read_parquet(path)
        rows = len(frame)
        if "data_fidelity" in frame.columns:
            counts = frame["data_fidelity"].value_counts()
            for row in counts.iter_rows(named=True):
                value = row["data_fidelity"]
                fidelity[str(value)] = int(row["count"])
    except Exception as exc:  # noqa: BLE001 - an unreadable dataset is reported, not skipped
        fidelity = {"<unreadable>": 0}
        report_reasons = report.reasons + (f"unreadable: {exc}",)
        return DatasetRecord(
            path=str(path.relative_to(BACKEND_ROOT)),
            rows=rows,
            fidelity=fidelity,
            admissible=False,
            source=report.source,
            reasons=report_reasons,
        )

    return DatasetRecord(
        path=str(path.relative_to(BACKEND_ROOT)),
        rows=rows,
        fidelity=fidelity,
        admissible=report.admissible,
        source=report.source,
        reasons=report.reasons,
    )


def iter_artifacts() -> Iterator[ArtifactRecord]:
    for path in sorted(ARTIFACT_DIR.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue

        rel = str(path.relative_to(BACKEND_ROOT))
        yield ArtifactRecord(
            path=rel,
            trained_at=payload.get("trained_at"),
            n_samples=payload.get("n_samples") or payload.get("total_records_evaluated"),
            model_version=payload.get("model_version"),
            target_spec_version=payload.get("target_spec_version"),
            extra={
                key: payload[key]
                for key in (
                    "ensemble_accuracy",
                    "xgb_accuracy",
                    "status",
                    "action_taken",
                    "retrain_recommended",
                    "feature_schema_version",
                    "n_features",
                    "horizon_minutes",
                )
                if key in payload
            },
        )

    registry = ARTIFACT_DIR / "registry.jsonl"
    if registry.exists():
        for line in registry.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            yield ArtifactRecord(
                path=f"{registry.relative_to(BACKEND_ROOT)}::{payload.get('model_version', '?')}",
                model_version=payload.get("model_version"),
                target_spec_version=payload.get("target_spec"),
                extra={"decision": payload.get("decision"), "dataset_hash": payload.get("dataset_hash")},
            )


def _match(n_samples: Optional[int], datasets: list[DatasetRecord]) -> Optional[DatasetRecord]:
    if n_samples is None:
        return None
    matches = [d for d in datasets if d.rows == int(n_samples)]
    if len(matches) == 1:
        return matches[0]
    # Ambiguous row-count matches are not evidence; require a single candidate.
    return None


def _verdict(artifact: ArtifactRecord, dataset: Optional[DatasetRecord]) -> str:
    if dataset is None:
        return V_UNVERIFIABLE
    if dataset.synthetic:
        return V_SYNTHETIC
    if dataset.admissible:
        return V_OK
    return V_UNVERIFIABLE


def audit() -> dict[str, Any]:
    datasets = list(iter_datasets())
    artifacts = list(iter_artifacts())

    rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        dataset = _match(artifact.n_samples, datasets)
        rows.append(
            {
                "artifact": artifact.path,
                "trained_at": artifact.trained_at,
                "n_samples": artifact.n_samples,
                "model_version": artifact.model_version,
                "target_spec_version": artifact.target_spec_version,
                "resolved_dataset": dataset.path if dataset else None,
                "dataset_source": dataset.source if dataset else None,
                "dataset_fidelity": dataset.fidelity if dataset else None,
                "verdict": _verdict(artifact, dataset),
                **artifact.extra,
            }
        )

    order = {V_SYNTHETIC: 0, V_UNVERIFIABLE: 1, V_OK: 2}
    rows.sort(key=lambda r: (order.get(r["verdict"], 3), r["artifact"]))

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    return {
        "generated_by": "scripts/audit_artifact_provenance.py",
        "artifacts": rows,
        "verdict_counts": counts,
        "datasets": [d.to_dict() for d in datasets],
        "note": (
            "SYNTHETIC means the artifact's sample count resolves uniquely to a dataset "
            "whose provenance is a fixture or whose data_fidelity is SYNTHETIC. "
            "UNVERIFIABLE means no dataset could be resolved with confidence — that is not "
            "a clean bill of health."
        ),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Artifact Provenance Audit",
        "",
        f"Generated by `{report['generated_by']}`.",
        "",
        "## Verdict summary",
        "",
    ]
    for verdict, count in sorted(report["verdict_counts"].items()):
        lines.append(f"- **{verdict}**: {count}")
    lines += ["", "## Artifacts", "", "| Artifact | n_samples | Verdict | Dataset | Dataset fidelity |", "|---|---:|---|---|---|"]
    for row in report["artifacts"]:
        lines.append(
            f"| `{row['artifact']}` | {row['n_samples']} | **{row['verdict']}** | "
            f"`{row['resolved_dataset'] or '—'}` | {row['dataset_fidelity'] or '—'} |"
        )

    lines += ["", "## Datasets", "", "| Dataset | Rows | Admissible | Source | Reasons |", "|---|---:|---|---|---|"]
    for dataset in report["datasets"]:
        lines.append(
            f"| `{dataset['path']}` | {dataset['rows']} | {dataset['admissible']} | "
            f"`{dataset['source']}` | {'; '.join(dataset['reasons']) or '—'} |"
        )
    lines += ["", report["note"], ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit artifact to dataset provenance.")
    parser.add_argument(
        "--out-dir",
        default=str(BACKEND_ROOT / "data" / "experiments"),
        help="Directory for the JSON and Markdown reports",
    )
    args = parser.parse_args()

    report = audit()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "artifact_provenance_audit.json"
    md_path = out_dir / "artifact_provenance_audit.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")

    print(json.dumps(report["verdict_counts"], indent=2))
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
