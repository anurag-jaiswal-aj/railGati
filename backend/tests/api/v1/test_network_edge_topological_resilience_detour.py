import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.graph_builder import build_graph_for_timetable_snapshot

@pytest.fixture
def test_data(db_session: Session) -> dict:
    source = DataSource(name="test_source", url="http://test", publisher="Test", license="Test")
    db_session.add(source)
    db_session.commit()

    snapshot = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    db_session.commit()
    
    stations = {
        code: Station(code=code) for code in ["A", "B", "C"]
    }
    db_session.add_all(stations.values())
    db_session.commit()

    for code, st in stations.items():
        db_session.add(StationObservation(station_id=st.id, snapshot_id=snapshot.id, name=f"St {code}"))
    db_session.commit()

    return {"snapshot": snapshot, "stations": stations}

def create_train(db_session: Session, snapshot_id: int, train_num: str, stops: list[str], stations: dict) -> Train:
    tr = Train(number=train_num)
    db_session.add(tr)
    db_session.commit()
    
    db_session.add(TrainObservation(train_id=tr.id, snapshot_id=snapshot_id, name=train_num))
    db_session.commit()
    
    for i, code in enumerate(stops, 1):
        db_session.add(
            TrainStopObservation(
                train_id=tr.id,
                snapshot_id=snapshot_id,
                station_id=stations[code].id,
                stop_sequence=i,
            )
        )
    db_session.commit()
    return tr

def test_api_bridge(client: TestClient, db_session: Session, test_data: dict):
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)

    resp = client.get("/api/v1/network/edges/A/B/topological-resilience-detour")
    assert resp.status_code == 200
    data = resp.json()
    assert data["from_station_code"] == "A"
    assert data["to_station_code"] == "B"
    assert data["detour_distance"] is None
    assert data["is_structural_bridge"] is True

def test_api_triangle(client: TestClient, db_session: Session, test_data: dict):
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T2", ["B", "C"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T3", ["A", "C"], test_data["stations"])
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)

    resp = client.get("/api/v1/network/edges/A/B/topological-resilience-detour")
    assert resp.status_code == 200
    data = resp.json()
    assert data["detour_distance"] == 2
    assert data["is_structural_bridge"] is False

def test_api_not_found(client: TestClient, db_session: Session, test_data: dict):
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)

    resp = client.get("/api/v1/network/edges/A/C/topological-resilience-detour")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()

def test_api_self_loop(client: TestClient, db_session: Session, test_data: dict):
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)

    resp = client.get("/api/v1/network/edges/A/A/topological-resilience-detour")
    assert resp.status_code == 400
    assert "self-loops" in resp.json()["detail"].lower()
