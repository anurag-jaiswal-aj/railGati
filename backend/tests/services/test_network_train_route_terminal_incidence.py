import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_route_terminal_incidence


@pytest.fixture
def terminal_incidence_fixtures(db_session: Session) -> typing.Any:
    # 1. Create Data Source and Active Snapshot
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.commit()
    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    # Create an INACTIVE snapshot
    inactive_snap = DatasetSnapshot(status="ARCHIVED", source_id=source.id)
    db_session.add(inactive_snap)
    db_session.commit()
    inactive_snap_id = inactive_snap.id

    # 2. Create stations
    stations = {}
    for code in ["A", "B", "C", "D", "E", "F"]:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()

    # Network Terminals in Active Snapshot:
    # T1: A -> B -> C (Terminals: A, C)
    t1 = Train(number="T1")
    db_session.add(t1)
    db_session.commit()
    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=t1.id, name="T1", type="EXP"))

    for idx, s_code in enumerate(["A", "B", "C"]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap_id,
                train_id=t1.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1,
            )
        )

    # T2: D -> E (Terminals: D, E)
    t2 = Train(number="T2")
    db_session.add(t2)
    db_session.commit()
    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=t2.id, name="T2", type="EXP"))

    for idx, s_code in enumerate(["D", "E"]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap_id,
                train_id=t2.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1,
            )
        )

    # T3 (Cyclic): C -> B -> D -> C (Terminals: C)
    # Target Train for Cyclic Tests
    t3 = Train(number="T3_CYCLIC")
    db_session.add(t3)
    db_session.commit()
    db_session.add(
        TrainObservation(snapshot_id=snap_id, train_id=t3.id, name="T3_CYCLIC", type="EXP")
    )

    for idx, s_code in enumerate(["C", "B", "D", "C"]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap_id,
                train_id=t3.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1,
            )
        )

    # T4: F -> A (Terminals: F, A) in INACTIVE snapshot
    t4 = Train(number="T4_INACTIVE")
    db_session.add(t4)
    db_session.commit()
    db_session.add(
        TrainObservation(
            snapshot_id=inactive_snap_id, train_id=t4.id, name="T4_INACTIVE", type="EXP"
        )
    )

    for idx, s_code in enumerate(["F", "A"]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=inactive_snap_id,
                train_id=t4.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1,
            )
        )

    # T5: B -> F (Terminals: B, F)
    # B is a terminal because of T5
    t5 = Train(number="T5")
    db_session.add(t5)
    db_session.commit()
    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=t5.id, name="T5", type="EXP"))

    for idx, s_code in enumerate(["B", "F"]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap_id,
                train_id=t5.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1,
            )
        )

    db_session.commit()

    return {"snapshot_id": snap_id, "stations": stations}


def test_calculate_train_route_terminal_incidence_normal(
    db_session: Session, terminal_incidence_fixtures: typing.Any
) -> None:
    # T1 Route: A -> B -> C
    # Terminals in snapshot: A(T1), C(T1, T3), D(T2, T3), E(T2), B(T5), F(T5)
    # Wait, in the active snapshot, the global terminals are: A, C, D, E, B, F.
    # Oh! B is a terminal because of T5.
    # So T1 stops are A, B, C. All 3 are terminals.

    # Let's add a train with non-terminal stops.
    t_normal = Train(number="T_NORMAL")
    db_session.add(t_normal)
    db_session.commit()
    db_session.add(
        TrainObservation(
            snapshot_id=terminal_incidence_fixtures["snapshot_id"],
            train_id=t_normal.id,
            name="T_NORMAL",
            type="EXP",
        )
    )

    # Create stations X, Y, Z
    s_x = Station(code="X")
    s_y = Station(code="Y")
    s_z = Station(code="Z")
    db_session.add_all([s_x, s_y, s_z])
    db_session.commit()

    # Route: X -> Y -> Z
    # Terminals: X (start), Z (end). Y is not a terminal.
    for idx, st in enumerate([s_x, s_y, s_z]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=terminal_incidence_fixtures["snapshot_id"],
                train_id=t_normal.id,
                station_id=st.id,
                stop_sequence=idx + 1,
            )
        )
    db_session.commit()

    res = calculate_train_route_terminal_incidence(db_session, "T_NORMAL")

    assert res["train_number"] == "T_NORMAL"
    assert res["route_stop_occurrence_count"] == 3
    assert res["distinct_route_station_count"] == 3
    # X and Z are terminals
    assert res["terminal_occurrence_count"] == 2
    assert res["distinct_terminal_station_count"] == 2
    assert res["incidence_ratio"] == round(2.0 / 3.0, 3)


def test_calculate_train_route_terminal_incidence_cyclic_repeated(
    db_session: Session, terminal_incidence_fixtures: typing.Any
) -> None:
    # T3_CYCLIC Route: C -> B -> D -> C
    # Terminals: C, B, D, E, A, F.
    # Wait, all of them are terminals in the active snapshot.
    # Let's count them: C (Terminal), B (Terminal), D (Terminal), C (Terminal).
    # Occurrences: 4. Route length: 4.

    # Let's make a cyclic train with a non-terminal in between.
    t_cyc = Train(number="T_CYC2")
    db_session.add(t_cyc)
    db_session.commit()
    db_session.add(
        TrainObservation(
            snapshot_id=terminal_incidence_fixtures["snapshot_id"],
            train_id=t_cyc.id,
            name="T_CYC2",
            type="EXP",
        )
    )

    s_w = Station(code="W")
    db_session.add(s_w)
    db_session.commit()

    # Route: A -> W -> A
    # A is terminal (from T1, and from T_CYC2). W is not a terminal (only mid-stop).
    for idx, st in enumerate(
        [
            terminal_incidence_fixtures["stations"]["A"],
            s_w,
            terminal_incidence_fixtures["stations"]["A"],
        ]
    ):
        db_session.add(
            TrainStopObservation(
                snapshot_id=terminal_incidence_fixtures["snapshot_id"],
                train_id=t_cyc.id,
                station_id=st.id,
                stop_sequence=idx + 1,
            )
        )
    db_session.commit()

    res = calculate_train_route_terminal_incidence(db_session, "T_CYC2")

    assert res["route_stop_occurrence_count"] == 3
    assert res["distinct_route_station_count"] == 2  # A and W
    assert res["terminal_occurrence_count"] == 2  # A (first) and A (last)
    assert res["distinct_terminal_station_count"] == 1  # Only A is terminal
    assert res["incidence_ratio"] == round(2.0 / 3.0, 3)


def test_calculate_train_route_terminal_incidence_not_found(
    db_session: Session, terminal_incidence_fixtures: typing.Any
) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_route_terminal_incidence(db_session, "INVALID_TRAIN")


def test_calculate_train_route_terminal_incidence_inactive_snapshot(
    db_session: Session, terminal_incidence_fixtures: typing.Any
) -> None:
    # T4_INACTIVE is in an INACTIVE snapshot, so it shouldn't be found by the active snapshot query
    with pytest.raises(ValueError, match="not found"):
        calculate_train_route_terminal_incidence(db_session, "T4_INACTIVE")
