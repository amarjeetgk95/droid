"""P3-2 minimal monitoring + auto-degrade + rollback bundle (1H forecast v2.3).

Implements IMPLEMENTATION_PLAN §P3-2 ("Minimal monitoring + auto-degrade +
rollback") with ``backend/app/api/monitoring.py`` (HTTP) and
``docs/FORECAST_1H_RUNBOOK.md`` (chaos matrix + rollback steps).

Core functions here are PURE (no DB, no network, no wall-clock I/O except an
injectable ``now_utc`` default):

- :func:`rolling_window_metrics` — last ``window`` (default 200) settleable
  joined prediction+outcome rows (plain dicts) ->
  ``{n, hit_rate, brier, ece, freshness, missing_tf_rate, ml_availability}``.
  Brier/ECE reuse ``app.ml.calibration_metrics`` (3-class, LABEL_MAP order
  0=BEARISH / 1=NEUTRAL / 2=BULLISH).
- :func:`check_degrade` — threshold gate ->
  ``{degraded: bool, reasons[]}``. Triggers: ``ECE > 0.12`` (P2-4 gate),
  Brier worse than baseline ``+ 0.02``, hit-rate drop vs baseline, stale
  candle/F&O provider, artifact/spec mismatch, missing-TF rate, ML
  availability. ``reasons`` is non-empty IFF ``degraded`` is True.
- :func:`resolve_release_bundle` — snapshot the current release bundle.
- :func:`rollback_to` — build a rollback PLAN from a bundle. NEVER mutates
  ``os.environ`` and NEVER writes files; the operator applies the plan.

Row-dict contract (all keys optional; unknown fields are ignored, missing
calibration fields only shrink the scored subset — never fabricated):

- identity/order: ``prediction_id``, ``timestamp`` / ``created_at`` /
  ``evaluated_at`` (datetime or ISO string; naive assumed UTC).
- calibration: ``probabilities`` dict ``{bullish, neutral, bearish}`` (also
  accepts ``bull``/``neut``/``bear`` aliases) or ``probs``/``p`` list in
  ``[bear, neut, bull]`` order; truth from ``actual_direction``
  (``BULLISH``/``NEUTRAL``/``BEARISH`` str or enum) or ``y_true`` /
  ``outcome_label`` int in ``{0, 1, 2}``.
- outcome: ``is_correct`` bool, ``settleable`` bool (rows explicitly
  ``False`` are excluded as unsettleable).
- freshness: ``candle_age_sec`` / ``fno_age_sec`` seconds (numeric), or
  ``candle_ts`` / ``fno_ts`` (``candle_timestamp`` / ``fno_timestamp``
  aliases; datetime or ISO) measured against ``now_utc``.
- data quality: ``missing_tfs`` (``missing_timeframes`` / ``missing_tf``
  aliases) and ``resampled_tfs`` (``resampled_timeframes`` alias) lists;
  ``ml_available`` bool (fallback: ``model_source != "unavailable"`` or
  ``ml_forecast is not None``).
- mismatch: ``artifact_mismatch`` bool, or a ``limitations`` list containing
  an ``"artifact-mismatch"`` entry, or ``target_spec_version`` /
  ``feature_schema`` disagreeing with the v2 contract.

§26 rollback-bundle spec (§26 = release = code + artifact triple + spec +
schema + weights; see ``TrendForecaster.validate_ml_artifact`` docstring):

- ``code``: ``forecast_weights_version`` (``FORECAST_WEIGHTS_VERSION``),
  ``forecast_v2_model`` (``FORECAST_V2_MODEL``), ``allow_heuristic``
  (``FORECAST_ALLOW_HEURISTIC``), best-effort ``git_sha``.
- ``model``: v2 logistic meta (``model_h60_logistic.json`` /
  ``meta_h60_logistic.json``: ``model_version="logistic-v2-h60-v1"``) plus
  the h60 xgb/lgb/meta artifact-triple existence flags.
- ``calibrator``: ``version="cal-v1"`` + per-instrument artifact existence.
- ``feature_schema``: ``"f12-v1"`` + width/names.
- ``target_spec``: ``"v2-atr-em-session"`` (v1 kept for reference).
"""

from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

#: Default rolling window: last N settleable joined rows.
MONITOR_WINDOW = 200

#: P2-4 ECE gate: rolling-200 ECE above this degrades.
ECE_DEGRADE_MAX = 0.12
#: Brier regression slack vs (shadow) baseline.
BRIER_BASELINE_SLACK = 0.02
#: Hit-rate drop vs (shadow) baseline that degrades.
HIT_RATE_DROP = 0.05

DEFAULT_THRESHOLDS: Dict[str, float] = {
    "ece_max": ECE_DEGRADE_MAX,
    "brier_slack": BRIER_BASELINE_SLACK,
    "hit_drop": HIT_RATE_DROP,
    "candle_stale_sec": 300.0,
    "fno_stale_sec": 600.0,
    "missing_tf_max_rate": 0.20,
    "ml_min_availability": 0.80,
    "min_n": 10,
}

_LABEL_INDEX = {"BEARISH": 0, "NEUTRAL": 1, "BULLISH": 2}


# ---------------------------------------------------------------------------
# small pure parsers
# ---------------------------------------------------------------------------

def _as_utc(value: Any) -> Optional[datetime]:
    """Parse datetime/ISO/epoch to aware UTC; None when unparseable."""
    try:
        if isinstance(value, datetime):
            ts = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            ts = datetime.fromtimestamp(float(value), tz=timezone.utc)
        elif isinstance(value, str) and value.strip():
            ts = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        else:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    except Exception:
        return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if isinstance(value, bool) or out != out:  # reject bools / NaN
        return None
    return out


def _row_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    for key in ("timestamp", "created_at", "evaluated_at"):
        ts = _as_utc(row.get(key))
        if ts is not None:
            return ts
    return None


def _row_probs(row: Dict[str, Any]) -> Optional[List[float]]:
    """Row probabilities as [bear, neut, bull] floats, or None."""
    raw = row.get("probabilities")
    if isinstance(raw, dict):
        low = {str(k).lower(): v for k, v in raw.items()}
        bear = low.get("bearish", low.get("bear"))
        neut = low.get("neutral", low.get("neut"))
        bull = low.get("bullish", low.get("bull"))
        vals = [_safe_float(bear), _safe_float(neut), _safe_float(bull)]
        if any(v is None or not (0.0 <= v <= 1.0) for v in vals):
            return None
        return [float(v) for v in vals]  # type: ignore[misc]
    for key in ("probs", "p", "p_row"):
        seq = row.get(key)
        if isinstance(seq, (list, tuple)) and len(seq) == 3:
            vals = [_safe_float(v) for v in seq]
            if any(v is None or not (0.0 <= v <= 1.0) for v in vals):
                return None
            return [float(v) for v in vals]  # type: ignore[misc]
    return None


def _row_label(row: Dict[str, Any]) -> Optional[int]:
    """True class index 0/1/2, or None when unknown/unscorable."""
    for key in ("y_true", "outcome_label", "label"):
        v = row.get(key)
        if isinstance(v, bool):
            continue
        try:
            iv = int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            iv = -1
        if iv in (0, 1, 2):
            return iv
    raw = row.get("actual_direction")
    text = getattr(raw, "value", raw)
    if isinstance(text, str) and text.strip().upper() in _LABEL_INDEX:
        return _LABEL_INDEX[text.strip().upper()]
    return None


def _row_age_sec(row: Dict[str, Any], age_key: str, ts_keys: tuple, now: datetime) -> Optional[float]:
    direct = _safe_float(row.get(age_key))
    if direct is not None and direct >= 0:
        return direct
    for key in ts_keys:
        if key in row and row.get(key) is not None:
            ts = _as_utc(row.get(key))
            if ts is not None:
                return max(0.0, (now - ts).total_seconds())
    return None


def _row_list(row: Dict[str, Any], *keys: str) -> Optional[list]:
    for key in keys:
        v = row.get(key)
        if isinstance(v, (list, tuple)):
            return list(v)
    return None


def _row_ml_available(row: Dict[str, Any]) -> Optional[bool]:
    v = row.get("ml_available")
    if isinstance(v, bool):
        return v
    for key in ("ml_availability", "ml_ok"):
        v = row.get(key)
        if isinstance(v, bool):
            return v
    src = row.get("model_source")
    src_text = getattr(src, "value", src)
    if isinstance(src_text, str) and src_text:
        return src_text != "unavailable"
    if "ml_forecast" in row:
        return row.get("ml_forecast") is not None
    return None


def _row_mismatch(row: Dict[str, Any]) -> bool:
    """True when the row carries an artifact/spec mismatch signal."""
    if row.get("artifact_mismatch") is True:
        return True
    lims = row.get("limitations")
    if isinstance(lims, (list, tuple)) and any(
        isinstance(x, str) and "artifact-mismatch" in x for x in lims
    ):
        return True
    spec = row.get("target_spec_version")
    spec_text = getattr(spec, "value", spec)
    if isinstance(spec_text, str) and spec_text and spec_text != _expected_target_spec():
        return True
    schema = row.get("feature_schema")
    if isinstance(schema, str) and schema and schema != _expected_feature_schema():
        return True
    return False


def _expected_target_spec() -> str:
    try:
        from app.ml.targets_v2 import TARGET_SPEC_VERSION_V2

        return str(TARGET_SPEC_VERSION_V2)
    except Exception:
        return "v2-atr-em-session"


def _expected_feature_schema() -> str:
    try:
        from app.ml.feature_extractor_v2 import FEATURE_SCHEMA_V2

        return str(FEATURE_SCHEMA_V2)
    except Exception:
        return "f12-v1"


# ---------------------------------------------------------------------------
# 1. rolling window metrics (pure)
# ---------------------------------------------------------------------------

def rolling_window_metrics(
    rows: List[Dict[str, Any]],
    window: int = MONITOR_WINDOW,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Aggregate the last ``window`` settleable joined rows.

    Filters OUT rows explicitly ``settleable=False`` and rows with no outcome
    (neither ``is_correct`` nor a true label) — unsettled rows stay out of
    accuracy-style metrics instead of being guessed. Sorts the survivors by
    timestamp (rows without one keep input order at the tail) and takes the
    last ``window``.

    Returns ``{n, n_scored, hit_rate, brier, ece, freshness{candle/fno max +
    median ages}, missing_tf_rate, resampled_tf_rate, ml_availability,
    artifact_mismatch_count, artifact_mismatch_rate, window}``. Uncomputable
    entries are ``None`` (unknown), never invented. Never raises on bad rows.
    """
    try:
        w = int(window)
    except (TypeError, ValueError):
        w = MONITOR_WINDOW
    w = max(1, w)
    now = now_utc if isinstance(now_utc, datetime) else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    usable: List[Dict[str, Any]] = []
    try:
        seq = list(rows or [])
    except TypeError:
        seq = []
    for r in seq:
        if not isinstance(r, dict):
            continue
        try:
            if r.get("settleable") is False:
                continue
            is_corr = r.get("is_correct")
            has_outcome = isinstance(is_corr, bool) or _row_label(r) is not None
            if not has_outcome:
                continue
            usable.append(r)
        except (KeyError, ValueError, TypeError):
            continue

    decorated = [(_row_timestamp(r), i, r) for i, r in enumerate(usable)]
    decorated.sort(key=lambda t: (t[0] is None, t[0] or datetime.max.replace(tzinfo=timezone.utc), t[1]))
    picked = [t[2] for t in decorated[-w:]]

    n = len(picked)
    hits = [r["is_correct"] for r in picked if isinstance(r.get("is_correct"), bool)]
    hit_rate = (sum(1 for h in hits if h) / len(hits)) if hits else None

    y_true: List[int] = []
    p_rows: List[List[float]] = []
    for r in picked:
        try:
            lab = _row_label(r)
            probs = _row_probs(r)
        except (KeyError, ValueError, TypeError):
            lab, probs = None, None
        if lab is not None and probs is not None:
            y_true.append(lab)
            p_rows.append(probs)
    n_scored = len(y_true)

    brier: Optional[float] = None
    ece: Optional[float] = None
    if n_scored:
        try:
            from app.ml.calibration_metrics import brier_score_3class, ece_equal_width

            brier = float(brier_score_3class(y_true, p_rows))
            pmax = [max(row) for row in p_rows]
            y_pred = [max(range(3), key=lambda k: row[k]) for row in p_rows]
            ece = float(ece_equal_width(y_true, pmax, 10, y_pred)["ece"])
        except Exception:
            brier, ece = None, None

    candle_ages: List[float] = []
    fno_ages: List[float] = []
    for r in picked:
        try:
            ca = _row_age_sec(r, "candle_age_sec", ("candle_ts", "candle_timestamp"), now)
            fa = _row_age_sec(r, "fno_age_sec", ("fno_ts", "fno_timestamp"), now)
        except (KeyError, ValueError, TypeError):
            ca, fa = None, None
        if ca is not None:
            candle_ages.append(ca)
        if fa is not None:
            fno_ages.append(fa)

    def _max_med(vals: List[float]) -> tuple:
        if not vals:
            return None, None
        try:
            return max(vals), float(statistics.median(vals))
        except Exception:
            return max(vals), None

    c_max, c_med = _max_med(candle_ages)
    f_max, f_med = _max_med(fno_ages)

    miss_flags: List[bool] = []
    res_flags: List[bool] = []
    for r in picked:
        try:
            miss = _row_list(r, "missing_tfs", "missing_timeframes", "missing_tf")
            res = _row_list(r, "resampled_tfs", "resampled_timeframes")
        except (KeyError, ValueError, TypeError):
            miss, res = None, None
        if miss is not None:
            miss_flags.append(len(miss) > 0)
        if res is not None:
            res_flags.append(len(res) > 0)
    missing_tf_rate = (sum(1 for f in miss_flags if f) / len(miss_flags)) if miss_flags else None
    resampled_tf_rate = (sum(1 for f in res_flags if f) / len(res_flags)) if res_flags else None

    ml_flags: List[bool] = []
    for r in picked:
        try:
            ml = _row_ml_available(r)
        except (KeyError, ValueError, TypeError):
            ml = None
        if ml is not None:
            ml_flags.append(bool(ml))
    ml_availability = (sum(1 for f in ml_flags if f) / len(ml_flags)) if ml_flags else None

    mismatch_count = 0
    for r in picked:
        try:
            if _row_mismatch(r):
                mismatch_count += 1
        except (KeyError, ValueError, TypeError):
            continue

    return {
        "n": n,
        "n_scored": n_scored,
        "hit_rate": hit_rate,
        "brier": brier,
        "ece": ece,
        "freshness": {
            "candle_age_sec_max": c_max,
            "candle_age_sec_median": c_med,
            "fno_age_sec_max": f_max,
            "fno_age_sec_median": f_med,
        },
        "missing_tf_rate": missing_tf_rate,
        "resampled_tf_rate": resampled_tf_rate,
        "ml_availability": ml_availability,
        "artifact_mismatch_count": mismatch_count,
        "artifact_mismatch_rate": (mismatch_count / n) if n else 0.0,
        "window": w,
    }


# ---------------------------------------------------------------------------
# 2. auto-degrade gate (pure)
# ---------------------------------------------------------------------------

def check_degrade(
    metrics: Dict[str, Any],
    baseline: Optional[Dict[str, Any]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply the P3-2 degrade triggers to a metrics dict.

    ``baseline`` (optional, e.g. the shadow/v1 comparator) may carry
    ``brier`` and ``hit_rate``; Brier/hit regression checks run ONLY when the
    corresponding baseline entry is present — otherwise they are skipped, not
    guessed. Calibration checks (ECE/Brier/hit) are skipped while
    ``metrics["n"] < min_n`` (default 10); freshness/mismatch/TF/ML checks
    always run. Returns exactly ``{degraded: bool, reasons[]}`` where
    ``reasons`` is non-empty IFF ``degraded`` is True. Never raises.
    """
    try:
        m = dict(metrics or {})
    except Exception:
        return {"degraded": False, "reasons": []}
    try:
        thr = dict(DEFAULT_THRESHOLDS)
        thr.update(dict(thresholds or {}))
    except (TypeError, ValueError):
        thr = dict(DEFAULT_THRESHOLDS)
    try:
        base = dict(baseline or {})
    except (TypeError, ValueError):
        base = {}

    reasons: List[str] = []
    try:
        n = int(m.get("n") or 0)
    except (TypeError, ValueError):
        n = 0
    try:
        min_n = int(thr.get("min_n", 10))
    except (TypeError, ValueError):
        min_n = 10
    scored_ok = n >= max(1, min_n)

    def _num(v: Any) -> Optional[float]:
        f = _safe_float(v)
        return f

    if scored_ok:
        ece = _num(m.get("ece"))
        try:
            ece_max = float(thr.get("ece_max", ECE_DEGRADE_MAX))
        except (TypeError, ValueError):
            ece_max = ECE_DEGRADE_MAX
        if ece is not None and ece > ece_max:
            reasons.append(f"ece-{ece:.4f}-above-{ece_max:.2f}")

        brier = _num(m.get("brier"))
        base_brier = _num(base.get("brier", base.get("brier_baseline")))
        try:
            slack = float(thr.get("brier_slack", BRIER_BASELINE_SLACK))
        except (TypeError, ValueError):
            slack = BRIER_BASELINE_SLACK
        if brier is not None and base_brier is not None and brier > base_brier + slack:
            reasons.append(f"brier-{brier:.4f}-worse-than-baseline-{base_brier:.4f}+{slack:.2f}")

        hit = _num(m.get("hit_rate"))
        base_hit = _num(base.get("hit_rate", base.get("hit_baseline")))
        try:
            drop = float(thr.get("hit_drop", HIT_RATE_DROP))
        except (TypeError, ValueError):
            drop = HIT_RATE_DROP
        if hit is not None and base_hit is not None and hit < base_hit - drop:
            reasons.append(f"hit-rate-{hit:.4f}-below-baseline-{base_hit:.4f}-drop-{drop:.2f}")

    fresh = m.get("freshness") or {}
    if isinstance(fresh, dict):
        try:
            c_thr = float(thr.get("candle_stale_sec", 300.0))
        except (TypeError, ValueError):
            c_thr = 300.0
        try:
            f_thr = float(thr.get("fno_stale_sec", 600.0))
        except (TypeError, ValueError):
            f_thr = 600.0
        c_max = _num(fresh.get("candle_age_sec_max"))
        if c_max is not None and c_max > c_thr:
            reasons.append(f"stale-candle-{c_max:.0f}s-over-{c_thr:.0f}s")
        f_max = _num(fresh.get("fno_age_sec_max"))
        if f_max is not None and f_max > f_thr:
            reasons.append(f"stale-fno-{f_max:.0f}s-over-{f_thr:.0f}s")

    try:
        mm_count = int(m.get("artifact_mismatch_count") or 0)
    except (TypeError, ValueError):
        mm_count = 0
    mm_rate = _num(m.get("artifact_mismatch_rate"))
    if mm_count > 0 or (mm_rate is not None and mm_rate > 0):
        reasons.append(f"artifact-spec-mismatch-count-{mm_count}")

    try:
        tf_thr = float(thr.get("missing_tf_max_rate", 0.20))
    except (TypeError, ValueError):
        tf_thr = 0.20
    miss_rate = _num(m.get("missing_tf_rate"))
    if miss_rate is not None and miss_rate > tf_thr:
        reasons.append(f"missing-tf-rate-{miss_rate:.2f}-above-{tf_thr:.2f}")
    res_rate = _num(m.get("resampled_tf_rate"))
    if res_rate is not None and res_rate > tf_thr:
        reasons.append(f"resampled-tf-rate-{res_rate:.2f}-above-{tf_thr:.2f}")

    try:
        ml_thr = float(thr.get("ml_min_availability", 0.80))
    except (TypeError, ValueError):
        ml_thr = 0.80
    ml_av = _num(m.get("ml_availability"))
    if ml_av is not None and ml_av < ml_thr:
        reasons.append(f"ml-availability-{ml_av:.2f}-below-{ml_thr:.2f}")

    return {"degraded": len(reasons) > 0, "reasons": reasons}


# ---------------------------------------------------------------------------
# 3. release bundle + rollback plan (no live-env mutation, no file writes)
# ---------------------------------------------------------------------------

def _forecast_env_flags() -> Dict[str, Any]:
    weights_raw = (os.getenv("FORECAST_WEIGHTS_VERSION", "v1") or "v1").strip() or "v1"
    model_raw = (os.getenv("FORECAST_V2_MODEL", "v1") or "v1").strip().lower() or "v1"
    heur_raw = (os.getenv("FORECAST_ALLOW_HEURISTIC", "true") or "true").strip().lower()
    return {
        "forecast_weights_version": f"forecast-{weights_raw}",
        "forecast_weights_raw": weights_raw,
        "forecast_v2_model": model_raw,
        "allow_heuristic": heur_raw not in ("false", "0", "no", "off"),
    }


def _git_sha_best_effort() -> str:
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(Path(__file__).resolve().parents[3]),
        )
        sha = (out.stdout or "").strip()
        return sha if sha else "unknown"
    except Exception:
        return "unknown"


def resolve_release_bundle(instrument: str = "NIFTY 50") -> Dict[str, Any]:
    """Snapshot the current forecast release bundle (§26 rollback spec).

    Reads (each section best-effort, never raises):
    - ``code``: ``FORECAST_WEIGHTS_VERSION`` / ``FORECAST_V2_MODEL`` /
      ``FORECAST_ALLOW_HEURISTIC`` (+ best-effort ``git_sha``).
    - ``model``: v2 logistic artifact meta
      (``model_version="logistic-v2-h60-v1"``) + h60 xgb/lgb/meta triple
      existence flags.
    - ``calibrator``: ``version="cal-v1"`` + per-instrument artifact path +
      existence flag.
    - ``feature_schema``: ``"f12-v1"`` + width/names.
    - ``target_spec``: ``"v2-atr-em-session"`` (v1 kept for reference).
    """
    flags = _forecast_env_flags()
    bundle: Dict[str, Any] = {
        "code": {
            **flags,
            "git_sha": _git_sha_best_effort(),
        },
        "model": {
            "version": None,
            "meta_path": None,
            "meta_exists": False,
            "meta": None,
            "artifacts_triple": {},
            "note": None,
        },
        "calibrator": {
            "version": None,
            "path": None,
            "exists": False,
            "note": None,
        },
        "feature_schema": None,
        "feature_names": [],
        "target_spec": _expected_target_spec(),
        "target_spec_v1": None,
        "bundle_fields": [
            "code", "model", "calibrator", "feature_schema",
            "target_spec", "feature_names",
        ],
    }

    try:
        from app.ml.feature_extractor_v2 import FEATURE_NAMES_V2, FEATURE_SCHEMA_V2

        bundle["feature_schema"] = str(FEATURE_SCHEMA_V2)
        bundle["feature_names"] = list(FEATURE_NAMES_V2)
    except Exception as e:
        bundle["feature_schema"] = _expected_feature_schema()
        bundle["feature_names"] = []
        bundle["feature_schema_note"] = f"extractor-unreadable:{e}"[:200]

    try:
        from app.ml.targets_v2 import TARGET_SPEC_VERSION_V2
        from app.ml.targets import TARGET_SPEC_VERSION as _V1

        bundle["target_spec"] = str(TARGET_SPEC_VERSION_V2)
        bundle["target_spec_v1"] = str(_V1)
    except Exception:
        pass

    try:
        from app.ml.model_v2 import LOGISTIC_META_PATH, MODEL_VERSION_V2

        bundle["model"]["version"] = str(MODEL_VERSION_V2)
        meta_path = Path(str(LOGISTIC_META_PATH))
        bundle["model"]["meta_path"] = str(meta_path)
        if meta_path.exists():
            bundle["model"]["meta_exists"] = True
            try:
                bundle["model"]["meta"] = json.loads(meta_path.read_text())
            except Exception as e:
                bundle["model"]["note"] = f"meta-unreadable:{e}"[:200]
        else:
            bundle["model"]["note"] = "no-h60-logistic-meta-artifact"
    except Exception as e:
        bundle["model"]["note"] = f"model-version-unreadable:{e}"[:200]

    try:
        from app.ml.trainer import artifact_paths

        xgb_p, lgb_p, meta_p = artifact_paths(60)
        bundle["model"]["artifacts_triple"] = {
            "xgb": {"path": str(xgb_p), "exists": bool(Path(str(xgb_p)).exists())},
            "lgb": {"path": str(lgb_p), "exists": bool(Path(str(lgb_p)).exists())},
            "meta": {"path": str(meta_p), "exists": bool(Path(str(meta_p)).exists())},
        }
    except Exception as e:
        bundle["model"]["artifacts_triple"] = {"note": f"triple-unreadable:{e}"[:200]}

    try:
        from app.ml.calibrators import CALIBRATOR_VERSION, calibrator_path

        bundle["calibrator"]["version"] = str(CALIBRATOR_VERSION)
        cal_p = calibrator_path(instrument or "UNKNOWN")
        bundle["calibrator"]["path"] = str(cal_p)
        bundle["calibrator"]["exists"] = bool(Path(str(cal_p)).exists())
        if not bundle["calibrator"]["exists"]:
            bundle["calibrator"]["note"] = "no-persisted-calibrator-uncalibrated"
    except Exception as e:
        bundle["calibrator"]["note"] = f"calibrator-unreadable:{e}"[:200]

    return bundle


def rollback_to(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Build a rollback PLAN for a previously resolved bundle.

    PLAN-ONLY: never mutates ``os.environ``, never writes files, never
    touches the DB or the network — the operator applies the steps (redeploy
    prior code + restore prior artifact triple + calibrator, then verify and
    run the staging rollback drill). Promotion is ALWAYS locked by the plan
    until a green rolling window + signed decision re-opens it.
    """
    try:
        b = dict(bundle or {})
    except Exception:
        b = {}
    code = b.get("code") if isinstance(b.get("code"), dict) else {}
    model = b.get("model") if isinstance(b.get("model"), dict) else {}
    cal = b.get("calibrator") if isinstance(b.get("calibrator"), dict) else {}

    weights_full = str(code.get("forecast_weights_version", "forecast-v1") or "forecast-v1")
    weights_raw = str(code.get("forecast_weights_raw", weights_full.replace("forecast-", "", 1)) or "v1")
    v2_model = str(code.get("forecast_v2_model", "v1") or "v1")
    allow_heur = code.get("allow_heuristic", True)

    triple = model.get("artifacts_triple") if isinstance(model.get("artifacts_triple"), dict) else {}
    artifacts_to_restore: List[str] = []
    for key in ("xgb", "lgb", "meta"):
        entry = triple.get(key)
        if isinstance(entry, dict) and entry.get("path"):
            artifacts_to_restore.append(str(entry["path"]))
    if model.get("meta_path"):
        artifacts_to_restore.append(str(model["meta_path"]))
    if cal.get("path"):
        artifacts_to_restore.append(str(cal["path"]))
    seen: List[str] = []
    for p in artifacts_to_restore:
        if p not in seen:
            seen.append(p)
    artifacts_to_restore = seen

    steps = [
        "Lock promotion: no MVIG promotion while the rollback is open "
        "(monitoring DEGRADED keeps the promotion lock engaged).",
        f"Redeploy prior code bundle (weights {weights_full}, "
        f"FORECAST_V2_MODEL={v2_model}); rollback = flip env + redeploy.",
        "Restore prior artifact triple (xgb/lgb/meta _h60) + persisted "
        "calibrator listed under artifacts_to_restore; verify "
        "meta.horizon_minutes==60, meta.target_spec_version, and "
        "len(meta.feature_names)==caller width (never silently remap h15).",
        "Verify feature schema (f12-v1) and target spec (v2-atr-em-session) "
        "match the restored bundle; refuse to serve on mismatch "
        "(ml_forecast=None + capped confidence, per P0-4).",
        "If heuristic output must be suppressed without an artifact "
        "redeploy, set FORECAST_ALLOW_HEURISTIC=false (forces "
        "heuristic-free capped output).",
        "Run the staging rollback drill, then require a green rolling-200 "
        "window (ECE<=0.12, no Brier/hit regression) + signed "
        "promotion/reject decision before unlocking.",
    ]

    return {
        "action": "rollback-plan-only-no-mutation",
        "promotion_locked": True,
        "promotion_lock_reason": "rollback-open-requires-green-rolling-window-plus-signed-decision",
        "env_flags": {
            "FORECAST_WEIGHTS_VERSION": weights_raw,
            "FORECAST_V2_MODEL": v2_model,
            "FORECAST_ALLOW_HEURISTIC": "true" if allow_heur else "false",
        },
        "artifacts_to_restore": artifacts_to_restore,
        "model_version": model.get("version"),
        "calibrator_version": cal.get("version"),
        "feature_schema": b.get("feature_schema"),
        "target_spec": b.get("target_spec"),
        "steps": steps,
        "bundle": b,
    }


__all__ = [
    "MONITOR_WINDOW",
    "DEFAULT_THRESHOLDS",
    "ECE_DEGRADE_MAX",
    "BRIER_BASELINE_SLACK",
    "HIT_RATE_DROP",
    "rolling_window_metrics",
    "check_degrade",
    "resolve_release_bundle",
    "rollback_to",
]
