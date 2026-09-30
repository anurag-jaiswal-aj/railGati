import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.graph import RailwayNetworkEdge


@pytest.fixture
def setup_api_diameter_data(db_session: Session) -> None:
    source = DataSource(name="api_test", url="http", publisher="pub", license="MIT")
    db_session.add(source)
    db_session.flush()

    snap = DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()

    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    t = Train(number="11013")
    db_session.add(t)
    db_session.flush()

    db_session.add(TrainObservation(train_id=t.id, snapshot_id=2, name="EXP"))
    for i, s in enumerate([s1, s2, s3], 1):
        db_session.add(TrainStopObservation(train_id=t.id, snapshot_id=2, station_id=s.id, stop_sequence=i))

    db_session.add(RailwayNetworkEdge(
        timetable_snapshot_id=2,
        from_station_id=min(s1.id, s2.id),
        to_station_id=max(s1.id, s2.id),
        train_count=1,
    ))
    db_session.add(RailwayNetworkEdge(
        timetable_snapshot_id=2,
        from_station_id=min(s2.id, s3.id),
        to_station_id=max(s2.id, s3.id),
        train_count=1,
    ))

    # Another train disconnected
    t2 = Train(number="DISCONN")
    db_session.add(t2)
    db_session.flush()
    db_session.add(TrainObservation(train_id=t2.id, snapshot_id=2, name="DISC"))
    db_session.add(TrainStopObservation(train_id=t2.id, snapshot_id=2, station_id=s1.id, stop_sequence=1))
    db_session.add(TrainStopObservation(train_id=t2.id, snapshot_id=2, station_id=s3.id, stop_sequence=2))
    # Note: s1-s3 edge does not exist -> disconnected

    db_session.commit()


def test_api_subgraph_diameter_success(
    client: TestClient,
    setup_api_diameter_data: None,
) -> None:
    response = client.get("/api/v1/network/trains/11013/subgraph-diameter")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "11013"
    assert data["route_station_count"] == 3
    assert data["subgraph_diameter"] == 2
    assert data["subgraph_connected"] is True
    assert data["component_count"] == 1

def test_api_subgraph_diameter_disconnected(
    client: TestClient,
    setup_api_diameter_data: None,
) -> None:
    response = client.get("/api/v1/network/trains/DISCONN/subgraph-diameter")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "DISCONN"
    assert data["route_station_count"] == 2
    assert data["subgraph_diameter"] is None
    assert data["subgraph_connected"] is False
    assert data["component_count"] == 2

def test_api_subgraph_diameter_unknown_train(
    client: TestClient,
    setup_api_diameter_data: None,
) -> None:
    response = client.get("/api/v1/network/trains/UNKNOWN/subgraph-diameter")
    assert response.status_code == 404
