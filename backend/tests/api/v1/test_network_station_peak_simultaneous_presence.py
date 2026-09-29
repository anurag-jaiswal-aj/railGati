import pytest
import typing
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from railgati.api.v1 import network
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.main import app
from railgati.db import get_db

client = TestClient(app)

def override_get_db(db_session: Session) -> None:
    def _override() -> typing.Generator[Session, None, None]:
        yield db_session
    app.dependency_overrides[get_db] = _override

def setup_data(db_session: Session) -> int:
    source = DataSource(name="test_api", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s1 = Station(code="STA")
    db_session.add_all([s1])
    db_session.flush()
    db_session.add_all([
        StationObservation(snapshot_id=1, station_id=s1.id, name="Station A"),
    ])

    t1 = Train(number="111")
    t2 = Train(number="222")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all([
        TrainObservation(snapshot_id=1, train_id=t1.id, name="T1", type="EXP"),
        TrainObservation(snapshot_id=1, train_id=t2.id, name="T2", type="EXP"),
    ])

    # t1: arr 10:00, dep 10:15
    # t2: arr 10:10, dep 10:20
    # Overlap at 10:10-10:15 => Peak 2
    db_session.add_all([
        TrainStopObservation(
            snapshot_id=1,
            train_id=t1.id,
            station_id=s1.id,
            stop_sequence=2,
            arrival_time="10:00:00",
            departure_time="10:15:00",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=1,
            train_id=t2.id,
            station_id=s1.id,
            stop_sequence=2,
            arrival_time="10:10:00",
            departure_time="10:20:00",
            source_day=1,
        ),
    ])
    db_session.commit()
    return 1

def test_api_simultaneous_presence_success(db_session: Session) -> None:
    setup_data(db_session)
    override_get_db(db_session)
    response = client.get("/api/v1/network/stations/STA/simultaneous-presence")
    print(response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "STA"
    assert data["qualifying_occurrence_count"] == 2
    assert data["peak_simultaneous_presence"] == 2

def test_api_simultaneous_presence_not_found(db_session: Session) -> None:
    setup_data(db_session)
    override_get_db(db_session)
    response = client.get("/api/v1/network/stations/XXX/simultaneous-presence")
    assert response.status_code == 404
