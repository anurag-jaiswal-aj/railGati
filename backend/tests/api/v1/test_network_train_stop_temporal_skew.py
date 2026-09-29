import pytest
import typing
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.main import app
from railgati.db import get_db

client = TestClient(app)

def setup_data(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(name="test_api_p54", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s1 = Station(code="S1")
    s2 = Station(code="S2")
    s3 = Station(code="S3")
    s4 = Station(code="S4")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    db_session.add_all([
        StationObservation(snapshot_id=1, station_id=s1.id, name="S1"),
        StationObservation(snapshot_id=1, station_id=s2.id, name="S2"),
        StationObservation(snapshot_id=1, station_id=s3.id, name="S3"),
        StationObservation(snapshot_id=1, station_id=s4.id, name="S4"),
    ])

    t_front = Train(number="FRONT1")
    t_back = Train(number="BACK1")
    t_bal = Train(number="BAL1")
    t_sparse = Train(number="SPARSE")
    t_invalid = Train(number="INV1")
    db_session.add_all([t_front, t_back, t_bal, t_sparse, t_invalid])
    db_session.flush()

    db_session.add_all([
        TrainObservation(snapshot_id=1, train_id=t_front.id, name="Front"),
        TrainObservation(snapshot_id=1, train_id=t_back.id, name="Back"),
        TrainObservation(snapshot_id=1, train_id=t_bal.id, name="Bal"),
        TrainObservation(snapshot_id=1, train_id=t_sparse.id, name="Sparse"),
        TrainObservation(snapshot_id=1, train_id=t_invalid.id, name="Inv"),
    ])

    # FRONT_LOADED: Total T=10h (600m). Stop at 1h (60m) and 2h (120m). 
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t_front.id, station_id=s1.id, stop_sequence=1, arrival_time=None, departure_time="00:00:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t_front.id, station_id=s2.id, stop_sequence=2, arrival_time="00:50:00", departure_time="01:10:00", source_day=1), # mid=1h
        TrainStopObservation(snapshot_id=1, train_id=t_front.id, station_id=s3.id, stop_sequence=3, arrival_time="01:50:00", departure_time="02:10:00", source_day=1), # mid=2h
        TrainStopObservation(snapshot_id=1, train_id=t_front.id, station_id=s4.id, stop_sequence=4, arrival_time="10:00:00", departure_time=None, source_day=1),
    ])

    # BACK_LOADED: Total T=10h. Stop at 8h and 9h.
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t_back.id, station_id=s1.id, stop_sequence=1, arrival_time=None, departure_time="00:00:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t_back.id, station_id=s2.id, stop_sequence=2, arrival_time="07:50:00", departure_time="08:10:00", source_day=1), # mid=8h
        TrainStopObservation(snapshot_id=1, train_id=t_back.id, station_id=s3.id, stop_sequence=3, arrival_time="08:50:00", departure_time="09:10:00", source_day=1), # mid=9h
        TrainStopObservation(snapshot_id=1, train_id=t_back.id, station_id=s4.id, stop_sequence=4, arrival_time="10:00:00", departure_time=None, source_day=1),
    ])

    # SPARSE: Only origin and dest
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t_sparse.id, station_id=s1.id, stop_sequence=1, arrival_time=None, departure_time="00:00:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t_sparse.id, station_id=s4.id, stop_sequence=4, arrival_time="10:00:00", departure_time=None, source_day=1),
    ])
    
    # MISSING ORIGIN DEP: Invalid case
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t_invalid.id, station_id=s1.id, stop_sequence=1, arrival_time=None, departure_time=None, source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t_invalid.id, station_id=s2.id, stop_sequence=2, arrival_time="05:00:00", departure_time="05:00:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t_invalid.id, station_id=s4.id, stop_sequence=4, arrival_time="10:00:00", departure_time=None, source_day=1),
    ])
    
    db_session.commit()
    return {}

def test_api_temporal_skew_front(db_session: Session) -> None:
    setup_data(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    response = client.get("/api/v1/network/trains/FRONT1/stop-temporal-skew?snapshot_id=1")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "FRONT1"
    assert data["intermediate_stop_occurrence_count"] == 2
    assert data["classification"] == "FRONT_LOADED"
    assert data["temporal_skew"] < 0

def test_api_temporal_skew_back(db_session: Session) -> None:
    setup_data(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    response = client.get("/api/v1/network/trains/BACK1/stop-temporal-skew?snapshot_id=1")
    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "BACK_LOADED"
    assert data["temporal_skew"] > 0

def test_api_temporal_skew_sparse(db_session: Session) -> None:
    setup_data(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    response = client.get("/api/v1/network/trains/SPARSE/stop-temporal-skew?snapshot_id=1")
    assert response.status_code == 200
    data = response.json()
    assert data["intermediate_stop_occurrence_count"] == 0
    assert data["temporal_skew"] is None

def test_api_temporal_skew_invalid(db_session: Session) -> None:
    setup_data(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    response = client.get("/api/v1/network/trains/INV1/stop-temporal-skew?snapshot_id=1")
    assert response.status_code == 200
    data = response.json()
    assert data["temporal_skew"] is None

def test_api_temporal_skew_not_found(db_session: Session) -> None:
    setup_data(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    response = client.get("/api/v1/network/trains/UNKNOWN/stop-temporal-skew?snapshot_id=1")
    assert response.status_code == 404
