import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.graph_builder import build_graph_for_timetable_snapshot
from railgati.services.network import get_edge_topological_biconnected_component

def _build_path(
    db_session: Session, snapshot_id: int, train: Train, station_codes: list[str]
) -> None:
    stations = []
    for code in station_codes:
        s = db_session.query(Station).filter_by(code=code).first()
        if not s:
            s = Station(code=code)
            db_session.add(s)
            db_session.flush()
        stations.append(s)

    seq_start = db_session.query(TrainStopObservation).filter_by(snapshot_id=snapshot_id, train_id=train.id).count()
    for i, s in enumerate(stations):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snapshot_id,
                train_id=train.id,
                stop_sequence=seq_start + i + 1,
                station_id=s.id,
                departure_time="10:00:00",
                source_day=1,
            )
        )
    obs = db_session.query(TrainObservation).filter_by(snapshot_id=snapshot_id, train_id=train.id).first()
    if not obs:
        db_session.add(
            TrainObservation(snapshot_id=snapshot_id, train_id=train.id, name=f"Test {train.number}")
        )
    db_session.flush()


def test_bcc_various_topologies(db_session: Session) -> None:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    snapshot = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    train_path = Train(number="100")
    train_tri = Train(number="101")
    train_square = Train(number="102")
    train_k4 = Train(number="103")
    train_tail = Train(number="104")
    train_two_cyc = Train(number="105")
    db_session.add_all([train_path, train_tri, train_square, train_k4, train_tail, train_two_cyc])
    db_session.flush()

    # 1. Simple Path: P1-P2-P3 (size 1 each)
    _build_path(db_session, snapshot.id, train_path, ["P1", "P2", "P3"])

    # 2. Triangle: T1-T2-T3-T1 (size 3)
    _build_path(db_session, snapshot.id, train_tri, ["T1", "T2", "T3", "T1"])

    # 3. Square: S1-S2-S3-S4-S1 (size 4)
    _build_path(db_session, snapshot.id, train_square, ["S1", "S2", "S3", "S4", "S1"])

    # 4. K4 / Square+Diag (size 6)
    _build_path(db_session, snapshot.id, train_k4, ["K1", "K2", "K3", "K4", "K1", "K3"])
    _build_path(db_session, snapshot.id, train_k4, ["K2", "K4"])

    # 5. Cycle with tail: C1-C2-C3-C1, C3-C4 (C3 is articulation)
    _build_path(db_session, snapshot.id, train_tail, ["C1", "C2", "C3", "C1"])
    _build_path(db_session, snapshot.id, train_tail, ["C3", "C4"])

    # 6. Two cycles sharing articulation vertex A3
    # A1-A2-A3-A1 and A3-A4-A5-A3
    _build_path(db_session, snapshot.id, train_two_cyc, ["A1", "A2", "A3", "A1"])
    _build_path(db_session, snapshot.id, train_two_cyc, ["A3", "A4", "A5", "A3"])

    db_session.commit()

    build_graph_for_timetable_snapshot(db_session, snapshot.id)

    # Validate Path
    p1 = get_edge_topological_biconnected_component(db_session, snapshot.id, "P1", "P2")
    assert p1 is not None and p1["block_edge_count"] == 1
    p2 = get_edge_topological_biconnected_component(db_session, snapshot.id, "P2", "P3")
    assert p2 is not None and p2["block_edge_count"] == 1

    # Validate Triangle
    t1 = get_edge_topological_biconnected_component(db_session, snapshot.id, "T1", "T2")
    assert t1 is not None and t1["block_edge_count"] == 3
    t2 = get_edge_topological_biconnected_component(db_session, snapshot.id, "T2", "T3")
    assert t2 is not None and t2["block_edge_count"] == 3
    t3 = get_edge_topological_biconnected_component(db_session, snapshot.id, "T3", "T1")
    assert t3 is not None and t3["block_edge_count"] == 3

    # Validate Square
    s1 = get_edge_topological_biconnected_component(db_session, snapshot.id, "S1", "S2")
    assert s1 is not None and s1["block_edge_count"] == 4
    s2 = get_edge_topological_biconnected_component(db_session, snapshot.id, "S4", "S1")
    assert s2 is not None and s2["block_edge_count"] == 4

    # Validate K4
    k1 = get_edge_topological_biconnected_component(db_session, snapshot.id, "K1", "K2")
    assert k1 is not None and k1["block_edge_count"] == 6
    k2 = get_edge_topological_biconnected_component(db_session, snapshot.id, "K1", "K3")
    assert k2 is not None and k2["block_edge_count"] == 6

    # Validate Tail
    c1 = get_edge_topological_biconnected_component(db_session, snapshot.id, "C1", "C2")
    assert c1 is not None and c1["block_edge_count"] == 3
    c2 = get_edge_topological_biconnected_component(db_session, snapshot.id, "C3", "C4")
    assert c2 is not None and c2["block_edge_count"] == 1

    # Validate Two Cycles
    a1 = get_edge_topological_biconnected_component(db_session, snapshot.id, "A1", "A2")
    assert a1 is not None and a1["block_edge_count"] == 3
    a2 = get_edge_topological_biconnected_component(db_session, snapshot.id, "A3", "A4")
    assert a2 is not None and a2["block_edge_count"] == 3


def test_bcc_self_loop(db_session: Session) -> None:
    with pytest.raises(ValueError, match="Self-loops"):
        get_edge_topological_biconnected_component(db_session, 1, "S1", "S1")


def test_bcc_no_build(db_session: Session) -> None:
    source = DataSource(name="test_source2", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    snapshot = DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    
    s1 = Station(code="N1")
    s2 = Station(code="N2")
    db_session.add_all([s1, s2])
    db_session.commit()

    with pytest.raises(ValueError, match="No ACTIVE RailwayGraphBuild"):
        get_edge_topological_biconnected_component(db_session, snapshot.id, "N1", "N2")


def test_api_bcc(client: TestClient, db_session: Session) -> None:
    source = DataSource(name="test_source3", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    snapshot = DatasetSnapshot(id=3, source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    train = Train(number="200")
    db_session.add(train)
    db_session.flush()

    _build_path(db_session, snapshot.id, train, ["API1", "API2", "API3", "API1"])
    db_session.commit()

    build_graph_for_timetable_snapshot(db_session, snapshot.id)

    response = client.get(f"/api/v1/network/edges/API1/API2/biconnected-component?timetable_snapshot_id={snapshot.id}")
    assert response.status_code == 200
    assert response.json()["block_edge_count"] == 3

    # Unknown Edge
    response = client.get(f"/api/v1/network/edges/API1/API4/biconnected-component?timetable_snapshot_id={snapshot.id}")
    assert response.status_code == 404
