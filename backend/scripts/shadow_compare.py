"""Shadow comparison report for 1H forecast v2.3 (P3-1).

Reads SETTLED pairs (``research_predictions`` + ``research_prediction_outcomes``)
for ``trend_forecast_1h`` (v1) vs ``trend_forecast_1h_v2`` (v2 candidate) and
emits a side-by-side markdown + JSON report:

    python backend/scripts/shadow_compare.py \\
        --instruments "NIFTY 50,BANKNIFTY" --min-settleable 250 \\
        --max-days 14 --out shadow.md+json

Metrics per side: hit-rate + Wilson95, Brier, ECE(10) + reliability table,
log-loss, DQ failure rate (+ data_quality/status breakdowns), latency
(``created_at - timestamp`` when both exist), per-regime / per-session
splits. Economics is DIAGNOSTIC ONLY (reference costs ``ref-v1`` provenance
recorded; no fills invented, no promotion decided here).

Minimum-evidence gate (plan P3-1: "2 weeks OR 250 settleable, whichever is
stronger evidence"): the report warns (``evidence.sufficient=false``) only
when BOTH bars are missed — ``n_pair < --min-settleable AND days < --max-days``
where ``n_pair = min(n_v1, n_v2)``. Meeting either bar is sufficient.

Stdlib + repo modules only. Never synthesizes data: without a configured
database the CLI exits non-zero; rows without outcomes are excluded (and
counted) rather than guessed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass

INDICATOR_V1 = "trend_forecast_1h"
INDICATOR_V2 = "trend_forecast_1h_v2"

_DIR_TO_IDX = {"BEARISH": 0, "NEUTRAL": 1, "BULLISH": 2}


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------

def parse_instruments(raw: str) -> List[str]:
    """Split --instruments on commas, dropping empties (order preserved)."""
    return [p.strip() for p in str(raw or "").split(",") if p.strip()]


def resolve_out_paths(raw: str) -> Tuple[Path, Path]:
    """Map --out to (md_path, json_path), supporting 'report.md+json'."""
    text = (raw or "").strip() or "shadow.md"
    if "+" in text:
        base = text.split("+")[0].strip()
        base = base.replace(".json", "").replace(".md", "").strip() or "shadow"
        return Path(base + ".md"), Path(base + ".json")
    if text.endswith(".md"):
        return Path(text), Path(text[: -len(".md")] + ".json")
    if text.endswith(".json"):
        stem = text[: -len(".json")]
        return Path(stem + ".md"), Path(text)
    return Path(text + ".md"), Path(text + ".json")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Shadow v1-vs-v2 comparison (P3-1).")
    p.add_argument("--instruments", default="NIFTY 50,BANKNIFTY",
                   help='Comma-separated instruments, e.g. "NIFTY 50,BANKNIFTY".')
    p.add_argument("--min-settleable", type=int, default=250,
                   help="Minimum settled pairs evidencing a side (default 250).")
    p.add_argument("--max-days", type=float, default=14,
                   help="Minimum calendar days of shadow coverage (default 14).")
    p.add_argument("--out", default="shadow.md+json",
                   help='"shadow.md+json" writes shadow.md + shadow.json.')
    return p


# ---------------------------------------------------------------------------
# Row extraction (pure; tolerant of DB/JSON shapes)
# ---------------------------------------------------------------------------

def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _parse_dt(value: Any) -> Optional[datetime]:
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str) and value.strip():
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        else:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def extract_probs(pred_row: Dict[str, Any]) -> Optional[List[float]]:
    """[P(bear), P(neut), P(bull)] or None when missing/invalid."""
    row = pred_row or {}
    candidates: List[Any] = []
    cv = _as_dict(row.get("component_values"))
    if isinstance(cv.get("probabilities"), dict):
        candidates.append(cv["probabilities"])
    if isinstance(row.get("probabilities"), dict):
        candidates.append(row["probabilities"])
    for probs in candidates:
        try:
            low = {str(k).lower(): v for k, v in probs.items()}
            vals = [float(low["bearish"]), float(low["neutral"]), float(low["bullish"])]
        except (KeyError, TypeError, ValueError):
            continue
        if any(v != v or v < 0.0 or v > 1.0 for v in vals):
            continue
        s = sum(vals)
        if not s > 0:
            continue
        return [v / s for v in vals]
    return None


def extract_regime(pred_row: Dict[str, Any]) -> str:
    row = pred_row or {}
    for key in ("regime",):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    cv = _as_dict(row.get("component_values"))
    for key in ("regime",):
        v = cv.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    snap = _as_dict(row.get("snapshot_features"))
    v2 = _as_dict(snap.get("v2"))
    for src in (v2, snap):
        v = src.get("regime")
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    return "UNKNOWN"


def extract_session(pred_row: Dict[str, Any]) -> str:
    row = pred_row or {}
    v = row.get("session")
    if isinstance(v, str) and v.strip():
        return v.strip().upper()
    cv = _as_dict(row.get("component_values"))
    v = cv.get("session")
    if isinstance(v, str) and v.strip():
        return v.strip().upper()
    snap = _as_dict(row.get("snapshot_features"))
    v2 = _as_dict(snap.get("v2"))
    for src in (v2, snap):
        vv = src.get("session")
        if isinstance(vv, str) and vv.strip():
            return vv.strip().upper()
    return "UNKNOWN"


def extract_dq_status(pred_row: Dict[str, Any]) -> Tuple[str, str]:
    """(data_quality, status) upper-cased, defaults ("UNKNOWN", "UNKNOWN")."""
    row = pred_row or {}
    cv = _as_dict(row.get("component_values"))
    dq = row.get("data_quality", cv.get("data_quality", "UNKNOWN"))
    st = row.get("status", cv.get("status", "UNKNOWN"))
    try:
        dq_s = str(dq).strip().upper() or "UNKNOWN"
    except Exception:
        dq_s = "UNKNOWN"
    try:
        st_s = str(st).strip().upper() or "UNKNOWN"
    except Exception:
        st_s = "UNKNOWN"
    return dq_s, st_s


def latency_sec(pred_row: Dict[str, Any]) -> Optional[float]:
    """created_at - timestamp in seconds, or None when either is missing."""
    ts = _parse_dt((pred_row or {}).get("timestamp"))
    created = _parse_dt((pred_row or {}).get("created_at"))
    if ts is None or created is None:
        return None
    try:
        return (created - ts).total_seconds()
    except Exception:
        return None


def direction_to_idx(value: Any) -> Optional[int]:
    try:
        key = getattr(value, "value", value)
        return _DIR_TO_IDX.get(str(key).strip().upper())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Math (pure; canonical repo metrics with stdlib fallbacks)
# ---------------------------------------------------------------------------

def wilson95(successes: int, total: int) -> List[float]:
    """Wilson 95% CI in percent [lo, hi]; stdlib fallback included."""
    try:
        from app.research.validation.statistical_evaluator import StatisticalEvaluator

        lo, hi = StatisticalEvaluator.calculate_confidence_interval(int(successes), int(total))
        return [float(lo), float(hi)]
    except Exception:
        pass
    if total <= 0:
        return [0.0, 0.0]
    z = 1.96
    p = successes / total
    den = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / den
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / den
    return [round(max(0.0, center - margin) * 100.0, 2),
            round(min(1.0, center + margin) * 100.0, 2)]


def _calibration_triplet(
    y_idx: List[int], P_rows: List[List[float]]
) -> Tuple[float, float, float, List[Dict[str, Any]]]:
    """(brier, log_loss, ece, reliability_bins) via canonical metrics."""
    if not y_idx or not P_rows:
        return 0.0, 0.0, 0.0, []
    try:
        from app.ml.calibration_metrics import (
            brier_score_3class as _brier,
            ece_equal_width as _ece,
            log_loss_3class as _ll,
        )

        brier = float(_brier(y_idx, P_rows))
        ll = float(_ll(y_idx, P_rows))
        pmax = [max(r) for r in P_rows]
        y_pred = [max(range(3), key=lambda k: r[k]) for r in P_rows]
        out = _ece(y_idx, pmax, 10, y_pred)
        return brier, ll, float(out["ece"]), list(out["bins"])
    except Exception:
        pass
    # stdlib fallback (same definitions as calibration_metrics).
    n = len(y_idx)
    brier = sum(
        (r[k] - (1.0 if k == t else 0.0)) ** 2 for t, r in zip(y_idx, P_rows) for k in range(3)
    ) / n
    ll = sum(-math.log(min(1.0, max(r[t], 1e-12))) for t, r in zip(y_idx, P_rows)) / n
    return float(brier), float(ll), 0.0, []


def _percentiles(xs: List[float]) -> Dict[str, Any]:
    if not xs:
        return {"n": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0}
    ordered = sorted(xs)
    n = len(ordered)
    mean = sum(ordered) / n
    p50 = ordered[min(n - 1, n // 2)]
    p95 = ordered[min(n - 1, int(math.ceil(0.95 * n)) - 1)]
    return {"n": n, "mean": round(mean, 3), "p50": round(float(p50), 3), "p95": round(float(p95), 3)}


def build_side_rows(
    pred_rows: List[Dict[str, Any]],
    outcome_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Join predictions to outcomes; rows without outcomes are dropped.

    Each row: {prediction_id, y_true (idx|None), probs ([bear,neut,bull]|None),
    y_pred, pmax, correct, confidence, regime, session, dq, status, latency}.
    """
    rows: List[Dict[str, Any]] = []
    for pred in pred_rows or []:
        pid = (pred or {}).get("prediction_id")
        outcome = (outcome_by_id or {}).get(pid)
        if not isinstance(outcome, dict):
            continue
        correct = outcome.get("is_correct")
        if not isinstance(correct, bool):
            continue
        probs = extract_probs(pred)
        y_true = direction_to_idx(outcome.get("actual_direction"))
        if probs is not None:
            y_pred = max(range(3), key=lambda k: probs[k])
            pmax = max(probs)
        else:
            y_pred, pmax = None, None
        try:
            confidence = float((pred or {}).get("confidence") or (pmax if pmax is not None else 0.0))
        except (TypeError, ValueError):
            confidence = float(pmax) if pmax is not None else 0.0
        dq, status = extract_dq_status(pred)
        rows.append({
            "prediction_id": pid,
            "timestamp": (pred or {}).get("timestamp"),
            "y_true": y_true,
            "probs": probs,
            "y_pred": y_pred,
            "pmax": pmax,
            "correct": bool(correct),
            "confidence": confidence,
            "regime": extract_regime(pred),
            "session": extract_session(pred),
            "dq": dq,
            "status": status,
            "latency": latency_sec(pred),
        })
    return rows


def summarize_side(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate one side's settled rows (pure)."""
    rows = list(rows or [])
    n = len(rows)
    hits = sum(1 for r in rows if r.get("correct"))
    hit_rate = round(hits / n * 100.0, 2) if n else 0.0

    cal = [r for r in rows if r.get("probs") is not None and r.get("y_true") in (0, 1, 2)]
    y_idx = [int(r["y_true"]) for r in cal]
    P_rows = [list(r["probs"]) for r in cal]
    brier, ll, ece, bins = _calibration_triplet(y_idx, P_rows)

    dq_fail = sum(1 for r in rows if str(r.get("dq") or "").upper() != "HEALTHY")
    dq_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    for r in rows:
        dq_counts[str(r.get("dq"))] = dq_counts.get(str(r.get("dq")), 0) + 1
        status_counts[str(r.get("status"))] = status_counts.get(str(r.get("status")), 0) + 1

    lats = [float(r["latency"]) for r in rows if isinstance(r.get("latency"), (int, float))]

    def _cell(sub: List[Dict[str, Any]]) -> Dict[str, Any]:
        sn = len(sub)
        sh = sum(1 for r in sub if r.get("correct"))
        return {
            "n": sn,
            "hits": sh,
            "hit_rate": round(sh / sn * 100.0, 2) if sn else 0.0,
            "wilson95": wilson95(sh, sn),
        }

    by_regime = {g: _cell(v) for g, v in _group(rows, "regime").items()}
    by_session = {g: _cell(v) for g, v in _group(rows, "session").items()}

    return {
        "n": n,
        "n_cal": len(cal),
        "hits": hits,
        "hit_rate": hit_rate,
        "wilson95": wilson95(hits, n),
        "brier": round(float(brier), 4),
        "log_loss": round(float(ll), 4),
        "ece10": round(float(ece), 4),
        "reliability": bins,
        "dq_failure_rate": round(dq_fail / n, 4) if n else 0.0,
        "dq_fail_n": dq_fail,
        "dq_breakdown": dq_counts,
        "status_breakdown": status_counts,
        "latency": _percentiles(lats),
        "by_regime": by_regime,
        "by_session": by_session,
    }


def _group(rows: List[Dict[str, Any]], key: str) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        g = str((r or {}).get(key) or "UNKNOWN")
        groups.setdefault(g, []).append(r)
    return dict(sorted(groups.items()))


def check_min_evidence(
    n_pair: int,
    days_covered: float,
    min_settleable: int = 250,
    max_days: float = 14,
) -> Dict[str, Any]:
    """Minimum-evidence gate: warn only when BOTH bars are missed (OR rule).

    Meeting either ``n_pair >= min_settleable`` or ``days >= max_days`` is
    sufficient evidence to proceed; missing both yields a warning.
    """
    try:
        n = int(n_pair)
    except (TypeError, ValueError):
        n = 0
    try:
        days = float(days_covered)
    except (TypeError, ValueError):
        days = 0.0
    warn = n < int(min_settleable) and days < float(max_days)
    return {
        "n_pair": n,
        "days_covered": round(days, 2),
        "min_settleable": int(min_settleable),
        "max_days": float(max_days),
        "sufficient": not warn,
        "warning": (
            None if not warn else (
                f"INSUFFICIENT EVIDENCE: {n} settled pairs (< {min_settleable}) "
                f"over {days:.1f}d (< {max_days}d). Shadow needs 250 settleable "
                "OR 14 days, whichever is stronger — extend the shadow window."
            )
        ),
    }


def days_covered(timestamps: List[Any]) -> float:
    """Calendar span in days over settled timestamps (0.0 when < 2)."""
    dts = [_parse_dt(t) for t in timestamps or []]
    dts = [d for d in dts if d is not None]
    if len(dts) < 2:
        return 0.0
    span = (max(dts) - min(dts)).total_seconds() / 86400.0
    return round(max(0.0, span), 2)


def build_report(
    v1_rows: List[Dict[str, Any]],
    v2_rows: List[Dict[str, Any]],
    *,
    instruments: List[str],
    min_settleable: int = 250,
    max_days: float = 14,
) -> Dict[str, Any]:
    """Assemble the full side-by-side report dict (pure)."""
    v1 = summarize_side(v1_rows)
    v2 = summarize_side(v2_rows)
    n_pair = min(v1["n"], v2["n"])
    stamps = [r.get("timestamp") for r in list(v1_rows or []) + list(v2_rows or [])]
    days = days_covered(stamps)
    evidence = check_min_evidence(n_pair, days, min_settleable, max_days)
    try:
        from app.research.validation.costs import COSTS_VERSION as _CV
        from app.research.validation.costs import REFERENCE_COSTS_V1 as _RC

        costs_version, ref_costs = str(_CV), dict(_RC)
    except Exception:
        costs_version, ref_costs = "ref-v1", {}
    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "instruments": list(instruments or []),
            "indicator_ids": {"v1": INDICATOR_V1, "v2": INDICATOR_V2},
            "min_settleable": int(min_settleable),
            "max_days": float(max_days),
            "costs_version": costs_version,
        },
        "evidence": evidence,
        "v1": v1,
        "v2": v2,
        "deltas_v2_minus_v1": {
            "hit_rate_pp": round(v2["hit_rate"] - v1["hit_rate"], 2),
            "brier": round(v2["brier"] - v1["brier"], 4),
            "log_loss": round(v2["log_loss"] - v1["log_loss"], 4),
            "ece10": round(v2["ece10"] - v1["ece10"], 4),
            "dq_failure_rate": round(v2["dq_failure_rate"] - v1["dq_failure_rate"], 4),
        },
        "reference_costs": ref_costs,
        "note_economics_diagnostic_only": (
            "Economics here is diagnostic only: no fills are invented and no "
            "promotion is decided by this report. Net figures (when computed "
            "offline) use reference costs ref-v1 under the §15 mapping; the "
            "promotion decision cites power/MDE explicitly and is signed off "
            "separately per the Cycle-1 budget."
        ),
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _side_row(label: str, s: Dict[str, Any]) -> str:
    w = s.get("wilson95") or [0.0, 0.0]
    lat = s.get("latency") or {}
    return (
        f"| {label} | {s.get('n', 0)} | {s.get('hit_rate', 0.0):.2f}% "
        f"[{float(w[0]):.2f}%, {float(w[1]):.2f}%] | {s.get('brier', 0.0):.4f} "
        f"| {s.get('log_loss', 0.0):.4f} | {s.get('ece10', 0.0):.4f} "
        f"| {s.get('dq_failure_rate', 0.0):.4f} ({s.get('dq_fail_n', 0)}) "
        f"| mean {lat.get('mean', 0.0)}s / p95 {lat.get('p95', 0.0)}s (n={lat.get('n', 0)}) |"
    )


def render_markdown(report: Dict[str, Any]) -> str:
    meta = report.get("meta", {})
    ev = report.get("evidence", {})
    v1 = report.get("v1", {})
    v2 = report.get("v2", {})
    deltas = report.get("deltas_v2_minus_v1", {})
    lines = [
        "# Shadow Comparison: 1H Forecast v1 vs v2-candidate (P3-1)",
        "",
        f"- Generated: `{meta.get('generated_at')}`",
        f"- Instruments: `{json.dumps(meta.get('instruments', []))}`",
        f"- Indicator ids: v1 `{INDICATOR_V1}` vs v2 `{INDICATOR_V2}`",
        f"- Costs provenance: `{meta.get('costs_version')}` (diagnostic only)",
        "",
        "## Evidence gate",
        "",
        f"- Settled: v1 n={v1.get('n', 0)} (cal n={v1.get('n_cal', 0)}), "
        f"v2 n={v2.get('n', 0)} (cal n={v2.get('n_cal', 0)}), "
        f"pair n={ev.get('n_pair', 0)} over {ev.get('days_covered', 0.0)}d",
        f"- Bar: `{ev.get('min_settleable', 250)} settleable OR "
        f"{ev.get('max_days', 14)} days` (whichever stronger)",
        f"- Verdict: `{'SUFFICIENT' if ev.get('sufficient') else 'INSUFFICIENT — EXTEND SHADOW'}`",
    ]
    if ev.get("warning"):
        lines.append(f"- WARNING: {ev['warning']}")
    lines += [
        "",
        "## Side-by-side (settled only)",
        "",
        "| side | n | hit-rate + Wilson95 | Brier | log-loss | ECE10 | DQ-fail (n) | latency |",
        "|---|---|---|---|---|---|---|---|",
        _side_row("v1", v1),
        _side_row("v2", v2),
        "",
        "## Deltas (v2 − v1)",
        "",
        f"- hit-rate: `{deltas.get('hit_rate_pp', 0.0):+.2f}pp`, "
        f"Brier: `{deltas.get('brier', 0.0):+.4f}` (negative is better), "
        f"log-loss: `{deltas.get('log_loss', 0.0):+.4f}`, "
        f"ECE10: `{deltas.get('ece10', 0.0):+.4f}`, "
        f"DQ-fail: `{deltas.get('dq_failure_rate', 0.0):+.4f}`",
        "",
        "## Reliability (ECE10 bins, confidence = max P vs hit)",
        "",
        "### v1",
        "",
        "| bin | range | n | acc | conf | gap |",
        "|---|---|---|---|---|---|",
    ]
    for b in v1.get("reliability", []) or []:
        lines.append(
            f"| {b.get('bin')} | [{b.get('lo')}, {b.get('hi')}] | {b.get('n')} "
            f"| {float(b.get('acc', 0.0)):.4f} | {float(b.get('conf', 0.0)):.4f} "
            f"| {float(b.get('gap', 0.0)):.4f} |"
        )
    lines += ["", "### v2", "", "| bin | range | n | acc | conf | gap |",
              "|---|---|---|---|---|---|"]
    for b in v2.get("reliability", []) or []:
        lines.append(
            f"| {b.get('bin')} | [{b.get('lo')}, {b.get('hi')}] | {b.get('n')} "
            f"| {float(b.get('acc', 0.0)):.4f} | {float(b.get('conf', 0.0)):.4f} "
            f"| {float(b.get('gap', 0.0)):.4f} |"
        )
    lines += ["", "## By regime", "",
              "| side | group | n | hit-rate + Wilson95 |",
              "|---|---|---|---|"]
    for label, side in (("v1", v1), ("v2", v2)):
        for g, cell in (side.get("by_regime", {}) or {}).items():
            w = cell.get("wilson95") or [0.0, 0.0]
            lines.append(
                f"| {label} | {g} | {cell.get('n', 0)} | {cell.get('hit_rate', 0.0):.2f}% "
                f"[{float(w[0]):.2f}%, {float(w[1]):.2f}%] |"
            )
    lines += ["", "## By session", "",
              "| side | group | n | hit-rate + Wilson95 |",
              "|---|---|---|---|"]
    for label, side in (("v1", v1), ("v2", v2)):
        for g, cell in (side.get("by_session", {}) or {}).items():
            w = cell.get("wilson95") or [0.0, 0.0]
            lines.append(
                f"| {label} | {g} | {cell.get('n', 0)} | {cell.get('hit_rate', 0.0):.2f}% "
                f"[{float(w[0]):.2f}%, {float(w[1]):.2f}%] |"
            )
    lines += [
        "",
        "## Data-quality / status breakdown",
        "",
        f"- v1 dq: `{json.dumps(v1.get('dq_breakdown', {}), default=str)}` "
        f"status: `{json.dumps(v1.get('status_breakdown', {}), default=str)}`",
        f"- v2 dq: `{json.dumps(v2.get('dq_breakdown', {}), default=str)}` "
        f"status: `{json.dumps(v2.get('status_breakdown', {}), default=str)}`",
        "",
        "## Notes",
        "",
        f"- {report.get('note_economics_diagnostic_only', '')}",
        "- Promotion requires the pre-registered win rules (Cycle-1 MDE/power) "
        "on fresh OOS plus a signed decision — this report never auto-promotes.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DB loading (settled pairs only; no synthesis)
# ---------------------------------------------------------------------------

async def fetch_settled_pairs(
    instruments: List[str],
    session: Any,
    limit: int = 5000,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Fetch settled rows split into (v1_rows, v2_rows).

    Each row is a flat dict the pure ``build_side_rows`` understands
    (prediction fields + ``outcome_is_correct``/``outcome_actual`` normalized
    into an outcome map by the caller). Rows WITHOUT outcomes are excluded
    by the INNER JOIN — never guessed.
    """
    from sqlalchemy import text

    insts = [str(i) for i in (instruments or []) if str(i).strip()]
    if not insts:
        return [], []
    placeholders = ", ".join(f":inst{i}" for i in range(len(insts)))
    stmt = text(
        f"""
        SELECT p.prediction_id, p.indicator_id, p.instrument, p.timestamp,
               p.created_at, p.direction, p.score, p.confidence,
               p.component_values, p.target_price, p.invalidation_price,
               p.snapshot_id,
               s.features AS snapshot_features,
               o.is_correct AS outcome_is_correct,
               o.actual_direction AS outcome_actual,
               o.evaluated_at AS outcome_evaluated_at
        FROM research_predictions p
        JOIN research_prediction_outcomes o ON o.prediction_id = p.prediction_id
        LEFT JOIN research_snapshots s ON s.snapshot_id = p.snapshot_id
        WHERE p.indicator_id IN (:v1, :v2)
          AND p.instrument IN ({placeholders})
        ORDER BY p.timestamp ASC
        LIMIT :limit
        """
    )
    params: Dict[str, Any] = {"v1": INDICATOR_V1, "v2": INDICATOR_V2, "limit": int(limit)}
    for i, name in enumerate(insts):
        params[f"inst{i}"] = name
    result = await session.execute(stmt, params)
    try:
        rows = [dict(r) for r in result.mappings().all()]
    except AttributeError:
        rows = [dict(r) if not isinstance(r, dict) else r for r in (result.all() or [])]
    v1_rows = [r for r in rows if r.get("indicator_id") == INDICATOR_V1]
    v2_rows = [r for r in rows if r.get("indicator_id") == INDICATOR_V2]
    return v1_rows, v2_rows


def _split_outcomes(
    rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Normalize DB-joined rows into (pred_rows, outcome_by_id)."""
    preds: List[Dict[str, Any]] = []
    outcomes: Dict[str, Dict[str, Any]] = {}
    for r in rows or []:
        r = dict(r)
        pid = r.get("prediction_id")
        if not pid:
            continue
        correct = r.pop("outcome_is_correct", None)
        actual = r.pop("outcome_actual", None)
        if not isinstance(correct, bool):
            continue
        preds.append(r)
        outcomes[str(pid)] = {"is_correct": correct, "actual_direction": actual}
    return preds, outcomes


async def main_async(args: argparse.Namespace) -> Dict[str, Any]:
    instruments = parse_instruments(args.instruments)
    if not instruments:
        raise SystemExit("--instruments must list at least one instrument")
    if args.min_settleable is not None and args.min_settleable < 1:
        raise SystemExit("--min-settleable must be >= 1")
    if args.max_days is not None and args.max_days <= 0:
        raise SystemExit("--max-days must be > 0")

    from app.core.database import get_async_session_factory

    factory = get_async_session_factory()
    if factory is None:
        raise RuntimeError(
            "Database is not configured (DATABASE_URL missing) — refusing to "
            "synthesize shadow data. Run inside the backend env with Postgres."
        )
    async with factory() as session:
        v1_db, v2_db = await fetch_settled_pairs(instruments, session)
    v1_preds, v1_out = _split_outcomes(v1_db)
    v2_preds, v2_out = _split_outcomes(v2_db)
    v1_rows = build_side_rows(v1_preds, v1_out)
    v2_rows = build_side_rows(v2_preds, v2_out)
    report = build_report(
        v1_rows, v2_rows,
        instruments=instruments,
        min_settleable=args.min_settleable,
        max_days=args.max_days,
    )
    report["evidence"]["settled_excluded_note"] = (
        "Rows without outcomes are excluded by INNER JOIN (never guessed)."
    )
    return report


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = asyncio.run(main_async(args))
    except SystemExit:
        raise
    except RuntimeError as e:
        print(f"shadow_compare failed: {e}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as e:
        print(f"shadow_compare failed: {e}", file=sys.stderr)
        raise SystemExit(1)
    md_path, json_path = resolve_out_paths(args.out)
    md_text = render_markdown(report)
    try:
        if str(md_path.parent) not in ("", "."):
            md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_text, encoding="utf-8")
        if str(json_path.parent) not in ("", "."):
            json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        print(f"failed writing reports: {e}", file=sys.stderr)
        raise SystemExit(1)
    ev = report.get("evidence", {})
    print(f"wrote {md_path} + {json_path} "
          f"(v1 n={report.get('v1', {}).get('n', 0)} "
          f"v2 n={report.get('v2', {}).get('n', 0)} "
          f"days={ev.get('days_covered', 0.0)} "
          f"sufficient={ev.get('sufficient')})")
    if ev.get("warning"):
        print(f"WARNING: {ev['warning']}", file=sys.stderr)


if __name__ == "__main__":
    main()
