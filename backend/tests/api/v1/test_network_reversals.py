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

    s_vskp = Station(code="VSKP")
    s_mipm = Station(code="MIPM")
    s_other = Station(code="OTHER")
    db_session.add_all([s_vskp, s_mipm, s_other])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_vskp.id, name="Visakhapatnam"),
            StationObservation(snapshot_id=1, station_id=s_mipm.id, name="Marripalem"),
            StationObservation(snapshot_id=1, station_id=s_other.id, name="Other"),
        ]
    )

    t_rev = Train(number="11019")
    t_straight = Train(number="12000")
    t_terminal = Train(number="13000")
    db_session.add_all([t_rev, t_straight, t_terminal])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t_rev.id, name="Rev"),
            TrainObservation(snapshot_id=1, train_id=t_straight.id, name="Straight"),
            TrainObservation(snapshot_id=1, train_id=t_terminal.id, name="Term"),
        ]
    )

    # Reversal: MIPM -> VSKP -> MIPM
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t_rev.id, stop_sequence=1, station_id=s_other.id),
            TrainStopObservation(snapshot_id=1, train_id=t_rev.id, stop_sequence=2, station_id=s_mipm.id),
            TrainStopObservation(snapshot_id=1, train_id=t_rev.id, stop_sequence=3, station_id=s_vskp.id, arrival_time="20:55:00", departure_time="21:15:00"),
            TrainStopObservation(snapshot_id=1, train_id=t_rev.id, stop_sequence=4, station_id=s_mipm.id),
            TrainStopObservation(snapshot_id=1, train_id=t_rev.id, stop_sequence=5, station_id=s_other.id),
        ]
    )

    # Straight: MIPM -> VSKP -> OTHER
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t_straight.id, stop_sequence=1, station_id=s_mipm.id),
            TrainStopObservation(snapshot_id=1, train_id=t_straight.id, stop_sequence=2, station_id=s_vskp.id, arrival_time="10:00:00", departure_time="10:10:00"),
            TrainStopObservation(snapshot_id=1, train_id=t_straight.id, stop_sequence=3, station_id=s_other.id),
        ]
    )
    
    # Terminal: OTHER -> VSKP (no next stop)
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t_terminal.id, stop_sequence=1, station_id=s_other.id),
            TrainStopObservation(snapshot_id=1, train_id=t_terminal.id, stop_sequence=2, station_id=s_vskp.id, arrival_time="12:00:00"),
        ]
    )

    db_session.commit()


def test_api_network_reversals_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/VSKP/reversals")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "VSKP"
    assert data["reversal_count"] == 1
    
    p1 = data["reversing_trains"][0]
    assert p1["train_number"] == "11019"
    assert p1["adjoining_station_code"] == "MIPM"
    assert p1["arrival_time"] == "20:55:00"
    assert p1["departure_time"] == "21:15:00"

def test_api_network_reversals_empty(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    # OTHER station has straight-through and terminal but no reversals
    response = client.get("/api/v1/network/stations/OTHER/reversals")
    assert response.status_code == 200
    data = response.json()
    assert data["reversal_count"] == 0
    assert data["reversing_trains"] == []

def test_api_network_reversals_unknown_station(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/XXX/reversals")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_api_network_reversals_isolation(client: TestClient, db_session: Session) -> None:
    # Set inactive
    setup_data(db_session)
    db_session.execute(DatasetSnapshot.__table__.update().values(status="ARCHIVED"))
    db_session.commit()
    
    response = client.get("/api/v1/network/stations/VSKP/reversals")
    assert response.status_code == 503
