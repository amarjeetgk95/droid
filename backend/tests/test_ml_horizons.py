"""Phase 0 multi-horizon predictor tests: label spec, horizon validation,
trainer guards, calibration aggregation. No xgboost/lightgbm required."""
import pytest

from app.ml.targets import (
    DEFAULT_HORIZON_MINUTES,
    SUPPORTED_HORIZONS,
    TARGET_SPEC_VERSION,
    describe_target,
    label_forward_return,
    validate_horizon,
)
from app.ml.calibration import settle_prediction, summarize_calibration
from app.ml.trainer import artifact_paths


class TestTargetSpec:
    def test_supported_horizons_cover_requested_set(self):
        for h in (5, 15, 30, 60, 90, 120):
            assert h in SUPPORTED_HORIZONS
        assert DEFAULT_HORIZON_MINUTES == 15

    def test_label_bullish_bearish_neutral(self):
        # spot 100, atr 2 -> band = 0.25*2/100 = 0.005
        assert label_forward_return(100.0, 101.0, 2.0) == 2  # +1% > band
        assert label_forward_return(100.0, 99.0, 2.0) == 0  # -1% < -band
        assert label_forward_return(100.0, 100.2, 2.0) == 1  # +0.2% inside band
        assert label_forward_return(100.0, 100.0, 2.0) == 1

    def test_label_refuses_missing_data(self):
        with pytest.raises(ValueError):
            label_forward_return(0.0, 100.0, 2.0)
        with pytest.raises(ValueError):
            label_forward_return(100.0, 100.0, 0.0)

    def test_horizon_never_silently_remapped(self):
        with pytest.raises(ValueError):
            validate_horizon(7)
        with pytest.raises(ValueError):
            validate_horizon(1200)
        assert validate_horizon(15) == 15

    def test_describe_target_marks_session_crossing(self):
        assert describe_target(15)["session_note"] == "intraday-clean"
        assert "EOD" in describe_target(120)["session_note"]
        assert describe_target(15)["target_spec_version"] == TARGET_SPEC_VERSION


class TestTrainerGuards:
    @pytest.mark.asyncio
    async def test_rejects_small_dataset_without_deps(self):
        from app.ml.trainer import train_ensemble

        with pytest.raises(ValueError, match="at least 100 samples"):
            await train_ensemble(features=[[0.1] * 10] * 10, labels=[1] * 10)

    @pytest.mark.asyncio
    async def test_rejects_bad_horizon_and_spec(self):
        from app.ml.trainer import train_ensemble

        feats = [[0.1] * 10] * 120
        labels = [1] * 120
        with pytest.raises(ValueError, match="Unsupported horizon"):
            await train_ensemble(features=feats, labels=labels, horizon_minutes=7)
        with pytest.raises(ValueError, match="target_spec_version"):
            await train_ensemble(features=feats, labels=labels, target_spec_version="v0-made-up")

    def test_per_horizon_artifact_paths(self):
        xgb, lgb, meta = artifact_paths(15)
        assert xgb.name == "xgb_model.json"  # default keeps legacy names
        xgb60, _, meta60 = artifact_paths(60)
        assert "h60" in xgb60.name and "h60" in meta60.name
        assert xgb60 != xgb


class TestPredictorHorizon:
    @pytest.mark.asyncio
    async def test_invalid_horizon_raises_before_io(self):
        from app.ml.predictor import ml_predictor

        with pytest.raises(ValueError, match="Unsupported horizon"):
            await ml_predictor.predict_probabilities("NIFTY", horizon_minutes=45)

    @pytest.mark.asyncio
    async def test_response_carries_horizon_and_source(self):
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock, patch

        from app.models.market import NormalizedQuote, DataStatus
        from app.ml.predictor import ml_predictor

        mock_quote = NormalizedQuote(
            symbol="NSE:NIFTY50-INDEX",
            display_name="NIFTY 50",
            timestamp=datetime.now(timezone.utc),
            ltp=25000.0,
            open=24900.0,
            high=25050.0,
            low=24850.0,
            previous_close=24900.0,
            change=100.0,
            change_percent=0.4,
            volume=1000000,
            status=DataStatus.LIVE,
        )
        with patch.object(ml_predictor.market_service, "get_quote", new=AsyncMock(return_value=mock_quote)):
            pred = await ml_predictor.predict_probabilities("NIFTY", horizon_minutes=30)
            assert pred.horizon_minutes == 30
            assert pred.target_spec_version == TARGET_SPEC_VERSION
            assert pred.model_source == "heuristic_ensemble"  # no artifacts in repo
            assert pred.calibrated is False


class TestCalibration:
    def test_settle_and_summarize(self):
        # spot 100, atr 2: +1% -> BULLISH(2); -1% -> BEARISH(0); flat -> NEUTRAL(1)
        assert settle_prediction(100.0, 101.0, 2.0)["outcome_label"] == 2
        rows = [
            {"symbol": "NIFTY", "horizon_minutes": 15, "predicted_bias": "BULLISH",
             "outcome_name": "BULLISH", "confidence_score": 70.0,
             "target_spec_version": TARGET_SPEC_VERSION},
            {"symbol": "NIFTY", "horizon_minutes": 15, "predicted_bias": "BULLISH",
             "outcome_name": "NEUTRAL", "confidence_score": 60.0,
             "target_spec_version": TARGET_SPEC_VERSION},
            {"symbol": "NIFTY", "horizon_minutes": 15, "predicted_bias": "BEARISH",
             "outcome_name": None, "confidence_score": 80.0,  # unsettled -> skipped
             "target_spec_version": TARGET_SPEC_VERSION},
            {"symbol": "NIFTY", "horizon_minutes": 15, "predicted_bias": "BULLISH",
             "outcome_name": "BULLISH", "confidence_score": 70.0,
             "target_spec_version": "v0-other"},  # wrong spec -> excluded
        ]
        summary = summarize_calibration(rows)
        assert summary["overall"]["n"] == 2
        assert summary["overall"]["hit_rate"] == 0.5
        assert summary["excluded_other_spec_versions"] == 1
        bull = next(c for c in summary["cells"] if c["predicted_bias"] == "BULLISH")
        assert bull["n"] == 2 and bull["hits"] == 1
