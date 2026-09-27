from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation


def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_api", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s1.id, name="Station A"),
            StationObservation(snapshot_id=1, station_id=s2.id, name="Station B"),
        ]
    )

    t1 = Train(number="111")
    t2 = Train(number="222")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1", type="EXP"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2", return_train_number="111"),
        ]
    )

    # Both Station A and Station B share Train 111 and 222
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s2.id),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s1.id),
        ]
    )
    db_session.commit()


def test_api_station_similarity_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/A/similar")
    assert response.status_code == 200
    data = response.json()
    assert data["target_station_code"] == "A"
    assert data["target_station_name"] == "Station A"
    assert data["target_train_count"] == 2
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["station_code"] == "B"
    assert item["station_name"] == "Station B"
    assert item["overlap_train_count"] == 2
    assert item["compared_train_count"] == 2
    assert item["union_train_count"] == 2
    assert item["similarity_pct"] == 100.0


def test_api_station_similarity_not_found(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/XXX/similar")
    assert response.status_code == 404


def test_api_station_similarity_validation(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/A/similar?limit=0")
    assert response.status_code == 422
    response = client.get("/api/v1/network/stations/A/similar?limit=51")
    assert response.status_code == 422
    response = client.get("/api/v1/network/stations/A/similar?min_overlap_trains=-1")
    assert response.status_code == 422


def test_api_station_similarity_empty_result(client: TestClient, db_session: Session) -> None:
    source = DataSource(name="test_api2", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s1 = Station(code="A")
    db_session.add(s1)
    db_session.flush()
    db_session.add(StationObservation(snapshot_id=1, station_id=s1.id, name="A"))

    t1 = Train(number="111")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"))
    db_session.commit()

    # Station exists but no stops, so no similar stations
    response = client.get("/api/v1/network/stations/A/similar")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_api_station_similarity_missing_snapshot(client: TestClient, db_session: Session) -> None:
    # No active snapshot
    response = client.get("/api/v1/network/stations/A/similar")
    assert response.status_code == 503
