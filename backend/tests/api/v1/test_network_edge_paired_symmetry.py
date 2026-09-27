import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation

@pytest.fixture
def setup_api_data(db_session: Session) -> None:
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.flush()

    snapshot = DatasetSnapshot(id=2, source_id=1, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    stations = []
    for code in ["MGS", "JEP", "GOGH", "GBY", "NDLS", "CNB"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}
    
    for s in stations:
        db_session.add(StationObservation(snapshot_id=2, station_id=s.id, name=f"{s.code} Name"))
    db_session.flush()

    trains = []
    for num in ["F1", "R1", "F3", "R3", "F5"]:
        t = Train(number=num)
        db_session.add(t)
        trains.append(t)
    db_session.flush()
    t_map = {t.number: t.id for t in trains}

    def add_train(train_num: str, return_num: str, stops: list[str]) -> None:
        db_session.add(TrainObservation(snapshot_id=2, train_id=t_map[train_num], name=f"{train_num} Name", type="EXP", return_train_number=return_num))
        db_session.flush()
        seq = 1
        for code in stops:
            db_session.execute(
                text("INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence) VALUES (2, :t, :s, :seq)"),
                {"t": t_map[train_num], "s": s_map[code], "seq": seq}
            )
            seq += 1

    add_train("F1", "R1", ["MGS", "JEP"])
    add_train("R1", "F1", ["JEP", "MGS"])
    add_train("F3", "R3", ["GOGH", "GBY"])
    add_train("F5", None, ["NDLS", "JEP", "CNB"])
    db_session.flush()


def test_api_edge_paired_route_symmetry_normal(client: TestClient, setup_api_data):
    response = client.get("/api/v1/network/edges/MGS/JEP/paired-symmetry")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "MGS"
    assert data["to_station_code"] == "JEP"
    assert data["total_forward_trains"] == 1
    assert data["symmetrical_return_trains"] == 1
    assert data["symmetry_ratio"] == 1.0


def test_api_edge_paired_route_symmetry_zero_reciprocal(client: TestClient, setup_api_data):
    response = client.get("/api/v1/network/edges/GOGH/GBY/paired-symmetry")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "GOGH"
    assert data["to_station_code"] == "GBY"
    assert data["total_forward_trains"] == 1
    assert data["symmetrical_return_trains"] == 0
    assert data["symmetry_ratio"] == 0.0


def test_api_edge_paired_route_symmetry_zero_forward(client: TestClient, setup_api_data):
    response = client.get("/api/v1/network/edges/NDLS/CNB/paired-symmetry")
    assert response.status_code == 400
    assert "No qualifying forward" in response.json()["detail"]


def test_api_edge_paired_route_symmetry_unknown_station(client: TestClient, setup_api_data):
    response = client.get("/api/v1/network/edges/FAKE/MGS/paired-symmetry")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_api_edge_paired_route_symmetry_no_snapshot(client: TestClient, db_session: Session, setup_api_data):
    db_session.execute(text("UPDATE dataset_snapshots SET status = 'OBSOLETE'"))
    db_session.flush()
    response = client.get("/api/v1/network/edges/MGS/JEP/paired-symmetry")
    assert response.status_code == 503
    assert "no active snapshot found" in response.json()["detail"].lower()
