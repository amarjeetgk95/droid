"""Unit and integration tests for DROID ML Engine Milestone 2.

Covers:
- Triple-Barrier Labeling & Path Excursion computation
- Probability Calibration (Platt & Isotonic) with ECE and Brier scoring
- Purged Walk-Forward Cross-Validation (purge window & embargo)
- Breakout Validation Model predictions
- Trade Outcome Meta-Label Model predictions
- Stage B Shadow Gating non-interference verification
- API /api/v1/ml/shadow-gate-eval endpoint
"""
from decimal import Decimal
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml.calibration.calibrators import ProbabilityCalibrator
from app.ml.features.schema import NEUTRAL_IMPUTE_V3, FEATURE_NAMES_V3
from app.ml.models.breakout_model import breakout_model
from app.ml.models.trade_outcome_model import trade_outcome_model
from app.ml.research.labeling import compute_triple_barrier
from app.ml.validation.purged_cv import PurgedWalkForwardCV
from app.signals.strategies.base import SignalCandidate


def test_triple_barrier_target_first():
    """Simulates price hitting Target 1 before Stop Loss."""
    entry = 25000.0
    target = 25050.0  # +50
    stop = 24975.0    # -25

    # Candles that move straight up to target
    candles = [
        {"high": 25010.0, "low": 24995.0, "close": 25005.0},
        {"high": 25030.0, "low": 25000.0, "close": 25025.0},
        {"high": 25060.0, "low": 25020.0, "close": 25055.0},  # Target reached here
    ]

    res = compute_triple_barrier(
        entry_price=entry,
        target_1=target,
        stop_loss=stop,
        direction="LONG_CALL",
        future_bars=candles,
        time_limit_bars=45,
    )

    assert res.label_name == "TARGET_FIRST"
    assert res.label == 2
    assert res.bars_to_exit == 3
    assert res.mfe_r >= 2.0  # +60 pts / 25 risk = 2.4R
    assert res.mae_r <= 0.2  # low was 24995 -> 5 pts adverse / 25 = 0.2R


def test_triple_barrier_stop_first():
    """Simulates price hitting Stop Loss before Target 1."""
    entry = 25000.0
    target = 25050.0
    stop = 24975.0

    # Candles that move down to stop
    candles = [
        {"high": 25005.0, "low": 24985.0, "close": 24990.0},
        {"high": 24990.0, "low": 24965.0, "close": 24970.0},  # Stop hit here (low 24965 < 24975)
    ]

    res = compute_triple_barrier(
        entry_price=entry,
        target_1=target,
        stop_loss=stop,
        direction="LONG_CALL",
        future_bars=candles,
        time_limit_bars=45,
    )

    assert res.label_name == "STOP_FIRST"
    assert res.label == 0
    assert res.bars_to_exit == 2


def test_triple_barrier_timeout():
    """Simulates horizontal barrier timeout when neither barrier is reached."""
    entry = 25000.0
    target = 25100.0
    stop = 24900.0

    # 10 flat candles with time_limit_bars=5
    candles = [{"high": 25010.0, "low": 24990.0, "close": 25000.0} for _ in range(10)]

    res = compute_triple_barrier(
        entry_price=entry,
        target_1=target,
        stop_loss=stop,
        direction="LONG_CALL",
        future_bars=candles,
        time_limit_bars=5,
    )

    assert res.label_name == "TIMEOUT"
    assert res.label == 1
    assert res.bars_to_exit == 5


def test_probability_calibrator_fit_and_persistence(tmp_path):
    """Tests Platt scaling calibration, metrics, and persistence round-trip."""
    np.random.seed(42)
    raw_p = np.random.uniform(0.1, 0.9, size=100)
    y_true = (raw_p > 0.55).astype(int)

    calibrator = ProbabilityCalibrator(method="platt")
    calibrator.fit(raw_p, y_true)

    assert calibrator.is_fitted
    assert 0.0 <= calibrator.brier_score <= 1.0
    assert 0.0 <= calibrator.ece_score <= 1.0

    p_test = 0.75
    cal_p = calibrator.calibrate(p_test)
    assert 0.0 <= cal_p <= 1.0

    # Test file persistence roundtrip
    saved_file = tmp_path / "test_calibrator.joblib"
    calibrator.save(saved_file)
    loaded = ProbabilityCalibrator.load(saved_file)

    assert loaded.is_fitted
    assert loaded.method == "platt"
    assert np.isclose(loaded.calibrate(p_test), cal_p)


def test_purged_walk_forward_cv():
    """Validates that PurgedWalkForwardCV enforces purge windows without index leakage."""
    n_samples = 300
    cv = PurgedWalkForwardCV(n_splits=3, purge_bars=10, embargo_bars=5)
    splits = list(cv.split(np.arange(n_samples)))

    assert len(splits) == 3
    for train_idx, test_idx in splits:
        assert len(train_idx) > 0
        assert len(test_idx) > 0
        assert len(set(train_idx).intersection(set(test_idx))) == 0
        assert min(test_idx) >= max(train_idx) + 10


def test_breakout_model_prediction():
    """Verifies Breakout Model outputs valid probabilities and continuation flag."""
    vec = [NEUTRAL_IMPUTE_V3[k] for k in FEATURE_NAMES_V3]
    res = breakout_model.predict_breakout_quality(vec, direction="CALL", strategy_name="BREAKOUT")

    assert "p_valid_breakout" in res
    assert "p_false_breakout" in res
    assert "is_continuation" in res
    assert np.isclose(res["p_valid_breakout"] + res["p_false_breakout"], 1.0, atol=1e-3)
    assert 0.0 <= res["p_valid_breakout"] <= 1.0


def test_trade_outcome_model_prediction():
    """Verifies Trade Outcome Model predicts calibrated 3-class distribution and excursions."""
    vec = [NEUTRAL_IMPUTE_V3[k] for k in FEATURE_NAMES_V3]
    res = trade_outcome_model.predict_trade_outcome(vec, direction_prob=0.60, breakout_prob=0.65)

    assert "p_target_before_stop" in res
    assert "p_stop_before_target" in res
    assert "p_timeout" in res
    assert "expected_mfe_r" in res
    assert "expected_mae_r" in res

    prob_sum = res["p_target_before_stop"] + res["p_stop_before_target"] + res["p_timeout"]
    assert np.isclose(prob_sum, 1.0, atol=1e-2)
    assert res["expected_mfe_r"] >= 0.0
    assert res["expected_mae_r"] >= 0.0


@pytest.mark.asyncio
async def test_stage_b_shadow_gating_non_interference():
    """Verifies Stage B Shadow Gating populates metadata but leaves candidate execution untouched."""
    from app.signals.pipeline.enrichment import enrich_candidate

    import time
    now_ms = int(time.time() * 1000)
    cand = SignalCandidate(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("25000.0"),
        entry_min=Decimal("25000.0"),
        entry_max=Decimal("25020.0"),
        trigger=Decimal("25010.0"),
        stop_loss=Decimal("24975.0"),
        target_1=Decimal("25050.0"),
        target_2=Decimal("25100.0"),
        risk_points=Decimal("25.0"),
        risk_reward_t1=2.0,
        risk_reward_t2=4.0,
        confidence=80.0,
        regime_score=80.0,
        context_snapshot={"timestamp_ms": now_ms, "regime": "TREND_UP"},
    )

    candles = [
        {
            "timestamp": now_ms,
            "timestamp_ms": now_ms,
            "open": 25000.0,
            "high": 25010.0,
            "low": 24990.0,
            "close": 25005.0,
            "volume": 1000,
        }
    ]

    fused_score, inst_overlay, explain, fsm_state, ai_advice, ml_pred = await enrich_candidate(
        cand=cand,
        active_candles=candles,
        fno_data=None,
        fno_is_degraded=False,
        risk_decision=None,
        overlay={},
        rejected_gates=[],
        decision_timestamp_ms=now_ms,
    )

    # Shadow gating must record in context snapshot
    assert "ml_shadow_gate" in cand.context_snapshot
    sg = cand.context_snapshot["ml_shadow_gate"]
    assert sg["action"] in ("PASS", "VETO")
    assert sg["counterfactual_tracked"] is True
    assert "p_target_before_stop" in sg

    # CRITICAL: Candidate must NOT be dropped or put in REJECT state by shadow gating
    assert fsm_state != "REJECT"
    assert any("ML Shadow Gate:" in r for r in cand.rationale)


def test_api_shadow_gate_endpoint():
    """Verifies GET /api/v1/ml/shadow-gate-eval returns structured shadow gating decision."""
    client = TestClient(app)
    response = client.get("/api/v1/ml/shadow-gate-eval?strategy=BREAKOUT&direction=CALL&direction_prob=0.65")
    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None
    payload = data["data"]
    assert payload["strategy"] == "BREAKOUT"
    assert "breakout" in payload
    assert "trade_outcome" in payload
    assert payload["shadow_decision"]["stage"] == "STAGE_B_SHADOW_GATING"
    assert payload["shadow_decision"]["authority"] == "OBSERVATIONAL_ONLY"
    assert payload["shadow_decision"]["recommendation"] in ("PASS", "VETO")
