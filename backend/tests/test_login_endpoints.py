import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings


@pytest.fixture
def client():
    return TestClient(app)


def test_fyers_login_redirect(client, monkeypatch):
    monkeypatch.setattr(settings, "fyers_app_id", "TEST_APP_100")
    monkeypatch.setattr(settings, "fyers_redirect_uri", "https://droid-backend-emeq.onrender.com/api/v1/tokens/fyers/callback")
    
    resp = client.get("/api/v1/tokens/fyers/login", follow_redirects=False)
    assert resp.status_code == 307 or resp.status_code == 302
    assert "api-t1.fyers.in/api/v3/generate-authcode" in resp.headers["location"]
    assert "TEST_APP_100" in resp.headers["location"]


def test_flattrade_login_redirect(client, monkeypatch):
    monkeypatch.setattr(settings, "flattrade_api_key", "FT_KEY_999")
    
    resp = client.get("/api/v1/tokens/flattrade/login", follow_redirects=False)
    assert resp.status_code == 307 or resp.status_code == 302
    assert "auth.flattrade.in/?app_key=FT_KEY_999" in resp.headers["location"]
