import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def api_edge_exclusivity_fixtures(db_session: Session) -> None:
    source = DataSource(
        name="test_api_exclusivity", url="http://test", publisher="pub", license="MIT"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["A", "B", "C"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    trains_data = [
        ("API_EXC", ["A", "B", "C"]),
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

def test_api_edge_exclusivity_success(client: TestClient, api_edge_exclusivity_fixtures: None) -> None:
    response = client.get("/api/v1/network/trains/API_EXC/route-edge-exclusivity")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "API_EXC"
    assert data["route_edge_count"] == 2
    assert data["exclusive_edge_count"] == 2
    assert data["shared_edge_count"] == 0

def test_api_edge_exclusivity_not_found(client: TestClient, api_edge_exclusivity_fixtures: None) -> None:
    response = client.get("/api/v1/network/trains/UNKNOWN/route-edge-exclusivity")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
