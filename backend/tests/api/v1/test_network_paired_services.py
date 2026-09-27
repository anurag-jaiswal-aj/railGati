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

    s_ndls = Station(code="NDLS")
    s_other = Station(code="OTHER")
    db_session.add_all([s_ndls, s_other])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_ndls.id, name="New Delhi"),
            StationObservation(snapshot_id=1, station_id=s_other.id, name="Other"),
        ]
    )

    t1 = Train(number="12486")
    t2 = Train(number="12485")
    t3 = Train(number="12000")
    t4 = Train(number="12001")
    t5 = Train(number="11000")
    t6 = Train(number="11001")
    db_session.add_all([t1, t2, t3, t4, t5, t6])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1", return_train_number="12485"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
            TrainObservation(snapshot_id=1, train_id=t3.id, name="T3", return_train_number="12001"),
            TrainObservation(snapshot_id=1, train_id=t4.id, name="T4"),
            TrainObservation(snapshot_id=1, train_id=t5.id, name="T5", return_train_number="11001"),
            TrainObservation(snapshot_id=1, train_id=t6.id, name="T6"),
        ]
    )

    # 12486 arrives 23:20 NDLS, 12485 departs 01:40 NDLS (140 mins)
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s_other.id,
                departure_time="20:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s_ndls.id,
                arrival_time="23:20:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=1,
                station_id=s_ndls.id,
                departure_time="01:40:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=2,
                station_id=s_other.id,
                arrival_time="05:00:00",
            ),
        ]
    )

    # 12000 arrives 12:00 NDLS, 12001 departs 12:00 NDLS (0 mins exact match)
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t3.id,
                stop_sequence=1,
                station_id=s_other.id,
                departure_time="10:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t3.id,
                stop_sequence=2,
                station_id=s_ndls.id,
                arrival_time="12:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t4.id,
                stop_sequence=1,
                station_id=s_ndls.id,
                departure_time="12:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t4.id,
                stop_sequence=2,
                station_id=s_other.id,
                arrival_time="15:00:00",
            ),
        ]
    )

    # 11000 arrives 12:00 OTHER, 11001 departs 14:00 OTHER (120 mins)
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t5.id,
                stop_sequence=1,
                station_id=s_ndls.id,
                departure_time="10:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t5.id,
                stop_sequence=2,
                station_id=s_other.id,
                arrival_time="12:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t6.id,
                stop_sequence=1,
                station_id=s_other.id,
                departure_time="14:00:00",
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t6.id,
                stop_sequence=2,
                station_id=s_ndls.id,
                arrival_time="15:00:00",
            ),
        ]
    )

    db_session.commit()


def test_api_network_paired_services_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/NDLS/paired-services")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "NDLS"
    assert data["paired_service_count"] == 2
    assert data["avg_clock_gap_minutes"] == 70.0  # (140 + 0) / 2

    # Check 12000 exact match
    p1 = data["paired_services"][0]
    assert p1["arriving_train_number"] == "12000"
    assert p1["departing_train_number"] == "12001"
    assert p1["clock_gap_minutes"] == 0

    # Check 12486 next day cross
    p2 = data["paired_services"][1]
    assert p2["arriving_train_number"] == "12486"
    assert p2["departing_train_number"] == "12485"
    assert p2["clock_gap_minutes"] == 140


def test_api_network_paired_services_empty(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)

    s_empty = Station(code="EMPTY")
    db_session.add(s_empty)
    db_session.flush()
    db_session.add(StationObservation(snapshot_id=1, station_id=s_empty.id, name="Empty"))
    db_session.commit()

    response = client.get("/api/v1/network/stations/EMPTY/paired-services")
    assert response.status_code == 200
    data = response.json()
    assert data["paired_service_count"] == 0
    assert data["avg_clock_gap_minutes"] is None
    assert data["paired_services"] == []


def test_api_network_paired_services_unknown_station(
    client: TestClient, db_session: Session
) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/XXX/paired-services")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_api_network_paired_services_isolation(client: TestClient, db_session: Session) -> None:
    # Set inactive
    setup_data(db_session)
    snap = db_session.scalar(DatasetSnapshot.__table__.select())
    db_session.execute(DatasetSnapshot.__table__.update().values(status="ARCHIVED"))
    db_session.commit()

    response = client.get("/api/v1/network/stations/NDLS/paired-services")
    assert response.status_code == 503
