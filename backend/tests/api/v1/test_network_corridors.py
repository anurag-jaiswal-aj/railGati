import pytest
from fastapi.testclient import TestClient
from railgati.main import app

def test_api_network_corridors_missing_params(client: TestClient) -> None:
    res = client.get("/api/v1/network/corridors")
    assert res.status_code == 422
    assert "Field required" in res.text

def test_api_network_corridors_same_station(client: TestClient) -> None:
    res = client.get("/api/v1/network/corridors?origin=NDLS&destination=ndls")
    assert res.status_code == 422
    assert "must not be the same" in res.json()["detail"]

def test_api_network_corridors_unknown_station(client: TestClient) -> None:
    res = client.get("/api/v1/network/corridors?origin=UNKNOWN&destination=NDLS")
    assert res.status_code == 404
    assert "Origin station 'UNKNOWN' not found" in res.json()["detail"]
