"""P3-1 shadow deployment tests. Hermetic: mocked forecasters, no network/DB.

Covers: shadow pair shape + same_inputs_hash, no global env mutation,
record=True indicator_id separation (trend_forecast_1h vs _v2), compare math
(hit-rate/Wilson/Brier/log-loss/ECE), minimum-evidence gate, and the
scheduler market-closed no-op.
"""

import copy
import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.research.predictions import PredictionService, SnapshotService
from app.research.shadow import (
    SHADOW_INDICATOR_ID_V1,
    SHADOW_INDICATOR_ID_V2,
    SHADOW_MODEL_V1,
    SHADOW_MODEL_V2,
    run_shadow_pair,
)
from app.research.shadow_scheduler import run_hourly_shadow

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _load_shadow_compare():
    spec = importlib.util.spec_from_file_location(
        "shadow_compare", str(SCRIPTS_DIR / "shadow_compare.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sc = _load_shadow_compare()

BASE_TS = datetime(2026, 9, 9, 4, 30, tzinfo=timezone.utc)  # 10:00 IST


def _payload(direction="BULLISH", probs=None, confidence=None, price=25000.0,
             regime="TRENDING_UP", session="EARLY", dq="HEALTHY", status="RESEARCH"):
    probs = probs or {"bullish": 0.6, "neutral": 0.2, "bearish": 0.2}
    return {
        "instrument": "NIFTY 50",
        "timeframe": "1h",
        "forecast_horizon": "1h",
        "horizon_candles": 1,
        "current_price": price,
        "direction": direction,
        "score": 45.0 if direction == "BULLISH" else (-45.0 if direction == "BEARISH" else 0.0),
        "confidence": confidence if confidence is not None else max(probs.values()),
        "probabilities": dict(probs),
        "status": status,
        "data_quality": dq,
        "regime": regime,
        "session": session,
        "settleable": True,
        "settle_reason": "same-regular-session",
        "model_source": "logistic_v2" if dq == "HEALTHY" else "unavailable",
        "calibrated": True,
        "model_version": "logistic-v2-h60",
        "calibrator_version": "cal-v1",
        "weights_version": "forecast-v1",
        "target_spec_version": "v2-atr-em-session",
        "layer_scores": {"mtf_alignment": 10.0, "indicators": 5.0, "ml": 8.0,
                         "options": 1.0, "structure": 2.0},
        "ml_forecast": None,
        "options_context": {"available": True},
        "target_price": price + 50.0,
        "invalidation_price": price - 30.0,
        "limitations": [],
        "prediction_id": None,
        "snapshot_id": None,
    }


class _MockForecaster:
    """Deterministic pair forecaster. Honors explicit model kwargs; else call order."""

    def __init__(self, v1_payload, v2_payload):
        self.v1 = copy.deepcopy(v1_payload)
        self.v2 = copy.deepcopy(v2_payload)
        self.calls = []

    async def forecast(self, instrument="NIFTY 50", horizon="1h", record=False, **kwargs):
        self.calls.append({"instrument": instrument, "horizon": horizon,
                           "record": record, "kwargs": dict(kwargs)})
        model = None
        for key in ("model_override", "forecast_v2_model", "model", "v2_model"):
            if key in kwargs and kwargs[key] is not None:
                model = str(kwargs[key]).lower()
                break
        if model is not None:
            payload = self.v2 if ("logistic" in model or model == "v2") else self.v1
        else:
            payload = self.v1 if len(self.calls) == 1 else self.v2
        return copy.deepcopy(payload)


@pytest.fixture
def clean_memory():
    PredictionService._memory_predictions.clear()
    PredictionService._memory_outcomes.clear()
    SnapshotService._memory_snapshots.clear()
    yield
    PredictionService._memory_predictions.clear()
    PredictionService._memory_outcomes.clear()
    SnapshotService._memory_snapshots.clear()


def test_indicator_ids_separated():
    assert SHADOW_INDICATOR_ID_V1 == "trend_forecast_1h"
    assert SHADOW_INDICATOR_ID_V2 == "trend_forecast_1h_v2"
    assert SHADOW_INDICATOR_ID_V1 != SHADOW_INDICATOR_ID_V2
    assert SHADOW_MODEL_V1 == "v1"
    assert SHADOW_MODEL_V2 == "logistic-v2"


async def test_shadow_pair_shape_and_hash(clean_memory):
    fc = _MockForecaster(_payload("BULLISH"), _payload("BEARISH"))
    pair = await run_shadow_pair("NIFTY 50", horizon="1h", record=False,
                                 forecaster=fc, now_utc=BASE_TS)
    assert set(("v1", "v2", "same_inputs_hash")) <= set(pair)
    assert pair["v1"]["indicator_id"] == SHADOW_INDICATOR_ID_V1
    assert pair["v2"]["indicator_id"] == SHADOW_INDICATOR_ID_V2
    assert pair["v1"]["shadow_model"] == "v1"
    assert pair["v2"]["shadow_model"] == "logistic-v2"
    assert pair["v1"]["direction"] == "BULLISH"
    assert pair["v2"]["direction"] == "BEARISH"
    assert pair["same_inputs"] is True  # same price on both legs
    assert len(pair["same_inputs_hash"]) == 64
    # Deterministic: same trigger re-run hashes identically.
    fc2 = _MockForecaster(_payload("BULLISH"), _payload("BEARISH"))
    pair2 = await run_shadow_pair("NIFTY 50", horizon="1h", record=False,
                                  forecaster=fc2, now_utc=BASE_TS)
    assert pair2["same_inputs_hash"] == pair["same_inputs_hash"]
    # Underlying forecaster always saw record=False (shadow owns persistence).
    assert all(c["record"] is False for c in fc.calls)


async def test_shadow_inputs_diverge_flagged(clean_memory):
    fc = _MockForecaster(_payload("BULLISH", price=25000.0),
                         _payload("BULLISH", price=25100.0))
    pair = await run_shadow_pair("NIFTY 50", record=False, forecaster=fc, now_utc=BASE_TS)
    assert pair["same_inputs"] is False
    assert pair["same_inputs_hash"]  # still produced


async def test_shadow_no_global_env_mutation(clean_memory, monkeypatch):
    import app.research.trend_forecast as tf

    monkeypatch.setenv("FORECAST_V2_MODEL", "v1")
    before_env = dict(os.environ)
    before_flag = tf._forecast_v2_model_flag
    assert tf._forecast_v2_model_flag() == "v1"

    fc = _MockForecaster(_payload("BULLISH"), _payload("BEARISH"))
    await run_shadow_pair("NIFTY 50", record=False, forecaster=fc, now_utc=BASE_TS)

    assert dict(os.environ) == before_env
    assert os.environ.get("FORECAST_V2_MODEL") == "v1"
    # Scoped patch restored: same function object, same behavior.
    assert tf._forecast_v2_model_flag is before_flag
    assert tf._forecast_v2_model_flag() == "v1"


async def test_shadow_record_persists_distinct_ids(clean_memory):
    fc = _MockForecaster(_payload("BULLISH"), _payload("BEARISH"))
    pair = await run_shadow_pair("NIFTY 50", record=True, forecaster=fc, now_utc=BASE_TS)
    v1_id = pair["v1"]["prediction_id"]
    v2_id = pair["v2"]["prediction_id"]
    assert v1_id and v2_id and v1_id != v2_id
    assert pair["v1"]["snapshot_id"] and pair["v2"]["snapshot_id"]
    assert pair["v1"]["snapshot_id"] != pair["v2"]["snapshot_id"]

    stored = list(PredictionService._memory_predictions.values())
    by_indicator = {p.indicator_id: p for p in stored}
    assert set(by_indicator) >= {SHADOW_INDICATOR_ID_V1, SHADOW_INDICATOR_ID_V2}
    assert by_indicator[SHADOW_INDICATOR_ID_V1].snapshot_id == pair["v1"]["snapshot_id"]
    assert by_indicator[SHADOW_INDICATOR_ID_V2].snapshot_id == pair["v2"]["snapshot_id"]
    # Every persisted shadow prediction links a real snapshot.
    for pred in (by_indicator[SHADOW_INDICATOR_ID_V1], by_indicator[SHADOW_INDICATOR_ID_V2]):
        snap = await SnapshotService.get_snapshot(pred.snapshot_id)
        assert snap is not None
        assert snap.instrument == "NIFTY 50"


# ---------------------------------------------------------------------------
# Compare math
# ---------------------------------------------------------------------------

def _settled_rows(specs):
    """Build (pred_rows, outcome_by_id) from compact specs.

    spec = (pid, probs{bull,neut,bear}, actual_dir, correct, regime, session, dq, ts, created)
    """
    preds, outcomes = [], {}
    for pid, probs, actual, correct, regime, session, dq, ts, created in specs:
        preds.append({
            "prediction_id": pid,
            "instrument": "NIFTY 50",
            "timestamp": ts,
            "created_at": created,
            "direction": "BULLISH",
            "confidence": max(probs.values()),
            "component_values": {"probabilities": dict(probs), "regime": regime,
                                 "session": session, "data_quality": dq, "status": "RESEARCH"},
        })
        outcomes[pid] = {"is_correct": correct, "actual_direction": actual}
    return preds, outcomes


def test_compare_math_correct():
    ts0 = BASE_TS.isoformat()
    v1_specs = [
        ("v1a", {"bullish": 0.6, "neutral": 0.2, "bearish": 0.2}, "BULLISH", True,
         "TRENDING_UP", "EARLY", "HEALTHY", ts0, ts0),
        ("v1b", {"bullish": 0.6, "neutral": 0.2, "bearish": 0.2}, "BEARISH", False,
         "RANGING", "MID", "HEALTHY", ts0, ts0),
        ("v1c", {"bullish": 0.2, "neutral": 0.2, "bearish": 0.6}, "BEARISH", True,
         "TRENDING_UP", "EARLY", "DEGRADED", ts0, ts0),
        ("v1d", {"bullish": 0.25, "neutral": 0.5, "bearish": 0.25}, "NEUTRAL", True,
         "RANGING", "MID", "HEALTHY", ts0, ts0),
    ]
    v1_preds, v1_out = _settled_rows(v1_specs)
    rows = sc.build_side_rows(v1_preds, v1_out)
    assert len(rows) == 4  # nothing dropped
    summary = sc.summarize_side(rows)

    # Hit-rate + Wilson match the canonical evaluator.
    from app.research.validation.statistical_evaluator import StatisticalEvaluator

    assert summary["n"] == 4
    assert summary["hits"] == 3
    assert summary["hit_rate"] == 75.0
    assert summary["wilson95"] == list(StatisticalEvaluator.calculate_confidence_interval(3, 4))

    # Brier / log-loss / ECE match canonical calibration metrics.
    from app.ml.calibration_metrics import (
        brier_score_3class,
        ece_equal_width,
        log_loss_3class,
    )

    y_idx = [2, 0, 0, 1]
    P = [[0.2, 0.2, 0.6], [0.2, 0.2, 0.6], [0.6, 0.2, 0.2], [0.25, 0.5, 0.25]]
    assert summary["brier"] == round(float(brier_score_3class(y_idx, P)), 4)
    assert summary["log_loss"] == round(float(log_loss_3class(y_idx, P)), 4)
    pmax = [max(r) for r in P]
    y_pred = [2, 2, 0, 1]
    assert summary["ece10"] == round(float(ece_equal_width(y_idx, pmax, 10, y_pred)["ece"]), 4)
    assert len(summary["reliability"]) == 10

    # DQ failure rate: 1/4 degraded.
    assert summary["dq_fail_n"] == 1
    assert summary["dq_failure_rate"] == 0.25
    # Splits present on both axes.
    assert set(summary["by_regime"]) == {"TRENDING_UP", "RANGING"}
    assert set(summary["by_session"]) == {"EARLY", "MID"}
    assert summary["by_regime"]["TRENDING_UP"]["n"] == 2


def test_compare_rows_without_outcome_dropped():
    ts0 = BASE_TS.isoformat()
    preds, outcomes = _settled_rows([
        ("k1", {"bullish": 0.6, "neutral": 0.2, "bearish": 0.2}, "BULLISH", True,
         "TRENDING_UP", "EARLY", "HEALTHY", ts0, ts0),
    ])
    preds.append({"prediction_id": "unsettled", "component_values": {}})
    rows = sc.build_side_rows(preds, outcomes)
    assert [r["prediction_id"] for r in rows] == ["k1"]


def test_min_evidence_gate():
    thin = sc.check_min_evidence(10, 2.0, 250, 14)
    assert thin["sufficient"] is False
    assert thin["warning"] and "INSUFFICIENT" in thin["warning"]

    # OR rule: either bar alone suffices.
    assert sc.check_min_evidence(250, 2.0, 250, 14)["sufficient"] is True
    assert sc.check_min_evidence(10, 14.0, 250, 14)["sufficient"] is True
    assert sc.check_min_evidence(300, 20.0, 250, 14)["sufficient"] is True
    assert sc.check_min_evidence(250, 2.0, 250, 14)["warning"] is None


def test_report_deltas_and_latency():
    ts0 = BASE_TS
    ts1 = (BASE_TS + timedelta(days=1)).isoformat()
    mk = lambda pid, hit, ts: (
        pid, {"bullish": 0.7, "neutral": 0.2, "bearish": 0.1}, "BULLISH", hit,
        "TRENDING_UP", "EARLY", "HEALTHY", ts,
        (datetime.fromisoformat(ts.replace("Z", "+00:00")) + timedelta(seconds=3)).isoformat(),
    )
    v1_preds, v1_out = _settled_rows([mk("a1", True, ts0.isoformat()), mk("a2", False, ts1)])
    v2_preds, v2_out = _settled_rows([mk("b1", True, ts0.isoformat()), mk("b2", True, ts1)])
    report = sc.build_report(sc.build_side_rows(v1_preds, v1_out),
                             sc.build_side_rows(v2_preds, v2_out),
                             instruments=["NIFTY 50"], min_settleable=250, max_days=14)
    assert report["deltas_v2_minus_v1"]["hit_rate_pp"] == 50.0
    assert report["v1"]["latency"]["n"] == 2
    assert report["v1"]["latency"]["mean"] == 3.0
    assert report["evidence"]["sufficient"] is False  # 2 pairs, 1 day
    md = sc.render_markdown(report)
    assert "Shadow Comparison" in md
    assert "INSUFFICIENT" in md


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def _closed_window():
    return {"universe": "nse", "settleable": False,
            "reason": "observation-outside-session",
            "t_plus_h_utc": BASE_TS, "session_close_utc": None}


def _open_window():
    return {"universe": "nse", "settleable": True, "reason": "same-regular-session",
            "t_plus_h_utc": BASE_TS, "session_close_utc": None}


async def test_scheduler_noop_when_market_closed(clean_memory, monkeypatch):
    from unittest.mock import AsyncMock, patch

    fc = AsyncMock()
    fc.forecast = AsyncMock(return_value=_payload())
    with patch("app.ml.sessions.classify_window", return_value=_closed_window()):
        summary = await run_hourly_shadow(["NIFTY 50"], forecaster=fc, now_utc=BASE_TS)
    assert summary["ran"] == []
    assert summary["results"]["NIFTY 50"]["status"] == "skipped-market-closed"
    assert fc.forecast.await_count == 0


async def test_scheduler_runs_when_open(clean_memory):
    from unittest.mock import patch

    fc = _MockForecaster(_payload("BULLISH"), _payload("BEARISH"))
    with patch("app.ml.sessions.classify_window", return_value=_open_window()):
        summary = await run_hourly_shadow(["NIFTY 50"], forecaster=fc, now_utc=BASE_TS)
    assert summary["ran"] == ["NIFTY 50"]
    assert summary["results"]["NIFTY 50"]["status"] == "recorded"
    assert summary["results"]["NIFTY 50"]["prediction_ids"]["v1"] is not None
    assert summary["results"]["NIFTY 50"]["prediction_ids"]["v2"] is not None
