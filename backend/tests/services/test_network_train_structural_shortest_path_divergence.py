import typing
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_structural_shortest_path_divergence

@pytest.fixture
def mock_divergence_data(db_session: Session) -> typing.Any:
    db_session.execute(text("DELETE FROM railway_network_edges"))
    db_session.execute(text("DELETE FROM railway_graph_builds"))
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.execute(text("DELETE FROM data_sources"))
    db_session.commit()

    source = DataSource(name="Src", publisher="pub", url="url", license="mit")
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    db_session.add(RailwayGraphBuild(timetable_snapshot_id=snap_id, status="ACTIVE"))
    db_session.commit()

    stn_codes = ["A", "B", "C", "X", "Y", "D", "E"]
    stations = {}
    for code in stn_codes:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()

    def add_train(number: str, route: list[str]):
        t = Train(number=number)
        db_session.add(t)
        db_session.commit()
        db_session.add(TrainObservation(snapshot_id=snap_id, train_id=t.id, name=number, type="EXP"))
        for idx, code in enumerate(route):
            db_session.add(TrainStopObservation(
                snapshot_id=snap_id, train_id=t.id, station_id=stations[code].id, stop_sequence=idx+1
            ))
        db_session.commit()
        return t

    # Train 1: Direct adjacent A -> B
    add_train("T_DIRECT", ["A", "B"])
    
    # Train 2: Multi-hop actual == shortest: A -> B -> C
    add_train("T_MULTI", ["A", "B", "C"])
    
    # Train 3: Detour A -> X -> Y -> B (but A->B exists)
    add_train("T_DETOUR", ["A", "X", "Y", "B"])
    
    # Train 4: Cyclic A -> B -> C -> B -> D (shortest A->D is 1 hop)
    add_train("T_CYCLIC", ["A", "B", "C", "B", "D"])
    
    # Train 5: One stop
    add_train("T_ONE", ["E"])

    # Train 6: Unreachable
    add_train("T_UNREACHABLE", ["X", "C"])

    edges = [
        ("A", "B"), ("B", "C"), # for T_DIRECT and T_MULTI
        ("A", "X"), ("X", "Y"), ("Y", "B"), # for T_DETOUR
        ("C", "B"), ("B", "D"), ("A", "D")  # for T_CYCLIC (plus A->B and B->C from above)
    ]

    for u, v in edges:
        db_session.add(RailwayNetworkEdge(
            timetable_snapshot_id=snap_id,
            from_station_id=stations[u].id,
            to_station_id=stations[v].id,
            train_count=1
        ))
    db_session.commit()

    return {"snapshot_id": snap_id}


def oracle_bfs(db: Session, snap_id: int, start_id: int, end_id: int, max_edges: int) -> int | None:
    if start_id == end_id:
        return 0
    from sqlalchemy import select
    
    # Preload the graph for the snapshot
    edges = db.execute(select(RailwayNetworkEdge.from_station_id, RailwayNetworkEdge.to_station_id).filter_by(timetable_snapshot_id=snap_id)).fetchall()
    adj: dict[int, set[int]] = {}
    for u, v in edges:
        adj.setdefault(u, set()).add(v)
        adj.setdefault(v, set()).add(u)
        
    visited = {start_id}
    q = [start_id]
    depth = 0
    
    while q and depth <= max_edges:
        if end_id in q:
            return depth
        next_q = set()
        for node in q:
            for nxt in adj.get(node, []):
                if nxt not in visited:
                    visited.add(nxt)
                    next_q.add(nxt)
        q = list(next_q)
        depth += 1
    return None

def test_divergence_direct(db_session: Session, mock_divergence_data):
    res = calculate_train_structural_shortest_path_divergence(
        db_session, mock_divergence_data["snapshot_id"], "T_DIRECT"
    )
    
    from sqlalchemy import select
    from railgati.models.train import Train, TrainStopObservation
    t_id = db_session.execute(select(Train.id).filter_by(number="T_DIRECT")).scalar()
    stops = db_session.execute(select(TrainStopObservation.station_id).filter_by(train_id=t_id).order_by(TrainStopObservation.stop_sequence)).scalars().all()
    oracle_val = oracle_bfs(db_session, mock_divergence_data["snapshot_id"], stops[0], stops[-1], len(stops)-1)
    
    assert res["actual_structural_edges"] == 1
    assert res["shortest_structural_edges"] == 1
    assert res["shortest_structural_edges"] == oracle_val
    assert res["divergence_absolute"] == 0
    assert res["divergence_ratio"] == 1.0


def test_divergence_multi(db_session: Session, mock_divergence_data):
    res = calculate_train_structural_shortest_path_divergence(
        db_session, mock_divergence_data["snapshot_id"], "T_MULTI"
    )
    
    from sqlalchemy import select
    from railgati.models.train import Train, TrainStopObservation
    t_id = db_session.execute(select(Train.id).filter_by(number="T_MULTI")).scalar()
    stops = db_session.execute(select(TrainStopObservation.station_id).filter_by(train_id=t_id).order_by(TrainStopObservation.stop_sequence)).scalars().all()
    oracle_val = oracle_bfs(db_session, mock_divergence_data["snapshot_id"], stops[0], stops[-1], len(stops)-1)

    assert res["actual_structural_edges"] == 2
    assert res["shortest_structural_edges"] == 2
    assert res["shortest_structural_edges"] == oracle_val
    assert res["divergence_absolute"] == 0
    assert res["divergence_ratio"] == 1.0


def test_divergence_detour(db_session: Session, mock_divergence_data):
    res = calculate_train_structural_shortest_path_divergence(
        db_session, mock_divergence_data["snapshot_id"], "T_DETOUR"
    )
    
    from sqlalchemy import select
    from railgati.models.train import Train, TrainStopObservation
    t_id = db_session.execute(select(Train.id).filter_by(number="T_DETOUR")).scalar()
    stops = db_session.execute(select(TrainStopObservation.station_id).filter_by(train_id=t_id).order_by(TrainStopObservation.stop_sequence)).scalars().all()
    oracle_val = oracle_bfs(db_session, mock_divergence_data["snapshot_id"], stops[0], stops[-1], len(stops)-1)

    assert res["actual_structural_edges"] == 3
    # A->B exists directly
    assert res["shortest_structural_edges"] == 1
    assert res["shortest_structural_edges"] == oracle_val
    assert res["divergence_absolute"] == 2
    assert res["divergence_ratio"] == 3.0


def test_divergence_cyclic(db_session: Session, mock_divergence_data):
    res = calculate_train_structural_shortest_path_divergence(
        db_session, mock_divergence_data["snapshot_id"], "T_CYCLIC"
    )
    
    from sqlalchemy import select
    from railgati.models.train import Train, TrainStopObservation
    t_id = db_session.execute(select(Train.id).filter_by(number="T_CYCLIC")).scalar()
    stops = db_session.execute(select(TrainStopObservation.station_id).filter_by(train_id=t_id).order_by(TrainStopObservation.stop_sequence)).scalars().all()
    oracle_val = oracle_bfs(db_session, mock_divergence_data["snapshot_id"], stops[0], stops[-1], len(stops)-1)

    assert res["actual_structural_edges"] == 4
    # A->D exists directly
    assert res["shortest_structural_edges"] == 1
    assert res["shortest_structural_edges"] == oracle_val
    assert res["divergence_absolute"] == 3
    assert res["divergence_ratio"] == 4.0


def test_divergence_one_stop(db_session: Session, mock_divergence_data):
    res = calculate_train_structural_shortest_path_divergence(
        db_session, mock_divergence_data["snapshot_id"], "T_ONE"
    )
    
    from sqlalchemy import select
    from railgati.models.train import Train, TrainStopObservation
    t_id = db_session.execute(select(Train.id).filter_by(number="T_ONE")).scalar()
    stops = db_session.execute(select(TrainStopObservation.station_id).filter_by(train_id=t_id).order_by(TrainStopObservation.stop_sequence)).scalars().all()
    oracle_val = oracle_bfs(db_session, mock_divergence_data["snapshot_id"], stops[0], stops[-1], len(stops)-1)

    assert res["actual_structural_edges"] == 0
    assert res["shortest_structural_edges"] == 0
    assert res["shortest_structural_edges"] == oracle_val
    assert res["divergence_absolute"] == 0
    assert res["divergence_ratio"] is None


def test_divergence_unreachable(db_session: Session, mock_divergence_data):
    res = calculate_train_structural_shortest_path_divergence(
        db_session, mock_divergence_data["snapshot_id"], "T_UNREACHABLE"
    )
    
    from sqlalchemy import select
    from railgati.models.train import Train, TrainStopObservation
    t_id = db_session.execute(select(Train.id).filter_by(number="T_UNREACHABLE")).scalar()
    stops = db_session.execute(select(TrainStopObservation.station_id).filter_by(train_id=t_id).order_by(TrainStopObservation.stop_sequence)).scalars().all()
    oracle_val = oracle_bfs(db_session, mock_divergence_data["snapshot_id"], stops[0], stops[-1], len(stops)-1)

    assert res["actual_structural_edges"] == 1
    assert res["shortest_structural_edges"] is None
    assert res["shortest_structural_edges"] == oracle_val
    assert res["divergence_absolute"] is None
    assert res["divergence_ratio"] is None


def test_divergence_unknown(db_session: Session, mock_divergence_data):
    with pytest.raises(ValueError, match="not found"):
        calculate_train_structural_shortest_path_divergence(
            db_session, mock_divergence_data["snapshot_id"], "UNKNOWN"
        )
