"""P2-4/P2-5: calibrator + abstention + risk v2 for 1H forecast v2.3.

Hermetic: pure-math unit tests + sync ensemble_forecast wiring with
monkeypatched env flags. No network, no broker, no DB, no filesystem
writes (calibrator persistence is covered via to_dict/from_dict only).
"""

import math

import pytest

from app.ml.calibration_metrics import ece_equal_width
from app.ml.calibrators import (
    CALIBRATOR_VERSION,
    CalibratorV1,
    fit_isotonic_ovr,
    fit_temperature,
)
from app.research import risk_v2
from app.research.trend_forecast import (
    apply_abstention_v2,
    get_abstain_threshold,
    should_abstain,
    validate_forecast_v2,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _overconfident_fixture(n: int = 240):
    """Deterministic miscalibrated fixture: 90% confidence, 60% accuracy.

    Rows cycle true labels 0/1/2; 3-in-5 rows put 0.90 on truth, the rest
    put 0.90 on the next class. ECE_before ~= |0.6 - 0.9| = 0.30.
    """
    y, P = [], []
    for i in range(n):
        true = i % 3
        y.append(true)
        if i % 5 < 3:
            row = [0.05, 0.05, 0.05]
            row[true] = 0.90
        else:
            wrong = (true + 1) % 3
            row = [0.05, 0.05, 0.05]
            row[wrong] = 0.90
        P.append(row)
    return y, P


def _ece_of(y, P):
    pmax = [max(r) for r in P]
    y_pred = [max(range(3), key=lambda k: r[k]) for r in P]
    return ece_equal_width(y, pmax, 10, y_pred)["ece"]


def _minimal_mtf(regime="RANGING", alignment=("BULLISH", 100.0)):
    bias, score = alignment
    return {
        "instrument": "NIFTY 50",
        "per_timeframe": {
            "1h": {"features": {
                "quant": {"supertrend_dir": "BULLISH", "rsi_14": 60.0, "atr_14": 50.0},
                "regime": regime,
                "session": "EARLY",
            }},
        },
        "alignment": {"overall_bias": bias, "alignment_score": score},
    }


def _ml_bull():
    return {
        "bullish_pct": 80.0, "neutral_pct": 10.0, "bearish_pct": 10.0,
        "predicted_bias": "BULLISH", "trend_strength": 70.0,
        "confidence_score": 80.0, "model_source": "heuristic_ensemble",
        "calibrated": False, "model_version": "XGBoost-LightGBM-Ensemble-v1.0-heuristic",
        "horizon_minutes": 60, "target_spec_version": "v1-atr-band",
    }


def _options(iv=15.0, dte=2.0):
    return {
        "instrument": "NIFTY 50", "available": True, "data_quality": "LIVE",
        "pcr_oi": 1.0, "pcr_vol": 1.0, "atm_iv": iv,
        "call_wall": None, "put_wall": None, "max_pain": None,
        "days_to_expiry": dte, "atm_theta": -10.0,
        "atm_gamma": 0.001, "atm_vega": 10.0,
    }


def _ensemble(**kw):
    from app.research.trend_forecast import TrendForecast1H
    fc = TrendForecast1H.__new__(TrendForecast1H)
    return fc.ensemble_forecast(**kw)


# ---------------------------------------------------------------------------
# P2-4 calibrator
# ---------------------------------------------------------------------------

def test_temperature_improves_ece_on_overconfident_fixture():
    y, P = _overconfident_fixture()
    before = _ece_of(y, P)
    assert before > 0.25  # fixture really is overconfident
    d = fit_temperature(P, y, oos=True)
    assert d["method"] == "temperature"
    assert d["version"] == CALIBRATOR_VERSION == "cal-v1"
    assert d["fit_n"] == len(y)
    assert d["T"] > 1.0  # softens overconfidence
    assert d["ece_after"] < d["ece_before"]
    assert d["nll_after"] < d["nll_before"]
    cal = CalibratorV1.from_dict(d)
    P_cal = cal.calibrate_rows(P)
    assert abs(_ece_of(y, P_cal) - d["ece_after"]) < 1e-9


def test_temperature_fit_requires_oos_flag():
    y, P = _overconfident_fixture(30)
    with pytest.raises(ValueError):
        fit_temperature(P, y, oos=False)
    with pytest.raises(ValueError):
        fit_temperature(P, y, oos=None)
    with pytest.raises(ValueError):
        CalibratorV1().fit(P, y, oos=False)
    with pytest.raises(ValueError):
        fit_isotonic_ovr(P, y, oos=False)


def test_simplex_preserved_and_T1_identity():
    y, P = _overconfident_fixture(30)
    d = fit_temperature(P, y, oos=True)
    cal = CalibratorV1.from_dict(d)
    for row in P[:10]:
        out = cal.calibrate(row)
        assert len(out) == 3
        assert abs(sum(out) - 1.0) < 1e-9
        assert all(0.0 <= v <= 1.0 for v in out)
    ident = CalibratorV1(T=1.0)
    for row in ([0.7, 0.2, 0.1], [0.1, 0.1, 0.8], [1 / 3] * 3):
        out = ident.calibrate(row)
        assert abs(sum(out) - 1.0) < 1e-9
        for a, b in zip(out, row):
            assert abs(a - b) < 1e-9
    dd = cal.calibrate_dict({"bullish": 0.7, "neutral": 0.2, "bearish": 0.1})
    assert set(dd) == {"bullish", "neutral", "bearish"}
    assert abs(sum(dd.values()) - 1.0) < 1e-9


def test_calibrator_dict_roundtrip_and_artifact_keys():
    y, P = _overconfident_fixture(60)
    d = fit_temperature(P, y, oos=True, fit_window={"start": "2026-01-01", "end": "2026-02-01"})
    for key in ("method", "T", "fit_n", "fit_window", "ece_before", "ece_after", "version"):
        assert key in d, f"artifact missing {key}"
    assert d["version"] == "cal-v1"
    assert d["fit_window"] == {"start": "2026-01-01", "end": "2026-02-01"}
    cal = CalibratorV1.from_dict(d)
    assert cal.to_dict()["T"] == pytest.approx(d["T"])
    assert CalibratorV1.from_dict(cal.to_dict()).T == pytest.approx(cal.T)
    with pytest.raises(ValueError):
        CalibratorV1.from_dict({"version": "cal-v0", "method": "temperature", "T": 1.0})


def test_isotonic_challenger_simplex():
    y, P = _overconfident_fixture(90)
    d = fit_isotonic_ovr(P, y, oos=True)
    assert d["method"] == "isotonic-ovr" and d["version"] == "cal-v1"
    cal = CalibratorV1.from_dict(d)
    for row in P[:15]:
        out = cal.calibrate(row)
        assert abs(sum(out) - 1.0) < 1e-9
        assert all(0.0 <= v <= 1.0 for v in out)


# ---------------------------------------------------------------------------
# P2-5 risk_v2 pure math + guards
# ---------------------------------------------------------------------------

def test_expected_move_math_and_dte_floor():
    em = risk_v2.expected_move(25000.0, 15.0, 1.0)
    assert em == pytest.approx(0.15 * 25000.0 * math.sqrt(1.0 / 365.0), rel=1e-9)
    # expiry-day guard: DTE<=0 clamps to 0.25d
    assert risk_v2.expected_move(25000.0, 15.0, 0.0) == pytest.approx(
        risk_v2.expected_move(25000.0, 15.0, 0.25))
    assert risk_v2.expected_move(25000.0, 15.0, -3.0) == pytest.approx(
        risk_v2.expected_move(25000.0, 15.0, 0.25))


def test_expected_move_guards_to_none():
    assert risk_v2.expected_move(25000.0, None, 1.0) is None      # missing IV
    assert risk_v2.expected_move(25000.0, 15.0, None) is None     # missing DTE
    assert risk_v2.expected_move(25000.0, 0.0, 1.0) is None       # zero IV
    assert risk_v2.expected_move(25000.0, -5.0, 1.0) is None      # negative IV
    assert risk_v2.expected_move(0.0, 15.0, 1.0) is None          # bad spot
    assert risk_v2.expected_move(None, 15.0, 1.0) is None
    assert risk_v2.expected_move(25000.0, 15.0, float("nan")) is None


def test_target_distances_em_vs_atr_only():
    d = risk_v2.target_distances(50.0, 200.0)
    assert d["target_distance"] == pytest.approx(min(1.8 * 50.0, 0.70 * 200.0))  # 90
    assert d["inval_distance"] == pytest.approx(max(1.1 * 50.0, 0.35 * 200.0))   # 70
    assert d["basis"] == "ATR+EM"
    fb = risk_v2.target_distances(50.0, None)  # risk fallback
    assert fb["target_distance"] == pytest.approx(90.0)
    assert fb["inval_distance"] == pytest.approx(55.0)
    assert fb["basis"] == "ATR-only"
    fb2 = risk_v2.target_distances(50.0, float("nan"))
    assert fb2["basis"] == "ATR-only"
    with_barrier = risk_v2.target_distances(50.0, 200.0, barrier=100.0)
    assert with_barrier["inval_distance"] == pytest.approx(100.0)
    with pytest.raises(ValueError):
        risk_v2.target_distances(0.0, 200.0)
    with pytest.raises(ValueError):
        risk_v2.target_distances(None, None)


def test_closing_scale():
    assert risk_v2.closing_scale(60, 60) == 1.0
    assert risk_v2.closing_scale(30, 60) == pytest.approx(0.5)
    assert risk_v2.closing_scale(120, 60) == 1.0
    assert risk_v2.closing_scale(0, 60) == 0.0
    assert risk_v2.closing_scale(-5, 60) == 0.0
    assert risk_v2.closing_scale(None, 60) == 1.0


def test_expected_range_neutral():
    r = risk_v2.expected_range_neutral(25000.0, 200.0)
    assert r == {"lower": 24800.0, "mid": 25000.0, "upper": 25200.0}
    with pytest.raises(ValueError):
        risk_v2.expected_range_neutral(25000.0, None)


def test_compute_targets_directional_and_neutral():
    bull = risk_v2.compute_targets("BULLISH", 25000.0, 50.0, 200.0)
    assert bull["target_price"] == pytest.approx(25090.0)
    assert bull["invalidation_price"] == pytest.approx(25000.0 - 70.0)
    assert bull["basis"] == "ATR+EM" and bull["expected_range"] is None
    bear = risk_v2.compute_targets("BEARISH", 25000.0, 50.0, 200.0)
    assert bear["target_price"] == pytest.approx(25000.0 - 90.0)
    assert bear["invalidation_price"] == pytest.approx(25000.0 + 70.0)
    neut = risk_v2.compute_targets("NEUTRAL", 25000.0, 50.0, 200.0)
    assert neut["target_price"] is None and neut["invalidation_price"] is None
    assert neut["expected_range"] == {"lower": 24800.0, "mid": 25000.0, "upper": 25200.0}
    neut_fb = risk_v2.compute_targets("NEUTRAL", 25000.0, 50.0, None)
    assert neut_fb["basis"] == "ATR-only"
    assert neut_fb["expected_range"] == {
        "lower": 25000.0 - 90.0, "mid": 25000.0, "upper": 25000.0 + 90.0}


# ---------------------------------------------------------------------------
# abstention pure matrix
# ---------------------------------------------------------------------------

def test_abstention_matrix_below_above_threshold():
    assert should_abstain(0.54, 0.55) is True
    assert should_abstain(0.55, 0.55) is False  # equal passes
    assert should_abstain(0.61, 0.60) is False
    v = apply_abstention_v2("BULLISH", 0.54, 0.55)
    assert v == {"direction": "NEUTRAL", "status": "ABSTAIN",
                 "abstained": True,
                 "limitation": "abstain-confidence-0.5400-below-0.55"}
    assert "abstain-confidence" in v["limitation"]
    v2 = apply_abstention_v2("BEARISH", 0.75, 0.60)
    assert v2["direction"] == "BEARISH" and v2["status"] == "RESEARCH"
    assert v2["abstained"] is False and v2["limitation"] is None


def test_abstain_threshold_volatile_bump_and_overrides(monkeypatch):
    assert get_abstain_threshold("RANGING", "EARLY") == 0.55
    assert get_abstain_threshold("VOLATILE", "EARLY") == 0.60
    assert get_abstain_threshold("RANGING", "CLOSING") == 0.60
    assert get_abstain_threshold("VOLATILE", "CLOSING") == 0.60  # single bump
    assert get_abstain_threshold("RANGING", "EARLY", override=0.60) == 0.60
    monkeypatch.setenv("FORECAST_ABSTAIN_T", "0.60")
    assert get_abstain_threshold("RANGING", "EARLY") == 0.60
    assert get_abstain_threshold("VOLATILE", "EARLY") == 0.65
    monkeypatch.setenv("FORECAST_ABSTAIN_T", "garbage")
    assert get_abstain_threshold("RANGING", "EARLY") == 0.55  # bad env -> default


# ---------------------------------------------------------------------------
# wiring: flag-gated v2 branch in ensemble_forecast
# ---------------------------------------------------------------------------

def test_v1_default_unchanged_no_v2_keys():
    res = _ensemble(mtf_features=_minimal_mtf(), indicator_outputs=[],
                    ml_forecast=_ml_bull(), options_ctx=_options(),
                    current_price=25000.0, horizon="1h")
    assert res["calibrator_version"] == "none-v0"
    assert res["calibrated"] is False
    assert res["raw_confidence"] == res["confidence"] == max(res["probabilities"].values())
    assert "target_basis" not in res
    assert "abstain_threshold" not in res
    assert "expected_range" not in res
    assert validate_forecast_v2(res, record=False) == []


def test_v2_branch_abstains_weak_score_with_risk_fallback(monkeypatch):
    monkeypatch.setenv("FORECAST_V2_MODEL", "logistic-v2")
    weak = _minimal_mtf(regime="RANGING", alignment=("NEUTRAL", 0.0))
    res = _ensemble(mtf_features=weak, indicator_outputs=[], ml_forecast=None,
                    options_ctx=_options(iv=None, dte=None),
                    current_price=25000.0, horizon="1h")
    # abstention: flat score -> neutral prob ~0.45 < 0.55
    assert res["status"] == "ABSTAIN"
    assert res["direction"] == "NEUTRAL"
    assert any(str(l).startswith("abstain-confidence-") for l in res["limitations"])
    # risk fallback: no IV/DTE -> ATR-only + limitation, range not nulls
    assert res["target_basis"] == "ATR-only"
    assert "target_basis=ATR-only" in res["limitations"]
    assert res["target_price"] is None and res["invalidation_price"] is None
    assert res["expected_range"] == {"lower": 25000.0 - 90.0, "mid": 25000.0,
                                     "upper": 25000.0 + 90.0}
    # calibration honesty: no artifact on disk -> uncalibrated, raw kept
    assert res["calibrated"] is False
    assert "calibrator-missing-uncalibrated" in res["limitations"]
    assert res["abstain_threshold"] == 0.55
    assert validate_forecast_v2(res, record=False) == []


def test_v2_branch_directional_above_threshold_em_targets(monkeypatch):
    monkeypatch.setenv("FORECAST_V2_MODEL", "logistic-v2")
    res = _ensemble(mtf_features=_minimal_mtf(), indicator_outputs=[],
                    ml_forecast=_ml_bull(), options_ctx=_options(),
                    current_price=25000.0, horizon="1h")
    assert res["direction"] == "BULLISH"
    assert res["status"] == "RESEARCH"
    assert res["confidence"] > 0.55
    assert res["raw_confidence"] == max(res["probabilities"].values())
    assert res["target_basis"] == "ATR+EM"
    assert "target_basis=ATR-only" not in res["limitations"]
    em = risk_v2.expected_move(25000.0, 15.0, 2.0)
    assert res["target_price"] == pytest.approx(25000.0 + min(1.8 * 50.0, 0.70 * em))
    assert res["invalidation_price"] == pytest.approx(25000.0 - max(1.1 * 50.0, 0.35 * em))
    assert res["expected_range"] is None
    assert validate_forecast_v2(res, record=False) == []


def test_v2_branch_conservative_threshold_param_abstains(monkeypatch):
    monkeypatch.setenv("FORECAST_V2_MODEL", "logistic-v2")
    res = _ensemble(mtf_features=_minimal_mtf(), indicator_outputs=[],
                    ml_forecast=_ml_bull(), options_ctx=_options(),
                    current_price=25000.0, horizon="1h",
                    abstain_threshold=0.60)  # second Cycle-1 candidate
    # bull prob ~0.64 > 0.55 but the 0.60 candidate still passes here...
    assert res["abstain_threshold"] == 0.60
    res2 = _ensemble(mtf_features=_minimal_mtf(), indicator_outputs=[],
                     ml_forecast=_ml_bull(), options_ctx=_options(),
                     current_price=25000.0, horizon="1h",
                     abstain_threshold=0.99)  # forces abstention
    assert res2["status"] == "ABSTAIN" and res2["direction"] == "NEUTRAL"
    assert validate_forecast_v2(res2, record=False) == []


def test_v2_branch_volatile_bump_triggers_abstain(monkeypatch):
    monkeypatch.setenv("FORECAST_V2_MODEL", "logistic-v2")
    calm = _ensemble(mtf_features=_minimal_mtf(regime="RANGING"),
                     indicator_outputs=[], ml_forecast=_ml_bull(),
                     options_ctx=_options(), current_price=25000.0, horizon="1h")
    assert calm["status"] == "RESEARCH"  # ~0.64 clears 0.55
    conf = calm["confidence"]
    assert 0.55 < conf < 0.70
    hot = _ensemble(mtf_features=_minimal_mtf(regime="VOLATILE"),
                    indicator_outputs=[], ml_forecast=_ml_bull(),
                    options_ctx=_options(), current_price=25000.0, horizon="1h")
    assert hot["abstain_threshold"] == 0.60
    # volatile bump must bite exactly when confidence sits between the lines
    mid = _ensemble(mtf_features=_minimal_mtf(regime="VOLATILE"),
                    indicator_outputs=[], ml_forecast=_ml_bull(),
                    options_ctx=_options(), current_price=25000.0, horizon="1h",
                    abstain_threshold=conf + 0.01)
    assert mid["status"] == "ABSTAIN"


def test_v2_branch_ignores_other_horizons(monkeypatch):
    monkeypatch.setenv("FORECAST_V2_MODEL", "logistic-v2")
    res = _ensemble(mtf_features=_minimal_mtf(), indicator_outputs=[],
                    ml_forecast=_ml_bull(), options_ctx=_options(),
                    current_price=25000.0, horizon="5m")
    assert "target_basis" not in res and "abstain_threshold" not in res
