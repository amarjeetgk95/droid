import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.providers.mock import MockProvider


@pytest.fixture
def client():
    """FastAPI test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_provider():
    """Deterministic mock provider."""
    return MockProvider(mode="deterministic", seed=42)
