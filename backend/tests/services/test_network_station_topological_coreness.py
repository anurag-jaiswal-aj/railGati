from sqlalchemy.orm import Session

from railgati.models.graph import (
    RailwayGraphBuild,
)
from railgati.models.station import Station


def _setup_graph(db_session: Session, edges: list[tuple[str, str]]) -> int:
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

    # We populate TrainStopObservation
    stops = []

    # A->B->C is a train route. If we have [("A", "B"), ("B", "C")],
    # we can just create one train route A->B->C.
    # To keep it generic for edges, we can create a separate train for each edge!
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


def test_coreness_simple_chain(db_session: Session) -> None:
    # A-B-C-D
    _setup_graph(db_session, [("A", "B"), ("B", "C"), ("C", "D")])

    from railgati.services.network import get_station_topological_coreness

    res_a = get_station_topological_coreness(db_session, "A")
    assert res_a is not None
    assert res_a["coreness"] == 1
    assert res_a["degree"] == 1

    res_b = get_station_topological_coreness(db_session, "B")
    assert res_b is not None
    assert res_b["coreness"] == 1
    assert res_b["degree"] == 2


def test_coreness_triangle(db_session: Session) -> None:
    # A-B-C-A
    _setup_graph(db_session, [("A", "B"), ("B", "C"), ("C", "A")])

    from railgati.services.network import get_station_topological_coreness

    for s in ["A", "B", "C"]:
        res = get_station_topological_coreness(db_session, s)
        assert res is not None
        assert res["coreness"] == 2
        assert res["degree"] == 2


def test_coreness_triangle_with_leaf(db_session: Session) -> None:
    # A-B-C-A, C-D
    _setup_graph(db_session, [("A", "B"), ("B", "C"), ("C", "A"), ("C", "D")])

    from railgati.services.network import get_station_topological_coreness

    res_a = get_station_topological_coreness(db_session, "A")
    assert res_a is not None
    assert res_a["coreness"] == 2

    res_c = get_station_topological_coreness(db_session, "C")
    assert res_c is not None
    assert res_c["coreness"] == 2
    assert res_c["degree"] == 3

    res_d = get_station_topological_coreness(db_session, "D")
    assert res_d is not None
    assert res_d["coreness"] == 1
    assert res_d["degree"] == 1


def test_coreness_dense_core(db_session: Session) -> None:
    # K4: A,B,C,D fully connected
    edges = [("A", "B"), ("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"), ("C", "D")]
    _setup_graph(db_session, edges)

    from railgati.services.network import get_station_topological_coreness

    for s in ["A", "B", "C", "D"]:
        res = get_station_topological_coreness(db_session, s)
        assert res is not None
        assert res["coreness"] == 3
        assert res["degree"] == 3


def test_coreness_isolated_station(db_session: Session) -> None:
    # Just one edge A-B and C isolated
    _setup_graph(db_session, [("A", "B")])
    db_session.add(Station(code="C"))
    db_session.commit()

    # We must insert C to coreness as degree 0?
    # Wait, graph_builder iterates over network_edges. If C has no edges, it's not in vertices.
    # Therefore, coreness row will NOT be generated for C.
    from railgati.services.network import get_station_topological_coreness

    res = get_station_topological_coreness(db_session, "C")
    assert res is None


def test_coreness_self_loop(db_session: Session) -> None:
    # A-B, A-A
    _setup_graph(db_session, [("A", "B"), ("A", "A")])

    from railgati.services.network import get_station_topological_coreness

    # The self loop is discarded. So degree is 1.
    res_a = get_station_topological_coreness(db_session, "A")
    assert res_a is not None
    assert res_a["coreness"] == 1
    assert res_a["degree"] == 1
