import pytest
from sqlalchemy.orm import Session
from datetime import UTC, datetime

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge
from railgati.services.network import calculate_station_pair_topological_edge_connectivity

def independent_oracle_min_cut(edges: list[tuple[int, int]], source: int, target: int) -> int | None:
    if source == target:
        return None
        
    canonical_edges = {tuple(sorted([u, v])) for u, v in edges if u != v}
    if not canonical_edges:
        return 0

    import itertools
    def is_connected(removed_edges):
        from collections import defaultdict
        adj = defaultdict(list)
        nodes = set()
        for u, v in canonical_edges:
            nodes.add(u)
            nodes.add(v)
            if (u, v) in removed_edges:
                continue
            adj[u].append(v)
            adj[v].append(u)
            
        if source not in nodes or target not in nodes:
            return False
            
        visited = set()
        q = [source]
        visited.add(source)
        while q:
            curr = q.pop(0)
            if curr == target:
                return True
            for nbr in adj[curr]:
                if nbr not in visited:
                    visited.add(nbr)
                    q.append(nbr)
        return False

    for k in range(len(canonical_edges) + 1):
        for subset in itertools.combinations(canonical_edges, k):
            if not is_connected(set(subset)):
                return k
    return 0

@pytest.fixture
def test_snapshot_id(db_session: Session) -> int:
    source = DataSource(name="api_test", url="http", publisher="pub", license="MIT")
    db_session.add(source)
    db_session.flush()

    snapshot = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime.now(UTC),
        status="ACTIVE",
    )
    db_session.add(snapshot)
    db_session.flush()
    return snapshot.id

def create_network(db_session: Session, snapshot_id: int, graph_edges: list[tuple[int, int]]):
    build = RailwayGraphBuild(
        timetable_snapshot_id=snapshot_id,
        status="ACTIVE"
    )
    db_session.add(build)
    
    nodes = set()
    for u, v in graph_edges:
        nodes.add(u)
        nodes.add(v)
        
    for n in nodes:
        db_session.add(Station(id=n, code=f"ST{n}"))
    db_session.flush()

    for u, v in graph_edges:
        # Include all directions to simulate real timetables (which have bidirectional trains)
        db_session.add(RailwayNetworkEdge(timetable_snapshot_id=snapshot_id, from_station_id=u, to_station_id=v, train_count=1))
        
    from railgati.models.train import Train, TrainObservation
    t = Train(number="DUMMY")
    db_session.add(t)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=snapshot_id, train_id=t.id, name="Dummy", return_train_number=None))
    db_session.commit()

def test_disconnected_graph(db_session, test_snapshot_id):
    graph = [(1,2), (3,4)]
    create_network(db_session, test_snapshot_id, graph)
    res = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST3")
    assert res["topological_edge_connectivity"] == 0
    assert independent_oracle_min_cut(graph, 1, 3) == 0

def test_single_bridge(db_session, test_snapshot_id):
    graph = [(1,2), (2,3)]
    create_network(db_session, test_snapshot_id, graph)
    res = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST3")
    assert res["topological_edge_connectivity"] == 1
    assert independent_oracle_min_cut(graph, 1, 3) == 1

def test_simple_path(db_session, test_snapshot_id):
    graph = [(1,2)]
    create_network(db_session, test_snapshot_id, graph)
    res = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST2")
    assert res["topological_edge_connectivity"] == 1
    assert independent_oracle_min_cut(graph, 1, 2) == 1

def test_triangle(db_session, test_snapshot_id):
    graph = [(1,2), (2,3), (3,1)]
    create_network(db_session, test_snapshot_id, graph)
    res = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST2")
    assert res["topological_edge_connectivity"] == 2
    assert independent_oracle_min_cut(graph, 1, 2) == 2

def test_two_edge_disjoint_paths(db_session, test_snapshot_id):
    # Diamond
    graph = [(1,2), (2,4), (1,3), (3,4)]
    create_network(db_session, test_snapshot_id, graph)
    res = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST4")
    assert res["topological_edge_connectivity"] == 2
    assert independent_oracle_min_cut(graph, 1, 4) == 2

def test_three_edge_disjoint_paths(db_session, test_snapshot_id):
    graph = [(1,2), (2,5), (1,3), (3,5), (1,4), (4,5)]
    create_network(db_session, test_snapshot_id, graph)
    res = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST5")
    assert res["topological_edge_connectivity"] == 3
    assert independent_oracle_min_cut(graph, 1, 5) == 3

def test_doubled_capacity_bug_prevention(db_session, test_snapshot_id):
    # If a buggy implementation treats A-B as capacity 2, min cut will be 2 instead of 1.
    graph = [(1,2)]
    create_network(db_session, test_snapshot_id, graph)
    res = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST2")
    assert res["topological_edge_connectivity"] == 1
    assert independent_oracle_min_cut(graph, 1, 2) == 1

def test_same_station(db_session, test_snapshot_id):
    graph = [(1,2)]
    create_network(db_session, test_snapshot_id, graph)
    res = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST1")
    assert res["topological_edge_connectivity"] is None
    assert independent_oracle_min_cut(graph, 1, 1) is None

def test_missing_origin(db_session, test_snapshot_id):
    graph = [(1,2)]
    create_network(db_session, test_snapshot_id, graph)
    with pytest.raises(ValueError, match="not found"):
        calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST99", "ST2")

def test_canonicalization_of_opposite_directions(db_session, test_snapshot_id):
    # A->B and B->A should collapse to one canonical edge with capacity 1
    graph = [(1,2), (2,1)]
    create_network(db_session, test_snapshot_id, graph)
    res = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST2")
    assert res["topological_edge_connectivity"] == 1

def test_self_loop_exclusion(db_session, test_snapshot_id):
    graph = [(1,2), (1,1)]
    create_network(db_session, test_snapshot_id, graph)
    res = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST2")
    assert res["topological_edge_connectivity"] == 1

def test_two_cycles_connected_by_bridge(db_session, test_snapshot_id):
    # 1-2-3-1  bridge 3-4  4-5-6-4
    graph = [(1,2), (2,3), (3,1), (3,4), (4,5), (5,6), (6,4)]
    create_network(db_session, test_snapshot_id, graph)
    # 1 to 3 -> cut 2
    res_13 = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST3")
    assert res_13["topological_edge_connectivity"] == 2
    assert independent_oracle_min_cut(graph, 1, 3) == 2
    
    # 1 to 4 -> cut 1
    res_14 = calculate_station_pair_topological_edge_connectivity(db_session, test_snapshot_id, "ST1", "ST4")
    assert res_14["topological_edge_connectivity"] == 1
    assert independent_oracle_min_cut(graph, 1, 4) == 1
