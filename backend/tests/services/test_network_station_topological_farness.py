import typing

import pytest

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.graph import RailwayNetworkEdge
from railgati.models.station import Station
from railgati.services.network import calculate_station_topological_farness


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
def farness_fixtures(db_session: typing.Any, test_snapshot_id: int) -> typing.Any:
    stations = {
        "A": Station(id=1, code="A"),
        "B": Station(id=2, code="B"),
        "C": Station(id=3, code="C"),
        "D": Station(id=4, code="D"),
        "E": Station(id=5, code="E"),
        "ISO": Station(id=6, code="ISO"),
    }

    db_session.add_all(stations.values())
    db_session.flush()

    edges = [
        # Two-node path A-B
        RailwayNetworkEdge(
            timetable_snapshot_id=test_snapshot_id,
            from_station_id=1,
            to_station_id=2,
            train_count=1,
        ),
        # Three-node path A-B-C
        RailwayNetworkEdge(
            timetable_snapshot_id=test_snapshot_id,
            from_station_id=2,
            to_station_id=3,
            train_count=1,
        ),
        # Four-node path A-B-C-D (and forms square if we add D-A)
        RailwayNetworkEdge(
            timetable_snapshot_id=test_snapshot_id,
            from_station_id=3,
            to_station_id=4,
            train_count=1,
        ),
        # Square A-B-C-D-A
        RailwayNetworkEdge(
            timetable_snapshot_id=test_snapshot_id,
            from_station_id=4,
            to_station_id=1,
            train_count=1,
        ),
        # Disconnected E
        RailwayNetworkEdge(
            timetable_snapshot_id=test_snapshot_id,
            from_station_id=5,
            to_station_id=5,  # Self-loop for E to keep it in graph but isolated from A-D
            train_count=1,
        ),

        # Reciprocal edge B-A
        RailwayNetworkEdge(
            timetable_snapshot_id=test_snapshot_id,
            from_station_id=2,
            to_station_id=1,
            train_count=1,
        ),
        # Different snapshot edge A-E
        RailwayNetworkEdge(
            timetable_snapshot_id=test_snapshot_id + 1,
            from_station_id=1,
            to_station_id=5,
            train_count=1,
        ),
    ]

    db_session.add_all(edges)
    db_session.commit()
    return stations


def oracle_farness(edges: list[tuple[int, int]], s: int) -> tuple[int, int]:
    import collections
    adj = collections.defaultdict(set)
    for u, v in edges:
        if u != v:
            adj[u].add(v)
            adj[v].add(u)

    if s not in adj:
        return 0, 1

    visited = {s}
    q = collections.deque([(s, 0)])
    sum_d = 0
    count = 0
    while q:
        curr, d = q.popleft()
        sum_d += d
        count += 1
        for nxt in adj[curr]:
            if nxt not in visited:
                visited.add(nxt)
                q.append((nxt, d + 1))
    return sum_d, count


def test_farness_single_isolated_vertex(db_session: typing.Any, test_snapshot_id: int, farness_fixtures: typing.Any) -> None:
    res = calculate_station_topological_farness(db_session, test_snapshot_id, "ISO")
    assert res["topological_farness"] == 0
    assert res["reachable_station_count"] == 1


def test_farness_square(db_session: typing.Any, test_snapshot_id: int, farness_fixtures: typing.Any) -> None:
    # A-B, B-C, C-D, D-A
    # from A: B(1), D(1), C(2) = 4
    res = calculate_station_topological_farness(db_session, test_snapshot_id, "A")
    assert res["topological_farness"] == 4
    assert res["reachable_station_count"] == 4


def test_farness_disconnected_component(db_session: typing.Any, test_snapshot_id: int, farness_fixtures: typing.Any) -> None:
    # E has a self-loop, so it is in the active graph but isolated from A,B,C,D
    res = calculate_station_topological_farness(db_session, test_snapshot_id, "E")
    assert res["topological_farness"] == 0
    assert res["reachable_station_count"] == 1


def test_farness_snapshot_isolation(db_session: typing.Any, test_snapshot_id: int, farness_fixtures: typing.Any) -> None:
    # snapshot_id+1 has an edge A-E
    res_other = calculate_station_topological_farness(db_session, test_snapshot_id + 1, "E")
    assert res_other["reachable_station_count"] == 2
    assert res_other["topological_farness"] == 1


def test_farness_unknown_station(db_session: typing.Any, test_snapshot_id: int, farness_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_station_topological_farness(db_session, test_snapshot_id, "UNKNOWN")


def test_farness_deterministic(db_session: typing.Any, test_snapshot_id: int, farness_fixtures: typing.Any) -> None:
    res1 = calculate_station_topological_farness(db_session, test_snapshot_id, "B")
    res2 = calculate_station_topological_farness(db_session, test_snapshot_id, "B")
    assert res1 == res2


def test_farness_oracle_match(db_session: typing.Any, test_snapshot_id: int, farness_fixtures: typing.Any) -> None:
    edges = [
        (1, 2), (2, 3), (3, 4), (4, 1), (5, 5), (1, 2), (2, 1)
    ]
    oracle_f, oracle_c = oracle_farness(edges, 1) # A
    res = calculate_station_topological_farness(db_session, test_snapshot_id, "A")
    assert res["topological_farness"] == oracle_f
    assert res["reachable_station_count"] == oracle_c
