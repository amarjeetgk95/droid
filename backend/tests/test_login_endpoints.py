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
    from app.core.broker_runtime import apply_app_settings
    apply_app_settings({"broker": {"provider": "flattrade", "flattrade": {"apiKey": "FT_KEY_999"}}})
    monkeypatch.setattr(settings, "flattrade_api_key", "FT_KEY_999")
    
    resp = client.get("/api/v1/tokens/flattrade/login", follow_redirects=False)
    assert resp.status_code == 307 or resp.status_code == 302
    assert "auth.flattrade.in/?app_key=FT_KEY_999" in resp.headers["location"]


def test_fyers_callback_no_code(client):
    resp = client.get("/api/v1/tokens/fyers/callback")
    assert resp.status_code == 200
    assert "FYERS OAuth Callback Ready" in resp.text


def test_fyers_callback_missing_creds(client, monkeypatch):
    from app.core.broker_runtime import reset
    reset()
    monkeypatch.setattr(settings, "fyers_app_id", "")
    monkeypatch.setattr(settings, "fyers_secret_key", "")
    resp = client.get("/api/v1/tokens/fyers/callback?auth_code=sample_code")
    assert resp.status_code == 400
    assert "Fyers App ID or Secret Missing" in resp.text


def test_fyers_callback_exchange_internal_server_error(client, monkeypatch):
    from app.core.broker_runtime import apply_app_settings
    apply_app_settings({
        "broker": {
            "provider": "fyers",
            "fyers": {
                "appId": "HVMUH3H2LQ-100",
                "secret": "wrong_secret",
            }
        }
    })
    
    class MockResponse:
        status_code = 400
        def json(self):
            return {"s": "error", "code": -1, "message": "internal server error"}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return MockResponse()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    resp = client.get("/api/v1/tokens/fyers/callback?auth_code=dummy_code")
    assert resp.status_code == 400
    assert "Fyers Token Exchange Failed" in resp.text
    assert "internal server error" in resp.text
    assert "HVMUH3H2LQ-100" in resp.text


def test_fyers_login_custom_credentials(client):
    resp = client.get(
        "/api/v1/tokens/fyers/login?app_id=CUSTOM_APP_200&secret_key=CUSTOM_SECRET_999",
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    loc = resp.headers["location"]
    assert "client_id=CUSTOM_APP_200" in loc
    assert "state=c_" in loc


def test_fyers_callback_error_redirect(client):
    resp = client.get("/api/v1/tokens/fyers/callback?s=error&message=Invalid+Client+ID")
    assert resp.status_code == 400
    assert "Fyers Auth Redirect Error" in resp.text
    assert "Invalid Client ID" in resp.text


def test_fyers_callback_exchange_success(client, monkeypatch):
    from app.core.broker_runtime import apply_app_settings
    apply_app_settings({
        "broker": {
            "provider": "fyers",
            "fyers": {
                "appId": "HVMUH3H2LQ-100",
                "secret": "valid_secret",
            }
        }
    })

    class MockSuccessResponse:
        status_code = 200
        def json(self):
            return {"s": "ok", "code": 200, "access_token": "valid_fyers_jwt_token_123"}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return MockSuccessResponse()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    # Encode state with return_url
    import json, base64
    state_payload = {"a": "HVMUH3H2LQ-100", "s": "valid_secret", "r": "https://test.fo-droid.web.app"}
    state_b64 = "c_" + base64.urlsafe_b64encode(json.dumps(state_payload).encode("utf-8")).decode("utf-8")

    resp = client.get(f"/api/v1/tokens/fyers/callback?auth_code=valid_code&state={state_b64}")
    assert resp.status_code == 200
    assert "FYERS Connected Successfully!" in resp.text
    assert "DROID_AUTH_SUCCESS" in resp.text
    assert "https://test.fo-droid.web.app" in resp.text
    assert "droid_auth_channel" in resp.text



