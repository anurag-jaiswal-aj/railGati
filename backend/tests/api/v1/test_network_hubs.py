import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation


@pytest.fixture
def hub_test_data(db_session: Session) -> None:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.add(RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE"))

    # Need active station snapshot too (ID 2 is fine)
    db_session.add(DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    from railgati.models.train import Train, TrainObservation
    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Test Train"))
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=2, station_id=s1.id, name="A"),
            StationObservation(snapshot_id=2, station_id=s2.id, name="B"),
            StationObservation(snapshot_id=2, station_id=s3.id, name="C"),
        ]
    )
    db_session.flush()

    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=5
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=3
            ),
        ]
    )
    db_session.flush()


def test_api_get_hubs_valid(client: TestClient, hub_test_data: None) -> None:
    response = client.get("/api/v1/network/hubs")
    assert response.status_code == 200
    data = response.json()
    assert data["timetable_snapshot_id"] == 1
    hubs = data["hubs"]
    assert len(hubs) == 3
    # B is the most central by total volume (5+3=8)
    assert hubs[0]["station_code"] == "B"
    assert hubs[0]["out_degree"] == 1
    assert hubs[0]["in_degree"] == 1
    assert hubs[0]["total_topological_degree"] == 2
    assert hubs[0]["inbound_service_occurrence_volume"] == 5
    assert hubs[0]["outbound_service_occurrence_volume"] == 3
    assert hubs[0]["combined_occurrence_volume"] == 8


def test_api_get_hubs_limit(client: TestClient, hub_test_data: None) -> None:
    response = client.get("/api/v1/network/hubs?limit=1")
    assert response.status_code == 200
    assert len(response.json()["hubs"]) == 1


def test_api_get_hubs_invalid_limit(client: TestClient, hub_test_data: None) -> None:
    response = client.get("/api/v1/network/hubs?limit=1000")
    assert response.status_code == 422

    response = client.get("/api/v1/network/hubs?limit=0")
    assert response.status_code == 422


def test_api_get_hubs_invalid_sort(client: TestClient, hub_test_data: None) -> None:
    response = client.get("/api/v1/network/hubs?sort_by=invalid")
    assert response.status_code == 422


def test_api_get_hubs_no_build(client: TestClient, db_session: Session) -> None:
    # Set up basic without graph build
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    response = client.get("/api/v1/network/hubs")
    assert response.status_code == 503
