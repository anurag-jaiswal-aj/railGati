import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def api_edge_dispersion_fixtures(db_session: Session) -> None:
    source = DataSource(
        name="test_api_dispersion", url="http://test", publisher="pub", license="MIT"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["X1", "X2", "A", "B", "Y1", "Y2"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    trains_data = [
        ("T1", ["X1", "A", "B", "Y1"]),
        ("T2", ["X1", "A", "B", "Y2"]),
        ("T3", ["X2", "A", "B", "Y1"]),
        ("T4", ["A", "B", "Y2"]),
        ("T5", ["X2", "A", "B"]),
        ("T6", ["B", "A"]),
        ("T7", ["X1", "A", "B", "Y1"]),
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

def test_api_edge_dispersion_success(client: TestClient, api_edge_dispersion_fixtures: None) -> None:
    response = client.get("/api/v1/network/edges/A/B/traversal-dispersion")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "A"
    assert data["to_station_code"] == "B"
    assert data["edge_volume"] == 6
    assert data["convergence_count"] == 2
    assert data["originating_count"] == 1
    assert data["bifurcation_count"] == 2
    assert data["terminating_count"] == 1

def test_api_edge_dispersion_reverse(client: TestClient, api_edge_dispersion_fixtures: None) -> None:
    response = client.get("/api/v1/network/edges/B/A/traversal-dispersion")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "B"
    assert data["to_station_code"] == "A"
    assert data["edge_volume"] == 1
    assert data["convergence_count"] == 0
    assert data["originating_count"] == 1
    assert data["bifurcation_count"] == 0
    assert data["terminating_count"] == 1

def test_api_edge_dispersion_no_edge(client: TestClient, api_edge_dispersion_fixtures: None) -> None:
    response = client.get("/api/v1/network/edges/A/Y1/traversal-dispersion")
    assert response.status_code == 400
    assert "no qualifying adjacent timetable edge found" in response.json()["detail"].lower()

def test_api_edge_dispersion_unknown_station(client: TestClient, api_edge_dispersion_fixtures: None) -> None:
    response = client.get("/api/v1/network/edges/UNKNOWN/B/traversal-dispersion")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
