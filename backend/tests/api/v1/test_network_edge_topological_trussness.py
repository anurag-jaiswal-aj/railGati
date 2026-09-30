from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from datetime import UTC, datetime

from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.services.graph_builder import build_graph_for_timetable_snapshot


@pytest.fixture
def test_graph_trussness(db_session: Session) -> int:
    src = DataSource(name="TEST", url="test://", publisher="test", license="test")
    db_session.add(src)
    db_session.commit()

    snap = DatasetSnapshot(
        source_id=src.id,
        retrieved_at=datetime.now(UTC),
        status="ACTIVE",
    )
    db_session.add(snap)

    st_snap = DatasetSnapshot(
        source_id=src.id,
        retrieved_at=datetime.now(UTC),
        status="ACTIVE",
    )
    db_session.add(st_snap)
    db_session.commit()

    edges = [("A", "B"), ("B", "C"), ("C", "A")]
    stations = {}
    for u, v in edges:
        for s in (u, v):
            if s not in stations:
                st = Station(code=s)
                db_session.add(st)
                stations[s] = st
    db_session.commit()

    for i, (u, v) in enumerate(edges):
        t = Train(number=f"T{i}")
        db_session.add(t)
        db_session.commit()

        tobs = TrainObservation(
            snapshot_id=snap.id,
            train_id=t.id,
            name=f"Train {i}",
        )
        db_session.add(tobs)
        db_session.commit()

        s1 = TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t.id,
            station_id=stations[u].id,
            stop_sequence=1,
        )
        s2 = TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t.id,
            station_id=stations[v].id,
            stop_sequence=2,
        )
        db_session.add_all([s1, s2])
    db_session.commit()

    build_graph_for_timetable_snapshot(db_session, snap.id)
    return snap.id


def test_api_trussness_success(client: TestClient, test_graph_trussness: int) -> None:
    res = client.get("/api/v1/network/edges/A/B/topological-trussness")
    assert res.status_code == 200
    data = res.json()
    assert data["from_station_code"] == "A"
    assert data["to_station_code"] == "B"
    assert data["trussness"] == 3
    assert data["triangle_support"] == 1


def test_api_trussness_symmetry(client: TestClient, test_graph_trussness: int) -> None:
    res1 = client.get("/api/v1/network/edges/A/B/topological-trussness")
    res2 = client.get("/api/v1/network/edges/B/A/topological-trussness")
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["trussness"] == res2.json()["trussness"]


def test_api_trussness_self_loop(client: TestClient, test_graph_trussness: int) -> None:
    res = client.get("/api/v1/network/edges/A/A/topological-trussness")
    assert res.status_code == 400


def test_api_trussness_not_found(client: TestClient, test_graph_trussness: int) -> None:
    res = client.get("/api/v1/network/edges/A/D/topological-trussness")
    assert res.status_code == 404
