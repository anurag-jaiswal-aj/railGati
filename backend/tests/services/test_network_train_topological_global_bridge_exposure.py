import typing
import pytest
from sqlalchemy.orm import Session
from datetime import UTC, datetime

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdgeResilience
from railgati.services.network import calculate_train_topological_global_bridge_exposure

def compute_bridge_fraction_oracle(
    graph_edges: list[tuple[int, int]], route_sequence: list[int]
) -> float | None:
    route_edges = set()
    for i in range(len(route_sequence) - 1):
        if route_sequence[i] != route_sequence[i+1]:
            route_edges.add(tuple(sorted([route_sequence[i], route_sequence[i+1]])))
            
    if not route_edges:
        return None

    def count_components(skip_edge=None):
        from collections import defaultdict
        adj = defaultdict(list)
        nodes = set()
        for u, v in graph_edges:
            nodes.add(u)
            nodes.add(v)
            if skip_edge and tuple(sorted([u, v])) == skip_edge:
                continue
            adj[u].append(v)
            adj[v].append(u)
            
        visited = set()
        components = 0
        def dfs(node):
            stack = [node]
            while stack:
                curr = stack.pop()
                if curr not in visited:
                    visited.add(curr)
                    for nbr in adj[curr]:
                        if nbr not in visited:
                            stack.append(nbr)
                            
        for n in nodes:
            if n not in visited:
                components += 1
                dfs(n)
        return components

    base_components = count_components()
    bridges = set()
    for e in graph_edges:
        ce = tuple(sorted(e))
        if count_components(skip_edge=ce) > base_components:
            bridges.add(ce)
            
    bridge_count = len(route_edges.intersection(bridges))
    return bridge_count / len(route_edges)

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

@pytest.fixture
def test_graph_build_id(db_session: Session, test_snapshot_id: int) -> int:
    build = RailwayGraphBuild(
        timetable_snapshot_id=test_snapshot_id,
        status="ACTIVE"
    )
    db_session.add(build)
    db_session.flush()
    return build.id

def create_network_and_train(
    db_session: Session, snapshot_id: int, build_id: int, 
    graph_edges: list[tuple[int, int]], train_number: str, route: list[int]
):
    nodes = set()
    for u, v in graph_edges:
        nodes.add(u)
        nodes.add(v)
    for n in route:
        nodes.add(n)
        
    for n in nodes:
        db_session.add(Station(id=n, code=f"ST{n}"))
    db_session.flush()

    # compute bridges for resilience table exactly as oracle does for test consistency
    def count_comp(skip_edge=None):
        from collections import defaultdict
        adj = defaultdict(list)
        for u, v in graph_edges:
            if skip_edge and tuple(sorted([u, v])) == skip_edge:
                continue
            adj[u].append(v)
            adj[v].append(u)
        visited = set()
        c = 0
        def dfs(node):
            stack = [node]
            while stack:
                curr = stack.pop()
                if curr not in visited:
                    visited.add(curr)
                    for nb in adj[curr]:
                        stack.append(nb)
        for node in nodes:
            if node not in visited:
                c += 1
                dfs(node)
        return c
    
    bc = count_comp()
    bridges = set()
    canonical_graph_edges = {tuple(sorted(e)) for e in graph_edges}
    for e in canonical_graph_edges:
        if count_comp(skip_edge=e) > bc:
            bridges.add(e)
            
    for u, v in canonical_graph_edges:
        is_bridge = (u, v) in bridges
        resilience = RailwayNetworkEdgeResilience(
            graph_build_id=build_id,
            timetable_snapshot_id=snapshot_id,
            station_a_id=u,
            station_b_id=v,
            detour_exists=not is_bridge,
            is_structural_bridge=is_bridge
        )
        db_session.add(resilience)
        
    train_id = abs(hash(train_number)) % 1000000 + 1
    db_session.add(Train(id=train_id, number=train_number))
    db_session.flush()
    db_session.add(TrainObservation(train_id=train_id, snapshot_id=snapshot_id, name=train_number, type="EXP"))
    for i, st in enumerate(route):
        db_session.add(TrainStopObservation(snapshot_id=snapshot_id, train_id=train_id, stop_sequence=i, station_id=st))
        
    db_session.commit()
    
def test_no_bridge_edges(db_session, test_snapshot_id, test_graph_build_id):
    # triangle
    graph = [(1,2), (2,3), (3,1)]
    route = [1, 2, 3]
    create_network_and_train(db_session, test_snapshot_id, test_graph_build_id, graph, "T0", route)
    res = calculate_train_topological_global_bridge_exposure(db_session, test_snapshot_id, "T0")
    assert res["total_route_distinct_edges"] == 2
    assert res["global_bridge_edges_count"] == 0
    assert res["global_bridge_exposure_fraction"] == 0.0
    assert compute_bridge_fraction_oracle(graph, route) == 0.0

def test_all_bridge_edges(db_session, test_snapshot_id, test_graph_build_id):
    # simple path graph
    graph = [(1,2), (2,3), (3,4)]
    route = [1, 2, 3, 4]
    create_network_and_train(db_session, test_snapshot_id, test_graph_build_id, graph, "T1", route)
    res = calculate_train_topological_global_bridge_exposure(db_session, test_snapshot_id, "T1")
    assert res["total_route_distinct_edges"] == 3
    assert res["global_bridge_edges_count"] == 3
    assert res["global_bridge_exposure_fraction"] == 1.0
    assert compute_bridge_fraction_oracle(graph, route) == 1.0

def test_mixed_bridge_edges(db_session, test_snapshot_id, test_graph_build_id):
    # triangle with a tail
    graph = [(1,2), (2,3), (3,1), (3,4), (4,5)]
    route = [1, 2, 3, 4, 5]
    create_network_and_train(db_session, test_snapshot_id, test_graph_build_id, graph, "T2", route)
    res = calculate_train_topological_global_bridge_exposure(db_session, test_snapshot_id, "T2")
    assert res["total_route_distinct_edges"] == 4
    # (1,2) and (2,3) are in cycle, (3,4) and (4,5) are bridges
    assert res["global_bridge_edges_count"] == 2
    assert res["global_bridge_exposure_fraction"] == 0.5
    assert compute_bridge_fraction_oracle(graph, route) == 0.5

def test_two_components_with_bridge(db_session, test_snapshot_id, test_graph_build_id):
    # two cyclic components connected by a bridge
    graph = [(1,2), (2,3), (3,1), (3,4), (4,5), (5,6), (6,4)]
    route = [1, 3, 4, 6]
    create_network_and_train(db_session, test_snapshot_id, test_graph_build_id, graph, "T3", route)
    res = calculate_train_topological_global_bridge_exposure(db_session, test_snapshot_id, "T3")
    assert res["total_route_distinct_edges"] == 3
    assert res["global_bridge_edges_count"] == 1
    assert abs(res["global_bridge_exposure_fraction"] - 0.333333333) < 1e-6
    assert abs(compute_bridge_fraction_oracle(graph, route) - 0.333333333) < 1e-6

def test_repeated_edges_deduplicated(db_session, test_snapshot_id, test_graph_build_id):
    graph = [(1,2), (2,3), (3,4)]
    route = [1, 2, 3, 2, 1, 2]
    create_network_and_train(db_session, test_snapshot_id, test_graph_build_id, graph, "T4", route)
    res = calculate_train_topological_global_bridge_exposure(db_session, test_snapshot_id, "T4")
    assert res["total_route_distinct_edges"] == 2
    assert res["global_bridge_edges_count"] == 2
    assert res["global_bridge_exposure_fraction"] == 1.0

def test_directional_traversal(db_session, test_snapshot_id, test_graph_build_id):
    graph = [(1,2), (2,3), (3,4)]
    route = [4, 3, 2, 1]
    create_network_and_train(db_session, test_snapshot_id, test_graph_build_id, graph, "T5", route)
    res = calculate_train_topological_global_bridge_exposure(db_session, test_snapshot_id, "T5")
    assert res["total_route_distinct_edges"] == 3
    assert res["global_bridge_edges_count"] == 3
    assert res["global_bridge_exposure_fraction"] == 1.0

def test_self_loop_ignored(db_session, test_snapshot_id, test_graph_build_id):
    graph = [(1,2), (2,3), (3,4)]
    route = [1, 1, 2, 3]
    create_network_and_train(db_session, test_snapshot_id, test_graph_build_id, graph, "T6", route)
    res = calculate_train_topological_global_bridge_exposure(db_session, test_snapshot_id, "T6")
    assert res["total_route_distinct_edges"] == 2
    assert res["global_bridge_edges_count"] == 2
    assert res["global_bridge_exposure_fraction"] == 1.0
    
def test_one_edge_route(db_session, test_snapshot_id, test_graph_build_id):
    graph = [(1,2)]
    route = [1, 2]
    create_network_and_train(db_session, test_snapshot_id, test_graph_build_id, graph, "T7", route)
    res = calculate_train_topological_global_bridge_exposure(db_session, test_snapshot_id, "T7")
    assert res["total_route_distinct_edges"] == 1
    assert res["global_bridge_edges_count"] == 1
    assert res["global_bridge_exposure_fraction"] == 1.0

def test_zero_distinct_route_edges(db_session, test_snapshot_id, test_graph_build_id):
    graph = [(1,2)]
    route = [1]
    create_network_and_train(db_session, test_snapshot_id, test_graph_build_id, graph, "T8", route)
    res = calculate_train_topological_global_bridge_exposure(db_session, test_snapshot_id, "T8")
    assert res["total_route_distinct_edges"] == 0
    assert res["global_bridge_exposure_fraction"] is None

def test_train_not_found(db_session, test_snapshot_id, test_graph_build_id):
    with pytest.raises(ValueError, match="not found"):
        calculate_train_topological_global_bridge_exposure(db_session, test_snapshot_id, "99999")
