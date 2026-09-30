import typing

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_single_station_intersections


@pytest.fixture
def mock_intersections_data(db_session: Session) -> typing.Any:
    # Cleanup
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.execute(text("DELETE FROM data_sources"))
    db_session.commit()

    source = DataSource(name="Source 61", publisher="pub", url="url", license="mit")
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stn_codes = ["A", "B", "C", "D", "X", "Y", "Z", "M", "N"]
    stations = {}
    for code in stn_codes:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()
    
    for code in stn_codes:
        db_session.add(StationObservation(station_id=stations[code].id, snapshot_id=snap_id, name=f"Stn {code}"))
    db_session.commit()

    def add_train(num: str, sequence: list[str]) -> None:
        t = Train(number=num)
        db_session.add(t)
        db_session.commit()
        db_session.add(TrainObservation(train_id=t.id, snapshot_id=snap_id, name=f"Train {num}", type="EXP"))
        for idx, code in enumerate(sequence):
            db_session.add(TrainStopObservation(
                train_id=t.id,
                snapshot_id=snap_id,
                station_id=stations[code].id,
                stop_sequence=idx + 1
            ))
        db_session.commit()

    # 1. Basic single-station intersection:
    # T = A-B-C
    add_train("T1", ["A", "B", "C"])
    # U = X-B-Y -> U qualifies at B.
    add_train("U1", ["X", "B", "Y"])

    # 2. Zero intersection:
    # U2 = X-Y-Z -> excluded.
    add_train("U2", ["X", "Y", "Z"])

    # 3. Two-station intersection:
    # U3 = X-B-C-Y -> excluded.
    add_train("U3", ["X", "B", "C", "Y"])

    # 4. Repeated target station:
    # T2 = A-B-C-B-D
    add_train("T2", ["A", "B", "C", "B", "D"])
    
    # 5. Repeated candidate station:
    # U4 = X-B-Y-B-Z -> qualifies at B exactly once for T1 (and T2)
    add_train("U4", ["X", "B", "Y", "B", "Z"])
    
    # Another target train with no intersections for itself initially
    add_train("T3", ["D", "Z"])
    
    # 6. Isolated target train with no intersections
    add_train("T4", ["M", "N"])

    return {"snapshot_id": snap_id}


def test_basic_single_intersection(db_session: Session, mock_intersections_data: typing.Any) -> None:
    snap_id = mock_intersections_data["snapshot_id"]
    res = calculate_train_single_station_intersections(db_session, snap_id, "T1")
    assert res["target_train_number"] == "T1"
    
    # U1 qualifies at B
    # U4 qualifies at B
    # U2 excluded (0)
    # U3 excluded (2)
    assert res["total_intersecting_trains"] == 2
    trains = {i["other_train_number"] for i in res["items"]}
    assert trains == {"U1", "U4"}
    
    for item in res["items"]:
        assert item["shared_station_code"] == "B"

def test_repeated_target_station(db_session: Session, mock_intersections_data: typing.Any) -> None:
    snap_id = mock_intersections_data["snapshot_id"]
    res = calculate_train_single_station_intersections(db_session, snap_id, "T2")
    assert res["target_train_number"] == "T2"
    
    # T2 visits B twice. U1 visits B once. U4 visits B twice.
    # intersection for U1 is {B} -> len 1 -> qualifies!
    # intersection for U4 is {B} -> len 1 -> qualifies!
    # intersection for U3 is {B, C} -> len 2 -> excluded!
    # intersection for T3 is {D} -> len 1 -> qualifies!
    
    assert res["total_intersecting_trains"] == 3
    trains = {i["other_train_number"]: i["shared_station_code"] for i in res["items"]}
    assert trains == {"U1": "B", "U4": "B", "T3": "D"}

def test_no_intersection(db_session: Session, mock_intersections_data: typing.Any) -> None:
    snap_id = mock_intersections_data["snapshot_id"]
    res = calculate_train_single_station_intersections(db_session, snap_id, "T4")
    assert res["target_train_number"] == "T4"
    assert res["total_intersecting_trains"] == 0
    assert res["items"] == []

def test_target_not_found(db_session: Session, mock_intersections_data: typing.Any) -> None:
    snap_id = mock_intersections_data["snapshot_id"]
    with pytest.raises(ValueError, match="not found"):
        calculate_train_single_station_intersections(db_session, snap_id, "UNKNOWN")
