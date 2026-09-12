"""P2-1/P2-2: v2 feature schema + basis decision + PIT. Hermetic, no network."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.ml import feature_extractor_v2 as v2
from app.research.features import (
    atr_pct_1h,
    minutes_to_close_ist,
    period_return_pct,
    relative_volume,
    ret_5_pct,
    ret_15_pct,
    vwap_distance_pct,
)

IST = timezone(timedelta(hours=5, minutes=30))
T = datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc)  # 10:30 IST
T_ISO = T.isoformat()


def _full_inputs(**over):
    kw = dict(
        quant_1h={"rsi_14": 60.0, "adx": 25.0, "supertrend_dir": "BULLISH",
                  "bb_pct_b": 0.7, "atr_14": 50.0, "timestamp": T_ISO},
        quant_15m={"supertrend_dir": "BULLISH"},
        quant_4h={"supertrend_dir": "BEARISH"},
        dynamics={"current_price": 25000.0, "return_5_pct": 0.4,
                  "return_15_pct": -0.3, "relative_volume": 1.2,
                  "vwap_dist_pct": 0.05},
        options_ctx={"pcr_oi": 1.1, "max_pain": 24900.0, "spot": 25000.0,
                     "available_time": T_ISO},
        vix=14.0,
        session_info={"minutes_to_close": 300},
        decision_time=T_ISO,
    )
    kw.update(over)
    return kw


# ---------------------------------------------------------------------------
# schema length / hash stability
# ---------------------------------------------------------------------------

def test_schema_tag_and_length():
    assert v2.FEATURE_SCHEMA_V2 == "f12-v1"
    assert 12 <= len(v2.FEATURE_NAMES_V2) <= 15
    assert len(v2.FEATURE_NAMES_V2) == 15
    assert len(set(v2.FEATURE_NAMES_V2)) == 15  # no duplicates


def test_schema_hash_stable_and_independent():
    expected = hashlib.sha256("|".join(["f12-v1", *v2.FEATURE_NAMES_V2]).encode()).hexdigest()
    assert v2.feature_schema_hash_v2() == expected
    assert len(expected) == 64
    assert v2.feature_schema_hash_v2() == v2.feature_schema_hash_v2()


def test_module_has_no_network_imports():
    import inspect

    src = inspect.getsource(v2)
    for banned in ("httpx", "requests", "socket", "urllib", "aiohttp"):
        assert f"import {banned}" not in src


# ---------------------------------------------------------------------------
# basis decision branch (P2-1: DROP, never constant-zero)
# ---------------------------------------------------------------------------

def test_basis_dropped_from_schema_with_replacement():
    assert "futures_basis" not in v2.FEATURE_NAMES_V2
    assert "max_pain_distance" in v2.FEATURE_NAMES_V2
    assert v2.BASIS_DECISION["decision"] == "DROP"
    assert v2.BASIS_DECISION["replacement_feature"] == "max_pain_distance"
    assert "reason" in v2.BASIS_DECISION and len(v2.BASIS_DECISION["reason"]) > 50


def test_basis_gate_rejects_everything_observed_in_repo():
    ok, reason = v2.check_basis_availability(None, T_ISO)
    assert ok is False and "DROP" in reason
    ok, _ = v2.check_basis_availability({}, T_ISO)
    assert ok is False
    # synthetic cost-of-carry estimate, not a market quote
    ok, reason = v2.check_basis_availability(
        {"available": True, "futures_basis": 8.5, "available_time": T_ISO, "synthetic": True}, T_ISO)
    assert ok is False and "synthetic" in reason
    # unavailable feed
    ok, _ = v2.check_basis_availability({"available": False, "reason": "offline"}, T_ISO)
    assert ok is False
    # constant-zero placeholder (fno/context.py hardcoded near_basis=0)
    ok, reason = v2.check_basis_availability(
        {"available": True, "futures_basis": 0, "futures_basis_percent": 0, "available_time": T_ISO}, T_ISO)
    assert ok is False and "zero" in reason
    # nonzero but no PIT timestamp -> cannot prove available_time <= T
    ok, reason = v2.check_basis_availability({"available": True, "futures_basis": 8.5}, T_ISO)
    assert ok is False and "timestamp" in reason
    # UNAVAILABLE curve even with a timestamp
    ok, _ = v2.check_basis_availability(
        {"available": True, "futures_basis": 8.5, "available_time": T_ISO, "curve_state": "UNAVAILABLE"}, T_ISO)
    assert ok is False
    # lookahead timestamp rejected
    future = (T + timedelta(hours=1)).isoformat()
    ok, reason = v2.check_basis_availability(
        {"available": True, "futures_basis": 8.5, "available_time": future}, T_ISO)
    assert ok is False and "lookahead" in reason


def test_basis_gate_accepts_genuinely_pit_safe_quote():
    ok, reason = v2.check_basis_availability(
        {"available": True, "futures_basis": 12.5, "available_time": T_ISO}, T_ISO)
    assert ok is True and reason.startswith("OK")


def test_extract_row_marks_basis_excluded_with_reason():
    row = v2.extract_feature_vector_v2(**_full_inputs())
    assert row["basis"]["included"] is False
    assert "DROP" in row["basis"]["decision"] or "constant-zero" in row["basis"]["reason"]


# ---------------------------------------------------------------------------
# happy-path values + standardization
# ---------------------------------------------------------------------------

def test_extract_happy_path_values():
    row = v2.extract_feature_vector_v2(**_full_inputs())
    v = row["values"]
    assert row["schema"] == "f12-v1"
    assert row["missing_count"] == 0
    assert v["rsi_1h"] == pytest.approx(0.2)
    assert v["adx_1h"] == pytest.approx(0.5)
    assert v["supertrend_1h"] == 1.0
    assert v["supertrend_15m"] == 1.0
    assert v["supertrend_4h"] == -1.0
    assert v["bb_pct_b_1h"] == pytest.approx(0.7)
    assert v["atr_pct_1h"] == pytest.approx(0.2)  # 50/25000*100
    assert v["ret_5"] == pytest.approx(0.4)
    assert v["ret_15"] == pytest.approx(-0.3)
    assert v["relative_volume"] == pytest.approx(1.2)
    assert v["vwap_distance"] == pytest.approx(0.05)
    assert v["pcr_oi"] == pytest.approx(0.2)
    assert v["max_pain_distance"] == pytest.approx(0.4)  # (25000-24900)/25000*100
    assert v["vix"] == pytest.approx(14.0)
    assert v["minutes_to_close"] == pytest.approx(0.8)  # 300/375
    assert row["available_time"] == T_ISO
    assert row["pit_ok"] is True


# ---------------------------------------------------------------------------
# missing-data handling: None + mask, never silent 0
# ---------------------------------------------------------------------------

def test_all_missing_gives_full_mask_and_documented_neutrals():
    row = v2.extract_feature_vector_v2(None, None, None, None, None, None, None)
    assert row["missing_count"] == 15
    assert all(val is None for val in row["values"].values())  # no silent zeros
    assert all(flag == 1 for flag in row["missing_mask"].values())
    vec, mask = v2.to_model_vector_v2(row)
    assert mask == [1] * 15
    for name, val in zip(v2.FEATURE_NAMES_V2, vec):
        assert val == pytest.approx(v2.NEUTRAL_IMPUTE_V2[name])
    assert all(row["imputed"].values())


def test_partial_missing_flags_only_missing():
    row = v2.extract_feature_vector_v2(**_full_inputs(vix=None, quant_15m=None, quant_4h=None))
    assert row["values"]["vix"] is None  # not 0.0
    assert row["missing_mask"]["vix"] == 1
    assert row["values"]["supertrend_15m"] is None
    assert row["values"]["supertrend_4h"] is None
    assert row["values"]["rsi_1h"] == pytest.approx(0.2)  # present inputs unaffected
    assert row["missing_mask"]["rsi_1h"] == 0
    assert row["missing_count"] == 3


def test_stale_vix_and_dead_options_become_missing():
    row = v2.extract_feature_vector_v2(**_full_inputs(
        vix={"value": 14.0, "available_time": T_ISO, "stale": True},
        options_ctx={"available": False, "reason": "stale chain"},
    ))
    assert row["values"]["vix"] is None
    assert row["values"]["pcr_oi"] is None
    assert row["values"]["max_pain_distance"] is None
    assert row["missing_count"] == 3


def test_model_vector_schema_mismatch_raises():
    row = v2.extract_feature_vector_v2(**_full_inputs())
    row["feature_names"] = ["rsi_1h"]
    with pytest.raises(ValueError, match="schema mismatch"):
        v2.to_model_vector_v2(row)


# ---------------------------------------------------------------------------
# PIT: no future inputs
# ---------------------------------------------------------------------------

def test_future_options_input_rejected():
    future = (T + timedelta(minutes=30)).isoformat()
    with pytest.raises(ValueError, match="lookahead"):
        v2.extract_feature_vector_v2(**_full_inputs(
            options_ctx={"pcr_oi": 1.1, "max_pain": 24900.0, "available_time": future}))


def test_future_vix_input_rejected():
    future = (T + timedelta(minutes=5)).isoformat()
    with pytest.raises(ValueError, match="lookahead"):
        v2.extract_feature_vector_v2(**_full_inputs(
            vix={"value": 14.0, "available_time": future}))


def test_unverifiable_input_rejected_when_decision_time_set():
    with pytest.raises(ValueError, match="no parseable timestamp"):
        v2.assert_pit("not-a-time", T_ISO, "probe")


def test_available_time_never_after_decision_time():
    earlier = (T - timedelta(minutes=60)).isoformat()
    row = v2.extract_feature_vector_v2(**_full_inputs(
        options_ctx={"pcr_oi": 1.0, "max_pain": 25000.0, "spot": 25000.0, "available_time": earlier}))
    assert row["available_time"] <= T_ISO  # ISO strings compare chronologically (same offset)


# ---------------------------------------------------------------------------
# supertrend mapping
# ---------------------------------------------------------------------------

def test_supertrend_sign_and_agreement():
    assert v2.supertrend_sign("BULLISH") == 1.0
    assert v2.supertrend_sign("bearish") == -1.0
    assert v2.supertrend_sign("NEUTRAL") is None
    assert v2.supertrend_sign(None) is None
    assert v2.supertrend_agreement("BULLISH", "BULLISH", "BEARISH") == pytest.approx(2 / 3, abs=1e-4)
    assert v2.supertrend_agreement("BULLISH", None, "BEARISH") is None


# ---------------------------------------------------------------------------
# research/features.py additive helpers (pure, None on bad input)
# ---------------------------------------------------------------------------

def test_minutes_to_close_ist():
    assert minutes_to_close_ist(datetime(2026, 9, 11, 10, 30, tzinfo=IST)) == 300
    assert minutes_to_close_ist(datetime(2026, 9, 11, 15, 29, tzinfo=IST)) == 1
    assert minutes_to_close_ist(datetime(2026, 9, 11, 15, 30, tzinfo=IST)) == 0
    assert minutes_to_close_ist(datetime(2026, 9, 11, 16, 0, tzinfo=IST)) == 0
    assert minutes_to_close_ist(datetime(2026, 9, 11, 8, 0, tzinfo=IST)) == 375
    assert minutes_to_close_ist(None) is None
    assert minutes_to_close_ist("garbage") is None
    assert minutes_to_close_ist(T_ISO) == 300  # ISO string accepted


def test_atr_pct_1h():
    assert atr_pct_1h(50.0, 25000.0) == pytest.approx(0.2)
    assert atr_pct_1h(None, 25000.0) is None
    assert atr_pct_1h(50.0, 0) is None
    assert atr_pct_1h(-5, 25000.0) is None


def test_period_returns():
    closes = [100.0 + i for i in range(20)]  # 100..119
    assert ret_5_pct(closes) == pytest.approx((119 - 114) / 114 * 100, abs=1e-3)
    assert ret_15_pct(closes) == pytest.approx((119 - 104) / 104 * 100, abs=1e-3)
    assert period_return_pct([100.0, 101.0], 5) is None  # too short
    assert period_return_pct(None, 5) is None
    assert period_return_pct([0.0] * 10, 5) is None  # non-positive base
    assert period_return_pct(closes, 0) is None


def test_relative_volume_and_vwap_distance():
    assert relative_volume(2000, 1000) == pytest.approx(2.0)
    assert relative_volume(1000, 0) is None
    assert relative_volume(None, 1000) is None
    assert vwap_distance_pct(25100.0, 25000.0) == pytest.approx(0.4)
    assert vwap_distance_pct(25000.0, None) is None
    assert vwap_distance_pct(25000.0, 0) is None
