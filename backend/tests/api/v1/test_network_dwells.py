import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation


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


@pytest.fixture
def dwell_api_test_data(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

    # Train 1: A -> B -> C (B dwell 10 mins)
    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s1.id,
                departure_time="10:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s2.id,
                arrival_time="11:00:00",
                departure_time="11:10:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=3,
                station_id=s3.id,
                arrival_time="12:00:00",
            ),
        ]
    )
    db_session.flush()


def test_api_get_network_dwells_basic(client: TestClient, dwell_api_test_data: None) -> None:
    response = client.get("/api/v1/network/dwells?min_transit_count=1")
    assert response.status_code == 200
    data = response.json()
    assert data["timetable_snapshot_id"] == 1
    assert data["limit"] == 50
    assert data["min_transit_count"] == 1

    dwells = data["items"]
    assert len(dwells) == 1

    assert dwells[0]["station_code"] == "B"
    assert dwells[0]["avg_dwell_minutes"] == 10.0
    assert dwells[0]["transit_count"] == 1


def test_api_get_network_dwells_invalid_params(client: TestClient) -> None:
    response = client.get("/api/v1/network/dwells?limit=0")
    assert response.status_code == 422

    response = client.get("/api/v1/network/dwells?limit=501")
    assert response.status_code == 422

    response = client.get("/api/v1/network/dwells?min_transit_count=0")
    assert response.status_code == 422


def test_api_get_network_dwells_empty(client: TestClient, db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()
    setup_stations(db_session)

    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))
    db_session.flush()

    response = client.get("/api/v1/network/dwells")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 0
