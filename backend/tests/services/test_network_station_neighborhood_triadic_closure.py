import typing

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_neighborhood_triadic_closure


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

    stations = []
    for code in ["S", "A", "B", "C", "D", "E", "F"]:
        st = Station(code=code)
        db_session.add(st)
        stations.append(st)
    db_session.flush()

    for st in stations:
        db_session.add(StationObservation(station_id=st.id, snapshot_id=2, name=st.code + " Name"))
    for t in trains:
        db_session.add(TrainObservation(train_id=t.id, snapshot_id=2, name=t.number + " Name", type="EXP"))
    db_session.flush()

    def add_stops(t_idx, st_codes):
        t = trains[t_idx]
        for seq, c in enumerate(st_codes, start=1):
            st = next(s for s in stations if s.code == c)
            db_session.add(TrainStopObservation(
                train_id=t.id,
                snapshot_id=2,
                station_id=st.id,
                stop_sequence=seq
            ))

    add_stops(0, ["S", "A"])
    add_stops(1, ["S", "B", "A", "A"]) # S->B, B->A, A->A
    add_stops(2, ["S", "A", "B"]) # S->A, A->B
    add_stops(3, ["S", "C", "D"]) # S->C, C->D

    # Station F (outbound degree 1)
    add_stops(4, ["F", "D"])

    # Station E (outbound degree 2, 0 closures)
    add_stops(5, ["E", "A"])
    db_session.add(TrainStopObservation(train_id=trains[5].id, snapshot_id=2, station_id=stations[2].id, stop_sequence=3))

    db_session.flush()

@pytest.fixture
def setup_zero_closure(db_session: Session, setup_service_data):
    stations = {s.code: s for s in db_session.query(Station).all()}
    t7 = Train(number="T7")
    t8 = Train(number="T8")
    db_session.add_all([t7, t8])
    db_session.flush()
    db_session.add_all([
        TrainObservation(train_id=t7.id, snapshot_id=2, name="T7 Name", type="EXP"),
        TrainObservation(train_id=t8.id, snapshot_id=2, name="T8 Name", type="EXP")
    ])
    # E -> C on T7
    db_session.add_all([
        TrainStopObservation(train_id=t7.id, snapshot_id=2, station_id=stations["E"].id, stop_sequence=1),
        TrainStopObservation(train_id=t7.id, snapshot_id=2, station_id=stations["C"].id, stop_sequence=2)
    ])
    # E -> F on T8
    db_session.add_all([
        TrainStopObservation(train_id=t8.id, snapshot_id=2, station_id=stations["E"].id, stop_sequence=1),
        TrainStopObservation(train_id=t8.id, snapshot_id=2, station_id=stations["F"].id, stop_sequence=2)
    ])
    db_session.flush()


def test_triadic_closure_success(db_session: Session, setup_service_data):
    res = calculate_station_neighborhood_triadic_closure(db_session, "S")
    assert res["outbound_degree"] == 3
    assert res["possible_neighbor_pairs"] == 3
    assert res["closed_neighbor_pairs"] == 1
    assert res["triadic_closure_ratio"] == 1.0 / 3.0


def test_triadic_closure_zero_closure(db_session: Session, setup_zero_closure):
    res = calculate_station_neighborhood_triadic_closure(db_session, "E")
    assert res["outbound_degree"] == 3
    assert res["possible_neighbor_pairs"] == 3
    assert res["closed_neighbor_pairs"] == 0
    assert res["triadic_closure_ratio"] == 0.0


def test_triadic_closure_undefined_degree_1(db_session: Session, setup_service_data):
    with pytest.raises(ValueError, match="outbound_degree < 2"):
        calculate_station_neighborhood_triadic_closure(db_session, "F")


def test_triadic_closure_undefined_degree_0(db_session: Session, setup_service_data):
    with pytest.raises(ValueError, match="outbound_degree < 2"):
        calculate_station_neighborhood_triadic_closure(db_session, "D")


def test_triadic_closure_unknown_station(db_session: Session, setup_service_data):
    with pytest.raises(ValueError, match="not found"):
        calculate_station_neighborhood_triadic_closure(db_session, "UNKNOWN")


def test_triadic_closure_no_snapshot(db_session: Session):
    st = Station(code="S")
    db_session.add(st)
    db_session.flush()
    with pytest.raises(HTTPException) as exc:
        calculate_station_neighborhood_triadic_closure(db_session, "S")
    assert "no active snapshot" in exc.value.detail.lower()

def test_triadic_closure_active_station_snapshot(db_session: Session, setup_service_data):
    from railgati.models.provenance import DatasetSnapshot
    
    # Create a stale station snapshot (inactive) where X has a name
    stale_snap = DatasetSnapshot(id=99, source_id=1, status="INACTIVE")
    db_session.add(stale_snap)
    db_session.flush()

    # Create a station X that only exists in the stale snapshot
    st_x = Station(code="X")
    db_session.add(st_x)
    db_session.flush()

    db_session.add(StationObservation(station_id=st_x.id, snapshot_id=99, name="Stale Name"))
    db_session.flush()

    # Because X does not exist in the active station snapshot (id=2), it should raise a 404-mapped ValueError
    with pytest.raises(ValueError, match="not found in active station snapshot"):
        calculate_station_neighborhood_triadic_closure(db_session, "X")
