import typing

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_pair_intermediate_halt_stratification


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
    db_session.flush()

    stations = {}
    for code in ["O", "D", "A", "B", "C", "X"]:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.flush()
    for st in stations.values():
        db_session.add(StationObservation(station_id=st.id, snapshot_id=2, name=f"St {st.code}"))
    db_session.flush()

    trains = {}
    for num in ["T1", "T2", "T3", "T4", "T5"]:
        t = Train(number=num)
        db_session.add(t)
        trains[num] = t
    db_session.flush()
    for t in trains.values():
        db_session.add(TrainObservation(train_id=t.id, snapshot_id=2, name=f"Train {t.number}"))
    db_session.flush()

    stops = [
        ("T1", "O", 1),
        ("T1", "A", 2),
        ("T1", "B", 3),
        ("T1", "D", 4),  # 2 intermediate halts (4-1-1=2)
        ("T2", "O", 10),
        ("T2", "C", 11),
        ("T2", "D", 12),  # 1 intermediate halt
        ("T3", "O", 5),
        ("T3", "X", 6),
        ("T3", "D", 7),  # 1 intermediate halt
        ("T4", "O", 1),
        ("T4", "D", 2),  # 0 intermediate halts (non-stop)
    ]
    for num, code, seq in stops:
        db_session.add(
            TrainStopObservation(
                snapshot_id=2,
                train_id=trains[num].id,
                stop_sequence=seq,
                station_id=stations[code].id,
            )
        )
    db_session.flush()


def test_stratification_heterogeneous(db_session: Session, setup_service_data: typing.Any) -> None:
    res = calculate_station_pair_intermediate_halt_stratification(db_session, "O", "D", 2)
    assert res["total_traversal_count"] == 4
    assert res["min_halts"] == 0
    assert res["max_halts"] == 2
    assert res["distinct_halt_strata_count"] == 3  # 0, 1, 2
    assert res["is_perfectly_homogeneous"] is False


def test_stratification_homogeneous(db_session: Session, setup_service_data: typing.Any) -> None:
    res = calculate_station_pair_intermediate_halt_stratification(db_session, "O", "X", 2)
    assert res["total_traversal_count"] == 1
    assert res["min_halts"] == 0
    assert res["max_halts"] == 0
    assert res["distinct_halt_strata_count"] == 1
    assert res["is_perfectly_homogeneous"] is True


def test_stratification_zero_traversals(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    res = calculate_station_pair_intermediate_halt_stratification(db_session, "X", "O", 2)
    assert res["total_traversal_count"] == 0
    assert res["min_halts"] is None
    assert res["max_halts"] is None
    assert res["distinct_halt_strata_count"] == 0
    assert res["is_perfectly_homogeneous"] is False


def test_stratification_same_station(db_session: Session, setup_service_data: typing.Any) -> None:
    with pytest.raises(ValueError, match="cannot be identical"):
        calculate_station_pair_intermediate_halt_stratification(db_session, "O", "O", 2)


def test_stratification_snapshot_isolation(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    res = calculate_station_pair_intermediate_halt_stratification(db_session, "O", "D", 999)
    assert res["total_traversal_count"] == 0


def test_stratification_repeated_and_cyclic(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    # Add a train that goes O -> A -> O -> D
    t = Train(number="TCYCLIC")
    db_session.add(t)
    db_session.flush()
    db_session.add(TrainObservation(train_id=t.id, snapshot_id=2, name="Cyclic"))
    db_session.flush()

    stations = {st.code: st.id for st in db_session.query(Station).all()}
    stops = [
        ("TCYCLIC", "O", 1),
        ("TCYCLIC", "A", 2),
        ("TCYCLIC", "O", 3),  # Repeated visit
        ("TCYCLIC", "D", 4),
    ]
    for _num, code, seq in stops:
        db_session.add(
            TrainStopObservation(
                snapshot_id=2, train_id=t.id, stop_sequence=seq, station_id=stations[code]
            )
        )
    db_session.flush()

    # traversals are based on the O->D pair.
    # O at seq 1 and D at seq 4 -> 2 halts.
    # O at seq 3 and D at seq 4 -> 0 halts.
    # SQL query uses `t1.stop_sequence < t2.stop_sequence`.
    # So it will match (1,4) and (3,4). That's 2 traversals for this train!
    res = calculate_station_pair_intermediate_halt_stratification(db_session, "O", "D", 2)
    # Originally 4 traversals, now +2 = 6 traversals
    assert res["total_traversal_count"] == 6
