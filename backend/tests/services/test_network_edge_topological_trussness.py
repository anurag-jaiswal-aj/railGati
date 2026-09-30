import pytest
from sqlalchemy.orm import Session
from datetime import UTC, datetime

from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.graph import RailwayGraphBuild
from railgati.services.graph_builder import build_graph_for_timetable_snapshot
from railgati.services.network import get_edge_topological_trussness


def _setup_graph(db_session: Session, edges: list[tuple[str, str]]) -> int:
    src = DataSource(name="TEST", url="test://", publisher="test", license="test")
    db_session.add(src)
    db_session.commit()

    # 2. Snapshot
    snap = DatasetSnapshot(
        source_id=src.id,
        retrieved_at=datetime.now(UTC),
        status="ACTIVE",
    )
    db_session.add(snap)
    db_session.commit()

    st_snap = DatasetSnapshot(
        source_id=src.id,
        retrieved_at=datetime.now(UTC),
        status="ACTIVE",
    )
    db_session.add(st_snap)
    db_session.commit()

    # Stations
    stations: dict[str, Station] = {}
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


def test_trussness_simple_path(db_session: Session) -> None:
    _setup_graph(db_session, [("A", "B"), ("B", "C")])

    res_ab = get_edge_topological_trussness(db_session, "A", "B")
    assert res_ab is not None
    assert res_ab["trussness"] == 2

    res_bc = get_edge_topological_trussness(db_session, "B", "C")
    assert res_bc is not None
    assert res_bc["trussness"] == 2


def test_trussness_triangle(db_session: Session) -> None:
    _setup_graph(db_session, [("A", "B"), ("B", "C"), ("C", "A")])

    for u, v in [("A", "B"), ("B", "C"), ("C", "A")]:
        res = get_edge_topological_trussness(db_session, u, v)
        assert res is not None
        assert res["trussness"] == 3
        assert res["triangle_support"] == 1


def test_trussness_square_no_diagonal(db_session: Session) -> None:
    _setup_graph(db_session, [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")])
    for u, v in [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")]:
        res = get_edge_topological_trussness(db_session, u, v)
        assert res is not None
        assert res["trussness"] == 2
        assert res["triangle_support"] == 0


def test_trussness_two_triangles_shared_edge(db_session: Session) -> None:
    # A-B-C-A and B-C-D-B
    # Edge B-C is shared
    _setup_graph(db_session, [("A", "B"), ("B", "C"), ("C", "A"), ("B", "D"), ("C", "D")])

    res_bc = get_edge_topological_trussness(db_session, "B", "C")
    assert res_bc is not None
    # Wait, B-C has initial support 2.
    # But A-B, C-A have support 1. B-D, C-D have support 1.
    # Peeling k=3 requires support >= 1. All have support >= 1, so all survive k=3.
    # Peeling k=4 requires support >= 2. B-C has support 2, but other edges only have support 1.
    # So other edges are removed for k=4.
    # Removing them drops B-C's support to 0. So B-C is also removed for k=4!
    # Therefore ALL edges have trussness 3.
    # Let's verify standard k-truss definition: B-C is not in a 4-truss because the whole graph is not a 4-truss.
    assert res_bc["trussness"] == 3
    assert res_bc["triangle_support"] == 2

    res_ab = get_edge_topological_trussness(db_session, "A", "B")
    assert res_ab is not None
    assert res_ab["trussness"] == 3
    assert res_ab["triangle_support"] == 1


def test_trussness_k4_complete_graph(db_session: Session) -> None:
    # K4 complete graph. Every edge is in 2 triangles.
    # Because removing NO edge drops support below 2 (which is k-2 for k=4),
    # the entire K4 graph is a 4-truss.
    _setup_graph(
        db_session, [("A", "B"), ("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"), ("C", "D")]
    )

    for u, v in [("A", "B"), ("B", "C"), ("C", "D")]:
        res = get_edge_topological_trussness(db_session, u, v)
        assert res is not None
        assert res["trussness"] == 4
        assert res["triangle_support"] == 2


def test_trussness_cascading_peeling(db_session: Session) -> None:
    # Construct K4 (A,B,C,D) plus a single triangle C-D-E
    # C-D is shared.
    _setup_graph(
        db_session,
        [
            ("A", "B"),
            ("A", "C"),
            ("A", "D"),
            ("B", "C"),
            ("B", "D"),
            ("C", "D"),
            ("C", "E"),
            ("D", "E"),
        ],
    )

    # C-E and D-E have support 1. They are peeled for k=4.
    # This drops C-D's support from 3 to 2.
    # C-D still has support 2 in the K4 core! So C-D survives k=4 along with K4 edges.
    res_ce = get_edge_topological_trussness(db_session, "C", "E")
    assert res_ce is not None
    assert res_ce["trussness"] == 3

    res_cd = get_edge_topological_trussness(db_session, "C", "D")
    assert res_cd is not None
    assert res_cd["trussness"] == 4
    assert res_cd["triangle_support"] == 3


def test_trussness_canonical_symmetry(db_session: Session) -> None:
    _setup_graph(db_session, [("A", "B")])
    res1 = get_edge_topological_trussness(db_session, "A", "B")
    res2 = get_edge_topological_trussness(db_session, "B", "A")
    assert res1 is not None and res2 is not None
    assert res1["trussness"] == res2["trussness"]
    assert res1["triangle_support"] == res2["triangle_support"]


def test_trussness_self_loop(db_session: Session) -> None:
    _setup_graph(db_session, [("A", "A")])
    with pytest.raises(ValueError):
        get_edge_topological_trussness(db_session, "A", "A")


def test_trussness_missing_edge(db_session: Session) -> None:
    _setup_graph(db_session, [("A", "B")])
    db_session.add(Station(code="C"))
    db_session.commit()
    res = get_edge_topological_trussness(db_session, "A", "C")
    assert res is None
