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
    s_dest = Station(code="DST")
    s_other = Station(code="OTH")
    db_session.add_all([s_orig, s_dest, s_other])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_orig.id, name="Origin"),
            StationObservation(snapshot_id=1, station_id=s_dest.id, name="Dest"),
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

    # 1. 09:00 train ORG -> DST
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s_orig.id, departure_time="09:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s_dest.id, arrival_time="10:00:00", source_day=1),
        ]
    )
    
    # 2. 09:30 train ORG -> DST
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s_orig.id, departure_time="09:30:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s_dest.id, arrival_time="10:30:00", source_day=1),
        ]
    )

    # 3. 23:45 train ORG -> DST (wraparound)
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=1, station_id=s_orig.id, departure_time="23:45:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=2, station_id=s_dest.id, arrival_time="01:00:00", source_day=2),
        ]
    )

    # 4. 00:15 train ORG -> DST (wraparound interaction with 23:45)
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t4.id, stop_sequence=1, station_id=s_orig.id, departure_time="00:15:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t4.id, stop_sequence=2, station_id=s_dest.id, arrival_time="02:00:00", source_day=1),
        ]
    )

    db_session.commit()


def test_api_network_bunching_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/edges/ORG/DST/temporal-bunching")
    assert response.status_code == 200
    data = response.json()
    
    assert data["origin_station_code"] == "ORG"
    assert data["destination_station_code"] == "DST"
    assert data["total_edge_volume"] == 4
    # The windows:
    # 09:00 -> includes 09:00, 09:30 (count 2)
    # 09:30 -> includes 09:30 (count 1)
    # 23:45 -> includes 23:45, 00:15 (count 2) because (00:15 + 1440) = 1455 < 1425 + 60
    # 00:15 -> includes 00:15 (count 1)
    # Max count should be 2.
    assert data["peak_60min_trains"] == 2

def test_api_network_bunching_no_edge(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/edges/DST/ORG/temporal-bunching")
    assert response.status_code == 404
    assert "no qualifying adjacent" in response.json()["detail"].lower()

def test_api_network_bunching_unknown_station(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/edges/ORG/XXX/temporal-bunching")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_api_network_bunching_same_station(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/edges/ORG/ORG/temporal-bunching")
    assert response.status_code == 400
    assert "cannot be the same station" in response.json()["detail"].lower()

def test_api_network_bunching_isolation(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    db_session.execute(DatasetSnapshot.__table__.update().values(status="ARCHIVED"))
    db_session.commit()
    
    response = client.get("/api/v1/network/edges/ORG/DST/temporal-bunching")
    assert response.status_code == 503
