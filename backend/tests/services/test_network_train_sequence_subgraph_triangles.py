import typing
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.graph import RailwayNetworkEdge
from railgati.services.network import calculate_train_sequence_subgraph_triangles

@pytest.fixture
def setup_subgraph_triangles_data(db_session: Session) -> typing.Any:
    # Clear tables
    db_session.execute(text("DELETE FROM railway_network_edges"))
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.execute(text("DELETE FROM data_sources"))
    db_session.flush()

    source = DataSource(name="test", url="http", publisher="pub", license="MIT")
    db_session.add(source)
    db_session.flush()

    snap = DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()

    stations = {}
    for c in ["A", "B", "C", "D", "E", "F", "Z", "S1", "S2"]:
        st = Station(code=c)
        db_session.add(st)
        stations[c] = st
    db_session.flush()

    def add_edge(u: str, v: str, snap_id: int = 2):
        s_u = stations[u].id
        s_v = stations[v].id
        e = RailwayNetworkEdge(
            timetable_snapshot_id=snap_id,
            from_station_id=min(s_u, s_v),
            to_station_id=max(s_u, s_v),
            train_count=1,
            min_duration_minutes=10,
        )
        db_session.add(e)

    # 1. Linear route edges (Train 1: A-B-C-D)
    add_edge("A", "B")
    add_edge("B", "C")
    add_edge("C", "D")

    # 2. Chorded triangle (Train 2: B-C-D)
    # Already have B-C, C-D. Let's add B-D.
    add_edge("B", "D")

    # 3. External third vertex (Train 3: E-F)
    # E-F, E-Z, F-Z. Z is outside Train 3's route.
    add_edge("E", "F")
    add_edge("E", "Z")
    add_edge("F", "Z")

    # 7. Self-loop (Train 4: S1-S2)
    add_edge("S1", "S2")
    db_session.add(
        RailwayNetworkEdge(
            timetable_snapshot_id=2,
            from_station_id=stations["S1"].id,
            to_station_id=stations["S1"].id,
            train_count=1,
            min_duration_minutes=10,
        )
    )

    # 9. Snapshot isolation edge
    # Let's add A-C to snapshot 99
    add_edge("A", "C", snap_id=99)

    db_session.flush()

    def create_train(num: str, route: list[str]):
        t = Train(number=num)
        db_session.add(t)
        db_session.flush()
        db_session.add(TrainObservation(train_id=t.id, snapshot_id=2, name=num))
        for seq, code in enumerate(route, 1):
            db_session.add(TrainStopObservation(
                train_id=t.id, snapshot_id=2, station_id=stations[code].id, stop_sequence=seq
            ))
        return t

    create_train("T1", ["A", "B", "C", "D"])
    create_train("T2", ["B", "C", "D"])
    create_train("T3", ["E", "F"])
    create_train("T4", ["S1", "S2"])
    create_train("T5", ["B", "C", "D", "B"]) # Repeated visit
    create_train("T_SHORT", ["A"])
    
    # Train 6: Multiple triangles. Route: A, B, C, D. Edges: A-B, B-C, C-D, B-D (Triangle B-C-D).
    # Add A-C to snapshot 2 to make A-B-C a triangle.
    add_edge("A", "C", snap_id=2)
    db_session.flush()

    create_train("T6", ["A", "B", "C", "D"])

    db_session.commit()
    return snap.id

def test_linear_route(db_session: Session, setup_subgraph_triangles_data: int) -> None:
    # Before we added A-C to snap 2 for T6, T1 was linear. Now T1 is the same as T6.
    # Let's check T_SHORT for < 3 stations
    res = calculate_train_sequence_subgraph_triangles(db_session, setup_subgraph_triangles_data, "T_SHORT")
    assert res["subgraph_triangles"] == 0
    assert res["route_length"] == 1

def test_chorded_triangle(db_session: Session, setup_subgraph_triangles_data: int) -> None:
    # T2 has B, C, D. Edges B-C, C-D, B-D. Triangle = 1.
    res = calculate_train_sequence_subgraph_triangles(db_session, setup_subgraph_triangles_data, "T2")
    assert res["subgraph_triangles"] == 1
    assert res["route_length"] == 3

def test_external_third_vertex(db_session: Session, setup_subgraph_triangles_data: int) -> None:
    # T3 has E, F. Edges E-F, E-Z, F-Z. Z is not in T3. Triangles = 0.
    res = calculate_train_sequence_subgraph_triangles(db_session, setup_subgraph_triangles_data, "T3")
    assert res["subgraph_triangles"] == 0
    assert res["route_length"] == 2

def test_multiple_triangles(db_session: Session, setup_subgraph_triangles_data: int) -> None:
    # T6 has A, B, C, D. Triangles: A-B-C and B-C-D. Total = 2.
    res = calculate_train_sequence_subgraph_triangles(db_session, setup_subgraph_triangles_data, "T6")
    assert res["subgraph_triangles"] == 2
    assert res["route_length"] == 4

def test_repeated_station(db_session: Session, setup_subgraph_triangles_data: int) -> None:
    # T5 has B, C, D, B. Route length is 3 (distinct). Triangles = 1.
    res = calculate_train_sequence_subgraph_triangles(db_session, setup_subgraph_triangles_data, "T5")
    assert res["subgraph_triangles"] == 1
    assert res["route_length"] == 3

def test_self_loop_ignored(db_session: Session, setup_subgraph_triangles_data: int) -> None:
    # T4 has S1, S2. Self loop S1-S1 exists. Triangles = 0.
    res = calculate_train_sequence_subgraph_triangles(db_session, setup_subgraph_triangles_data, "T4")
    assert res["subgraph_triangles"] == 0

def test_unknown_train(db_session: Session, setup_subgraph_triangles_data: int) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_sequence_subgraph_triangles(db_session, setup_subgraph_triangles_data, "UNKNOWN")
