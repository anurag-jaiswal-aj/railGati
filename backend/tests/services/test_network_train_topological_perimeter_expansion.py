import typing
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_topological_perimeter_expansion

@pytest.fixture
def mock_perimeter_data(db_session: Session) -> typing.Any:
    db_session.execute(text("DELETE FROM railway_network_edges"))
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.execute(text("DELETE FROM data_sources"))
    db_session.commit()

    source = DataSource(name="Source 64", publisher="pub", url="url", license="mit")
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    snap2 = DatasetSnapshot(source_id=source.id, status="ARCHIVED")
    db_session.add_all([snap, snap2])
    db_session.commit()
    snap_id = snap.id
    snap2_id = snap2.id

    # Create 15 stations
    stn_codes = [
        "A", "B", "C", "D", "X", "Y", "Z", "ISOLATED", "SELF_LOOP",
        "W", "MULTIPLE_IN", "OTHER_SNAP_STN", "OTHER_TRAIN_STN"
    ]
    stations = {}
    for code in stn_codes:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()

    for code in stn_codes:
        db_session.add(StationObservation(station_id=stations[code].id, snapshot_id=snap_id, name=f"Stn {code}"))
        db_session.add(StationObservation(station_id=stations[code].id, snapshot_id=snap2_id, name=f"Stn {code} v2"))
    db_session.commit()

    edges_to_insert = [
        # Basic adjacency
        {"f": stations["A"].id, "t": stations["X"].id, "s": snap_id},
        {"f": stations["B"].id, "t": stations["X"].id, "s": snap_id}, # Shared external X
        {"f": stations["B"].id, "t": stations["Y"].id, "s": snap_id},
        {"f": stations["C"].id, "t": stations["Z"].id, "s": snap_id},
        {"f": stations["D"].id, "t": stations["Y"].id, "s": snap_id}, # Shared external Y
        
        # Internal edges (Route stations connected to each other)
        {"f": stations["A"].id, "t": stations["B"].id, "s": snap_id},
        {"f": stations["B"].id, "t": stations["C"].id, "s": snap_id},
        {"f": stations["C"].id, "t": stations["D"].id, "s": snap_id},
        
        # Reciprocal edges (A->W, W->A)
        {"f": stations["A"].id, "t": stations["W"].id, "s": snap_id},
        {"f": stations["W"].id, "t": stations["A"].id, "s": snap_id},
        
        # Self-edge
        {"f": stations["SELF_LOOP"].id, "t": stations["SELF_LOOP"].id, "s": snap_id},
        
        # Extreme multiplication (3 incoming edges to MULTIPLE_IN)
        {"f": stations["A"].id, "t": stations["MULTIPLE_IN"].id, "s": snap_id},
        {"f": stations["B"].id, "t": stations["MULTIPLE_IN"].id, "s": snap_id},
        {"f": stations["C"].id, "t": stations["MULTIPLE_IN"].id, "s": snap_id},

        # Snapshot 2 adjacency (should not be seen)
        {"f": stations["A"].id, "t": stations["OTHER_SNAP_STN"].id, "s": snap2_id},
    ]

    db_session.execute(text("INSERT INTO railway_network_edges (from_station_id, to_station_id, timetable_snapshot_id, train_count) VALUES (:f, :t, :s, 1)"), edges_to_insert)
    db_session.commit()

    def add_train(tr_num: str, path: list[str], target_snap: int = snap_id):
        tr = Train(number=tr_num)
        db_session.add(tr)
        db_session.commit()
        db_session.add(TrainObservation(train_id=tr.id, snapshot_id=target_snap, name=f"Train {tr_num}", type="EXP"))
        for i, code in enumerate(path, 1):
            tso = TrainStopObservation(
                snapshot_id=target_snap,
                train_id=tr.id,
                station_id=stations[code].id,
                stop_sequence=i
            )
            db_session.add(tso)
        db_session.commit()

    add_train("T1", ["A", "B", "C", "D"]) # Basic route
    add_train("T2", ["A"]) # One-stop train
    add_train("T3", ["A", "B"]) # Two-stop train
    add_train("T4", ["A", "B", "A", "B"]) # Cyclic visits
    add_train("T_ZERO", ["ISOLATED"]) # Zero perimeter / isolated
    add_train("T_SELF", ["SELF_LOOP"]) # Route station connected to itself
    add_train("T_OTHER", ["OTHER_TRAIN_STN"]) # Another train to ensure isolation

    return {"snap_id": snap_id, "snap2_id": snap2_id}


def test_train_perimeter_success_basic(db_session: Session, mock_perimeter_data: typing.Any) -> None:
    # Covers: 1, 5, 7, 12, 15
    snap_id = mock_perimeter_data["snap_id"]
    res = calculate_train_topological_perimeter_expansion(db_session, snap_id, "T1")
    
    assert res["target_train_number"] == "T1"
    assert res["route_station_count"] == 4 # A, B, C, D
    # Perimeter: X (from A,B), Y (from B,D), Z (from C), W (from A), MULTIPLE_IN (from A,B,C)
    assert res["perimeter_station_count"] == 5
    assert res["perimeter_expansion_ratio"] == 1.25
    
    # 12. Deterministic ordering, 5. Shared external station, 15. No row multiplication
    expected_codes = ["MULTIPLE_IN", "W", "X", "Y", "Z"]
    actual_codes = [s["station_code"] for s in res["perimeter_stations"]]
    assert actual_codes == expected_codes # Explicit order check
    
    # 7. Internal route edge exclusion (A, B, C, D are not in perimeter)
    for code in ["A", "B", "C", "D"]:
        assert code not in actual_codes


def test_train_perimeter_one_stop(db_session: Session, mock_perimeter_data: typing.Any) -> None:
    # Covers: 2
    snap_id = mock_perimeter_data["snap_id"]
    res = calculate_train_topological_perimeter_expansion(db_session, snap_id, "T2")
    
    assert res["route_station_count"] == 1
    # Perimeter of A: X, B, W, MULTIPLE_IN
    assert res["perimeter_station_count"] == 4 
    actual_codes = [s["station_code"] for s in res["perimeter_stations"]]
    assert actual_codes == ["B", "MULTIPLE_IN", "W", "X"]


def test_train_perimeter_two_stop(db_session: Session, mock_perimeter_data: typing.Any) -> None:
    # Covers: 3
    snap_id = mock_perimeter_data["snap_id"]
    res = calculate_train_topological_perimeter_expansion(db_session, snap_id, "T3")
    
    assert res["route_station_count"] == 2
    # Perimeter of A, B: X, Y, W, MULTIPLE_IN, C
    assert res["perimeter_station_count"] == 5 
    actual_codes = [s["station_code"] for s in res["perimeter_stations"]]
    assert actual_codes == ["C", "MULTIPLE_IN", "W", "X", "Y"]


def test_train_perimeter_cyclic(db_session: Session, mock_perimeter_data: typing.Any) -> None:
    # Covers: 4
    snap_id = mock_perimeter_data["snap_id"]
    res = calculate_train_topological_perimeter_expansion(db_session, snap_id, "T4")
    
    # A->B->A->B should collapse to exactly 2 distinct identities
    assert res["route_station_count"] == 2
    assert res["perimeter_station_count"] == 5 
    actual_codes = [s["station_code"] for s in res["perimeter_stations"]]
    assert actual_codes == ["C", "MULTIPLE_IN", "W", "X", "Y"]


def test_train_perimeter_zero_and_isolated(db_session: Session, mock_perimeter_data: typing.Any) -> None:
    # Covers: 9, 10
    snap_id = mock_perimeter_data["snap_id"]
    res = calculate_train_topological_perimeter_expansion(db_session, snap_id, "T_ZERO")
    
    assert res["route_station_count"] == 1
    assert res["perimeter_station_count"] == 0
    assert res["perimeter_expansion_ratio"] == 0.0
    assert res["perimeter_stations"] == []


def test_train_perimeter_self_connected(db_session: Session, mock_perimeter_data: typing.Any) -> None:
    # Covers: 8
    snap_id = mock_perimeter_data["snap_id"]
    res = calculate_train_topological_perimeter_expansion(db_session, snap_id, "T_SELF")
    
    assert res["route_station_count"] == 1
    assert res["perimeter_station_count"] == 0
    assert res["perimeter_stations"] == []


def test_train_perimeter_snapshot_isolation(db_session: Session, mock_perimeter_data: typing.Any) -> None:
    # Covers: 11
    snap_id = mock_perimeter_data["snap_id"]
    res = calculate_train_topological_perimeter_expansion(db_session, snap_id, "T1")
    actual_codes = [s["station_code"] for s in res["perimeter_stations"]]
    # A->OTHER_SNAP_STN exists only in snap2_id
    assert "OTHER_SNAP_STN" not in actual_codes


def test_train_perimeter_reciprocal_edges(db_session: Session, mock_perimeter_data: typing.Any) -> None:
    # Covers: 6
    snap_id = mock_perimeter_data["snap_id"]
    res = calculate_train_topological_perimeter_expansion(db_session, snap_id, "T1")
    actual_codes = [s["station_code"] for s in res["perimeter_stations"]]
    # W connects A->W and W->A. It must appear exactly once.
    assert actual_codes.count("W") == 1


def test_train_perimeter_multiple_trains_isolation(db_session: Session, mock_perimeter_data: typing.Any) -> None:
    # Covers: 16
    snap_id = mock_perimeter_data["snap_id"]
    res = calculate_train_topological_perimeter_expansion(db_session, snap_id, "T1")
    actual_codes = [s["station_code"] for s in res["perimeter_stations"]]
    # T_OTHER visits OTHER_TRAIN_STN, shouldn't affect T1
    assert "OTHER_TRAIN_STN" not in actual_codes


def test_train_perimeter_unknown(db_session: Session, mock_perimeter_data: typing.Any) -> None:
    # Covers: 14
    snap_id = mock_perimeter_data["snap_id"]
    with pytest.raises(ValueError, match="Train not found"):
        calculate_train_topological_perimeter_expansion(db_session, snap_id, "UNKNOWN")
