"""
Unit and integration tests for VORTEX-SNAP Machine Learning Validator & Calibrator.
Validates 22-factor extraction, calibration, trainer, veto logic, and fail-open safety (§25-§27).
"""
from datetime import datetime, timezone
import numpy as np
import pytest

from app.signals.strategies.vortex_snap.types import Candle, EventType, LevelType, StructuralLevel
from app.signals.strategies.vortex_snap.session import MarketSessionModel
from app.signals.strategies.vortex_snap.strategy import VortexSnapStrategy
from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader
from app.signals.strategies.vortex_snap.ml.features import (
    FEATURE_NAMES,
    extract_features,
    MLFeatureVector,
)
from app.signals.strategies.vortex_snap.ml.calibrator import ProbabilityCalibrator
from app.signals.strategies.vortex_snap.ml.trainer import VortexMLTrainer
from app.signals.strategies.vortex_snap.ml.validator import VortexMLValidator, ValidationDecision


class TestVortexMLValidator:
    @pytest.fixture
    def sample_snapshot(self):
        strat = VortexSnapStrategy()
        d = datetime(2026, 9, 21, tzinfo=timezone.utc)
        candles = HistoricalDataLoader.generate_synthetic_session(d, start_price=24000.0, seed=42)
        snap = strat.feature_engine.compute_snapshot(
            instrument="NIFTY",
            candles_1m=candles[:40],
            timestamp_ms=candles[39].timestamp,
            spot_price=candles[39].close,
            pdh=24100.0,
            pdl=23900.0,
        )
        return snap, candles[39]

    def test_feature_extraction_dimension_and_bounds(self, sample_snapshot):
        snap, candle = sample_snapshot
        session_model = MarketSessionModel()
        session_info = session_model.evaluate(candle.timestamp)
        lvl = StructuralLevel(
            level_type=LevelType.PDH,
            price=24100.0,
            relevance_score=1.0,
            distance_points=100.0,
            distance_pct=0.0041,
            touch_count=2,
            rejection_count=0,
        )

        vec = extract_features(
            snapshot=snap,
            current_candle=candle,
            session_info=session_info,
            interacted_level=lvl,
            event_type=EventType.CONTINUATION,
            direction=1,
        )

        arr = vec.to_array()
        assert len(arr) == 22
        assert len(FEATURE_NAMES) == 22
        assert not np.isnan(arr).any()
        assert not np.isinf(arr).any()

    def test_probability_calibrator_sigmoid(self):
        calibrator = ProbabilityCalibrator(method="sigmoid")
        raw_p = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
        y = np.array([0, 0, 0, 1, 1, 1])

        calibrator.fit(raw_p, y)
        calibrated = calibrator.calibrate(raw_p)

        assert len(calibrated) == len(raw_p)
        assert (calibrated >= 0.0).all() and (calibrated <= 1.0).all()
        # Monotonicity check
        assert calibrated[0] < calibrated[-1]

    def test_calibration_diagnostics(self):
        raw_p = np.array([0.2, 0.4, 0.6, 0.8])
        cal_p = np.array([0.1, 0.3, 0.7, 0.9])
        y = np.array([0, 0, 1, 1])

        diag = ProbabilityCalibrator.compute_diagnostics(raw_p, cal_p, y, n_bins=5)
        assert 0.0 <= diag.brier_score_calibrated <= 1.0
        assert 0.0 <= diag.expected_calibration_error <= 1.0
        assert 0.0 <= diag.max_calibration_error <= 1.0
        assert len(diag.bin_counts) == 5

    def test_model_trainer_pipeline(self, tmp_path):
        # Generate 2 days of sessions for training
        d1 = datetime(2026, 9, 21, tzinfo=timezone.utc)
        d2 = datetime(2026, 9, 22, tzinfo=timezone.utc)
        c1 = HistoricalDataLoader.generate_synthetic_session(d1, start_price=24000.0, seed=1)
        c2 = HistoricalDataLoader.generate_synthetic_session(d2, start_price=24050.0, seed=2)
        contexts = HistoricalDataLoader.compute_session_levels(c1 + c2)

        trainer = VortexMLTrainer(forward_bars_window=10)
        dataset = trainer.build_dataset_from_contexts(contexts, instrument="NIFTY")

        assert len(dataset.X) > 0
        assert len(dataset.y) == len(dataset.X)

        model, calibrator, report = trainer.train_and_calibrate(dataset)
        assert report.roc_auc >= 0.0
        assert len(report.feature_importances) == 22

        artifact_file = tmp_path / "model.joblib"
        trainer.save_model_artifact(model, calibrator, report, artifact_file)
        assert artifact_file.exists()

    def test_ml_validator_veto_logic(self, sample_snapshot, tmp_path):
        snap, candle = sample_snapshot
        session_model = MarketSessionModel()
        session_info = session_model.evaluate(candle.timestamp)

        # Train and save mock model
        trainer = VortexMLTrainer()
        X = np.random.randn(30, 22).astype(np.float32)
        y = np.array([0, 1] * 15, dtype=np.int32)
        dataset = trainer.build_dataset_from_contexts([], "NIFTY")
        dataset.X = X
        dataset.y = y

        model, calibrator, report = trainer.train_and_calibrate(dataset)
        artifact_path = tmp_path / "validator_model.joblib"
        trainer.save_model_artifact(model, calibrator, report, artifact_path)

        # High threshold validator -> should veto low probability candidate
        validator = VortexMLValidator(
            artifact_path=artifact_path,
            acceptance_threshold=0.85,
            enabled=True,
        )
        decision = validator.validate(
            snapshot=snap,
            current_candle=candle,
            session_info=session_info,
        )
        assert isinstance(decision, ValidationDecision)
        assert decision.is_accepted is False
        assert "below threshold" in (decision.veto_reason or "")

    def test_ml_validator_fail_safe_fallback(self, sample_snapshot):
        snap, candle = sample_snapshot
        session_model = MarketSessionModel()
        session_info = session_model.evaluate(candle.timestamp)

        # Validator with nonexistent artifact -> must fail open
        validator = VortexMLValidator(
            artifact_path="nonexistent/path/model.joblib",
            acceptance_threshold=0.50,
            enabled=True,
        )
        decision = validator.validate(
            snapshot=snap,
            current_candle=candle,
            session_info=session_info,
        )
        # Fail open (§25)
        assert decision.is_accepted is True
        assert decision.veto_reason is None
        assert decision.calibrated_probability == 0.50
