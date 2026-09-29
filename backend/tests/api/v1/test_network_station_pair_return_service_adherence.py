import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation


from typing import Any

@pytest.fixture
def setup_api_data(db_session: Session) -> Any:
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.flush()

    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    st_o = Station(code="O")
    st_d = Station(code="D")
    st_a = Station(code="A")
    db_session.add_all([st_o, st_d, st_a])
    db_session.commit()

    t1 = Train(number="T1")
    r1 = Train(number="R1")
    db_session.add_all([t1, r1])
    db_session.commit()

    db_session.add_all([
        StationObservation(snapshot_id=snap_id, station_id=st_o.id, name="O"),
        StationObservation(snapshot_id=snap_id, station_id=st_d.id, name="D"),
        StationObservation(snapshot_id=snap_id, station_id=st_a.id, name="A"),
        TrainObservation(snapshot_id=snap_id, train_id=t1.id, name="T1", return_train_number="R1"),
        TrainObservation(snapshot_id=snap_id, train_id=r1.id, name="R1", return_train_number="T1"),
        TrainStopObservation(snapshot_id=snap_id, train_id=t1.id, stop_sequence=1, station_id=st_o.id),
        TrainStopObservation(snapshot_id=snap_id, train_id=t1.id, stop_sequence=2, station_id=st_d.id),
        TrainStopObservation(snapshot_id=snap_id, train_id=r1.id, stop_sequence=1, station_id=st_d.id),
        TrainStopObservation(snapshot_id=snap_id, train_id=r1.id, stop_sequence=2, station_id=st_o.id)
    ])
    db_session.commit()
    return snap_id

def test_api_return_adherence_success(client: TestClient, db_session: Session, setup_api_data: Any) -> None:
    response = client.get("/api/v1/network/station-pairs/O/D/return-service-adherence")
    assert response.status_code == 200
    data = response.json()
    assert data["origin_station_code"] == "O"
    assert data["destination_station_code"] == "D"
    assert data["timetable_snapshot_id"] == setup_api_data
    assert data["total_forward_traversal_count"] == 1
    assert data["unpaired_traversal_count"] == 0
    assert data["adherent_return_traversal_count"] == 1
    assert data["non_adherent_return_traversal_count"] == 0
    assert data["adherence_ratio"] == 1.0

def test_api_return_adherence_missing_origin(client: TestClient, db_session: Session, setup_api_data: Any) -> None:
    response = client.get("/api/v1/network/station-pairs/MISSING/D/return-service-adherence")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_api_return_adherence_missing_destination(client: TestClient, db_session: Session, setup_api_data: Any) -> None:
    response = client.get("/api/v1/network/station-pairs/O/MISSING/return-service-adherence")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_api_return_adherence_same_station(client: TestClient, db_session: Session, setup_api_data: Any) -> None:
    response = client.get("/api/v1/network/station-pairs/O/o/return-service-adherence")
    assert response.status_code == 400
    assert "cannot be identical" in response.json()["detail"].lower()

def test_api_return_adherence_zero_results(client: TestClient, db_session: Session, setup_api_data: Any) -> None:
    response = client.get("/api/v1/network/station-pairs/A/O/return-service-adherence")
    assert response.status_code == 200
    data = response.json()
    assert data["total_forward_traversal_count"] == 0
    assert data["adherence_ratio"] is None
