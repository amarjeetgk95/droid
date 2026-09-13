"""Full-module regression: futures/options-flow/breadth/vix/composite/v3/stacker/drift."""
import asyncio


def test_futures_engine_fail_closed():
    from app.institutional.futures_engine import classify_buildup, get_futures_snapshot

    assert classify_buildup(1.0, 2.0) == "LONG_BUILDUP"
    assert classify_buildup(-1.0, 2.0) == "SHORT_BUILDUP"
    assert classify_buildup(1.0, -2.0) == "SHORT_COVERING"
    assert classify_buildup(-1.0, -2.0) == "LONG_UNWINDING"
    snap = asyncio.run(get_futures_snapshot("NIFTY"))
    assert snap["timestamp_ms"] and snap["available_time"]
    # No live feed in this env -> UNAVAILABLE with reason, never synthetic numbers.
    assert snap["status"] in ("LIVE", "UNAVAILABLE")
    if snap["status"] == "UNAVAILABLE":
        assert snap["basis"] is None and snap["buildup"] == "UNKNOWN"


def test_options_flow_needs_pair():
    from app.institutional.options_flow_engine import compute_options_flow

    cur = {"total_call_oi": 100, "total_put_oi": 120, "spot": 25000, "call_wall": 25100,
           "put_wall": 24900, "available_time": "2026-09-01T00:00:00+00:00"}
    assert compute_options_flow(cur, None)["status"] == "INSUFFICIENT_DATA"
    prev = {"total_call_oi": 90, "total_put_oi": 100}
    live = compute_options_flow(cur, prev)
    assert live["status"] == "LIVE"
    assert live["ce_oi_change"] == 10 and live["pe_oi_change"] == 20


def test_composite_fail_closed_and_live():
    from app.institutional.composite import compute_composite

    assert compute_composite(None, None, None, None, None)["status"] == "INSUFFICIENT"

    class _F:
        fii_cash_5d_z = 2.0
        dii_cash_5d_z = 1.0
        fii_lsr = 1.2
        pit_ok = True

    out = compute_composite(_F(), {"status": "LIVE", "net_write_pressure": 0.5},
                            {"ad_ratio": 0.6}, {"vix": 14.0}, {"pcr": 1.3}, "TREND_UP")
    assert out["status"] in ("LIVE", "DEGRADED") and out["score"] is not None
    assert out["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")


def test_v3_width_and_stacker_row():
    from app.ml.feature_extractor_v3 import FEATURE_NAMES_V3, build_v3_extension, to_v3_vector
    from app.ml.stacker_v1 import STACKER_WIDTH, build_stacker_row, predict_stacker

    assert len(FEATURE_NAMES_V3) == 20

    class _F:
        fii_cash_5d_z = 1.0
        dii_cash_5d_z = -0.5
        fii_lsr = 1.1
        pit_ok = True

    ext, mask = build_v3_extension(_F(), {"status": "LIVE", "net_write_pressure": 0.2}, {"ad_ratio": 0.55})
    vec, m = to_v3_vector([0.0] * 15, ext)
    assert len(vec) == 20 and len(m) == 20
    row = build_stacker_row({"mtf": 10, "indicators": 20, "ml": 30, "options": 40, "structure": 50})
    assert len(row) == STACKER_WIDTH
    # No artifact in repo -> honest None fallback, never crash.
    assert predict_stacker(row) is None


def test_drift_check_never_raises():
    from app.institutional.drift import check_drift, is_degraded

    out = check_drift()
    assert "degraded" in out and isinstance(is_degraded(), bool)


def test_flow_api():
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    r = c.get("/api/v1/fii-dii/flow")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["live"] is False and "pit_note" in body
