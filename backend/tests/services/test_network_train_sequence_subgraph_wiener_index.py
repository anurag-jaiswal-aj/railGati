import collections

import pytest
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayNetworkEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import (
    calculate_train_sequence_subgraph_wiener_index,
)


def _oracle_wiener_index(
    stops: set[int], adj: dict[int, set[int]]
) -> int | None:
    """Independent BFS oracle for the Wiener index."""
    # Check connectivity first
    if not stops:
        return 0
    start = next(iter(stops))
    visited: set[int] = {start}
    q: collections.deque[int] = collections.deque([start])
    while q:
        curr = q.popleft()
        for nxt in adj.get(curr, set()):
            if nxt not in visited:
                visited.add(nxt)
                q.append(nxt)
    if len(visited) != len(stops):
        return None  # Disconnected

    # Compute Wiener index: sum d(u,v) for all unordered pairs
    sorted_nodes = sorted(stops)
    wiener = 0
    for s in sorted_nodes:
        bfs_visited: set[int] = {s}
        bfs_q: collections.deque[tuple[int, int]] = (
            collections.deque([(s, 0)])
        )
        while bfs_q:
            curr, dist = bfs_q.popleft()
            if curr > s:
                wiener += dist
            for nxt in adj.get(curr, set()):
                if nxt not in bfs_visited:
                    bfs_visited.add(nxt)
                    bfs_q.append((nxt, dist + 1))
    return wiener


@pytest.fixture
def setup_subgraph_wiener_data(
    db_session: Session,
) -> dict[str, int]:
    from datetime import UTC, datetime

    source = DataSource(
        name="api_test", url="http", publisher="pub", license="MIT"
    )
    db_session.add(source)
    db_session.flush()

    snap_id = 999
    snap = DatasetSnapshot(
        id=snap_id,
        source_id=source.id,
        status="ACTIVE",
        retrieved_at=datetime.now(UTC),
    )
    db_session.add(snap)
    db_session.flush()

    snap2 = DatasetSnapshot(
        id=1000,
        source_id=source.id,
        status="INACTIVE",
        retrieved_at=datetime.now(UTC),
    )
    db_session.add(snap2)
    db_session.flush()

    stations: dict[str, int] = {}

    def get_station(code: str) -> int:
        if code not in stations:
            s = Station(code=code)
            db_session.add(s)
            db_session.flush()
            stations[code] = s.id
        return stations[code]

    def add_train(number: str, stops: list[str]) -> None:
        t = Train(number=number)
        db_session.add(t)
        db_session.flush()
        db_session.add(
            TrainObservation(
                train_id=t.id, snapshot_id=snap_id, name="EXP"
            )
        )
        for i, code in enumerate(stops, 1):
            sid = get_station(code)
            db_session.add(
                TrainStopObservation(
                    train_id=t.id,
                    snapshot_id=snap_id,
                    station_id=sid,
                    stop_sequence=i,
                )
            )

    def add_edge(
        u: str, v: str, snapshot: int = snap_id
    ) -> None:
        uid = get_station(u)
        vid = get_station(v)
        if uid == vid:
            db_session.add(
                RailwayNetworkEdge(
                    timetable_snapshot_id=snapshot,
                    from_station_id=uid,
                    to_station_id=vid,
                    train_count=1,
                )
            )
            return
        uid_min = min(uid, vid)
        vid_max = max(uid, vid)
        existing = (
            db_session.query(RailwayNetworkEdge)
            .filter_by(
                timetable_snapshot_id=snapshot,
                from_station_id=uid_min,
                to_station_id=vid_max,
            )
            .first()
        )
        if not existing:
            db_session.add(
                RailwayNetworkEdge(
                    timetable_snapshot_id=snapshot,
                    from_station_id=uid_min,
                    to_station_id=vid_max,
                    train_count=1,
                )
            )

    # W1: Single vertex -> W = 0
    add_train("W1", ["W1_A"])

    # W2: Two connected -> W = 1
    add_train("W2", ["W2_A", "W2_B"])
    add_edge("W2_A", "W2_B")

    # W3: Three-node path A-B-C -> W = 1+1+2 = 4
    add_train("W3", ["W3_A", "W3_B", "W3_C"])
    add_edge("W3_A", "W3_B")
    add_edge("W3_B", "W3_C")

    # W4: Four-node path A-B-C-D -> W = 1+2+3+1+2+1 = 10
    add_train("W4", ["W4_A", "W4_B", "W4_C", "W4_D"])
    add_edge("W4_A", "W4_B")
    add_edge("W4_B", "W4_C")
    add_edge("W4_C", "W4_D")

    # W5: Triangle A-B-C-A -> W = 1+1+1 = 3
    add_train("W5", ["W5_A", "W5_B", "W5_C"])
    add_edge("W5_A", "W5_B")
    add_edge("W5_B", "W5_C")
    add_edge("W5_A", "W5_C")

    # W6: Square A-B-C-D-A -> W = 1+2+1+1+2+1 = 8
    add_train("W6", ["W6_A", "W6_B", "W6_C", "W6_D"])
    add_edge("W6_A", "W6_B")
    add_edge("W6_B", "W6_C")
    add_edge("W6_C", "W6_D")
    add_edge("W6_D", "W6_A")

    # W7: Disconnected {X1-X2, X3-X4}
    add_train("W7", ["W7_X1", "W7_X2", "W7_X3", "W7_X4"])
    add_edge("W7_X1", "W7_X2")
    add_edge("W7_X3", "W7_X4")

    # W8: Isolated vertex + connected component {Y1-Y2-Y3, Y4}
    add_train("W8", ["W8_Y1", "W8_Y2", "W8_Y3", "W8_Y4"])
    add_edge("W8_Y1", "W8_Y2")
    add_edge("W8_Y2", "W8_Y3")

    # W9: Global shortcut outside V_T
    # V_T = {A, B, C}, induced A-B-C path
    # Global has A-Z, Z-C but Z not in V_T
    add_train("W9", ["W9_A", "W9_B", "W9_C"])
    add_edge("W9_A", "W9_B")
    add_edge("W9_B", "W9_C")
    add_edge("W9_A", "W9_Z")
    add_edge("W9_Z", "W9_C")

    # W10: Repeated station A-B-C-A
    add_train("W10", ["W10_A", "W10_B", "W10_C", "W10_A"])
    add_edge("W10_A", "W10_B")
    add_edge("W10_B", "W10_C")

    # W11: Self-loop A-A, A-B
    add_train("W11", ["W11_A", "W11_B"])
    add_edge("W11_A", "W11_B")
    add_edge("W11_A", "W11_A")

    # W12: Reciprocal edges / Multitrains
    add_train("W12", ["W12_A", "W12_B"])
    # canonical edge handled

    # W13: Snapshot isolation
    add_train("W13", ["W13_A", "W13_B", "W13_C"])
    add_edge("W13_A", "W13_B")
    add_edge("W13_B", "W13_C")
    # Edge A-C only in snapshot 1000
    add_edge("W13_A", "W13_C", snapshot=1000)

    # W17: Disconnected 3 components
    add_train("W17", ["W17_1", "W17_2", "W17_3"])

    db_session.commit()
    return {"snap_id": snap_id}


def test_wiener_single_vertex(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W1"
    )
    assert res["route_station_count"] == 1
    assert res["subgraph_wiener_index"] == 0
    assert res["subgraph_connected"] is True
    assert res["component_count"] == 1


def test_wiener_two_vertices(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W2"
    )
    assert res["route_station_count"] == 2
    assert res["subgraph_wiener_index"] == 1
    assert res["subgraph_connected"] is True


def test_wiener_three_node_path(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W3"
    )
    assert res["route_station_count"] == 3
    # A-B=1, B-C=1, A-C=2 -> W=4
    assert res["subgraph_wiener_index"] == 4
    assert res["subgraph_connected"] is True


def test_wiener_four_node_path(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W4"
    )
    assert res["route_station_count"] == 4
    # A-B=1, A-C=2, A-D=3, B-C=1, B-D=2, C-D=1 -> W=10
    assert res["subgraph_wiener_index"] == 10
    assert res["subgraph_connected"] is True


def test_wiener_triangle(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W5"
    )
    assert res["route_station_count"] == 3
    # All pairs at distance 1 -> W=3
    assert res["subgraph_wiener_index"] == 3
    assert res["subgraph_connected"] is True


def test_wiener_square(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W6"
    )
    assert res["route_station_count"] == 4
    # Adjacent pairs at 1: A-B, B-C, C-D, D-A = 4
    # Opposite pairs at 2: A-C, B-D = 4
    # W = 8
    assert res["subgraph_wiener_index"] == 8
    assert res["subgraph_connected"] is True


def test_wiener_disconnected(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W7"
    )
    assert res["route_station_count"] == 4
    assert res["subgraph_wiener_index"] is None
    assert res["subgraph_connected"] is False
    assert res["component_count"] == 2


def test_wiener_isolated_vertex_plus_component(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W8"
    )
    assert res["route_station_count"] == 4
    assert res["subgraph_wiener_index"] is None
    assert res["subgraph_connected"] is False
    assert res["component_count"] == 2


def test_wiener_global_shortcut_outside_vt(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W9"
    )
    assert res["route_station_count"] == 3
    # V_T = {A,B,C}, induced path A-B-C -> W=4
    # Z is outside V_T, must not provide a shortcut
    assert res["subgraph_wiener_index"] == 4
    assert res["subgraph_connected"] is True


def test_wiener_repeated_station(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W10"
    )
    # V_T = {A, B, C} (deduplicated), path A-B-C -> W=4
    assert res["route_station_count"] == 3
    assert res["subgraph_wiener_index"] == 4


def test_wiener_self_loop(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W11"
    )
    assert res["subgraph_wiener_index"] == 1
    assert res["route_station_count"] == 2


def test_wiener_snapshot_isolation(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    # W13: A-B-C in snap 999. A-C edge only in snap 1000.
    # In 999, path A-B-C -> W=4
    # If A-C leaked from 1000, W would be 3
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W13"
    )
    assert res["subgraph_wiener_index"] == 4


def test_wiener_unknown_train(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    with pytest.raises(ValueError, match="not found"):
        calculate_train_sequence_subgraph_wiener_index(
            db_session, snap, "UNKNOWN"
        )


def test_wiener_3_components(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W17"
    )
    assert res["route_station_count"] == 3
    assert res["subgraph_wiener_index"] is None
    assert res["subgraph_connected"] is False
    assert res["component_count"] == 3


def test_wiener_pair_count_correctness(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    """For a connected graph the Wiener index must be >= n*(n-1)/2."""
    snap = setup_subgraph_wiener_data["snap_id"]
    # W4: 4-node path, n=4, n*(n-1)/2 = 6
    res = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W4"
    )
    n = res["route_station_count"]
    w = res["subgraph_wiener_index"]
    assert w is not None
    assert w >= n * (n - 1) // 2


def test_wiener_deterministic(
    db_session: Session,
    setup_subgraph_wiener_data: dict[str, int],
) -> None:
    snap = setup_subgraph_wiener_data["snap_id"]
    res1 = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W4"
    )
    res2 = calculate_train_sequence_subgraph_wiener_index(
        db_session, snap, "W4"
    )
    assert res1["subgraph_wiener_index"] == res2["subgraph_wiener_index"]
