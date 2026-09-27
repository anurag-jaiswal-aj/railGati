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
def terminus_api_test_data(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id),
        TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s3.id),
    ])
    db_session.flush()


def test_api_get_network_termini_basic(client: TestClient, terminus_api_test_data: None) -> None:
    response = client.get("/api/v1/network/termini")
    assert response.status_code == 200
    data = response.json()
    assert data["timetable_snapshot_id"] == 1

    termini = data["termini"]
    assert len(termini) == 2

    # Order: C (1 orig, 0 term = 1 volume? No, C is term -> 0 orig, 1 term => 1)
    # A (1 orig, 0 term => 1)
    # Both have 1 total volume. Tie-break: orig count. A has 1 orig, C has 0 orig. So A should be first.
    assert termini[0]["station_code"] == "A"
    assert termini[0]["originating_count"] == 1
    assert termini[0]["terminating_count"] == 0
    assert termini[0]["total_terminus_volume"] == 1

    assert termini[1]["station_code"] == "C"
    assert termini[1]["originating_count"] == 0
    assert termini[1]["terminating_count"] == 1
    assert termini[1]["total_terminus_volume"] == 1


def test_api_get_network_termini_explicit_limit(client: TestClient, terminus_api_test_data: None) -> None:
    response = client.get("/api/v1/network/termini?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["termini"]) == 1
    assert data["termini"][0]["station_code"] == "A"


def test_api_get_network_termini_invalid_limit(client: TestClient) -> None:
    response = client.get("/api/v1/network/termini?limit=0")
    assert response.status_code == 422

    response = client.get("/api/v1/network/termini?limit=501")
    assert response.status_code == 422


def test_api_get_network_termini_empty(client: TestClient, db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()
    setup_stations(db_session)

    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))
    db_session.flush()

    response = client.get("/api/v1/network/termini")
    assert response.status_code == 200
    assert len(response.json()["termini"]) == 0
