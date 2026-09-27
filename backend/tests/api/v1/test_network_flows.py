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
def flow_api_test_data(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s3.id),
        ]
    )
    db_session.flush()


def test_api_get_network_flows_basic(client: TestClient, flow_api_test_data: None) -> None:
    response = client.get("/api/v1/network/flows")
    assert response.status_code == 200
    data = response.json()
    assert data["timetable_snapshot_id"] == 1

    flows = data["flows"]
    assert len(flows) == 1

    assert flows[0]["origin_station_code"] == "A"
    assert flows[0]["destination_station_code"] == "C"
    assert flows[0]["flow_volume"] == 1


def test_api_get_network_flows_explicit_limit(client: TestClient, flow_api_test_data: None) -> None:
    response = client.get("/api/v1/network/flows?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["flows"]) == 1
    assert data["flows"][0]["origin_station_code"] == "A"


def test_api_get_network_flows_invalid_limit(client: TestClient) -> None:
    response = client.get("/api/v1/network/flows?limit=0")
    assert response.status_code == 422

    response = client.get("/api/v1/network/flows?limit=501")
    assert response.status_code == 422


def test_api_get_network_flows_empty(client: TestClient, db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()
    setup_stations(db_session)

    t1 = Train(number="101")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))
    db_session.flush()

    response = client.get("/api/v1/network/flows")
    assert response.status_code == 200
    assert len(response.json()["flows"]) == 0
