"""HPI API endpoint tests (isolated from the app singleton state) for NIFTY, BANKNIFTY, SENSEX."""
import pytest
from fastapi.testclient import TestClient

from app.hpi.engine import HPITrendPatternEngine
from app.hpi.service import HPIService


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Fresh isolated HPI service + engine for API tests
    from app.hpi import service as svc_mod
    import app.api.hpi as hpi_api_mod

    fresh = HPIService(state_path=tmp_path / "hpi_state.json")
    monkeypatch.setattr(svc_mod, "hpi_service", fresh)
    monkeypatch.setattr(hpi_api_mod, "hpi_service", fresh)
    monkeypatch.setattr(hpi_api_mod, "engine", HPITrendPatternEngine(fresh))

    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_universe_endpoint(client):
    r = client.get("/api/v1/hpi/universe")
    assert r.status_code == 200
    data = r.json()["data"]
    assert [d["symbol"] for d in data["derivatives"]] == ["NIFTY", "BANKNIFTY", "SENSEX"]
    assert data["storage_budget"]["hard_ceiling_mb"] == 200.0


def test_selection_roundtrip(client):
    r = client.get("/api/v1/hpi/selection")
    assert r.status_code == 200
    entries = r.json()["data"]["entries"]
    assert len(entries) == 3

    payload = {"entries": [
        {"symbol": "NIFTY", "enabled": True,
         "data_categories": ["1m_market_data", "option_chain", "iv", "pcr", "futures", "open_interest", "greeks"]},
        {"symbol": "SENSEX", "enabled": False, "data_categories": []},
    ]}
    r = client.put("/api/v1/hpi/selection", json=payload)
    assert r.status_code == 200
    updated = {e["symbol"]: e for e in r.json()["data"]["entries"]}
    assert updated["NIFTY"]["enabled"] is True
    assert updated["SENSEX"]["enabled"] is False

    r = client.put("/api/v1/hpi/selection", json={"entries": [
        {"symbol": "DOGE", "enabled": True}]})
    assert r.status_code == 400


def test_import_estimate_and_execute(client):
    est = client.post("/api/v1/hpi/import", json={
        "symbol": "NIFTY", "categories": ["1m_market_data"],
        "retention_days": 3, "sampling_interval": "1h", "estimate_only": True,
    })
    assert est.status_code == 200
    body = est.json()["data"]
    assert body["status"] == "WITHIN_TARGET"
    assert body["breakdown"][0]["estimated_records"] == 73  # 3 days hourly

    # Execute import
    done = client.post("/api/v1/hpi/import", json={
        "symbol": "NIFTY", "categories": ["1m_market_data"],
        "retention_days": 3, "sampling_interval": "1h",
    })
    assert done.status_code == 200
    assert done.json()["data"]["records_imported"] > 0


def test_storage_report_and_delete_flow(client):
    client.put("/api/v1/hpi/selection", json={"entries": [
        {"symbol": "NIFTY", "enabled": True,
         "data_categories": ["1m_market_data", "option_chain"]}]})
    client.post("/api/v1/hpi/import", json={
        "symbol": "NIFTY", "categories": ["1m_market_data", "option_chain"],
        "retention_days": 5, "sampling_interval": "1h"})

    rep = client.get("/api/v1/hpi/storage/report")
    assert rep.status_code == 200
    nifty = next(d for d in rep.json()["data"]["datasets"] if d["symbol"] == "NIFTY")
    assert nifty["enabled"] is True
    assert nifty["records_stored"] > 0
    assert nifty["storage_used_mb"] > 0
    assert len(nifty["category_stats"]) == 7

    # Delete flow: preview → confirm (§6/§7)
    prev = client.post("/api/v1/hpi/delete/preview", json={
        "symbol": "NIFTY", "categories": ["option_chain"], "range_type": "all_time",
        "reason": "api test",
    })
    assert prev.status_code == 200
    preview = prev.json()["data"]
    assert preview["total_records"] > 0
    assert preview["confirmation_token"]
    assert "Not affected" in preview["price_technical_impact"]

    # Wrong token rejected
    bad = client.post("/api/v1/hpi/delete/confirm", json={"confirmation_token": "nope"})
    assert bad.status_code == 400

    ok = client.post("/api/v1/hpi/delete/confirm",
                     json={"confirmation_token": preview["confirmation_token"]})
    assert ok.status_code == 200
    assert ok.json()["data"]["records_deleted"] == preview["total_records"]

    audit = client.get("/api/v1/hpi/audit/deletions?symbol=NIFTY")
    assert audit.status_code == 200
    entries = audit.json()["data"]
    assert len(entries) == 1
    assert entries[0]["dataset"] == "option_chain"
    assert entries[0]["records_deleted"] == preview["total_records"]


def test_coverage_and_analysis_endpoints(client):
    client.put("/api/v1/hpi/selection", json={"entries": [
        {"symbol": "NIFTY", "enabled": True, "data_categories": ["1m_market_data"]}]})
    client.post("/api/v1/hpi/import", json={
        "symbol": "NIFTY", "categories": ["1m_market_data"],
        "retention_days": 180, "sampling_interval": "1h"})

    cov = client.get("/api/v1/hpi/coverage/NIFTY")
    assert cov.status_code == 200
    cdata = cov.json()["data"]
    assert cdata["overall"] == "FULL"
    assert cdata["historical_coverage_months"] == pytest.approx(6.0, abs=0.2)

    ana = client.get("/api/v1/hpi/analysis/NIFTY?timeframe=5m")
    assert ana.status_code == 200
    adata = ana.json()["data"]
    assert "6 months" in adata["historical_coverage_label"]
    assert adata["similar_setups"] > 0
    assert adata["confidence"] > 0

    # Unsupported derivative → 400
    assert client.get("/api/v1/hpi/coverage/RELIANCE").status_code == 400


def test_policy_endpoints(client):
    created = client.post("/api/v1/hpi/policies", json={
        "instrument": "SENSEX", "derivative_category": "INDEX", "feature_group": "iv",
        "retention_days": 30, "sampling_interval": "1h", "auto_delete_enabled": True,
    })
    assert created.status_code == 200
    pid = created.json()["data"]["policy_id"]

    patched = client.patch(f"/api/v1/hpi/policies/{pid}", json={"retention_days": 60})
    assert patched.status_code == 200
    assert patched.json()["data"]["retention_days"] == 60

    assert client.get("/api/v1/hpi/policies?symbol=SENSEX").status_code == 200
    assert client.delete(f"/api/v1/hpi/policies/{pid}").status_code == 200


def test_auto_delete_endpoint(client):
    r = client.post("/api/v1/hpi/maintenance/auto-delete")
    assert r.status_code == 200
    assert r.json()["data"]["executed"] is True


def test_seed_endpoint(client, monkeypatch):
    from app.hpi import service as svc_mod
    monkeypatch.setattr(svc_mod, "ENABLE_REAL_CRYPTO", False)

    r = client.post("/api/v1/hpi/seed?retention_days=2&sampling_interval=1h")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "seeded"
    assert data["records_imported"] > 0

    # Storage report reflects the seeded flag + populated datasets.
    rep = client.get("/api/v1/hpi/storage/report")
    assert rep.status_code == 200
    assert rep.json()["data"]["seeded"] is True
    enabled = [d for d in rep.json()["data"]["datasets"] if d["enabled"]]
    assert len(enabled) == 3
    assert all(d["records_stored"] > 0 for d in enabled)

    # Idempotent second call.
    r2 = client.post("/api/v1/hpi/seed?retention_days=2&sampling_interval=1h")
    assert r2.json()["data"]["status"] == "already_seeded"

    # Analysis now produces real results for every derivative.
    for sym in ("NIFTY", "BANKNIFTY", "SENSEX"):
        a = client.get(f"/api/v1/hpi/analysis/{sym}")
        assert a.status_code == 200
        assert a.json()["data"]["similar_setups"] > 0
