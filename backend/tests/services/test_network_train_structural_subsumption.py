import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_structural_subsumption


@pytest.fixture
def subsumption_fixtures(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(
        name="test_source", url="http://test", publisher="test_publisher", license="test_license"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["A", "B", "C", "X", "Y", "Z"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    # Define trains
    # 1. Basic contiguous subsumption:
    # Target: T_BASIC (A, B, C)
    # Candidate: C_BASIC (X, A, B, C, Y) -> qualifies

    # 2. Reverse order rejection:
    # Candidate: C_REVERSE (X, C, B, A, Y) -> rejected

    # 3. Non-contiguous rejection:
    # Candidate: C_NONCONT (A, B, X, C, Y) -> rejected

    # 4. Repeated-station valid case:
    # Target: T_REP (A, B, A)
    # Candidate: C_REP_VALID (X, A, B, A, Y) -> qualifies

    # 5. Repeated-station false-positive case:
    # Candidate: C_REP_INVALID (X, A, B, C, A, Y) -> rejected

    # 6. Exact same route but different train:
    # Candidate: C_SAME (A, B, C) -> qualifies for T_BASIC

    # 7. Candidate shorter than target:
    # Candidate: C_SHORT (A, B) -> rejected for T_BASIC

    # 8. Multiple valid offsets / repeated sequence occurrences:
    # Target: T_MULTI (A, B)
    # Candidate: C_MULTI (A, B, C, A, B) -> qualifies (should count as 1 candidate, not 2)

    # 9. Train with duplicate identity:
    # Target: T_DUP (A, B) and another T_DUP (A, B, C)

    trains_data = [
        ("T_BASIC", ["A", "B", "C"]),
        ("C_BASIC", ["X", "A", "B", "C", "Y"]),
        ("C_REVERSE", ["X", "C", "B", "A", "Y"]),
        ("C_NONCONT", ["A", "B", "X", "C", "Y"]),
        ("T_REP", ["A", "B", "A"]),
        ("C_REP_VALID", ["X", "A", "B", "A", "Y"]),
        ("C_REP_INVALID", ["X", "A", "B", "C", "A", "Y"]),
        ("C_SAME", ["A", "B", "C"]),
        ("C_SHORT", ["A", "B"]),
        ("T_MULTI", ["A", "B"]),
        ("C_MULTI", ["A", "B", "C", "A", "B"])
    ]

    for t_num, route in trains_data:
        tr = Train(number=t_num)
        db_session.add(tr)
        db_session.commit()
        db_session.add(
            TrainObservation(snapshot_id=snap_id, train_id=tr.id, name=t_num, type="EXP")
        )
        for idx, s_code in enumerate(route):
            db_session.add(TrainStopObservation(
                snapshot_id=snap_id,
                train_id=tr.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1
            ))
        db_session.commit()

    return {"snapshot_id": snap_id, "stations": stations}


def test_subsumption_basic_cases(db_session: Session, subsumption_fixtures: typing.Any) -> None:
    res = calculate_train_structural_subsumption(db_session, subsumption_fixtures["snapshot_id"], "T_BASIC")

    assert res["train_number"] == "T_BASIC"
    assert res["is_structurally_subsumed"] is True
    # For T_BASIC (A, B, C), the valid candidates are:
    # - C_BASIC (X, A, B, C, Y)
    # - C_SAME (A, B, C)
    # - C_MULTI (A, B, C, A, B)
    # - C_REP_INVALID (X, A, B, C, A, Y)
    # Total = 4.
    assert res["subsuming_train_count"] == 4


def test_subsumption_repeated_stations(db_session: Session, subsumption_fixtures: typing.Any) -> None:
    res = calculate_train_structural_subsumption(db_session, subsumption_fixtures["snapshot_id"], "T_REP")
    # For T_REP (A, B, A), candidates:
    # - C_REP_VALID (X, A, B, A, Y) -> qualifies
    # - C_REP_INVALID (X, A, B, C, A, Y) -> rejected
    assert res["subsuming_train_count"] == 1


def test_subsumption_multiple_offsets(db_session: Session, subsumption_fixtures: typing.Any) -> None:
    res = calculate_train_structural_subsumption(db_session, subsumption_fixtures["snapshot_id"], "T_MULTI")
    # T_MULTI is A, B.
    # Candidates that contain A, B contiguously:
    # - T_BASIC (A, B, C)
    # - C_BASIC (X, A, B, C, Y)
    # - C_NONCONT (A, B, X, C, Y)
    # - T_REP (A, B, A)
    # - C_REP_VALID (X, A, B, A, Y)
    # - C_REP_INVALID (X, A, B, C, A, Y)
    # - C_SAME (A, B, C)
    # - C_SHORT (A, B)
    # - C_MULTI (A, B, C, A, B) -> occurs twice but should only count as 1 candidate!
    # Total candidates: 9 (excluding T_MULTI itself)
    assert res["subsuming_train_count"] == 9


def test_subsumption_unknown_train(db_session: Session, subsumption_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_structural_subsumption(db_session, subsumption_fixtures["snapshot_id"], "UNKNOWN")


def test_subsumption_active_snapshot_isolation(db_session: Session, subsumption_fixtures: typing.Any) -> None:
    # Query with a non-existent snapshot
    # Since the train exists, it will run the query but find 0 candidates in snapshot 999.
    res = calculate_train_structural_subsumption(db_session, 999, "T_BASIC")
    assert res["subsuming_train_count"] == 0
    assert res["is_structurally_subsumed"] is False


