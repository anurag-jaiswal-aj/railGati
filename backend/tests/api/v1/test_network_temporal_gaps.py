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

    s1 = Station(code="STA")
    s_empty = Station(code="MTY")
    s_single = Station(code="SGL")
    db_session.add_all([s1, s_empty, s_single])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s1.id, name="Station 1"),
            StationObservation(snapshot_id=1, station_id=s_empty.id, name="Empty"),
            StationObservation(snapshot_id=1, station_id=s_single.id, name="Single"),
        ]
    )

    t1 = Train(number="12345")
    t2 = Train(number="12346")
    t3 = Train(number="12347")
    db_session.add_all([t1, t2, t3])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
            TrainObservation(snapshot_id=1, train_id=t3.id, name="T3"),
        ]
    )

    # STA gets three departures: 10:00, 11:30, 23:30
    # Gaps:
    # 10:00 to 11:30 = 90 mins
    # 11:30 to 23:30 = 720 mins
    # 23:30 to 10:00 (+1 day) = 30 mins to midnight + 600 mins = 630 mins
    # Sum: 1440, Total departures: 3. Avg: 480. Max: 720
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s1.id, departure_time="11:30:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=1, station_id=s1.id, arrival_time="23:25:00", departure_time="23:30:00", source_day=1),
            
            # Null departure (terminating)
            TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=2, station_id=s1.id, arrival_time="23:45:00", departure_time=None, source_day=1),
            
            # SGL gets one departure
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s_single.id, departure_time="12:00:00", source_day=1),
        ]
    )

    db_session.commit()


def test_api_network_temporal_gaps_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/STA/temporal-gaps")
    assert response.status_code == 200
    data = response.json()
    
    assert data["station_code"] == "STA"
    assert data["total_departures"] == 3
    assert data["max_departure_gap_minutes"] == 720.0
    assert data["average_departure_gap_minutes"] == 480.0

def test_api_network_temporal_gaps_single_departure(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/SGL/temporal-gaps")
    assert response.status_code == 200
    data = response.json()
    
    assert data["station_code"] == "SGL"
    assert data["total_departures"] == 1
    assert data["max_departure_gap_minutes"] == 1440.0

def test_api_network_temporal_gaps_no_departures(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/MTY/temporal-gaps")
    assert response.status_code == 404
    assert "no qualifying departures" in response.json()["detail"].lower()

def test_api_network_temporal_gaps_unknown_station(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/XXX/temporal-gaps")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_api_network_temporal_gaps_isolation(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    db_session.execute(DatasetSnapshot.__table__.update().values(status="ARCHIVED"))
    db_session.commit()
    
    response = client.get("/api/v1/network/stations/STA/temporal-gaps")
    assert response.status_code == 503
