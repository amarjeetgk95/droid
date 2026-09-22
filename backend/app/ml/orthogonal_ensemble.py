"""Orthogonal Machine Learning Ensemble & Disjoint Calibration (Tier 1).

Implements Feature-View Separation with diverse inductive biases:
- View A (Macro/Regime/Structural): Regularized ElasticNet Logistic Regression
- View B (Microstructure/Momentum): LightGBM Gradient Boosted Decision Tree
- Disjoint Probability Calibration: Fitted exclusively on validation folds
- Model Agreement & Continuous Disagreement Dispersion Metrics
- Confidence Engine: Blends calibrated probabilities penalized by disagreement
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, List, Dict, Any, Optional
import polars as pl
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV
from lightgbm import LGBMClassifier
import structlog

logger = structlog.get_logger(__name__)

VIEW_A_FEATURES = [
    "vwap_distance",
    "ema_cross_spread",
    "atr_pct",
    "realized_vol_20",
    "return_15m",
    "rsi",
]

VIEW_B_FEATURES = [
    "return_1m",
    "return_3m",
    "candle_body_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "volume_ratio",
]


@dataclass
class EnsemblePrediction:
    p_linear: Optional[float]
    p_lgbm: Optional[float]
    p_ensemble: Optional[float]
    calibrated_prob: Optional[float]
    disagreement: Optional[float]
    agreement: Optional[float]
    confidence_score: Optional[float]  # 0 to 100, None when unfitted
    is_qualified: bool       # True if probability >= threshold and agreement is sufficient
    # Honesty contract: unfitted returns status="unfitted" with NULL probs
    # (never 0.5). Callers MUST check `status`/`is_fitted` before using probs.
    status: str = "ok"
    is_fallback: bool = False


class OrthogonalEnsemble:
    """Combines a linear regularized model (View A) and LightGBM (View B)."""

    def __init__(
        self,
        confidence_threshold: float = 0.55,
        max_disagreement: float = 0.35,
        l1_ratio: float = 0.5,
        c_reg: float = 0.1,
        n_estimators: int = 40,
        max_depth: int = 3,
        num_leaves: int = 7,
        learning_rate: float = 0.05,
        random_state: int = 42,
    ):
        self.confidence_threshold = confidence_threshold
        self.max_disagreement = max_disagreement

        # Scaler for linear model
        self.scaler = StandardScaler()

        # Model A: Regularized ElasticNet Logistic Regression (SAGA solver)
        self.linear_model = LogisticRegression(
            solver="saga",
            l1_ratio=l1_ratio,
            C=c_reg,
            max_iter=1000,
            random_state=random_state,
        )

        # Model B: Shallow regularized LightGBM (non-linear interactions)
        self.lgbm_model = LGBMClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            num_leaves=num_leaves,
            learning_rate=learning_rate,
            min_child_samples=5,
            random_state=random_state,
            verbose=-1,
        )

        # Calibrator fitted strictly on validation fold
        self.calibrator: Optional[CalibratedClassifierCV] = None
        self.is_fitted = False

    def _extract_views(
        self,
        df: pl.DataFrame,
        indices: list[int],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Extracts orthogonal feature views A and B from DataFrame at given indices."""
        sub_df = df[indices]

        # Extract View A (fill nulls with 0.0 or median)
        view_a_data = []
        for col in VIEW_A_FEATURES:
            if col in sub_df.columns:
                s = sub_df[col].fill_null(0.0).to_numpy()
            else:
                s = np.zeros(len(sub_df))
            view_a_data.append(s)
        X_a = np.column_stack(view_a_data)

        # Extract View B
        view_b_data = []
        for col in VIEW_B_FEATURES:
            if col in sub_df.columns:
                s = sub_df[col].fill_null(0.0).to_numpy()
            else:
                s = np.zeros(len(sub_df))
            view_b_data.append(s)
        X_b = np.column_stack(view_b_data)

        return X_a, X_b

    def fit(
        self,
        df: pl.DataFrame,
        train_indices: list[int],
        y_train: np.ndarray,  # Binary: 1 (win) or 0 (loss)
        val_indices: Optional[list[int]] = None,
        y_val: Optional[np.ndarray] = None,
    ):
        """Fits Model A on View A and Model B on View B using training data.
        If validation data provided, fits probability calibration on val fold.
        """
        if len(train_indices) < 10:
            raise ValueError(f"Insufficient training samples: {len(train_indices)}")

        X_a_train, X_b_train = self._extract_views(df, train_indices)
        X_a_scaled = self.scaler.fit_transform(X_a_train)

        # Check class balance
        unique_classes = np.unique(y_train)
        if len(unique_classes) < 2:
            # Degenerate case (all 1s or all 0s)
            logger.warning("degenerate_training_classes", unique=unique_classes.tolist())
            return

        # Fit models on respective feature views
        self.linear_model.fit(X_a_scaled, y_train)
        self.lgbm_model.fit(X_b_train, y_train)
        self.is_fitted = True

        # Disjoint Calibration on Validation Fold
        if val_indices is not None and y_val is not None and len(val_indices) >= 10:
            X_a_val, X_b_val = self._extract_views(df, val_indices)
            X_a_val_scaled = self.scaler.transform(X_a_val)

            p_lin_val = self.linear_model.predict_proba(X_a_val_scaled)[:, 1]
            p_lgb_val = self.lgbm_model.predict_proba(X_b_val)[:, 1]
            p_raw_val = 0.5 * (p_lin_val + p_lgb_val)

            # Fit Platt scaler (univariate logistic regression) on raw ensemble probability
            from sklearn.linear_model import LogisticRegression as PlattScaler
            self.calibrator = PlattScaler(C=1.0, max_iter=200)
            self.calibrator.fit(p_raw_val.reshape(-1, 1), y_val)
            logger.info("disjoint_calibration_fitted", val_samples=len(val_indices))

    def predict_one(
        self,
        df: pl.DataFrame,
        index: int,
    ) -> EnsemblePrediction:
        """Predicts outcome probability and disagreement for a single candidate.

        Unfitted returns status="unfitted" with NULL probs (never 0.5).
        Callers MUST check `status` before using probs.
        """
        if not self.is_fitted:
            logger.warning("orthogonal_ensemble_unfitted_fallback")
            return EnsemblePrediction(
                p_linear=None,
                p_lgbm=None,
                p_ensemble=None,
                calibrated_prob=None,
                disagreement=None,
                agreement=None,
                confidence_score=None,
                is_qualified=False,
                status="unfitted",
                is_fallback=True,
            )

        X_a, X_b = self._extract_views(df, [index])
        X_a_scaled = self.scaler.transform(X_a)

        p_linear = float(self.linear_model.predict_proba(X_a_scaled)[0, 1])
        p_lgbm = float(self.lgbm_model.predict_proba(X_b)[0, 1])
        p_raw = 0.5 * (p_linear + p_lgbm)

        # Calibrated probability
        if self.calibrator is not None:
            cal_p = float(self.calibrator.predict_proba(np.array([[p_raw]]))[0, 1])
        else:
            cal_p = p_raw

        disagreement = abs(p_lgbm - p_linear)
        agreement = 1.0 - disagreement

        # Confidence score: base probability penalized by disagreement
        penalty = disagreement * 20.0
        confidence = float(np.clip((cal_p * 100.0) - penalty, 0.0, 100.0))

        is_qualified = (
            cal_p >= self.confidence_threshold and
            disagreement <= self.max_disagreement
        )

        return EnsemblePrediction(
            p_linear=round(p_linear, 4),
            p_lgbm=round(p_lgbm, 4),
            p_ensemble=round(p_raw, 4),
            calibrated_prob=round(cal_p, 4),
            disagreement=round(disagreement, 4),
            agreement=round(agreement, 4),
            confidence_score=round(confidence, 1),
            is_qualified=is_qualified,
            status="ok",
            is_fallback=False,
        )

    def predict_batch(
        self,
        df: pl.DataFrame,
        indices: list[int],
    ) -> list[EnsemblePrediction]:
        """Vectorized batch prediction across candidates."""
        return [self.predict_one(df, idx) for idx in indices]
