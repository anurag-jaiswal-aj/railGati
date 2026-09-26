"""Tests for the Stations API."""

from fastapi.testclient import TestClient

def test_search_stations_exact_code(client: TestClient, populated_db) -> None:
    """Test exact code match gets ordered first."""
    response = client.get("/api/v1/stations/search?q=ndls")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] >= 1
    # NDLS should be first
    assert data["items"][0]["code"] == "NDLS"

def test_search_stations_name_match(client: TestClient, populated_db) -> None:
    """Test name match."""
    response = client.get("/api/v1/stations/search?q=mumbai")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 1
    assert data["items"][0]["code"] == "BCT"

def test_search_stations_pagination(client: TestClient, populated_db) -> None:
    """Test pagination bounds."""
    response = client.get("/api/v1/stations/search?q=n&page=1&size=1")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 3
    assert len(data["items"]) == 1

def test_search_stations_empty_query(client: TestClient, populated_db) -> None:
    """Test empty query validation."""
    response = client.get("/api/v1/stations/search?q=")
    assert response.status_code == 422

def test_search_stations_excludes_failed_snapshots(client: TestClient, populated_db) -> None:
    """Test that FAIL code from FAILED snapshot is not returned."""
    response = client.get("/api/v1/stations/search?q=fail")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 0

def test_get_station_detail(client: TestClient, populated_db) -> None:
    """Test canonical station detail."""
    response = client.get("/api/v1/stations/ndls")
    assert response.status_code == 200
    data = response.json()
    
    assert data["code"] == "NDLS"
    assert data["name"] == "New Delhi"
    assert data["provenance"]["snapshot_id"] is not None

def test_get_station_detail_not_found(client: TestClient, populated_db) -> None:
    """Test non-existent station."""
    response = client.get("/api/v1/stations/UNKNOWN")
    assert response.status_code == 404
