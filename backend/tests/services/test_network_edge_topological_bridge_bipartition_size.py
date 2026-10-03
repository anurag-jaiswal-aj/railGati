import typing

import pytest

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.graph import RailwayNetworkEdge
from railgati.models.station import Station
from railgati.services.network import calculate_bridge_bipartition_size


@pytest.fixture
def test_snapshot_id(db_session: typing.Any) -> int:
    from datetime import UTC, datetime

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
def bridge_fixtures(db_session: typing.Any, test_snapshot_id: int) -> typing.Any:
    stations = {
        "S_A": Station(id=1, code="S_A"),
        "S_B": Station(id=2, code="S_B"),
        "S_C": Station(id=3, code="S_C"),
        "S_D": Station(id=4, code="S_D"),
        
        "U1": Station(id=11, code="U1"),
        "U2": Station(id=12, code="U2"),
        "B1": Station(id=13, code="B1"),
        "B2": Station(id=14, code="B2"),
        "V1": Station(id=15, code="V1"),
        "V2": Station(id=16, code="V2"),
        "V3": Station(id=17, code="V3"),
        
        "C1": Station(id=21, code="C1"),
        "C2": Station(id=22, code="C2"),
        "C3": Station(id=23, code="C3"),
        "C4": Station(id=24, code="C4"),
        
        "E1": Station(id=31, code="E1"),
        "E2": Station(id=32, code="E2"),
        "E3": Station(id=33, code="E3"),
        "F1": Station(id=34, code="F1"),
        "F2": Station(id=35, code="F2"),
        "F3": Station(id=36, code="F3"),
        
        "SE1": Station(id=41, code="SE1"),
        "SE2": Station(id=42, code="SE2"),
        
        "ISO": Station(id=51, code="ISO"),
    }
    
    db_session.add_all(stations.values())
    db_session.flush()

    edges = [
        (1, 2), (3, 2), (4, 2),
        (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (15, 17),
        (21, 22), (22, 23), (23, 24), (24, 21),
        (31, 32), (32, 33), (33, 34), (34, 35), (35, 36),
        (41, 42), (42, 41), (41, 41),
    ]

    db_edges = [
        RailwayNetworkEdge(
            timetable_snapshot_id=test_snapshot_id,
            from_station_id=u,
            to_station_id=v,
            train_count=1,
        )
        for u, v in edges
    ]
    
    db_session.add_all(db_edges)
    db_session.commit()
    
    return test_snapshot_id


def test_bridge_separating_leaf(db_session: typing.Any, bridge_fixtures: typing.Any) -> None:
    res = calculate_bridge_bipartition_size(db_session, bridge_fixtures, "S_A", "S_B")
    assert res["is_bridge"] is True
    assert res["bridge_bipartition_size"] == 1


def test_bridge_separating_unequal(db_session: typing.Any, bridge_fixtures: typing.Any) -> None:
    res = calculate_bridge_bipartition_size(db_session, bridge_fixtures, "B1", "B2")
    assert res["is_bridge"] is True
    assert res["bridge_bipartition_size"] == 3


def test_bridge_separating_equal(db_session: typing.Any, bridge_fixtures: typing.Any) -> None:
    res = calculate_bridge_bipartition_size(db_session, bridge_fixtures, "E3", "F1")
    assert res["is_bridge"] is True
    assert res["bridge_bipartition_size"] == 3


def test_non_bridge_in_cycle(db_session: typing.Any, bridge_fixtures: typing.Any) -> None:
    res = calculate_bridge_bipartition_size(db_session, bridge_fixtures, "C1", "C2")
    assert res["is_bridge"] is False
    assert res["bridge_bipartition_size"] == 0


def test_bidirectional_same_result(db_session: typing.Any, bridge_fixtures: typing.Any) -> None:
    res1 = calculate_bridge_bipartition_size(db_session, bridge_fixtures, "U2", "B1")
    res2 = calculate_bridge_bipartition_size(db_session, bridge_fixtures, "B1", "U2")
    assert res1["is_bridge"] is True
    assert res1["bridge_bipartition_size"] == 2
    assert res2["is_bridge"] is True
    assert res2["bridge_bipartition_size"] == 2


def test_single_edge_graph(db_session: typing.Any, bridge_fixtures: typing.Any) -> None:
    res = calculate_bridge_bipartition_size(db_session, bridge_fixtures, "SE1", "SE2")
    assert res["is_bridge"] is True
    assert res["bridge_bipartition_size"] == 1


def test_self_loop_raises(db_session: typing.Any, bridge_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="Self-loops are excluded"):
        calculate_bridge_bipartition_size(db_session, bridge_fixtures, "SE1", "SE1")


def test_unknown_station(db_session: typing.Any, bridge_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_bridge_bipartition_size(db_session, bridge_fixtures, "UNKNOWN", "SE2")


def test_missing_edge(db_session: typing.Any, bridge_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found in the active graph"):
        calculate_bridge_bipartition_size(db_session, bridge_fixtures, "S_A", "C1")


def test_oracle_validation(db_session: typing.Any, bridge_fixtures: typing.Any) -> None:
    def oracle_bipartition_size(edges: list[tuple[str, str]], u: str, v: str) -> tuple[bool, int]:
        import collections
        adj = collections.defaultdict(set)
        for a, b in edges:
            if a != b:
                adj[a].add(b)
                adj[b].add(a)
            
        visited = {u}
        q = [u]
        while q:
            curr = q.pop(0)
            for n in adj[curr]:
                if n not in visited:
                    visited.add(n)
                    q.append(n)
        comp_size = len(visited)
        
        adj[u].discard(v)
        adj[v].discard(u)
        
        visited_u = {u}
        q = [u]
        while q:
            curr = q.pop(0)
            for n in adj[curr]:
                if n not in visited_u:
                    visited_u.add(n)
                    q.append(n)
                    
        is_bridge = len(visited_u) < comp_size
        return is_bridge, min(len(visited_u), comp_size - len(visited_u)) if is_bridge else 0

    edge_list = [
        ("S_A", "S_B"), ("S_C", "S_B"), ("S_D", "S_B"),
        ("U1", "U2"), ("U2", "B1"), ("B1", "B2"), ("B2", "V1"), ("V1", "V2"), ("V1", "V3"),
        ("C1", "C2"), ("C2", "C3"), ("C3", "C4"), ("C4", "C1"),
        ("E1", "E2"), ("E2", "E3"), ("E3", "F1"), ("F1", "F2"), ("F2", "F3"),
        ("SE1", "SE2"),
    ]
    
    test_cases = [
        ("S_A", "S_B"),
        ("B1", "B2"),
        ("C1", "C2"),
        ("E3", "F1"),
        ("SE1", "SE2"),
    ]
    
    for u, v in test_cases:
        res = calculate_bridge_bipartition_size(db_session, bridge_fixtures, u, v)
        is_bridge, size = oracle_bipartition_size(edge_list, u, v)
        assert res["is_bridge"] == is_bridge
        assert res["bridge_bipartition_size"] == size
