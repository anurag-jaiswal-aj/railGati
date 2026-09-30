from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.graph import (
    RailwayGraphBuild,
)
from railgati.models.station import Station


def _setup_api_graph(db_session: Session, edges: list[tuple[str, str]]) -> int:
    from railgati.models.provenance import DatasetSnapshot, DataSource
    from railgati.models.train import Train, TrainObservation, TrainStopObservation

    source = DataSource(name="test_source", url="http://test", publisher="Test", license="Test")
    db_session.add(source)
    db_session.flush()

    snapshot = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()
    snap_id = snapshot.id

    t = Train(number="123")
    db_session.add(t)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=t.id, name="Test"))
    db_session.flush()

    stations = set()
    for u, v in edges:
        stations.add(u)
        stations.add(v)

    for s in stations:
        db_session.add(Station(code=s))
    db_session.flush()

    st_map = {s.code: s.id for s in db_session.query(Station).all()}

    build = RailwayGraphBuild(timetable_snapshot_id=snap_id, status="ACTIVE")
    db_session.add(build)
    db_session.flush()

    stops = []
    for i, (u, v) in enumerate(edges):
        t_edge = Train(number=f"T{i}")
        db_session.add(t_edge)
        db_session.flush()
        db_session.add(TrainObservation(snapshot_id=snap_id, train_id=t_edge.id, name=f"T{i}"))

        stops.append(
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t_edge.id, stop_sequence=1, station_id=st_map[u]
            )
        )
        stops.append(
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t_edge.id, stop_sequence=2, station_id=st_map[v]
            )
        )

    db_session.add_all(stops)
    db_session.flush()
    db_session.commit()

    from railgati.services.graph_builder import build_graph_for_timetable_snapshot

    build_graph_for_timetable_snapshot(db_session, snap_id)
    return snap_id


def test_api_coreness_success(client: TestClient, db_session: Session) -> None:
    _setup_api_graph(db_session, [("A", "B"), ("B", "C"), ("C", "A")])

    response = client.get("/api/v1/network/stations/A/topological-coreness")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "A"
    assert data["coreness"] == 2
    assert data["degree"] == 2


def test_api_coreness_not_found(client: TestClient, db_session: Session) -> None:
    _setup_api_graph(db_session, [("A", "B")])
    db_session.add(Station(code="X"))
    db_session.commit()

    response = client.get("/api/v1/network/stations/X/topological-coreness")
    assert response.status_code == 404
    assert "has no topological coreness" in response.json()["detail"]


def test_api_coreness_unknown_station(client: TestClient, db_session: Session) -> None:
    _setup_api_graph(db_session, [("A", "B")])

    response = client.get("/api/v1/network/stations/Y/topological-coreness")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
