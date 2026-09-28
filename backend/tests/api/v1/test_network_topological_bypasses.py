import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def api_bypass_fixtures(db_session: Session) -> None:
    source = DataSource(
        name="test_api_source", url="http://test", publisher="pub", license="MIT"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    trains_data = [
        ("NO_BYPASS", ["S6", "S7", "S8"]),
        ("HAS_BYPASS", ["S1", "S2", "S3", "S4", "S5"]),
        ("BYPASS_PROVIDER", ["S1", "S3", "S5"]),
    ]

    for t_num, route in trains_data:
        tr = Train(number=t_num)
        db_session.add(tr)
        db_session.commit()
        db_session.add(
            TrainObservation(snapshot_id=snap_id, train_id=tr.id, name=t_num, type="EXP")
        )
        for idx, s_code in enumerate(route):
            db_session.add(TrainStopObservation(
                snapshot_id=snap_id,
                train_id=tr.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1
            ))
        db_session.commit()

def test_api_topological_bypasses_success(client: TestClient, api_bypass_fixtures: None) -> None:
    response = client.get("/api/v1/network/trains/HAS_BYPASS/topological-bypasses")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "HAS_BYPASS"
    assert data["route_length"] == 5
    assert data["bypass_edge_count"] == 2
    assert data["has_topological_bypasses"] is True

def test_api_topological_bypasses_no_bypasses(client: TestClient, api_bypass_fixtures: None) -> None:
    response = client.get("/api/v1/network/trains/NO_BYPASS/topological-bypasses")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "NO_BYPASS"
    assert data["route_length"] == 3
    assert data["bypass_edge_count"] == 0
    assert data["has_topological_bypasses"] is False

def test_api_topological_bypasses_not_found(client: TestClient, api_bypass_fixtures: None) -> None:
    response = client.get("/api/v1/network/trains/UNKNOWN/topological-bypasses")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
