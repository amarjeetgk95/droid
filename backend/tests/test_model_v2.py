"""P2-3: logistic-v2 primary, strict h60 loader, registry. No network, fast."""
import json
import random

import pytest

from app.ml import model_v2
from app.ml.model_v2 import (
    EXPECTED_WIDTH_V2,
    FEATURE_NAMES_V2,
    FEATURE_SCHEMA_V2,
    MODEL_VERSION_V2,
    TARGET_SPEC_V2,
    hash_dataset,
    load_logistic_v2,
    predict_proba_v2,
    save_logistic_v2,
    train_logistic_v2,
    validate_logistic_artifact,
)
from app.ml import trainer


def _synthetic_v2_dataset(n: int = 90, seed: int = 42):
    """Deterministic 12-wide 3-class dataset (separable shifts, no network)."""
    rng = random.Random(seed)
    X, y = [], []
    for i in range(n):
        cls = i % 3  # balanced bear/neut/bull
        shift = {0: -0.8, 1: 0.0, 2: 0.8}[cls]
        row = [rng.gauss(shift, 1.0) for _ in range(EXPECTED_WIDTH_V2)]
        X.append(row)
        y.append(cls)
    return X, y


class TestV2Contract:
    def test_feature_schema_width(self):
        # Width follows the canonical extractor when it exists (plan: 12-15
        # under f12-v1), else the pinned 12-name fallback contract.
        try:
            from app.ml.feature_extractor_v2 import FEATURE_NAMES_V2 as _REAL
            assert list(FEATURE_NAMES_V2) == list(_REAL)
        except ImportError:
            assert len(FEATURE_NAMES_V2) == 12
        assert EXPECTED_WIDTH_V2 == len(FEATURE_NAMES_V2)
        assert 12 <= EXPECTED_WIDTH_V2 <= 15
        assert FEATURE_SCHEMA_V2 == "f12-v1"
        assert TARGET_SPEC_V2 == "v2-atr-em-session"
        assert MODEL_VERSION_V2 == "logistic-v2-h60-v1"


class TestLogisticV2:
    def test_simplex_output(self):
        X, y = _synthetic_v2_dataset()
        model = train_logistic_v2(X, y)
        assert set(model.keys()) >= {"coef", "intercept", "classes"}
        assert model["classes"] == [0, 1, 2]
        assert len(model["coef"]) == 3 and len(model["coef"][0]) == EXPECTED_WIDTH_V2
        for vec in (X[0], X[1], [0.0] * EXPECTED_WIDTH_V2):
            p = predict_proba_v2(model, vec)
            assert len(p) == 3
            assert all(0.0 <= v <= 1.0 for v in p)
            assert abs(sum(p) - 1.0) < 1e-6

    def test_rejects_bad_width_and_single_class(self):
        X, y = _synthetic_v2_dataset(n=9)
        with pytest.raises(ValueError, match="width"):
            train_logistic_v2([r[:5] for r in X], y)
        with pytest.raises(ValueError, match="width"):
            predict_proba_v2(train_logistic_v2(X, y), [0.0] * 5)
        with pytest.raises(ValueError, match="distinct classes"):
            train_logistic_v2([[0.1] * EXPECTED_WIDTH_V2] * 6, [1] * 6)
        with pytest.raises(ValueError, match="Labels must be"):
            train_logistic_v2([[0.1] * EXPECTED_WIDTH_V2] * 6, [0, 1, 2, 5, 1, 0])

    def test_numpy_fallback_backend_when_no_sklearn(self):
        # Pure-numpy path must work regardless; when sklearn exists the
        # backend flag flips but the simplex contract is identical.
        X, y = _synthetic_v2_dataset(n=30)
        model = train_logistic_v2(X, y)
        assert model["backend"] in ("numpy-gd", "sklearn")
        if not model_v2.HAS_SKLEARN:
            assert model["backend"] == "numpy-gd"
        p = predict_proba_v2(model, X[0])
        assert abs(sum(p) - 1.0) < 1e-6

    def test_save_load_roundtrip_tmp(self, tmp_path):
        X, y = _synthetic_v2_dataset(n=60)
        model = train_logistic_v2(X, y)
        dh = hash_dataset(X, y)
        m_path = tmp_path / "model_h60_logistic.json"
        mt_path = tmp_path / "meta_h60_logistic.json"
        meta = save_logistic_v2(model, dataset_hash=dh, n=len(X),
                                model_path=m_path, meta_path=mt_path)
        assert meta["model_version"] == "logistic-v2-h60-v1"
        assert meta["dataset_hash"] == dh
        assert meta["feature_schema"] == "f12-v1"
        assert meta["target_spec"] == "v2-atr-em-session"
        assert meta["n"] == len(X)
        assert meta["training_time"] and meta["git_sha"]
        assert m_path.exists() and mt_path.exists()
        loaded, loaded_meta = load_logistic_v2(m_path, mt_path)
        assert loaded is not None and loaded_meta is not None
        assert loaded["coef"] == model["coef"]
        assert loaded["intercept"] == model["intercept"]
        assert validate_logistic_artifact(loaded, loaded_meta)
        # Inference identical after roundtrip.
        assert predict_proba_v2(loaded, X[0]) == pytest.approx(predict_proba_v2(model, X[0]))

    def test_load_missing_returns_none_none(self, tmp_path):
        m, mt = load_logistic_v2(tmp_path / "nope.json", tmp_path / "nope_meta.json")
        assert m is None and mt is None

    @pytest.mark.skipif(not model_v2.HAS_SKLEARN, reason="sklearn not installed")
    def test_sklearn_challenger_backend(self):
        # Only runs when the ml extra is installed; guards the sklearn path.
        from sklearn.linear_model import LogisticRegression  # noqa: F401

        X, y = _synthetic_v2_dataset(n=60)
        model = train_logistic_v2(X, y, C=1.0, max_iter=500)
        assert model["backend"] == "sklearn"
        assert abs(sum(predict_proba_v2(model, X[0])) - 1.0) < 1e-6


class TestValidateWidth:
    def test_matrix_and_vector(self):
        X, _ = _synthetic_v2_dataset(n=6)
        assert trainer.validate_width(X) == EXPECTED_WIDTH_V2
        assert trainer.validate_width(X[0]) == EXPECTED_WIDTH_V2
        assert trainer.validate_width(EXPECTED_WIDTH_V2) == EXPECTED_WIDTH_V2
        wrong = 10 if EXPECTED_WIDTH_V2 != 10 else 5
        with pytest.raises(ValueError, match="width mismatch"):
            trainer.validate_width(X, expected_width=wrong)
        with pytest.raises(ValueError, match="ragged"):
            trainer.validate_width([X[0], X[1][:3]])
        with pytest.raises(ValueError, match="empty"):
            trainer.validate_width([])


class TestStrictLoader:
    def test_missing_returns_none_no_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(trainer, "MODEL_DIR", tmp_path)
        assert trainer.load_ensemble_strict(60, EXPECTED_WIDTH_V2, "v2-atr-em-session") is None
        # Legacy loader stays intact for v1 compat (triple, no raise).
        assert trainer.load_ensemble(60) == (None, None, None)

    def _write_fake_triple(self, tmp_path, monkeypatch, *, horizon, width, spec):
        monkeypatch.setattr(trainer, "MODEL_DIR", tmp_path)
        xgb_path, lgb_path, meta_path = trainer.artifact_paths(horizon)
        xgb_path.write_text("{}")
        lgb_path.write_text("dummy")
        meta_path.write_text(json.dumps({
            "horizon_minutes": horizon,
            "target_spec_version": spec,
            "feature_names": [f"f{i}" for i in range(width)],
            "model_version": "fake",
        }))
        return xgb_path, lgb_path, meta_path

    def test_rejects_wrong_width(self, tmp_path, monkeypatch):
        wrong = 10 if EXPECTED_WIDTH_V2 != 10 else 5
        self._write_fake_triple(tmp_path, monkeypatch, horizon=60, width=wrong,
                                 spec="v2-atr-em-session")
        assert trainer.load_ensemble_strict(60, EXPECTED_WIDTH_V2, "v2-atr-em-session") is None

    def test_rejects_wrong_spec(self, tmp_path, monkeypatch):
        self._write_fake_triple(tmp_path, monkeypatch, horizon=60, width=EXPECTED_WIDTH_V2,
                                 spec="v1-atr-band")
        assert trainer.load_ensemble_strict(60, EXPECTED_WIDTH_V2, "v2-atr-em-session") is None

    def test_rejects_horizon_mismatch(self, tmp_path, monkeypatch):
        # Files exist at the requested horizon but meta records another one.
        self._write_fake_triple(tmp_path, monkeypatch, horizon=30, width=10,
                                 spec="v1-atr-band")
        _, _, meta_path = trainer.artifact_paths(30)
        meta = json.loads(meta_path.read_text())
        meta["horizon_minutes"] = 60
        meta_path.write_text(json.dumps(meta))
        assert trainer.load_ensemble_strict(30, 10, "v1-atr-band") is None

    def test_strict_predict_no_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(trainer, "MODEL_DIR", tmp_path)
        vec = [0.0] * EXPECTED_WIDTH_V2
        assert trainer.ensemble_predict_proba_strict(vec) is None
        assert trainer.ensemble_predict_proba(vec, horizon_minutes=60,
                                              use_strict=True) is None
        # Wrong-width input vector is rejected (None, never raises).
        wrong_vec = [0.0] * (10 if EXPECTED_WIDTH_V2 != 10 else 5)
        assert trainer.ensemble_predict_proba_strict(wrong_vec) is None
        # Legacy signature still works positionally (backward compat).
        assert trainer.ensemble_predict_proba(vec, 60) is None


class TestTrainerH60Guards:
    @pytest.mark.asyncio
    async def test_h60_v2_width_spec_reaches_dep_check(self):
        # xgb/lgb/sklearn are NOT installed here -> RuntimeError proves the
        # h60/12-wide/v2-spec validation passed (a ValueError would mean
        # the challenger path rejected the v2 contract).
        X, y = _synthetic_v2_dataset(n=120)
        with pytest.raises(RuntimeError, match="ML deps not installed"):
            await trainer.train_ensemble(features=X, labels=y, horizon_minutes=60,
                                         target_spec_version="v2-atr-em-session")

    @pytest.mark.asyncio
    async def test_rejects_unknown_spec_and_width_mismatch(self):
        X, y = _synthetic_v2_dataset(n=120)
        with pytest.raises(ValueError, match="target_spec_version"):
            await trainer.train_ensemble(features=X, labels=y, horizon_minutes=60,
                                         target_spec_version="v0-made-up")
        with pytest.raises(ValueError, match="width mismatch"):
            await trainer.train_ensemble(features=X, labels=y, horizon_minutes=60,
                                         target_spec_version="v2-atr-em-session",
                                         expected_width=10)


class TestRegistry:
    def test_append_and_read_tmp(self, tmp_path):
        from app.ml.registry import read_registry, record_model

        reg = tmp_path / "registry.jsonl"
        e1 = record_model({
            "model_version": "logistic-v2-h60-v1",
            "dataset_hash": "abc123",
            "feature_schema": "f12-v1",
            "target_spec": "v2-atr-em-session",
            "calibrator_version": "none-v0",
            "git_sha": "testsha",
            "validation_report_id": None,
            "decision": "candidate",
        }, registry_path=reg)
        assert e1["timestamp"]
        assert reg.exists()
        rows = read_registry(reg)
        assert len(rows) == 1 and rows[0]["model_version"] == "logistic-v2-h60-v1"
        record_model(dict(e1, decision="promoted"), registry_path=reg)
        assert len(read_registry(reg)) == 2
        assert reg.read_text().strip().count("\n") == 1  # JSONL: 2 lines

    def test_rejects_non_dict(self, tmp_path):
        from app.ml.registry import record_model

        with pytest.raises(ValueError):
            record_model("not-a-dict", registry_path=tmp_path / "r.jsonl")
