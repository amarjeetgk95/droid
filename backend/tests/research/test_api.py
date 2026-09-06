"""Integration tests for Research Laboratory API endpoints (§45)."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_list_indicators():
    """GET /api/v1/research/indicators"""
    r = client.get("/api/v1/research/indicators")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    ids = [i["indicator_id"] for i in data]
    assert "ompi" in ids
    assert "rsi" in ids
    assert "vwap" in ids


def test_get_single_indicator():
    """GET /api/v1/research/indicators/{id}"""
    r = client.get("/api/v1/research/indicators/ompi")
    assert r.status_code == 200
    ind = r.json()
    assert ind["indicator_id"] == "ompi"
    assert ind["category"] == "PROPRIETARY"
    assert ind["lifecycle"] == "EXPERIMENTAL"


def test_calculate_indicator_api():
    """POST /api/v1/research/indicators/ompi/calculate with custom candles"""
    candles = [
        {
            "open": 24000.0 + i,
            "high": 24005.0 + i,
            "low": 23995.0 + i,
            "close": 24002.0 + i,
            "volume": 1000.0 + i * 10,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for i in range(50)
    ]

    payload = {
        "instrument": "NIFTY 50",
        "timeframe": "5m",
        "parameters": {"bull_threshold": 15.0},
        "candles": candles,
    }

    r = client.post("/api/v1/research/indicators/ompi/calculate", json=payload)
    assert r.status_code == 200
    out = r.json()
    assert out["indicator_id"] == "ompi"
    assert -100.0 <= out["score"] <= 100.0
    assert "p_dir" in out["component_values"]
    assert "p_opt" in out["component_values"]


def test_prediction_api_lifecycle():
    """POST /api/v1/research/predictions and GET /api/v1/research/predictions"""
    now = datetime.now(timezone.utc).isoformat()
    pred_payload = {
        "prediction_id": "api_test_pred_01",
        "indicator_id": "rsi",
        "indicator_version": "1.0.0",
        "instrument": "NIFTY 50",
        "timeframe": "5m",
        "timestamp": now,
        "current_price": 24100.0,
        "direction": "BULLISH",
        "score": 45.0,
        "confidence": 0.85,
        "forecast_horizon": "15m",
        "horizon_candles": 3,
        "target_price": 24180.0,
        "invalidation_price": 24050.0,
    }

    post_r = client.post("/api/v1/research/predictions", json=pred_payload)
    assert post_r.status_code == 200
    assert post_r.json()["status"] == "RECORDED_IMMUTABLE"

    get_r = client.get("/api/v1/research/predictions/api_test_pred_01")
    assert get_r.status_code == 200
    assert get_r.json()["prediction_id"] == "api_test_pred_01"

    # Measure outcome
    forward_candles = [
        {"open": 24100.0, "high": 24190.0, "low": 24090.0, "close": 24185.0},
    ]
    meas_r = client.post(
        "/api/v1/research/predictions/api_test_pred_01/measure",
        json={"forward_candles": forward_candles},
    )
    assert meas_r.status_code == 200
    outcome = meas_r.json()
    assert outcome["actual_direction"] == "BULLISH"
    assert outcome["target_hit"] is True


def test_experiment_run_api():
    """POST /api/v1/research/experiments/run"""
    candles = [
        {
            "open": 24000.0 + (i % 5) * 5,
            "high": 24010.0 + (i % 5) * 5,
            "low": 23990.0 + (i % 5) * 5,
            "close": 24005.0 + (i % 5) * 5,
            "volume": 1200.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for i in range(50)
    ]

    exp_payload = {
        "indicator_id": "rsi",
        "instrument": "NIFTY 50",
        "timeframe": "5m",
        "horizon_candles": 3,
        "stride": 3,
        "candles": candles,
    }

    r = client.post("/api/v1/research/experiments/run", json=exp_payload)
    assert r.status_code == 200
    res = r.json()
    assert "run" in res
    assert "report" in res
    assert res["run"]["status"] == "COMPLETED"
    assert res["report"]["sample_size"] > 0


def test_snapshots_and_annotations_api():
    """POST/GET snapshots and annotations"""
    # Snapshot
    snap_payload = {
        "instrument": "BANKNIFTY",
        "timeframe": "15m",
        "price": 51500.0,
        "regime": "TRENDING_UP",
        "session": "MID",
        "features": {"adx": 32.5},
        "data_quality": "LIVE",
    }
    snap_r = client.post("/api/v1/research/snapshots", json=snap_payload)
    assert snap_r.status_code == 200
    assert snap_r.json()["instrument"] == "BANKNIFTY"

    list_snaps = client.get("/api/v1/research/snapshots?instrument=BANKNIFTY")
    assert list_snaps.status_code == 200
    assert len(list_snaps.json()) >= 1

    # Annotation
    ann_payload = {
        "annotation_id": "ann_test_01",
        "instrument": "BANKNIFTY",
        "timeframe": "15m",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title": "Resistance test at 51500",
        "notes": "Testing supply zone rejection",
        "author": "tester",
        "tags": ["resistance", "supply"],
    }
    ann_r = client.post("/api/v1/research/annotations", json=ann_payload)
    assert ann_r.status_code == 200
    assert ann_r.json()["title"] == "Resistance test at 51500"

    list_anns = client.get("/api/v1/research/annotations?instrument=BANKNIFTY")
    assert list_anns.status_code == 200
    assert len(list_anns.json()) >= 1
