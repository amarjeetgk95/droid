import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_events_upcoming_api():
    r = client.get("/api/v1/events/upcoming")
    assert r.status_code == 200
    events = r.json()
    assert isinstance(events, list)
    assert len(events) > 0

    first = events[0]
    assert "canonical_event_id" in first
    assert "title" in first
    assert "scores" in first
    assert "impact_mappings" in first
    assert first["entity_id"] == "RBI"


def test_events_today_api():
    r = client.get("/api/v1/events/today")
    assert r.status_code == 200
    events = r.json()
    assert isinstance(events, list)


def test_event_detail_and_scores_api():
    # First get list to pick an ID
    list_r = client.get("/api/v1/events/upcoming")
    events = list_r.json()
    assert len(events) > 0
    event_id = events[0]["canonical_event_id"]

    # Detail
    detail_r = client.get(f"/api/v1/events/{event_id}")
    assert detail_r.status_code == 200
    detail = detail_r.json()
    assert detail["canonical_event_id"] == event_id
    assert len(detail["impact_mappings"]) > 0

    # Scores
    scores_r = client.get(f"/api/v1/events/{event_id}/scores")
    assert scores_r.status_code == 200
    scores = scores_r.json()
    assert "importance" in scores
    assert "market_impact" in scores
    assert "opportunity" in scores
    assert scores["final_decision"] == "NO_TRADE"


def test_event_prediction_and_comparables_api():
    list_r = client.get("/api/v1/events/upcoming")
    events = list_r.json()
    event_id = events[0]["canonical_event_id"]

    # Prediction
    pred_r = client.get(f"/api/v1/events/{event_id}/prediction")
    assert pred_r.status_code == 200
    pred = pred_r.json()
    assert "data_cutoff_timestamp" in pred
    assert pred["decision"] == "NO_TRADE"

    # Comparables
    comp_r = client.get(f"/api/v1/events/{event_id}/comparables")
    assert comp_r.status_code == 200
    comps = comp_r.json()
    assert isinstance(comps, list)


def test_create_manual_event_api():
    now = datetime.now(timezone.utc) + timedelta(days=5)
    payload = {
        "title": "RBI Special Banking Liquidity Meeting",
        "description": "Ad-hoc meeting on system liquidity and overnight call rates.",
        "event_type": "CENTRAL_BANK",
        "sub_type": "LIQUIDITY_MEASURES",
        "entity_id": "RBI",
        "entity_name": "Reserve Bank of India",
        "sector": "BANKING",
        "event_timestamp": now.isoformat(),
        "timezone": "Asia/Kolkata",
        "timestamp_precision": "EXACT",
        "verification_status": "VERIFIED",
        "certainty": "CONFIRMED",
        "expected_direction": "NEUTRAL",
        "time_horizon": "INTRADAY",
        "source_name": "MANUAL_OPS",
        "notes": "Operations desk scheduled entry",
    }

    create_r = client.post("/api/v1/events/manual", json=payload)
    assert create_r.status_code == 201
    created = create_r.json()
    assert created["title"] == payload["title"]
    assert created["scores"]["final_decision"] == "NO_TRADE"


def test_live_opportunity_and_shadow_signals_api():
    list_r = client.get("/api/v1/events/upcoming")
    events = list_r.json()
    event_id = events[0]["canonical_event_id"]

    # Live Opportunity
    opp_r = client.get(f"/api/v1/events/{event_id}/live-opportunity")
    assert opp_r.status_code == 200
    opp_data = opp_r.json()
    assert "live_options" in opp_data
    assert "opportunity_score" in opp_data
    assert opp_data["execution_mode"] == "SHADOW_MODE"

    # Corporate Sync
    corp_r = client.post("/api/v1/events/corporate/sync")
    assert corp_r.status_code == 200
    corp_events = corp_r.json()
    assert isinstance(corp_events, list)

    # Alerts Queue
    alerts_r = client.get("/api/v1/events/alerts/queue")
    assert alerts_r.status_code == 200
    alerts = alerts_r.json()
    assert isinstance(alerts, list)

    # Shadow Signals
    shadow_r = client.get("/api/v1/events/shadow-signals")
    assert shadow_r.status_code == 200
    shadows = shadow_r.json()
    assert isinstance(shadows, list)


def test_phase3_endpoints():
    # 1. Track record analytics
    track_r = client.get("/api/v1/events/analytics/track-record")
    assert track_r.status_code == 200
    tr = track_r.json()
    assert "total_events_evaluated" in tr
    assert "sample_size_gate_passed" in tr
    assert "recommendation" in tr

    # 2. Source health telemetry
    health_r = client.get("/api/v1/events/sources/health")
    assert health_r.status_code == 200
    health = health_r.json()
    assert "overall_status" in health
    assert "RBI_OFFICIAL" in health["sources"]

    # 3. Risk overlay
    risk_r = client.get("/api/v1/events/risk/overlay?underlying=BANKNIFTY")
    assert risk_r.status_code == 200
    risk = risk_r.json()
    assert "proximity_state" in risk
    assert "can_enter" in risk

    # 4. Calibrate events
    cal_r = client.post("/api/v1/events/calibrate")
    assert cal_r.status_code == 200
    cal_res = cal_r.json()
    assert "calibrated_events" in cal_res
    assert "summary" in cal_res
