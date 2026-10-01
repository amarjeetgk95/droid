"""Price Action Prediction (PAP) research status API.

Serves the Stage 1 research state to the Lab / Signal Centre:

- ``GET /api/v1/pap/status`` â€” phase gates, pre-registered success/kill
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
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import envelope
from app.core.config import settings as cfg
from app.core.database import get_db_session
from app.models.market import DataStatus
from app.market_core.data.provenance import check_provenance

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/pap", tags=["pap"])

_PROVIDER = "pap"

#: Versioned pre-registered criteria. Frozen BEFORE the untouched final test
#: is evaluated; modifying them after seeing final-test results invalidates
#: the experiment. Mirrors docs/PAP_IMPLEMENTATION_NOTE.md Â§5.
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


@router.get("/live/{instrument}/horizons")
async def pap_live_horizons(instrument: str):
    """Multi-horizon slice only (3m/5m/10m distributions)."""
    from app.services import pap_service

    try:
        payload = await pap_service.get_pap_live(instrument)
    except pap_service.PapUnavailable as exc:
        return envelope(
            pap_service.unavailable_payload(instrument, exc.code, exc.detail),
            provider=_PROVIDER,
            status=DataStatus.OFFLINE,
        )
    return envelope(
        {
            "instrument": payload["instrument"],
            "timestamp": payload["timestamp"],
            "price": payload["price"],
            "data_status": payload["data_status"],
            "data_age_s": payload["data_age_s"],
            "available": payload["available"],
            "horizons": payload["horizons"],
            "horizon_consensus": payload["horizon_consensus"],
        },
        provider=_PROVIDER,
        status=DataStatus.LIVE if payload["data_status"] == "LIVE" else DataStatus.STALE,
    )


@router.get("/live/{instrument}")
async def pap_live(instrument: str):
    """Live PAP Intelligence payload from real market data (shadow only).

    Never fabricates: missing quotes/candles yield ``available=false`` with
    an explicit reason instead of zero-filled horizons.
    """
    from app.services import pap_service

    try:
        payload = await pap_service.get_pap_live(instrument)
    except pap_service.PapUnavailable as exc:
        return envelope(
            pap_service.unavailable_payload(instrument, exc.code, exc.detail),
            provider=_PROVIDER,
            status=DataStatus.OFFLINE,
        )
    return envelope(
        payload,
        provider=_PROVIDER,
        status=DataStatus.LIVE if payload["data_status"] == "LIVE" else DataStatus.STALE,
    )


def _research_db_guard(session: AsyncSession | None):
    if session is None:
        return envelope(
            {
                "status": "INSUFFICIENT_SAMPLE",
                "n": 0,
                "reason": "Prediction ledger database is not configured â€” no settled PAP rows to evaluate.",
            },
            provider=_PROVIDER,
            status=DataStatus.OFFLINE,
        )
    return None


@router.get("/research/summary")
async def pap_research_summary(
    instrument: str | None = Query(default=None),
    horizon_minutes: int | None = Query(default=None),
    session: AsyncSession | None = Depends(get_db_session),
):
    """PAP vs baseline predictive performance + walk-forward verdict."""
    from app.services import pap_research

    guard = _research_db_guard(session)
    if guard is not None:
        return guard
    assert session is not None
    rows = await pap_research.fetch_predictions(
        session, instrument=instrument, horizon=horizon_minutes, settled_only=True, limit=2000
    )
    dicts = [pap_research.row_to_dict(r) for r in rows]
    payload = pap_research.summarize(dicts)
    payload["filters"] = {"instrument": instrument, "horizon_minutes": horizon_minutes}
    counts = await pap_research.research_counts(session)
    payload["ledger"] = counts
    return envelope(payload, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/research/predictions")
async def pap_research_predictions(
    instrument: str | None = Query(default=None),
    horizon_minutes: int | None = Query(default=None),
    outcome: str | None = Query(default=None, description="correct | incorrect"),
    prediction: str | None = Query(default=None, description="UP | DOWN | NEUTRAL"),
    min_confidence: float | None = Query(default=None, ge=0.0, le=100.0),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession | None = Depends(get_db_session),
):
    """Interactive prediction-vs-actual ledger rows with honest filters."""
    from app.services import pap_research

    guard = _research_db_guard(session)
    if guard is not None:
        return guard
    assert session is not None
    rows = await pap_research.fetch_predictions(
        session, instrument=instrument, horizon=horizon_minutes, limit=limit * 2
    )
    dicts = [pap_research.row_to_dict(r) for r in rows]
    pred = (prediction or "").upper() or None
    if pred not in (None, "UP", "DOWN", "NEUTRAL"):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="prediction must be UP, DOWN or NEUTRAL")
    out = []
    for d in dicts:
        if outcome == "correct" and d.get("correct") is not True:
            continue
        if outcome == "incorrect" and d.get("correct") is not False:
            continue
        if pred and d.get("prediction") != pred:
            continue
        if min_confidence is not None and float(d.get("confidence") or 0.0) < min_confidence:
            continue
        out.append(d)
        if len(out) >= limit:
            break
    return envelope(
        {
            "rows": out,
            "count": len(out),
            "filters": {
                "instrument": instrument,
                "horizon_minutes": horizon_minutes,
                "outcome": outcome,
                "prediction": pred,
                "min_confidence": min_confidence,
            },
            "notes": "MFE/MAE are not tracked by the prediction ledger and return null (never zero).",
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.get("/research/calibration")
async def pap_research_calibration(
    instrument: str | None = Query(default=None),
    horizon_minutes: int | None = Query(default=None),
    session: AsyncSession | None = Depends(get_db_session),
):
    """Predicted probability vs observed frequency buckets."""
    from app.services import pap_research

    guard = _research_db_guard(session)
    if guard is not None:
        return guard
    assert session is not None
    rows = await pap_research.fetch_predictions(
        session, instrument=instrument, horizon=horizon_minutes, settled_only=True, limit=2000
    )
    dicts = [pap_research.row_to_dict(r) for r in rows]
    payload = pap_research.calibration_buckets(dicts)
    payload["filters"] = {"instrument": instrument, "horizon_minutes": horizon_minutes}
    return envelope(payload, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/research/regimes")
async def pap_research_regimes(
    instrument: str | None = Query(default=None),
    horizon_minutes: int | None = Query(default=None),
    session: AsyncSession | None = Depends(get_db_session),
):
    """Performance grouped by recorded market regime."""
    from app.services import pap_research

    guard = _research_db_guard(session)
    if guard is not None:
        return guard
    assert session is not None
    rows = await pap_research.fetch_predictions(
        session, instrument=instrument, horizon=horizon_minutes, settled_only=True, limit=2000
    )
    dicts = [pap_research.row_to_dict(r) for r in rows]
    return envelope(
        {
            "regimes": pap_research.group_by(dicts, "market_regime"),
            "filters": {"instrument": instrument, "horizon_minutes": horizon_minutes},
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.get("/research/sessions")
async def pap_research_sessions(
    instrument: str | None = Query(default=None),
    horizon_minutes: int | None = Query(default=None),
    session: AsyncSession | None = Depends(get_db_session),
):
    """Performance grouped by IST intraday session window."""
    from app.services import pap_research

    guard = _research_db_guard(session)
    if guard is not None:
        return guard
    assert session is not None
    rows = await pap_research.fetch_predictions(
        session, instrument=instrument, horizon=horizon_minutes, settled_only=True, limit=2000
    )
    dicts = [pap_research.row_to_dict(r) for r in rows]
    return envelope(
        {
            "sessions": pap_research.group_by(dicts, "session"),
            "filters": {"instrument": instrument, "horizon_minutes": horizon_minutes},
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.get("/research/chart")
async def pap_research_chart(
    instrument: str = Query(default="NIFTY"),
    horizon_minutes: int | None = Query(default=None),
    limit: int = Query(default=200, ge=10, le=500),
    session: AsyncSession | None = Depends(get_db_session),
):
    """1m candles with PAP prediction markers joined by timestamp.

    Candles come from the market-data stack; markers from the append-only
    prediction ledger. An empty marker list means no predictions were
    recorded for the slice â€” never synthesized markers.
    """
    from app.services import pap_research
    from app.services.market_service import MarketService

    underlying = (instrument or "").upper().replace(" 50", "")
    market = MarketService()
    try:
        candles = await market.get_candles(underlying, timeframe="1m")
    except Exception as exc:
        return envelope(
            {
                "status": "INSUFFICIENT_SAMPLE",
                "reason": f"1m candles unavailable for {underlying}: {exc}",
                "candles": [],
                "markers": [],
            },
            provider=_PROVIDER,
            status=DataStatus.OFFLINE,
        )
    tail = (candles or [])[-limit:]
    out_candles = []
    for c in tail:
        try:
            ts = c.timestamp
            epoch = int(ts.timestamp()) if hasattr(ts, "timestamp") else None
            if epoch is None:
                continue
            out_candles.append(
                {
                    "time": epoch,
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                }
            )
        except Exception:
            continue
    if not out_candles:
        return envelope(
            {
                "status": "INSUFFICIENT_SAMPLE",
                "reason": f"No 1m candles for {underlying}.",
                "candles": [],
                "markers": [],
            },
            provider=_PROVIDER,
            status=DataStatus.OFFLINE,
        )
    markers: list[dict] = []
    if session is not None:
        try:
            rows = await pap_research.fetch_predictions(
                session, instrument=underlying, horizon=horizon_minutes, limit=500
            )
            candle_times = sorted(c["time"] for c in out_candles)
            for r in rows:
                d = pap_research.row_to_dict(r)
                if not d.get("time"):
                    continue
                try:
                    from datetime import datetime as _dt

                    pred_epoch = int(_dt.fromisoformat(d["time"]).timestamp())
                except Exception:
                    continue
                # Join to the nearest rendered candle (<=90s) â€” never invent one.
                nearest = min(candle_times, key=lambda t: abs(t - pred_epoch))
                if abs(nearest - pred_epoch) > 90:
                    continue
                markers.append(
                    {
                        "time": nearest,
                        "prediction": d.get("prediction"),
                        "horizon": d.get("horizon"),
                        "p_up": d.get("p_up"),
                        "p_neutral": d.get("p_neutral"),
                        "p_down": d.get("p_down"),
                        "actual": d.get("actual"),
                        "correct": d.get("correct"),
                        "price_change_pct": d.get("price_change_pct"),
                        "confidence": d.get("confidence"),
                    }
                )
        except Exception as exc:
            logger.warning("pap_chart_markers_failed", error=str(exc))
    markers.sort(key=lambda m: m["time"])
    return envelope(
        {
            "status": "OK" if markers else "INSUFFICIENT_SAMPLE",
            "reason": None if markers else "No ledger predictions join to this candle window.",
            "instrument": underlying,
            "horizon_minutes": horizon_minutes,
            "candles": out_candles,
            "markers": markers,
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.get("/research/ablation")
async def pap_research_ablation():
    """Feature ablation â€” no backend ablation experiment exists yet."""
    return envelope(
        {
            "status": "NOT_AVAILABLE",
            "reason": "No feature-ablation experiment has been executed by the research pipeline.",
            "experiments": [],
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.get("/research/tradability")
async def pap_research_tradability():
    """Cost-adjusted tradability â€” no backend cost model exists yet."""
    return envelope(
        {
            "status": "NOT_AVAILABLE",
            "reason": "PAP predicts index direction only; no backend execution-cost / spread / slippage model exists, so no cost-adjusted expectancy is reported.",
            "expected_move_pct": None,
            "estimated_cost_pct": None,
            "net_expectancy_pct": None,
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.get("/status")
async def pap_status():
    """Read-only PAP research status: gates, criteria, data readiness, verdict."""
    token_present = False
    token = (cfg.fyers_access_token or "").strip().strip("\"'")
    if not token:
        token_file = Path(".fyers_token")
        if token_file.exists():
            try:
                token = token_file.read_text(encoding="utf-8").strip()
            except Exception:
                token = ""
    token_present = bool(token) and "placeholder" not in token.lower()
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
                else "FYERS_ACCESS_TOKEN empty â€” generate via /api/v1/tokens/fyers/login (expires daily)."
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
