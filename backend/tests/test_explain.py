"""Tests for immutable forecast explainability bundles (signals + research)."""
from types import SimpleNamespace

from app.research.trend_forecast import LAYER_WEIGHTS
from app.signals.explain import (
    STRATEGY_RULES,
    build_forecast_explain,
    build_signal_explain,
    layman_for_fno,
    layman_for_indicators,
)


def _candidate(**kw):
    base = dict(
        strategy="BREAKOUT",
        direction="LONG_CALL",
        technical_score=70.0,
        mtf_score=72.0,
        fno_score=68.0,
        regime_score=70.0,
        fno_degraded=False,
        vwap_degraded=False,
        vwap_coverage_pct=100.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _inputs(**kw):
    base = dict(
        spot=25000.0,
        vwap=24980.0,
        rsi=65.0,
        adx=28.0,
        volume_ratio=1.8,
        pcr=1.25,
        atm_iv=14.5,
        regime="TREND_UP",
        mtf_bias="BULLISH",
        indicators={"momentum": {"rsi": 65.0, "adx": 28.0}, "volume": {"ratio": 1.8}},
        fno={"pcr": 1.25, "atm_iv": 14.5, "max_pain": 25000.0},
        mtf={"overall_bias": "BULLISH"},
    )
    base.update(kw)
    return base


def _weights():
    return {
        "weights_fraction": {"technical": 0.40, "mtf": 0.20, "fno": 0.15, "regime": 0.10, "ai": 0.10, "ml_max": 0.07},
        "version": 2,
    }


def test_signal_explain_points_sum_sanity():
    cand = _candidate()
    ai = {"status": "AVAILABLE", "score": 70.0}
    ml = {"is_available": True, "bullish_pct": 70.0, "bearish_pct": 30.0}
    ex = build_signal_explain(cand, 70.0, ai, ml, None, _weights(), {"armed": 70.0}, [], _inputs(), {})
    assert ex["verdict"]["direction"] == "LONG_CALL"
    assert ex["weights_version"] == 2
    assert ex["threshold_armed"] == 70.0
    for m in ex["maths"]:
        if m["score"] is not None:
            assert m["points"] == round(m["score"] * m["weight"], 1)
    total = sum(m["points"] for m in ex["maths"])
    # weighted-sum ≈ fused (weights sum ≈ 1.02, no haircuts in this fixture)
    assert abs(total - 70.0) < 15.0


def test_signal_explain_layman_non_empty():
    ind = {"momentum": {"rsi": 65.0, "adx": 28.0}, "volume": {"ratio": 1.8}}
    bullets = layman_for_indicators(ind, "TREND_UP", 24980.0, 25000.0)
    assert 1 <= len(bullets) <= 5
    fno_bullets = layman_for_fno({"pcr": 1.25, "atm_iv": 14.5, "max_pain": 25000.0})
    assert len(fno_bullets) >= 1
    ex = build_signal_explain(_candidate(), 75.0, None, None, None, _weights(), {"armed": 70.0}, [], _inputs(), {})
    assert len(ex["why_layman"]) >= 1
    assert len(ex["what_would_change_mind"]) >= 2
    assert STRATEGY_RULES["BREAKOUT"] in ex["strategy_rule"]
    # every required strategy has a rule
    for s in ("BREAKOUT", "MEAN_REVERSION", "TREND_PULLBACK", "VWAP_SCALP", "MICRO_MOMENTUM",
              "EMA_RIBBON", "GAMMA_SQUEEZE", "GAMMA_SPIKE", "ORB"):
        assert STRATEGY_RULES[s]


def test_signal_explain_handles_missing_ai_ml():
    cand = _candidate()
    ex = build_signal_explain(cand, 60.0, None, None, None, None, None, None, None, None)
    assert ex["verdict"]["confidence"] == 60.0
    assert ex["verdict"]["state"] == "VALIDATED"  # below default 70 threshold
    assert ex["why_layman"]  # never empty
    assert ex["weights_version"] == 2
    # ai/ml domains present but unscored
    domains = {m["domain"]: m for m in ex["maths"]}
    assert domains["ai"]["score"] is None
    assert domains["ml"]["score"] is None
    assert any("AI" in p for p in ex["penalties"])


def test_signal_explain_degraded_flagged():
    cand = _candidate(fno_degraded=True, vwap_degraded=True, vwap_coverage_pct=42.0)
    dh = {"fno_degraded": True, "vwap_degraded": True, "vwap_coverage_pct": 42.0}
    ex = build_signal_explain(cand, 65.0, None, None, None, _weights(), {"armed": 70.0},
                              ["ORB:BLOCKED_BY_RESISTANCE_5.0pts"], _inputs(), dh)
    assert any("F&O" in p for p in ex["penalties"])
    assert any("VWAP" in p for p in ex["penalties"])
    assert ex["data_health"]["fno_degraded"] is True
    # other-strategy gates surfaced, own-strategy gates excluded
    assert ex["gates_rejected_by_others"] == ["ORB:BLOCKED_BY_RESISTANCE_5.0pts"]
    # never throws on garbage
    ex2 = build_signal_explain(None, None, None, None, None, "garbage", "garbage", "garbage", "garbage", "garbage")
    assert ex2["why_layman"]


def test_forecast_explain_domains_match_layer_weights():
    ensemble = {
        "direction": "BULLISH", "score": 37.5, "confidence": 0.7, "timeframe": "1h",
        "forecast_horizon": "1h",
        "layer_scores": {"mtf_alignment": 60.0, "indicators": 40.0, "ml": 20.0, "options": 10.0, "structure": 30.0},
    }
    mtf_features = {
        "instrument": "NIFTY",
        "alignment": {"overall_bias": "BULLISH", "alignment_score": 60.0},
        "per_timeframe": {"1h": {"features": {"quant": {"supertrend_dir": "BULLISH", "rsi_14": 62.0, "atr_14": 50.0}}}},
    }
    options_ctx = {"pcr_oi": 1.25, "max_pain": 25000.0, "call_wall": 25200.0, "put_wall": 24800.0}
    ex = build_forecast_explain(ensemble, mtf_features, [], {"bullish_pct": 60.0, "bearish_pct": 25.0,
                                "neutral_pct": 15.0, "predicted_bias": "BULLISH"}, options_ctx, 25000.0)
    assert [m["domain"] for m in ex["maths"]] == ["mtf_alignment", "indicators", "ml", "options", "structure"]
    for m in ex["maths"]:
        assert m["weight"] == LAYER_WEIGHTS[m["domain"]]
        assert m["points"] == round(m["score"] * m["weight"], 2)
    # weighted sum reproduces the ensemble score
    assert abs(sum(m["points"] for m in ex["maths"]) - 37.5) < 1.0
    assert ex["verdict"]["direction"] == "BULLISH"
    assert ex["inputs_snapshot"]["rsi_14"] == 62.0
    assert ex["inputs_snapshot"]["supertrend_dir"] == "BULLISH"
    assert ex["inputs_snapshot"]["pcr_oi"] == 1.25
    assert ex["inputs_snapshot"]["max_pain"] == 25000.0
    assert ex["inputs_snapshot"]["alignment_score"] == 60.0
    assert len(ex["why_layman"]) >= 1
    assert any("Supertrend BULLISH" in b for b in ex["why_layman"])
    # degraded path: missing TFs flagged, never throws on None
    ex2 = build_forecast_explain(None, None, None, None, None, None)
    assert ex2["why_layman"]
    assert ex2["data_health"]["degraded"] is True
