"""Tests for the health check endpoint."""

from fastapi.testclient import TestClient

from railgati import __version__
from railgati.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    """Health endpoint should return HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_structure() -> None:
    """Health response should contain required fields."""
    response = client.get("/health")
    data = response.json()

    assert data["status"] == "ok"
    assert data["service"] == "railgati-api"
    assert data["version"] == __version__
    assert "timestamp" in data


def test_health_version_matches_package() -> None:
    """Health version should match the package version."""
    response = client.get("/health")
    data = response.json()
    assert data["version"] == "0.1.0"
