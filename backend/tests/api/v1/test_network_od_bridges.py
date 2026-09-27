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
    s_dest = Station(code="DST")
    s_other = Station(code="OTH")
    db_session.add_all([s_orig, s_mid1, s_dest, s_other])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_orig.id, name="Origin"),
            StationObservation(snapshot_id=1, station_id=s_mid1.id, name="Mid 1"),
            StationObservation(snapshot_id=1, station_id=s_dest.id, name="Dest"),
            StationObservation(snapshot_id=1, station_id=s_other.id, name="Other"),
        ]
    )

    t1 = Train(number="12345")
    t2 = Train(number="12346")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
        ]
    )

    # Train 1: ORG -> MD1 -> DST
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s_orig.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s_mid1.id, arrival_time="11:00:00", departure_time="11:10:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s_dest.id, arrival_time="12:00:00", source_day=1),
        ]
    )
    
    # Train 2: OTH -> MD1 -> DST
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s_other.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s_mid1.id, arrival_time="11:00:00", departure_time="11:10:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=3, station_id=s_dest.id, arrival_time="12:00:00", source_day=1),
        ]
    )

    db_session.commit()


def test_api_network_od_bridges_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/MD1/od-bridges")
    assert response.status_code == 200
    data = response.json()
    
    assert data["station_code"] == "MD1"
    assert data["unique_origins_count"] == 2 # ORG, OTH
    assert data["unique_destinations_count"] == 1 # DST
    assert data["unique_od_pairs_count"] == 2
    
    pairs = data["top_od_pairs"]
    assert len(pairs) == 2
    assert pairs[0]["origin_station_code"] in ["ORG", "OTH"]
    assert pairs[0]["train_volume"] == 1

def test_api_network_od_bridges_unknown_station(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/XXX/od-bridges")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_api_network_od_bridges_isolation(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    db_session.execute(DatasetSnapshot.__table__.update().values(status="ARCHIVED"))
    db_session.commit()
    
    response = client.get("/api/v1/network/stations/MD1/od-bridges")
    assert response.status_code == 503
