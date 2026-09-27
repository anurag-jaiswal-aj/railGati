from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
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

    t1 = Train(number="12301")
    t2 = Train(number="12302")
    t3 = Train(number="0001") # no paired train
    t4 = Train(number="0002") # paired train not in snapshot
    t5 = Train(number="0003") # incomplete timing data
    db_session.add_all([t1, t2, t3, t4, t5])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1", return_train_number="12302"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2", return_train_number="12301"),
            TrainObservation(snapshot_id=1, train_id=t3.id, name="T3", return_train_number=None),
            TrainObservation(snapshot_id=1, train_id=t4.id, name="T4", return_train_number="99999"),
            TrainObservation(snapshot_id=1, train_id=t5.id, name="T5", return_train_number="12302"),
        ]
    )

    # T1: 1020 mins (A->B)
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s1.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s2.id, arrival_time="03:00:00", source_day=2),
        ]
    )
    
    # T2: 1015 mins (B->A)
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s2.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s1.id, arrival_time="02:55:00", source_day=2),
        ]
    )

    # T4: 60 mins (A->B)
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t4.id, stop_sequence=1, station_id=s1.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t4.id, stop_sequence=2, station_id=s2.id, arrival_time="11:00:00", source_day=1),
        ]
    )

    # T5: Incomplete timing data
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t5.id, stop_sequence=1, station_id=s1.id, departure_time=None, source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t5.id, stop_sequence=2, station_id=s2.id, arrival_time="11:00:00", source_day=1),
        ]
    )

    db_session.commit()


def test_api_network_paired_symmetry_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/12301/paired-symmetry")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "12301"
    assert data["return_train_number"] == "12302"
    assert data["forward_train_duration_minutes"] == 1020.0
    assert data["return_train_duration_minutes"] == 1015.0
    assert data["duration_asymmetry_minutes"] == 5.0

def test_api_network_paired_symmetry_unknown_train(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/XXX/paired-symmetry")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_api_network_paired_symmetry_no_paired_service(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/0001/paired-symmetry")
    assert response.status_code == 404
    assert "no paired service found" in response.json()["detail"].lower()

def test_api_network_paired_symmetry_paired_not_in_snapshot(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/0002/paired-symmetry")
    assert response.status_code == 404
    assert "not present" in response.json()["detail"].lower()

def test_api_network_paired_symmetry_incomplete_timing(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/0003/paired-symmetry")
    assert response.status_code == 404
    assert "incomplete timing data" in response.json()["detail"].lower()

def test_api_network_paired_symmetry_isolation(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    db_session.execute(DatasetSnapshot.__table__.update().values(status="ARCHIVED"))
    db_session.commit()
    
    response = client.get("/api/v1/network/trains/12301/paired-symmetry")
    assert response.status_code == 503
