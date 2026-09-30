import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime, UTC

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.graph import RailwayNetworkEdge
from railgati.services.network import calculate_train_sequence_subgraph_diameter

@pytest.fixture
def setup_subgraph_diameter_data(db_session: Session) -> dict[str, int]:
    source = DataSource(name="api_test", url="http", publisher="pub", license="MIT")
    db_session.add(source)
    db_session.flush()

    snap_id = 999
    snap = DatasetSnapshot(id=snap_id, source_id=source.id, status="ACTIVE", retrieved_at=datetime.now(UTC))
    db_session.add(snap)
    db_session.flush()

    # Another snapshot
    snap2 = DatasetSnapshot(id=1000, source_id=source.id, status="INACTIVE", retrieved_at=datetime.now(UTC))
    db_session.add(snap2)
    db_session.flush()

    # Stations
    # Let's generate stations on the fly
    stations = {}
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
        db_session.add(TrainObservation(train_id=t.id, snapshot_id=snap_id, name="EXP"))
        for i, code in enumerate(stops, 1):
            sid = get_station(code)
            db_session.add(TrainStopObservation(train_id=t.id, snapshot_id=snap_id, station_id=sid, stop_sequence=i))

    def add_edge(u: str, v: str, snapshot: int = snap_id) -> None:
        uid = get_station(u)
        vid = get_station(v)
        if uid == vid:
            db_session.add(RailwayNetworkEdge(timetable_snapshot_id=snapshot, from_station_id=uid, to_station_id=vid, train_count=1))
            return
        uid_min = min(uid, vid)
        vid_max = max(uid, vid)
        # Avoid duplicates
        existing = db_session.query(RailwayNetworkEdge).filter_by(
            timetable_snapshot_id=snapshot, from_station_id=uid_min, to_station_id=vid_max
        ).first()
        if not existing:
            db_session.add(RailwayNetworkEdge(timetable_snapshot_id=snapshot, from_station_id=uid_min, to_station_id=vid_max, train_count=1))

    # T1: Single vertex
    add_train("T1", ["T1_A"])

    # T2: Two connected
    add_train("T2", ["T2_A", "T2_B"])
    add_edge("T2_A", "T2_B")

    # T3: Linear A-B-C-D
    add_train("T3", ["T3_A", "T3_B", "T3_C", "T3_D"])
    add_edge("T3_A", "T3_B")
    add_edge("T3_B", "T3_C")
    add_edge("T3_C", "T3_D")

    # T4: Triangle A-B-C
    add_train("T4", ["T4_A", "T4_B", "T4_C"])
    add_edge("T4_A", "T4_B")
    add_edge("T4_B", "T4_C")
    add_edge("T4_A", "T4_C")

    # T5: Square A-B-C-D-A
    add_train("T5", ["T5_A", "T5_B", "T5_C", "T5_D"])
    add_edge("T5_A", "T5_B")
    add_edge("T5_B", "T5_C")
    add_edge("T5_C", "T5_D")
    add_edge("T5_D", "T5_A")

    # T6: Disconnected X1-X2, X3-X4
    add_train("T6", ["T6_X1", "T6_X2", "T6_X3", "T6_X4"])
    add_edge("T6_X1", "T6_X2")
    add_edge("T6_X3", "T6_X4")

    # T7: Isolated + connected Y1-Y2-Y3 and Y4
    add_train("T7", ["T7_Y1", "T7_Y2", "T7_Y3", "T7_Y4"])
    add_edge("T7_Y1", "T7_Y2")
    add_edge("T7_Y2", "T7_Y3")

    # T8: Global shortcut outside V_T. V_T={A, B, C}.
    add_train("T8", ["T8_A", "T8_B", "T8_C"])
    add_edge("T8_A", "T8_B")
    add_edge("T8_B", "T8_C")
    add_edge("T8_A", "T8_Z")
    add_edge("T8_Z", "T8_C")

    # T9: Repeated station A-B-C-A
    add_train("T9", ["T9_A", "T9_B", "T9_C", "T9_A"])
    add_edge("T9_A", "T9_B")
    add_edge("T9_B", "T9_C")

    # T10: Self loop A-A, A-B
    add_train("T10", ["T10_A", "T10_B"])
    add_edge("T10_A", "T10_B")
    add_edge("T10_A", "T10_A")

    # T11: Reciprocal edges / Multitrains
    add_train("T11", ["T11_A", "T11_B"])
    # handled by canonical edge

    # T13: Snapshot isolation
    add_train("T13", ["T13_A", "T13_B", "T13_C"])
    add_edge("T13_A", "T13_B")
    add_edge("T13_B", "T13_C")
    add_edge("T13_A", "T13_C", snapshot=1000) # This edge shouldn't be visible in 999

    # T17: Disconnected 3+ components
    add_train("T17", ["T17_1", "T17_2", "T17_3"])

    db_session.commit()
    return {"snap_id": snap_id}


def test_calculate_diameter_single_vertex(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T1")
    assert res["route_station_count"] == 1
    assert res["subgraph_diameter"] == 0
    assert res["subgraph_connected"] is True
    assert res["component_count"] == 1

def test_calculate_diameter_two_vertices(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T2")
    assert res["route_station_count"] == 2
    assert res["subgraph_diameter"] == 1
    assert res["subgraph_connected"] is True

def test_calculate_diameter_linear(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T3")
    assert res["route_station_count"] == 4
    assert res["subgraph_diameter"] == 3
    assert res["subgraph_connected"] is True

def test_calculate_diameter_triangle(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T4")
    assert res["route_station_count"] == 3
    assert res["subgraph_diameter"] == 1

def test_calculate_diameter_square(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T5")
    assert res["route_station_count"] == 4
    assert res["subgraph_diameter"] == 2

def test_calculate_diameter_disconnected_two_components(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T6")
    assert res["route_station_count"] == 4
    assert res["subgraph_diameter"] is None
    assert res["subgraph_connected"] is False
    assert res["component_count"] == 2

def test_calculate_diameter_isolated_vertex(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T7")
    assert res["route_station_count"] == 4
    assert res["subgraph_diameter"] is None
    assert res["subgraph_connected"] is False
    assert res["component_count"] == 2

def test_calculate_diameter_global_shortcut(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T8")
    assert res["route_station_count"] == 3
    # A-B, B-C exist. A-Z and Z-C exist but Z not in V_T. Thus diameter should be 2.
    assert res["subgraph_diameter"] == 2
    assert res["subgraph_connected"] is True

def test_calculate_diameter_repeated_station(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T9")
    assert res["route_station_count"] == 3 # deduplicated

def test_calculate_diameter_self_loop(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T10")
    assert res["subgraph_diameter"] == 1
    assert res["route_station_count"] == 2

def test_calculate_diameter_snapshot_isolation(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    # T13 has A, B, C. In 999, A-B, B-C exist -> diam 2. In 1000, A-C exists -> diam 1.
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T13")
    assert res["subgraph_diameter"] == 2

def test_calculate_diameter_unknown_train(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "UNKNOWN")

def test_calculate_diameter_3_components(db_session: Session, setup_subgraph_diameter_data: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_diameter(db_session, setup_subgraph_diameter_data["snap_id"], "T17")
    assert res["route_station_count"] == 3
    assert res["subgraph_diameter"] is None
    assert res["subgraph_connected"] is False
    assert res["component_count"] == 3
