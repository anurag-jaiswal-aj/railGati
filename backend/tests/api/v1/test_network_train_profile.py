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

    s_orig = Station(code="ORG")
    s_mid1 = Station(code="MD1")
    s_mid2 = Station(code="MD2")
    s_dest = Station(code="DST")
    db_session.add_all([s_orig, s_mid1, s_mid2, s_dest])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_orig.id, name="Origin"),
            StationObservation(snapshot_id=1, station_id=s_mid1.id, name="Mid 1"),
            StationObservation(snapshot_id=1, station_id=s_mid2.id, name="Mid 2"),
            StationObservation(snapshot_id=1, station_id=s_dest.id, name="Dest"),
        ]
    )

    t1 = Train(number="12345")
    t_no_obs = Train(number="00000")
    db_session.add_all([t1, t_no_obs])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
        ]
    )

    # Train 1: ORG -> MD1 -> MD2 -> DST
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s_orig.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s_mid1.id,
                arrival_time="11:00:00",
                departure_time="11:10:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=3,
                station_id=s_mid2.id,
                arrival_time="23:55:00",
                departure_time="00:05:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=4,
                station_id=s_dest.id,
                arrival_time="02:00:00",
                source_day=2,
            ),
        ]
    )

    db_session.commit()


def test_api_network_train_profile_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/12345/profile")
    assert response.status_code == 200
    data = response.json()

    assert data["train_number"] == "12345"
    assert data["origin_station_code"] == "ORG"
    assert data["destination_station_code"] == "DST"
    assert data["total_stops"] == 4

    # Total duration: day 1 (10:00) to day 2 (02:00) = 14 hours = 840 mins
    # MD1 dwell: 10 mins
    # MD2 dwell: 23:55 to 00:05 = 10 mins
    # Total dwell = 20 mins
    assert data["total_duration_minutes"] == 960.0
    assert data["total_dwell_minutes"] == 20.0
    assert data["dwell_percentage"] == round((20.0 / 960.0) * 100, 1)


def test_api_network_train_profile_unknown_train(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/99999/profile")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_api_network_train_profile_no_observations(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/00000/profile")
    assert response.status_code == 404
    assert "no usable observations" in response.json()["detail"].lower()


def test_api_network_train_profile_isolation(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    db_session.execute(DatasetSnapshot.__table__.update().values(status="ARCHIVED"))
    db_session.commit()

    response = client.get("/api/v1/network/trains/12345/profile")
    assert response.status_code == 503
