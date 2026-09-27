import typing

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_neighborhood_symmetry


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

    trains = []
    for num in ["T1", "T2", "T3", "T4", "T5", "T6"]:
        t = Train(number=num)
        db_session.add(t)
        trains.append(t)
    db_session.flush()
    t_map = {t.number: t.id for t in trains}

    for num in ["T1", "T2", "T3", "T4", "T5", "T6"]:
        to = TrainObservation(snapshot_id=2, train_id=t_map[num], name=f"{num}_NAME")
        db_session.add(to)
    db_session.flush()

    stations = []
    for code in ["SYM", "ASYM", "ISOLATED", "A", "B", "C", "D"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}

    for code in ["SYM", "ASYM", "ISOLATED", "A", "B", "C", "D"]:
        so = StationObservation(
            snapshot_id=2, station_id=s_map[code], name=f"{code}_NAME", state="N/A", zone="N/A"
        )
        db_session.add(so)
    db_session.flush()

    # Create topology
    def add_edge(train_num, from_st, to_st, base_seq):
        tso1 = TrainStopObservation(
            snapshot_id=2,
            train_id=t_map[train_num],
            stop_sequence=base_seq,
            station_id=s_map[from_st],
        )
        tso2 = TrainStopObservation(
            snapshot_id=2,
            train_id=t_map[train_num],
            stop_sequence=base_seq + 1,
            station_id=s_map[to_st],
        )
        db_session.add_all([tso1, tso2])

    # SYM: outbound to A, B, C; inbound from A, B, C (Symmetric 1.0)
    add_edge("T1", "SYM", "A", 1)
    add_edge("T2", "SYM", "B", 1)
    add_edge("T3", "SYM", "C", 1)
    add_edge("T4", "A", "SYM", 3)
    add_edge("T5", "B", "SYM", 3)
    add_edge("T6", "C", "SYM", 3)

    # ASYM: outbound to A, inbound from B. Union 2, intersection 0 (Asymmetric 0.0)
    add_edge("T1", "ASYM", "A", 10)
    add_edge("T2", "B", "ASYM", 10)

    db_session.commit()
    return None


def test_calculate_neighborhood_symmetry_symmetric(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    res = calculate_station_neighborhood_symmetry(db_session, "SYM")
    assert res["outbound_destinations_count"] == 3
    assert res["inbound_origins_count"] == 3
    assert res["symmetric_neighbors_count"] == 3
    assert res["total_neighborhood_size"] == 3
    assert res["symmetry_ratio"] == 1.0
    assert res["timetable_snapshot_id"] == 2
    assert res["station_name"] == "SYM_NAME"


def test_calculate_neighborhood_symmetry_asymmetric(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    res = calculate_station_neighborhood_symmetry(db_session, "ASYM")
    assert res["outbound_destinations_count"] == 1
    assert res["inbound_origins_count"] == 1
    assert res["symmetric_neighbors_count"] == 0
    assert res["total_neighborhood_size"] == 2
    assert res["symmetry_ratio"] == 0.0


def test_calculate_neighborhood_symmetry_unknown_station(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_station_neighborhood_symmetry(db_session, "UNKNOWN")


def test_calculate_neighborhood_symmetry_isolated_station(
    db_session: Session, setup_service_data: typing.Any
) -> None:
    with pytest.raises(ValueError, match="has no adjacent scheduled timetable occurrences"):
        calculate_station_neighborhood_symmetry(db_session, "ISOLATED")
