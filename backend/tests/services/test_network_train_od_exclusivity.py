import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_route_od_exclusivity


@pytest.fixture
def od_exclusivity_fixtures(db_session: Session) -> typing.Any:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.commit()
    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    # Create stations
    stations = {}
    for code in ["A", "B", "C", "D", "E"]:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()

    # Target Train: TARGET (A -> B -> C -> D)
    tr = Train(number="TARGET")
    db_session.add(tr)
    db_session.commit()
    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=tr.id, name="TARGET", type="EXP"))

    for idx, s_code in enumerate(["A", "B", "C", "D"]):
        db_session.add(TrainStopObservation(
            snapshot_id=snap_id, train_id=tr.id, station_id=stations[s_code].id, stop_sequence=idx + 1
        ))
    db_session.commit()

    # Candidate trains to test edge cases
    candidates = [
        ("M_A_C", ["A", "C"]),            # Shared: A->C
        ("M_B_A", ["B", "A"]),            # Reverse: B->A (should not share A->B)
        ("M_A_X_D", ["A", "E", "D"]),     # Shared: A->D
        ("M_D_C_B", ["D", "C", "B"]),     # Reverse: D->C, C->B, D->B
        ("M_MULT", ["A", "E", "B"]),      # Shared: A->B
    ]

    for t_num, route in candidates:
        cand_tr = Train(number=t_num)
        db_session.add(cand_tr)
        db_session.commit()
        db_session.add(TrainObservation(snapshot_id=snap_id, train_id=cand_tr.id, name=t_num, type="EXP"))
        for idx, s_code in enumerate(route):
            db_session.add(TrainStopObservation(
                snapshot_id=snap_id, train_id=cand_tr.id, station_id=stations[s_code].id, stop_sequence=idx + 1
            ))
    db_session.commit()

    # Now let's test repeated stations in the target train.
    # Target 2: A -> B -> A -> C
    tr2 = Train(number="T2")
    db_session.add(tr2)
    db_session.commit()
    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=tr2.id, name="T2", type="EXP"))

    for idx, s_code in enumerate(["A", "B", "A", "C"]):
        db_session.add(TrainStopObservation(
            snapshot_id=snap_id, train_id=tr2.id, station_id=stations[s_code].id, stop_sequence=idx + 1
        ))
    db_session.commit()

    # Train with no exclusive pairs
    tr3 = Train(number="NO_EXC")
    db_session.add(tr3)
    db_session.commit()
    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=tr3.id, name="NO_EXC", type="EXP"))
    for idx, s_code in enumerate(["A", "C"]):
        db_session.add(TrainStopObservation(
            snapshot_id=snap_id, train_id=tr3.id, station_id=stations[s_code].id, stop_sequence=idx + 1
        ))
    db_session.commit()

    return {"snapshot_id": snap_id, "stations": stations}


def test_calculate_train_route_od_exclusivity_success(db_session: Session, od_exclusivity_fixtures: typing.Any) -> None:
    # Target A->B->C->D has pairs:
    # (A,B), (A,C), (A,D), (B,C), (B,D), (C,D)
    # Candidates:
    # M_A_C shares A->C
    # M_B_A shares B->A (reverse, so target's A->B is NOT shared by this)
    # M_A_X_D shares A->D
    # M_MULT shares A->B
    # M_D_C_B shares D->C, C->B, D->B (all reverse, so no target pairs shared)

    # Target pairs:
    # A->B : shared by M_MULT
    # B->C : shared by T2 (which goes B->A->C)
    # B->D : NOT shared
    # C->D : NOT shared

    res = calculate_train_route_od_exclusivity(db_session, "TARGET")
    assert res["target_train_number"] == "TARGET"

    pairs = res["exclusive_od_pairs"]
    assert len(pairs) == 2
    assert res["exclusive_od_pair_count"] == 2

    # B->D
    assert pairs[0]["origin_station_code"] == "B"
    assert pairs[0]["destination_station_code"] == "D"
    assert pairs[0]["origin_stop_sequence"] == 2
    assert pairs[0]["destination_stop_sequence"] == 4

    # C->D
    assert pairs[1]["origin_station_code"] == "C"
    assert pairs[1]["destination_station_code"] == "D"
    assert pairs[1]["origin_stop_sequence"] == 3
    assert pairs[1]["destination_stop_sequence"] == 4


def test_calculate_train_route_od_exclusivity_repeated_stops(db_session: Session, od_exclusivity_fixtures: typing.Any) -> None:
    # Target 2: A(1) -> B(2) -> A(3) -> C(4)
    # Pairs:
    # A(1)->B(2): shared by M_MULT
    # A(1)->A(3): impossible for candidate to share unless candidate also goes A->A
    # A(1)->C(4): shared by M_A_C
    # B(2)->A(3): shared by M_B_A
    # B(2)->C(4): shared by TARGET (B->C)
    # A(3)->C(4): shared by M_A_C

    res = calculate_train_route_od_exclusivity(db_session, "T2")
    pairs = res["exclusive_od_pairs"]

    # Exclusive: A(1)->A(3)
    assert len(pairs) == 1

    assert pairs[0]["origin_station_code"] == "A"
    assert pairs[0]["destination_station_code"] == "A"
    assert pairs[0]["origin_stop_sequence"] == 1
    assert pairs[0]["destination_stop_sequence"] == 3


def test_calculate_train_route_od_exclusivity_no_exclusive(db_session: Session, od_exclusivity_fixtures: typing.Any) -> None:
    # NO_EXC goes A->C. This is shared by M_A_C.
    res = calculate_train_route_od_exclusivity(db_session, "NO_EXC")
    assert res["exclusive_od_pair_count"] == 0
    assert len(res["exclusive_od_pairs"]) == 0


def test_calculate_train_route_od_exclusivity_not_found(db_session: Session, od_exclusivity_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_route_od_exclusivity(db_session, "INVALID")
