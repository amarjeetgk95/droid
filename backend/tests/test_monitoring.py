"""P3-2 monitoring tests: rolling metrics, degrade triggers, bundle roundtrip.

Hermetic: pure ``app.research.monitoring`` dicts + FastAPI TestClient over the
unregistered monitoring router (in-memory PredictionService fallback, no DB).
No network, no broker, no filesystem writes.
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.research import monitoring as mon

BASE = datetime(2026, 9, 9, 4, 30, tzinfo=timezone.utc)  # 10:00 IST


def _probs(bull: float, neut: float, bear: float):
    return {"bullish": bull, "neutral": neut, "bearish": bear}


def _make_row(
    i: int,
    correct: bool = True,
    conf: float = 0.6,
    settleable: bool = True,
    missing=None,
    ml_available: bool = True,
    candle_age: float = 30.0,
    fno_age: float = 60.0,
    mismatch: bool = False,
    actual: str | None = None,
):
    """One joined prediction+outcome row.

    correct=True  -> actual BULLISH, predicted bull=conf.
    correct=False -> actual BEARISH, predicted bull=conf (confident-wrong).
    """
    rest = round((1.0 - conf) / 2.0, 4)
    if actual is None:
        actual = "BULLISH" if correct else "BEARISH"
    probs = _probs(conf, rest, rest) if correct else _probs(conf, rest, rest)
    if not correct and actual == "BEARISH":
        # confident-wrong: mass on bull, truth bear
        probs = _probs(conf, rest, rest)
    row = {
        "prediction_id": f"pred_{i:04d}",
        "timestamp": (BASE + timedelta(minutes=i)).isoformat(),
        "settleable": settleable,
        "probabilities": probs,
        "actual_direction": actual,
        "is_correct": correct,
        "candle_age_sec": candle_age,
        "fno_age_sec": fno_age,
        "ml_available": ml_available,
    }
    if missing is not None:
        row["missing_tfs"] = list(missing)
    if mismatch:
        row["limitations"] = ["artifact-mismatch-h60: meta horizon 15 != 60"]
    return row


def _mixed_rows(n: int = 100, hit: float = 0.6, conf: float = 0.6):
    n_hit = int(n * hit)
    return [_make_row(i, correct=(i < n_hit), conf=conf) for i in range(n)]


# ---------------------------------------------------------------------------
# rolling metrics
# ---------------------------------------------------------------------------

def test_rolling_metrics_basic():
    rows = _mixed_rows(100, hit=0.6, conf=0.6)
    m = mon.rolling_window_metrics(rows)
    assert m["n"] == 100
    assert m["n_scored"] == 100
    assert abs(m["hit_rate"] - 0.6) < 1e-9
    assert m["brier"] is not None and 0.0 < m["brier"] < 2.0
    # confidence matches accuracy (single-bin) -> near-zero ECE
    assert m["ece"] is not None and m["ece"] < 0.05
    assert m["freshness"]["candle_age_sec_max"] == 30.0
    assert m["freshness"]["fno_age_sec_max"] == 60.0
    assert m["ml_availability"] == 1.0
    assert m["artifact_mismatch_count"] == 0
    # no missing info carried -> unknown, not invented
    assert m["missing_tf_rate"] is None


def test_rolling_metrics_rates_and_freshness():
    rows = _mixed_rows(50, hit=0.8)
    for i in range(50):  # explicit: absent key would mean unknown, not healthy
        rows[i]["missing_tfs"] = ["4h", "1D"] if i < 10 else []
    for i in range(5):  # 10% ml-unavailable
        rows[i]["ml_available"] = False
    rows[0]["candle_age_sec"] = 120.0
    m = mon.rolling_window_metrics(rows)
    assert m["n"] == 50
    assert abs(m["missing_tf_rate"] - 0.2) < 1e-9
    assert abs(m["ml_availability"] - 0.9) < 1e-9
    assert m["freshness"]["candle_age_sec_max"] == 120.0


def test_window_takes_last_200_settleable():
    rows = _mixed_rows(250, hit=0.5)
    rows[0]["is_correct"] = True  # oldest row must fall out of the window
    for r in rows[:10]:
        r["settleable"] = False  # unsettleable rows never enter the window
    m = mon.rolling_window_metrics(rows, window=200)
    assert m["n"] == 200


def test_unsettled_and_empty_rows():
    m = mon.rolling_window_metrics([{"prediction_id": "x"}])  # no outcome
    assert m["n"] == 0
    assert m["hit_rate"] is None and m["brier"] is None and m["ece"] is None
    v = mon.check_degrade(m)
    assert v == {"degraded": False, "reasons": []}
    m2 = mon.rolling_window_metrics([])
    assert m2["n"] == 0


# ---------------------------------------------------------------------------
# degrade triggers
# ---------------------------------------------------------------------------

def test_degrade_ece_breach():
    # confidently wrong every time: pmax 0.85, acc 0 -> ECE ~0.85
    rows = [_make_row(i, correct=False, conf=0.85) for i in range(50)]
    m = mon.rolling_window_metrics(rows)
    assert m["ece"] is not None and m["ece"] > 0.12
    v = mon.check_degrade(m)
    assert v["degraded"] is True
    assert any(r.startswith("ece-") for r in v["reasons"])


def test_degrade_brier_and_hit_vs_baseline():
    rows = [_make_row(i, correct=(i < 10), conf=0.85) for i in range(50)]
    m = mon.rolling_window_metrics(rows)
    baseline = {"brier": 0.5, "hit_rate": 0.6}
    v = mon.check_degrade(m, baseline=baseline)
    assert v["degraded"] is True
    assert any(r.startswith("brier-") for r in v["reasons"])
    assert any(r.startswith("hit-rate-") for r in v["reasons"])


def test_no_baseline_no_regression_reasons():
    rows = [_make_row(i, correct=(i < 10), conf=0.85) for i in range(50)]
    m = mon.rolling_window_metrics(rows)
    v = mon.check_degrade(m)  # ECE still fires; brier/hit need a baseline
    assert v["degraded"] is True
    assert not any(r.startswith("brier-") for r in v["reasons"])
    assert not any(r.startswith("hit-rate-") for r in v["reasons"])


def test_degrade_stale_provider():
    rows = _mixed_rows(20, hit=0.6, conf=0.6)
    for r in rows:
        r["candle_age_sec"] = 900.0
        r["fno_age_sec"] = 1200.0
    m = mon.rolling_window_metrics(rows)
    v = mon.check_degrade(m)
    assert v["degraded"] is True
    assert any(r.startswith("stale-candle-") for r in v["reasons"])
    assert any(r.startswith("stale-fno-") for r in v["reasons"])


def test_degrade_artifact_mismatch_and_missing_tf():
    rows = _mixed_rows(20, hit=0.6, conf=0.6)
    rows[0]["limitations"] = ["artifact-mismatch-h60: meta horizon 15 != 60"]
    for i, r in enumerate(rows):  # 50% missing-TF rate over explicit flags
        r["missing_tfs"] = ["1h"] if i < 10 else []
    m = mon.rolling_window_metrics(rows)
    assert m["artifact_mismatch_count"] == 1
    v = mon.check_degrade(m)
    assert v["degraded"] is True
    assert any("artifact-spec-mismatch" in r for r in v["reasons"])
    assert any(r.startswith("missing-tf-rate-") for r in v["reasons"])


def test_healthy_window_not_degraded():
    rows = _mixed_rows(100, hit=0.6, conf=0.6)
    m = mon.rolling_window_metrics(rows)
    v = mon.check_degrade(m, baseline={"brier": 5.0, "hit_rate": 0.1})
    assert v == {"degraded": False, "reasons": []}


# ---------------------------------------------------------------------------
# bundle roundtrip (no live-env mutation)
# ---------------------------------------------------------------------------

def test_bundle_roundtrip():
    before = dict(os.environ)
    bundle = mon.resolve_release_bundle()
    assert bundle["feature_schema"] == "f12-v1"
    assert bundle["target_spec"] == "v2-atr-em-session"
    assert bundle["code"]["forecast_weights_version"].startswith("forecast-")
    assert bundle["code"]["forecast_v2_model"] in ("v1", "logistic-v2")
    assert bundle["calibrator"]["version"] == "cal-v1"
    assert bundle["model"]["version"] == "logistic-v2-h60-v1"
    assert set(bundle["bundle_fields"]) >= {
        "code", "model", "calibrator", "feature_schema", "target_spec",
    }

    plan = mon.rollback_to(bundle)
    assert plan["action"] == "rollback-plan-only-no-mutation"
    assert plan["promotion_locked"] is True
    assert "FORECAST_WEIGHTS_VERSION" in plan["env_flags"]
    assert "FORECAST_V2_MODEL" in plan["env_flags"]
    assert len(plan["steps"]) >= 5
    assert plan["bundle"] == bundle
    assert dict(os.environ) == before  # never mutates live env


# ---------------------------------------------------------------------------
# HTTP router (unregistered in main; fail-open, never 500)
# ---------------------------------------------------------------------------

def _client():
    from app.api import monitoring as api_mon

    app = FastAPI()
    app.include_router(api_mon.router)
    return TestClient(app)


def test_forecast_health_never_500():
    resp = _client().get("/api/v1/monitoring/forecast-health?limit=50")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {"status", "degraded", "reasons", "metrics", "thresholds"}
    assert body["status"] in ("healthy", "degraded", "unknown")
    assert isinstance(body["degraded"], bool)


def test_forecast_config_ok():
    resp = _client().get("/api/v1/monitoring/forecast-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["bundle"]["feature_schema"] == "f12-v1"
    assert body["bundle"]["target_spec"] == "v2-atr-em-session"
