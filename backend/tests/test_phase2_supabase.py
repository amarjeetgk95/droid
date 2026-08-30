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


class TestWatchlistEndpoints:
    """Test watchlist API endpoints."""

    def test_list_watchlists_no_db(self, no_db_client: TestClient):
        """GET watchlists should return 503 when DB not configured."""
        r = no_db_client.get("/api/v1/watchlists")
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]

    def test_create_watchlist_no_db(self, no_db_client: TestClient):
        """POST watchlists should return 503 when DB not configured."""
        r = no_db_client.post("/api/v1/watchlists", json={"name": "Test"})
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]

    def test_get_watchlist_no_db(self, no_db_client: TestClient):
        """GET watchlist by ID should return 503 when DB not configured."""
        r = no_db_client.get(f"/api/v1/watchlists/{uuid4()}")
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]

    def test_update_watchlist_no_db(self, no_db_client: TestClient):
        """PATCH watchlist should return 503 when DB not configured."""
        r = no_db_client.patch(f"/api/v1/watchlists/{uuid4()}", json={"name": "Updated"})
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]

    def test_delete_watchlist_no_db(self, no_db_client: TestClient):
        """DELETE watchlist should return 503 when DB not configured."""
        r = no_db_client.delete(f"/api/v1/watchlists/{uuid4()}")
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]

    def test_list_items_no_db(self, no_db_client: TestClient):
        """GET watchlist items should return 503 when DB not configured."""
        r = no_db_client.get(f"/api/v1/watchlists/{uuid4()}/items")
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]

    def test_add_item_no_db(self, no_db_client: TestClient):
        """POST watchlist item should return 503 when DB not configured."""
        r = no_db_client.post(f"/api/v1/watchlists/{uuid4()}/items", json={"symbol": "NIFTY"})
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]

    def test_update_item_no_db(self, no_db_client: TestClient):
        """PATCH watchlist item should return 503 when DB not configured."""
        r = no_db_client.patch(f"/api/v1/watchlists/{uuid4()}/items/{uuid4()}", json={"display_order": 1})
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]

    def test_remove_item_no_db(self, no_db_client: TestClient):
        """DELETE watchlist item should return 503 when DB not configured."""
        r = no_db_client.delete(f"/api/v1/watchlists/{uuid4()}/items/{uuid4()}")
        assert r.status_code == 503
        assert "Database not configured" in r.json()["detail"]

    def test_watchlist_requires_auth_in_production(self):
        """Watchlist endpoints should require auth when AUTH_REQUIRED=true."""
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.auth_required = True
            mock_settings.supabase_jwt_secret = "test-secret"
            from app.main import app
            with TestClient(app) as c:
                r = c.get("/api/v1/watchlists")
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


class TestWatchlistService:
    """Test WatchlistService with mocked database."""

    @pytest.mark.asyncio
    async def test_get_user_watchlists(self):
        """WatchlistService should return user watchlists."""
        from app.services.user_service import WatchlistService
        mock_session = AsyncMock()
        user_id = uuid4()
        mock_wl = MagicMock()
        mock_wl.id = uuid4()
        mock_wl.user_id = user_id
        mock_wl.name = "Test Watchlist"
        mock_wl.created_at = "2024-01-01T00:00:00Z"
        mock_wl.updated_at = "2024-01-01T00:00:00Z"

        with patch("app.services.user_service.WatchlistRepository.get_by_user", return_value=[mock_wl]):
            result = await WatchlistService.get_user_watchlists(mock_session, user_id)
            assert len(result) == 1
            assert result[0].name == "Test Watchlist"

    @pytest.mark.asyncio
    async def test_create_watchlist(self):
        """WatchlistService should create a new watchlist."""
        from app.services.user_service import WatchlistService
        from app.models.user import WatchlistCreate
        mock_session = AsyncMock()
        user_id = uuid4()
        mock_wl = MagicMock()
        mock_wl.id = uuid4()
        mock_wl.user_id = user_id
        mock_wl.name = "New Watchlist"
        mock_wl.created_at = "2024-01-01T00:00:00Z"
        mock_wl.updated_at = "2024-01-01T00:00:00Z"

        with patch("app.services.user_service.ProfileRepository.get_or_create"), \
             patch("app.services.user_service.WatchlistRepository.create", return_value=mock_wl):
            data = WatchlistCreate(name="New Watchlist")
            result = await WatchlistService.create_watchlist(mock_session, user_id, data)
            assert result.name == "New Watchlist"

    @pytest.mark.asyncio
    async def test_watchlist_ownership_check(self):
        """WatchlistService should enforce ownership."""
        from app.services.user_service import WatchlistService
        mock_session = AsyncMock()
        owner_id = uuid4()
        other_id = uuid4()
        watchlist_id = uuid4()

        with patch("app.services.user_service.WatchlistRepository.belongs_to_user", return_value=False):
            result = await WatchlistService.get_watchlist(mock_session, watchlist_id, other_id)
            assert result is None


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
