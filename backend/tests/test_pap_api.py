"""API tests for the PAP research status endpoint."""

from fastapi.testclient import TestClient
import pytest

import app.api.pap as pap_api
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolated_data_roots(tmp_path, monkeypatch):
    """Point the endpoint's data/report roots at a temp dir.

    The repository now holds real FYERS data under data/historical/parquet;
    asserting 'missing' against the live tree would encode today's inventory
    as an invariant. Each test declares its own data reality.
    """
    monkeypatch.setattr(pap_api, "DATA_DIR", tmp_path / "raw")
    monkeypatch.setattr(pap_api, "HIST_DIR", tmp_path / "historical" / "parquet")
    monkeypatch.setattr(pap_api, "REPORTS_DIR", tmp_path / "experiments" / "pap")


def _get_payload() -> dict:
    response = TestClient(app).get("/api/v1/pap/status")
    assert response.status_code == 200
    return response.json()["data"]


class TestPapStatus:
    def test_envelope_shape(self, client):
        response = client.get("/api/v1/pap/status")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"data", "error", "meta"}
        assert body["error"] is None

    def test_historical_store_dataset_is_discovered(self):
        """A dataset in the canonical Historical Data Module store is found by
        the endpoint (admissibility itself is covered by the provenance-gate
        HDM translation tests; the screen needs real candle columns, which a
        discovery stub intentionally lacks)."""
        import json

        import polars as pl

        hist = pap_api.HIST_DIR / "sensex" / "1m"
        hist.mkdir(parents=True)
        path = hist / "candles_v1.parquet"
        pl.DataFrame({"timestamp": [1], "close": [1.0]}).write_parquet(path)
        path.with_suffix(".json").write_text(
            json.dumps(
                {
                    "symbol": "SENSEX",
                    "timeframe": "1m",
                    "version_tag": "v1",
                    "row_count": 1,
                    "checksum_sha256": "0" * 64,
                    "quality_score": 99.0,
                    "lineage": {"provider_id": "fyers", "provider_api_version": "v3"},
                }
            ),
            encoding="utf-8",
        )

        sensex = next(i for i in _get_payload()["instruments"] if i["slug"] == "sensex")
        assert sensex["present"] is True
        assert not any(r == "dataset_missing" for r in sensex["reasons"])

    def test_pre_registered_criteria_are_served(self, client):
        payload = client.get("/api/v1/pap/status").json()["data"]
        assert payload["criteria_version"] == pap_api.PAP_CRITERIA_VERSION
        assert payload["pre_registered"]["min_absolute_uplift"] == 0.03
        assert payload["verdict"] == "NOT_RUN"  # no reports dir in tmp cwd

    def test_missing_datasets_reported_not_fabricated(self):
        sensex = next(i for i in _get_payload()["instruments"] if i["slug"] == "sensex")
        assert sensex["present"] is False
        assert sensex["admissible"] is False
        nifty = next(i for i in _get_payload()["instruments"] if i["slug"] == "nifty")
        assert nifty["admissible"] is False

    def test_verdict_never_fabricated_from_unreadable_report(self, client, tmp_path, monkeypatch):
        reports_dir = tmp_path / "pap"
        reports_dir.mkdir()
        (reports_dir / "broken.json").write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(pap_api, "REPORTS_DIR", reports_dir)

        payload = client.get("/api/v1/pap/status").json()["data"]
        assert payload["reports"][0]["unreadable"] is True
        assert payload["verdict"] == "NOT_RUN"

    def test_pass_verdict_from_latest_readable_report(self, client, tmp_path, monkeypatch):
        import json

        reports_dir = tmp_path / "pap"
        reports_dir.mkdir()
        (reports_dir / "exp_old.json").write_text(
            json.dumps({"verdict": "FAIL", "created_at": "2026-09-01"}), encoding="utf-8"
        )
        (reports_dir / "exp_new.json").write_text(
            json.dumps({"verdict": "PASS", "created_at": "2026-09-20"}), encoding="utf-8"
        )
        monkeypatch.setattr(pap_api, "REPORTS_DIR", reports_dir)

        payload = client.get("/api/v1/pap/status").json()["data"]
        assert payload["verdict"] == "PASS"
        assert payload["phase"] == "STAGE_2_ALLOWED"

    def test_phase_blocked_without_real_data(self, client, tmp_path, monkeypatch):
        reports_dir = tmp_path / "pap"  # never created -> no reports
        monkeypatch.setattr(pap_api, "REPORTS_DIR", reports_dir)

        payload = client.get("/api/v1/pap/status").json()["data"]
        assert payload["verdict"] == "NOT_RUN"
        assert payload["phase"] == "STAGE_1_BLOCKED_NO_REAL_DATA"
