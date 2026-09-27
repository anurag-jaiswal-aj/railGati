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
    s_csb = Station(code="CSB")
    s_dsb = Station(code="DSB")
    s_other = Station(code="OTHER")
    db_session.add_all([s_ndls, s_csb, s_dsb, s_other])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_ndls.id, name="New Delhi"),
            StationObservation(snapshot_id=1, station_id=s_csb.id, name="Shivaji Bridge"),
            StationObservation(snapshot_id=1, station_id=s_dsb.id, name="Delhi Sadar Bazar"),
            StationObservation(snapshot_id=1, station_id=s_other.id, name="Other"),
        ]
    )

    t1 = Train(number="0001")
    t2 = Train(number="0002")
    t3 = Train(number="0003")
    t4 = Train(number="0004")
    db_session.add_all([t1, t2, t3, t4])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
            TrainObservation(snapshot_id=1, train_id=t3.id, name="T3"),
            TrainObservation(snapshot_id=1, train_id=t4.id, name="T4"),
        ]
    )

    # 1. Normal transit NDLS -> CSB
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=1,
                station_id=s_ndls.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t1.id,
                stop_sequence=2,
                station_id=s_csb.id,
                arrival_time="10:05:00",
                source_day=1,
            ),
        ]
    )

    # 2. Another transit NDLS -> CSB (different time)
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=1,
                station_id=s_ndls.id,
                departure_time="11:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t2.id,
                stop_sequence=2,
                station_id=s_csb.id,
                arrival_time="11:10:00",
                source_day=1,
            ),
        ]
    )

    # 3. Anomalous transit NDLS -> DSB (source day increment but low hour gap)
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t3.id,
                stop_sequence=1,
                station_id=s_ndls.id,
                departure_time="00:10:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t3.id,
                stop_sequence=2,
                station_id=s_dsb.id,
                arrival_time="00:17:00",
                source_day=2,
            ),
        ]
    )

    # 4. Terminal train at NDLS (should not be included)
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=1,
                train_id=t4.id,
                stop_sequence=1,
                station_id=s_other.id,
                departure_time="08:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=1,
                train_id=t4.id,
                stop_sequence=2,
                station_id=s_ndls.id,
                arrival_time="09:00:00",
                source_day=1,
            ),
        ]
    )

    db_session.commit()


def test_api_network_outbound_transit_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/NDLS/outbound-edges/transit")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "NDLS"
    assert data["station_name"] == "New Delhi"

    edges = data["outbound_edges"]
    assert len(edges) == 2

    csb = next(e for e in edges if e["next_station_code"] == "CSB")
    assert csb["train_volume"] == 2
    assert csb["min_duration_minutes"] == 5.0
    assert csb["max_duration_minutes"] == 10.0
    assert csb["avg_duration_minutes"] == 7.5

    dsb = next(e for e in edges if e["next_station_code"] == "DSB")
    assert dsb["train_volume"] == 1
    # 1440 + 17 - 10 = 1447
    assert dsb["min_duration_minutes"] == 1447.0


def test_api_network_outbound_transit_empty(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/OTHER/outbound-edges/transit")
    assert response.status_code == 200
    data = response.json()
    assert len(data["outbound_edges"]) == 1  # OTHER -> NDLS

    # CSB has no outbound edges
    response = client.get("/api/v1/network/stations/CSB/outbound-edges/transit")
    assert response.status_code == 200
    assert len(response.json()["outbound_edges"]) == 0


def test_api_network_outbound_transit_unknown_station(
    client: TestClient, db_session: Session
) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/XXX/outbound-edges/transit")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_api_network_outbound_transit_isolation(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    db_session.execute(DatasetSnapshot.__table__.update().values(status="ARCHIVED"))
    db_session.commit()

    response = client.get("/api/v1/network/stations/NDLS/outbound-edges/transit")
    assert response.status_code == 503
