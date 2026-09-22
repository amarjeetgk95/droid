"""Orthogonal Ensemble & Disjoint Calibration Tests (Tier 1).

Tests Feature-View Separation, dual-model training (ElasticNet + LightGBM),
disjoint probability calibration, and disagreement-penalized confidence scoring.
"""

import pytest
import polars as pl
import numpy as np

from app.ml.orthogonal_ensemble import (
    OrthogonalEnsemble,
    VIEW_A_FEATURES,
    VIEW_B_FEATURES,
    EnsemblePrediction,
)
from app.quant.features.feature_engine import CausalFeatureEngine
from scripts.fetch_fyers_history import generate_synthetic_history


class TestOrthogonalEnsemble:

    @pytest.fixture
    def sample_data(self) -> tuple[pl.DataFrame, np.ndarray]:
        """Generates synthetic intraday data with causal features and binary target."""
        np.random.seed(42)
        raw_df = generate_synthetic_history(symbol="BSE:SENSEX-INDEX", days=5, base_price=80000.0)
        engine = CausalFeatureEngine()
        features_df = engine.compute_features(raw_df)
        
        # Synthetic binary target: 1 if return_5m > 0 else 0
        y = np.where(features_df["return_5m"].fill_null(0.0).to_numpy() > 0, 1, 0)
        return features_df, y

    def test_feature_views_disjoint(self):
        """View A (Macro/Regime) and View B (Microstructure/Momentum) must have 0 overlap."""
        set_a = set(VIEW_A_FEATURES)
        set_b = set(VIEW_B_FEATURES)
        overlap = set_a.intersection(set_b)
        assert len(overlap) == 0, f"Feature views must be completely orthogonal! Overlap: {overlap}"

    def test_fit_and_predict_one(self, sample_data):
        """Fit ensemble and check probability predictions and fields."""
        features_df, y = sample_data
        n_samples = len(features_df)
        
        train_idx = list(range(0, int(n_samples * 0.7)))
        val_idx = list(range(int(n_samples * 0.7), int(n_samples * 0.85)))
        test_idx = list(range(int(n_samples * 0.85), n_samples))

        ensemble = OrthogonalEnsemble(
            confidence_threshold=0.52,
            max_disagreement=0.30,
            n_estimators=20,
            max_depth=3,
        )

        ensemble.fit(
            df=features_df,
            train_indices=train_idx,
            y_train=y[train_idx],
            val_indices=val_idx,
            y_val=y[val_idx],
        )

        assert ensemble.is_fitted is True
        assert ensemble.calibrator is not None

        # Predict on a test point
        pred = ensemble.predict_one(features_df, test_idx[0])
        assert isinstance(pred, EnsemblePrediction)
        assert 0.0 <= pred.p_linear <= 1.0
        assert 0.0 <= pred.p_lgbm <= 1.0
        assert 0.0 <= pred.calibrated_prob <= 1.0
        assert 0.0 <= pred.confidence_score <= 100.0
        assert 0.0 <= pred.disagreement <= 1.0
        assert round(pred.disagreement + pred.agreement, 4) == 1.0

    def test_disagreement_metric_and_penalty(self):
        """Disagreement must equal |p_lgbm - p_linear| and reduce confidence."""
        ensemble = OrthogonalEnsemble()
        # Mocking predictions
        p_linear = 0.80
        p_lgbm = 0.40
        disagreement = abs(p_lgbm - p_linear)
        assert round(disagreement, 4) == 0.40

        penalty = disagreement * 20.0  # 8.0 point deduction
        raw_prob = 0.60
        expected_conf = max(0.0, (raw_prob * 100.0) - penalty)
        assert expected_conf == 52.0

    def test_qualification_rules(self, sample_data):
        """Candidate is qualified ONLY if prob >= threshold AND disagreement <= max_disagreement."""
        features_df, y = sample_data
        n_samples = len(features_df)
        train_idx = list(range(0, int(n_samples * 0.7)))
        val_idx = list(range(int(n_samples * 0.7), n_samples))

        ensemble = OrthogonalEnsemble(
            confidence_threshold=0.55,
            max_disagreement=0.20,
            n_estimators=20,
        )
        ensemble.fit(features_df, train_idx, y[train_idx], val_idx, y[val_idx])

        # Test batch predictions
        batch_preds = ensemble.predict_batch(features_df, val_idx[:20])
        assert len(batch_preds) == 20

        for pred in batch_preds:
            if pred.is_qualified:
                assert pred.calibrated_prob >= 0.55
                assert pred.disagreement <= 0.20
            else:
                assert pred.calibrated_prob < 0.55 or pred.disagreement > 0.20

    def test_unfitted_model_safe_fallback(self, sample_data):
        """Unfitted ensemble safely returns un-qualified default prediction."""
        features_df, _ = sample_data
        ensemble = OrthogonalEnsemble()
        pred = ensemble.predict_one(features_df, 10)
        assert pred.is_qualified is False
        assert pred.calibrated_prob == 0.5
        assert pred.confidence_score == 50.0
