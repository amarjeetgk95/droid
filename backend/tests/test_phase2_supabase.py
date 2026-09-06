"""
Tests for Phase 2: Supabase/PostgreSQL integration.

These tests verify:
- Settings API endpoints
- Watchlist API endpoints
- Profile API endpoints
- Authorization (JWT validation)
- Development/demo mode behavior
- Database not configured behavior
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4
from app.core.database import get_db_session


async def mock_get_db_none():
    yield None


@pytest.fixture
def no_db_client():
    from app.main import app
    app.dependency_overrides[get_db_session] = mock_get_db_none
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db_session, None)


class TestAuthEndpoints:
    """Test authentication and profile endpoints."""

    def test_profile_endpoint_dev_mode(self, client: TestClient):
        """Profile endpoint should work in dev mode without JWT."""
        r = client.get("/api/v1/auth/profile")
        assert r.status_code == 200
        data = r.json()
        # In dev mode auth_required=False, provider returns deterministic UUID for DB compatibility
        assert data["user_id"] == "00000000-0000-0000-0000-000000000001"
        assert data["email"] == "dev@localhost"
        assert data["role"] == "admin"

    def test_profile_endpoint_requires_auth_in_production(self):
        """Profile endpoint should require auth when AUTH_REQUIRED=true."""
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.auth_required = True
            mock_settings.supabase_jwt_secret = "test-secret"
            from app.main import app
            with TestClient(app) as c:
                r = c.get("/api/v1/auth/profile")
                assert r.status_code == 401

    def test_profile_full_endpoint_no_db(self, no_db_client: TestClient):
        """Full profile endpoint should return 503 when DB not configured."""
        r = no_db_client.get("/api/v1/auth/profile/full")
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]

    def test_profile_patch_no_db(self, no_db_client: TestClient):
        """Profile PATCH should return 503 when DB not configured."""
        r = no_db_client.patch("/api/v1/auth/profile", json={"display_name": "Test User"})
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]


class TestSettingsEndpoints:
    """Test settings API endpoints."""

    def test_get_settings_no_db(self, no_db_client: TestClient):
        """GET settings in dev mode should fallback to in-memory (200) when DB not configured."""
        r = no_db_client.get("/api/v1/settings")
        # In dev mode (auth_required=False) fallback to in-memory store yields 200, not 503
        assert r.status_code == 200
        assert "theme" in r.json()

    def test_create_settings_no_db(self, no_db_client: TestClient):
        """POST settings in dev mode should fallback to in-memory (200) when DB not configured."""
        r = no_db_client.post("/api/v1/settings", json={"theme": "dark"})
        assert r.status_code == 200
        assert r.json()["theme"] == "dark"

    def test_update_settings_no_db(self, no_db_client: TestClient):
        """PATCH settings in dev mode should fallback to in-memory (200) when DB not configured."""
        r = no_db_client.patch("/api/v1/settings", json={"theme": "light"})
        assert r.status_code == 200
        assert r.json()["theme"] == "light"

    def test_settings_requires_auth_in_production(self):
        """Settings endpoints should require auth when AUTH_REQUIRED=true."""
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.auth_required = True
            mock_settings.supabase_jwt_secret = "test-secret"
            from app.main import app
            with TestClient(app) as c:
                r = c.get("/api/v1/settings")
                assert r.status_code == 401


class TestSettingsService:
    """Test SettingsService with mocked database."""

    @pytest.mark.asyncio
    async def test_get_settings_creates_default(self):
        """SettingsService should create default settings if none exist."""
        from app.services.user_service import SettingsService
        mock_session = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.id = uuid4()
        mock_settings.user_id = uuid4()
        mock_settings.theme = "dark"
        mock_settings.default_symbol = "NIFTY"
        mock_settings.default_timeframe = "5m"
        mock_settings.default_expiry = None
        mock_settings.preferred_market_provider = "fyers"
        mock_settings.preferred_ai_provider = "gemini"
        mock_settings.preferred_ai_model = None
        mock_settings.notification_enabled = True
        mock_settings.created_at = "2024-01-01T00:00:00Z"
        mock_settings.updated_at = "2024-01-01T00:00:00Z"

        with patch("app.services.user_service.SettingsRepository.get_or_create", return_value=mock_settings):
            result = await SettingsService.get_settings(mock_session, mock_settings.user_id)
            assert result is not None
            assert result.theme == "dark"
            assert result.default_symbol == "NIFTY"

    @pytest.mark.asyncio
    async def test_update_settings(self):
        """SettingsService should update settings correctly."""
        from app.services.user_service import SettingsService
        from app.models.user import UserSettingsUpdate
        mock_session = AsyncMock()
        user_id = uuid4()
        mock_settings = MagicMock()
        mock_settings.id = uuid4()
        mock_settings.user_id = user_id
        mock_settings.theme = "light"
        mock_settings.default_symbol = "BANKNIFTY"
        mock_settings.default_timeframe = "15m"
        mock_settings.default_expiry = None
        mock_settings.preferred_market_provider = "fyers"
        mock_settings.preferred_ai_provider = "gemini"
        mock_settings.preferred_ai_model = None
        mock_settings.notification_enabled = True
        mock_settings.created_at = "2024-01-01T00:00:00Z"
        mock_settings.updated_at = "2024-01-01T00:00:00Z"

        with patch("app.services.user_service.ProfileRepository.get_or_create"), \
             patch("app.services.user_service.SettingsRepository.get_or_create", return_value=mock_settings), \
             patch("app.services.user_service.SettingsRepository.update", return_value=mock_settings):
            data = UserSettingsUpdate(theme="light", default_symbol="BANKNIFTY")
            result = await SettingsService.update_settings(mock_session, user_id, data)
            assert result is not None
            assert result.theme == "light"


class TestProfileService:
    """Test ProfileService with mocked database."""

    @pytest.mark.asyncio
    async def test_get_profile_creates_if_missing(self):
        """ProfileService should create profile if missing."""
        from app.services.user_service import ProfileService
        mock_session = AsyncMock()
        user_id = uuid4()
        mock_profile = MagicMock()
        mock_profile.id = user_id
        mock_profile.display_name = "Test User"
        mock_profile.created_at = "2024-01-01T00:00:00Z"
        mock_profile.updated_at = "2024-01-01T00:00:00Z"

        with patch("app.services.user_service.ProfileRepository.get_or_create", return_value=mock_profile):
            result = await ProfileService.get_profile(mock_session, user_id)
            assert result is not None
            assert result.display_name == "Test User"

    @pytest.mark.asyncio
    async def test_update_profile(self):
        """ProfileService should update profile display name."""
        from app.services.user_service import ProfileService
        from app.models.user import ProfileUpdate
        mock_session = AsyncMock()
        user_id = uuid4()
        mock_profile = MagicMock()
        mock_profile.id = user_id
        mock_profile.display_name = "Updated Name"
        mock_profile.created_at = "2024-01-01T00:00:00Z"
        mock_profile.updated_at = "2024-01-01T00:00:00Z"

        with patch("app.services.user_service.ProfileRepository.get_or_create", return_value=mock_profile), \
             patch("app.services.user_service.ProfileRepository.update", return_value=mock_profile):
            data = ProfileUpdate(display_name="Updated Name")
            result = await ProfileService.update_profile(mock_session, user_id, data)
            assert result is not None
            assert result.display_name == "Updated Name"
