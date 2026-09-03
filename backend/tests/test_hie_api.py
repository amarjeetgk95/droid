"""
Tests for Historical Intelligence Engine FastAPI Endpoints — §§24, 25, 26, 36
"""
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.historical_intelligence.schemas import CandleData
from app.historical_intelligence.state_builder import state_builder
from app.historical_intelligence.outcome_engine import construct_forward_outcomes
from app.historical_intelligence.retriever import vector_retriever
from app.historical_intelligence.monitoring import hie_monitor

client = TestClient(app)


def _seed_test_corpus():
    base_t = datetime.now(timezone.utc) - timedelta(days=2)
    for i in range(10):
        t = base_t + timedelta(hours=i)
        candles = [
            CandleData(
                timestamp_utc=int(t.timestamp() * 1000) - (20 - j) * 60000,
                open=24000.0 + j * 2,
                high=24005.0 + j * 2,
                low=23995.0 + j * 2,
                close=24002.0 + j * 2,
                volume=1000.0,
            )
            for j in range(20)
        ]
        fut_candles = [
            CandleData(
                timestamp_utc=int(t.timestamp() * 1000) + j * 60000,
                open=24040.0 + j,
                high=24050.0 + j,
                low=24035.0 + j,
                close=24045.0 + j,
                volume=1000.0,
            )
            for j in range(60)
        ]
        snap = state_builder.build_snapshot("NIFTY", candles, t, "1m")
        out = construct_forward_outcomes(snap.snapshot_id, "NIFTY", t, candles[-1].close, fut_candles)
        vector_retriever.in_memory_index.upsert(snap, out)


class TestHIEEndpoints:

    @classmethod
    def setup_class(cls):
        _seed_test_corpus()

    def test_hie_status_endpoint(self):
        r = client.get("/api/v1/hie/status")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        data = body["data"]
        assert "versions" in data
        assert data["versions"]["engine_version"] == "2.5.0"
        assert data["versions"]["feature_version"] == "1.0.0"
        assert "health" in data
        assert data["health"]["lifecycle_state"] in ("ACTIVE", "BUILDING", "VALIDATING")

    def test_hie_query_endpoint(self):
        r = client.get("/api/v1/hie/query?symbol=NIFTY&timeframe=1m&top_k=10&min_similarity=0.40")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        data = body["data"]
        assert data["instrument"] == "NIFTY"
        assert "probability_15m" in data
        assert "probability_30m" in data
        assert "probability_60m" in data
        assert "confidence" in data
        assert "sample_count" in data

    def test_hie_candidate_analysis_endpoint(self):
        payload = {
            "instrument": "NIFTY",
            "timeframe": "1m",
            "strategy_id": "ORB_BREAKOUT_BULLISH",
            "top_k": 10,
            "min_similarity": 0.40,
        }
        r = client.post("/api/v1/hie/candidate-analysis", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        data = body["data"]
        assert data["instrument"] == "NIFTY"
        assert "median_return_30m" in data
        assert "target_hit_rate" in data

    def test_hie_ai_context_endpoint(self):
        r = client.get("/api/v1/hie/ai-context?symbol=NIFTY&timeframe=1m")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        data = body["data"]
        assert "historical_summary_text" in data
        assert "evidence_table" in data
        assert "failure_analysis" in data
        assert "sample_reliability" in data

    def test_index_lifecycle_validation(self):
        # Validation failure when record counts mismatch
        ok_fail = hie_monitor.validate_index_activation(
            record_count=100,
            embedding_count=50,  # Mismatch
            feature_version_ok=True,
            pit_tests_ok=True,
        )
        assert not ok_fail

        # Validation success
        ok_pass = hie_monitor.validate_index_activation(
            record_count=100,
            embedding_count=100,
            feature_version_ok=True,
            pit_tests_ok=True,
        )
        assert ok_pass
        assert hie_monitor.health.total_records == 100
