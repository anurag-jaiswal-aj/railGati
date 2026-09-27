import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation


def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    return source


def setup_stations(db_session: Session) -> tuple[Station, Station, Station]:
    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s1.id, name="Station A"),
            StationObservation(snapshot_id=1, station_id=s2.id, name="Station B"),
            StationObservation(snapshot_id=1, station_id=s3.id, name="Station C"),
        ]
    )
    db_session.flush()
    return s1, s2, s3


def setup_edges_graph(db_session: Session, source_id: int) -> None:
    db_session.add(DatasetSnapshot(id=1, source_id=source_id, status="ACTIVE"))
    db_session.flush()
    db_session.add(DatasetSnapshot(id=2, source_id=source_id, status="ACTIVE"))
    db_session.flush()

    db_session.add(RailwayGraphBuild(timetable_snapshot_id=2, status="ACTIVE"))
    db_session.flush()

    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=2, train_id=t1.id, name="Test Train"))
    db_session.flush()


@pytest.fixture
def edge_api_test_data(db_session: Session) -> None:
    source = create_deps(db_session)
    setup_edges_graph(db_session, source.id)
    s1, s2, s3 = setup_stations(db_session)

    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=2,
                from_station_id=s1.id,
                to_station_id=s2.id,
                train_count=100,
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=2,
                from_station_id=s2.id,
                to_station_id=s3.id,
                train_count=200,
            ),
        ]
    )
    db_session.flush()


def test_api_get_edges_volume(client: TestClient, edge_api_test_data: None) -> None:
    response = client.get("/api/v1/network/edges/volume")
    assert response.status_code == 200
    data = response.json()
    assert data["timetable_snapshot_id"] == 2
    assert len(data["edges"]) == 2

    # Check ordering and data
    assert data["edges"][0]["service_occurrence_volume"] == 200
    assert data["edges"][0]["from_station_code"] == "B"
    assert data["edges"][0]["to_station_code"] == "C"

    assert data["edges"][1]["service_occurrence_volume"] == 100
    assert data["edges"][1]["from_station_code"] == "A"
    assert data["edges"][1]["to_station_code"] == "B"


def test_api_get_edges_volume_limit(client: TestClient, edge_api_test_data: None) -> None:
    response = client.get("/api/v1/network/edges/volume?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["edges"]) == 1
    assert data["edges"][0]["service_occurrence_volume"] == 200


def test_api_get_edges_volume_invalid_limit(client: TestClient, edge_api_test_data: None) -> None:
    response = client.get("/api/v1/network/edges/volume?limit=0")
    assert response.status_code == 422

    response = client.get("/api/v1/network/edges/volume?limit=501")
    assert response.status_code == 422


def test_api_get_edges_volume_missing_build(client: TestClient, db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()
    db_session.add(DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=2, train_id=t1.id, name="Test Train"))
    db_session.flush()

    # Missing RailwayGraphBuild
    response = client.get("/api/v1/network/edges/volume")
    assert response.status_code == 503
    assert "No ACTIVE RailwayGraphBuild found" in response.json()["detail"]


def test_api_get_edges_volume_empty(client: TestClient, db_session: Session) -> None:
    source = create_deps(db_session)
    setup_edges_graph(db_session, source.id)
    setup_stations(db_session)

    # No edges
    response = client.get("/api/v1/network/edges/volume")
    assert response.status_code == 200
    data = response.json()
    assert len(data["edges"]) == 0
