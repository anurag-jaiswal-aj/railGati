"""Tests for the Trains API."""

from fastapi.testclient import TestClient

def test_search_trains_between_unavailable(client: TestClient) -> None:
    """Test train discovery returns 501 Not Implemented with graceful message."""
    response = client.get("/api/v1/trains/between?source=NDLS&destination=BCT")
    assert response.status_code == 501
    
    data = response.json()
    assert data["available"] is False
    assert "unavailable" in data["message"].lower()

def test_search_trains_between_validation(client: TestClient) -> None:
    """Test validation errors on empty source/destination."""
    response = client.get("/api/v1/trains/between?source=&destination=")
    assert response.status_code == 422
