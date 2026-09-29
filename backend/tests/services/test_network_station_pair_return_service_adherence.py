import typing

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_pair_return_service_adherence


@pytest.fixture
def setup_service_data(db_session: Session) -> typing.Any:
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.flush()

    snapshot = DatasetSnapshot(id=2, source_id=1, status="ACTIVE")
    db_session.add(snapshot)

    snapshot_other = DatasetSnapshot(id=3, source_id=1, status="ACTIVE")
    db_session.add(snapshot_other)
    db_session.flush()

    stations = {}
    for code in ["O", "D", "A", "B"]:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.flush()
    for st in stations.values():
        db_session.add(StationObservation(station_id=st.id, snapshot_id=2, name=f"St {st.code}"))
        db_session.add(StationObservation(station_id=st.id, snapshot_id=3, name=f"St {st.code}"))
    db_session.flush()

    trains = {}
    for num in ["T1", "R1", "T2", "R2", "T3", "R3", "T4", "T5", "R5", "T6", "R6_OTHER_SNAP", "TCYCLIC", "RCYCLIC"]:
        t = Train(number=num)
        db_session.add(t)
        trains[num] = t
    db_session.flush()

    # Setup train observations
    # T1 -> valid adherent R1
    db_session.add(TrainObservation(train_id=trains["T1"].id, snapshot_id=2, name="T1", return_train_number="R1"))
    db_session.add(TrainObservation(train_id=trains["R1"].id, snapshot_id=2, name="R1", return_train_number="T1"))

    # T2 -> non-adherent R2 (R2 doesn't visit D->O properly)
    db_session.add(TrainObservation(train_id=trains["T2"].id, snapshot_id=2, name="T2", return_train_number="R2"))
    db_session.add(TrainObservation(train_id=trains["R2"].id, snapshot_id=2, name="R2", return_train_number="T2"))

    # T3 -> non-adherent R3 (R3 is missing from DB completely or from snapshot)
    db_session.add(TrainObservation(train_id=trains["T3"].id, snapshot_id=2, name="T3", return_train_number="R3"))
    # R3 not in train_observations for snap 2

    # T4 -> missing return_train_number
    db_session.add(TrainObservation(train_id=trains["T4"].id, snapshot_id=2, name="T4", return_train_number=None))

    # T5 -> non-adherent R5 (R5 exists but visits O->D, not D->O)
    db_session.add(TrainObservation(train_id=trains["T5"].id, snapshot_id=2, name="T5", return_train_number="R5"))
    db_session.add(TrainObservation(train_id=trains["R5"].id, snapshot_id=2, name="R5", return_train_number="T5"))

    # T6 -> return train in another snapshot
    db_session.add(TrainObservation(train_id=trains["T6"].id, snapshot_id=2, name="T6", return_train_number="R6_OTHER_SNAP"))
    db_session.add(TrainObservation(train_id=trains["R6_OTHER_SNAP"].id, snapshot_id=3, name="R6", return_train_number="T6"))

    # TCYCLIC
    db_session.add(TrainObservation(train_id=trains["TCYCLIC"].id, snapshot_id=2, name="TC", return_train_number="RCYCLIC"))
    db_session.add(TrainObservation(train_id=trains["RCYCLIC"].id, snapshot_id=2, name="RC", return_train_number="TCYCLIC"))

    db_session.flush()

    stops = [
        # T1 forward O->D
        (2, "T1", "O", 1),
        (2, "T1", "D", 2),
        # R1 return D->O
        (2, "R1", "D", 1),
        (2, "R1", "O", 2),

        # T2 forward O->D
        (2, "T2", "O", 1),
        (2, "T2", "D", 2),
        # R2 return (only visits D)
        (2, "R2", "D", 1),
        (2, "R2", "A", 2),

        # T3 forward O->D
        (2, "T3", "O", 1),
        (2, "T3", "D", 2),

        # T4 forward O->D
        (2, "T4", "O", 1),
        (2, "T4", "D", 2),

        # T5 forward O->D
        (2, "T5", "O", 1),
        (2, "T5", "D", 2),
        # R5 returns O->D instead of D->O
        (2, "R5", "O", 1),
        (2, "R5", "D", 2),

        # T6 forward O->D
        (2, "T6", "O", 1),
        (2, "T6", "D", 2),
        # R6 return D->O in snap 3
        (3, "R6_OTHER_SNAP", "D", 1),
        (3, "R6_OTHER_SNAP", "O", 2),

        # TCYCLIC O(1)->D(3)->O(5)->D(7)
        (2, "TCYCLIC", "O", 1),
        (2, "TCYCLIC", "D", 3),
        (2, "TCYCLIC", "O", 5),
        (2, "TCYCLIC", "D", 7),

        # RCYCLIC D(1)->O(3)->D(5)->O(7) multiple D->O
        (2, "RCYCLIC", "D", 1),
        (2, "RCYCLIC", "O", 3),
        (2, "RCYCLIC", "D", 5),
        (2, "RCYCLIC", "O", 7),
    ]
    for snap, num, code, seq in stops:
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap,
                train_id=trains[num].id,
                stop_sequence=seq,
                station_id=stations[code].id,
            )
        )
    db_session.flush()

def test_return_adherence_valid_pair(db_session: Session, setup_service_data: typing.Any) -> None:
    res = calculate_station_pair_return_service_adherence(db_session, "O", "D", 2)
    assert res["total_forward_traversal_count"] == 11
    assert res["unpaired_traversal_count"] == 1
    assert res["adherent_return_traversal_count"] == 5
    assert res["non_adherent_return_traversal_count"] == 5
    assert res["adherence_ratio"] == 5 / 11
    assert res["unpaired_ratio"] == 1 / 11
    assert res["non_adherent_ratio"] == 5 / 11

def test_return_adherence_zero_traversals(db_session: Session, setup_service_data: typing.Any) -> None:
    res = calculate_station_pair_return_service_adherence(db_session, "A", "B", 2)
    assert res["total_forward_traversal_count"] == 0
    assert res["unpaired_traversal_count"] == 0
    assert res["adherent_return_traversal_count"] == 0
    assert res["non_adherent_return_traversal_count"] == 0
    assert res["adherence_ratio"] is None
    assert res["unpaired_ratio"] is None
    assert res["non_adherent_ratio"] is None

def test_return_adherence_same_station(db_session: Session, setup_service_data: typing.Any) -> None:
    with pytest.raises(ValueError, match="cannot be identical"):
        calculate_station_pair_return_service_adherence(db_session, "O", "O", 2)

def test_return_adherence_snapshot_isolation(db_session: Session, setup_service_data: typing.Any) -> None:
    res = calculate_station_pair_return_service_adherence(db_session, "O", "D", 999)
    assert res["total_forward_traversal_count"] == 0
