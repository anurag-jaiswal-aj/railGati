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
    db_session.add_all([s1, s2])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s1.id, name="Stn A"),
            StationObservation(snapshot_id=1, station_id=s2.id, name="Stn B"),
        ]
    )

    t1 = Train(number="101")
    t2 = Train(number="102")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
        ]
    )

    db_session.add_all(
        [
            # Station A has 1 transit at 08:00
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s1.id,
                departure_time="08:00:00",
            ),
            # Station B has 2 transits at 18:00 and 19:00
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s2.id,
                arrival_time="18:30:00",
                departure_time="18:40:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=2,
                station_id=s2.id,
                arrival_time="19:00:00",
            ),
        ]
    )
    db_session.commit()


def test_get_temporal_concentration(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)

    response = client.get("/api/v1/network/temporal-concentration?min_service_count=1")
    assert response.status_code == 200
    data = response.json()

    assert data["timetable_snapshot_id"] == 1
    assert data["limit"] == 50
    assert data["min_service_count"] == 1
    assert len(data["items"]) == 2

    # Should be sorted by concentration desc (both are 100% or 50%? wait, B is 50%, A is 100%)
    assert data["items"][0]["station_code"] == "A"
    assert data["items"][0]["concentration_pct"] == 100.0
    assert data["items"][0]["peak_hour_val"] == 8

    assert data["items"][1]["station_code"] == "B"
    assert data["items"][1]["concentration_pct"] == 50.0
    # Peak hour for B tie breaks to the earlier hour (18)
    assert data["items"][1]["peak_hour_val"] == 18


def test_get_temporal_concentration_empty(client: TestClient, db_session: Session) -> None:
    source = DataSource(name="test_api2", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.commit()

    response = client.get("/api/v1/network/temporal-concentration")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_get_temporal_concentration_validation(client: TestClient) -> None:
    response = client.get("/api/v1/network/temporal-concentration?limit=0")
    assert response.status_code == 422

    response = client.get("/api/v1/network/temporal-concentration?limit=1000")
    assert response.status_code == 422

    response = client.get("/api/v1/network/temporal-concentration?min_service_count=0")
    assert response.status_code == 422
