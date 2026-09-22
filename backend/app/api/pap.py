"""Price Action Prediction (PAP) research status API.

Serves the Stage 1 research state to the Lab / Signal Centre:

- ``GET /api/v1/pap/status`` — phase gates, pre-registered success/kill
  criteria, data readiness (provenance-verified 1m datasets per instrument),
  FYERS token presence, and any on-disk experiment reports.

Read-only by construction: PAP is shadow-mode research until its
pre-registered PASS verdict exists, so this router deliberately exposes no
run/trigger endpoint. The experiment is executed offline via the research
runner, which writes its report to ``data/experiments/pap/``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter

from app.api.envelope import envelope
from app.core.config import settings as cfg
from app.models.market import DataStatus
from app.quant.data.provenance import check_provenance

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/pap", tags=["pap"])

_PROVIDER = "pap"

#: Versioned pre-registered criteria. Frozen BEFORE the untouched final test
#: is evaluated; modifying them after seeing final-test results invalidates
#: the experiment. Mirrors docs/PAP_IMPLEMENTATION_NOTE.md §5.
PAP_CRITERIA_VERSION = "pap-criteria-v1"
PRE_REGISTERED_CRITERIA: Dict[str, Any] = {
    "primary_metric": "balanced_accuracy_uplift_vs_no_skill",
    "secondary_metric": "macro_f1_uplift_vs_no_skill",
    "min_absolute_uplift": 0.03,
    "stability": "uplift must appear in a majority of valid walk-forward folds, with no dependence on one isolated fold",
    "statistical": "primary out-of-sample uplift 95% confidence interval must exclude zero",
    "economic": "uplift must survive the conservative cost/tradability filter",
    "multiple_comparisons": "one primary hypothesis; regime/session claims only after multiplicity correction",
    "note": "Frozen before final-test evaluation. A null (FAIL) result is a valid research outcome.",
}

#: Evaluation grid per the Stage 1 spec: 3 instruments x 3 horizons.
INSTRUMENTS: List[Dict[str, str]] = [
    {"instrument": "NIFTY", "slug": "nifty"},
    {"instrument": "BANKNIFTY", "slug": "banknifty"},
    {"instrument": "SENSEX", "slug": "sensex"},
]

HORIZONS = ["3m", "5m", "10m"]

DATA_DIR = Path("data/raw")
HIST_DIR = Path("data/historical/parquet")
REPORTS_DIR = Path("data/experiments/pap")


def _dataset_candidates(slug: str) -> List[Path]:
    """Candidate 1m datasets for an instrument, preferred first.

    The Historical Data Module store (data/historical/parquet) is the canonical
    ingestion path; legacy data/raw is still accepted for older datasets.
    """
    hist = sorted((HIST_DIR / slug / "1m").glob("candles_*.parquet"))
    return [*reversed(hist), DATA_DIR / slug / "1m.parquet"]


def _instrument_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for spec in INSTRUMENTS:
        candidates = _dataset_candidates(spec["slug"])
        path = next((c for c in candidates if c.exists()), candidates[-1])
        row: Dict[str, Any] = {
            "instrument": spec["instrument"],
            "slug": spec["slug"],
            "path": str(path),
            "present": path.exists(),
            "admissible": False,
            "source": None,
            "row_count": None,
            "checksum_sha256": None,
            "reasons": [],
            "screen": None,
        }
        if path.exists():
            try:
                prov = check_provenance(path)
                row.update(
                    {
                        "admissible": prov.admissible,
                        "source": prov.source,
                        "row_count": prov.row_count,
                        "checksum_sha256": prov.checksum_sha256,
                        "reasons": list(prov.reasons),
                        "screen": prov.screen.to_dict() if prov.screen is not None else None,
                    }
                )
            except Exception as exc:  # defensive: status must never 500 on one bad file
                logger.warning("pap_provenance_check_failed", path=str(path), error=str(exc))
                row["reasons"] = [f"provenance_check_error: {exc}"]
        rows.append(row)
    return rows


def _report_summaries() -> List[Dict[str, Any]]:
    if not REPORTS_DIR.exists():
        return []
    summaries: List[Dict[str, Any]] = []
    for path in sorted(REPORTS_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("pap_report_unreadable", path=str(path), error=str(exc))
            summaries.append({"file": path.name, "verdict": None, "unreadable": True, "path_mtime": path.stat().st_mtime})
            continue
        created = payload.get("created_at") or payload.get("generated_at")
        summaries.append(
            {
                "file": path.name,
                "verdict": payload.get("verdict"),
                "created": created,
                "criteria_version": payload.get("criteria_version"),
                "experiment_id": payload.get("experiment_id"),
                "path_mtime": path.stat().st_mtime,
            }
        )
    return summaries


def _report_sort_key(summary: Dict[str, Any]) -> float:
    """Newest-report ordering: parsed timestamp when available, else file mtime."""
    created = summary.get("created")
    if isinstance(created, str):
        try:
            return datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    mtime = summary.get("path_mtime")
    return float(mtime) if isinstance(mtime, (int, float)) else 0.0


def _experiment_verdict(summaries: List[Dict[str, Any]]) -> str:
    """Latest readable report decides; unreadable files never fabricate a verdict."""
    readable = [s for s in summaries if s.get("verdict") in ("PASS", "FAIL", "INCONCLUSIVE")]
    if not readable:
        return "NOT_RUN"
    latest = max(readable, key=_report_sort_key)
    return str(latest["verdict"])


def _derive_phase(gates: List[Dict[str, Any]], verdict: str) -> str:
    if verdict == "PASS":
        return "STAGE_2_ALLOWED"
    if verdict == "FAIL":
        return "STAGE_1_COMPLETE_FAIL"
    if verdict == "INCONCLUSIVE":
        return "STAGE_1_INCONCLUSIVE"
    data_gate = next((g for g in gates if g["name"] == "real_1m_data"), None)
    return "STAGE_1_READY" if data_gate is not None and data_gate["passed"] else "STAGE_1_BLOCKED_NO_REAL_DATA"


@router.get("/status")
async def pap_status():
    """Read-only PAP research status: gates, criteria, data readiness, verdict."""
    token_present = bool(cfg.fyers_access_token)
    instruments = _instrument_rows()
    admissible = [r["instrument"] for r in instruments if r["admissible"]]
    missing = [r["instrument"] for r in instruments if not r["admissible"]]

    reports = _report_summaries()
    verdict = _experiment_verdict(reports)

    gates = [
        {
            "name": "fyers_credentials",
            "passed": token_present,
            "detail": (
                "FYERS access token present."
                if token_present
                else "FYERS_ACCESS_TOKEN empty — generate via /api/v1/tokens/fyers/login (expires daily)."
            ),
        },
        {
            "name": "real_1m_data",
            "passed": len(admissible) == len(INSTRUMENTS),
            "detail": (
                "All instruments have provenance-verified 1m data."
                if len(admissible) == len(INSTRUMENTS)
                else f"Provenance-admissible: {', '.join(admissible) if admissible else 'none'}. Missing/refused: {', '.join(missing)}."
            ),
        },
        {
            "name": "experiment_report",
            "passed": verdict != "NOT_RUN",
            "detail": (
                f"Experiment verdict: {verdict}."
                if verdict != "NOT_RUN"
                else f"No experiment report in {REPORTS_DIR} yet."
            ),
        },
    ]

    payload = {
        "phase": _derive_phase(gates, verdict),
        "verdict": verdict,
        "criteria_version": PAP_CRITERIA_VERSION,
        "pre_registered": PRE_REGISTERED_CRITERIA,
        "gates": gates,
        "instruments": instruments,
        "token_present": token_present,
        "horizons": HORIZONS,
        "reports": reports,
    }
    return envelope(payload, provider=_PROVIDER, status=DataStatus.OFFLINE)
