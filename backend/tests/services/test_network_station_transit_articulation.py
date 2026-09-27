import typing

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_transit_articulation


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
    for num in ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]:
        t = Train(number=num)
        db_session.add(t)
        trains.append(t)
    db_session.flush()

    stations = []
    for code in ["S", "A", "B", "C", "D", "E", "F", "X", "Y"]:
        st = Station(code=code)
        db_session.add(st)
        stations.append(st)
    db_session.flush()

    for st in stations:
        db_session.add(StationObservation(station_id=st.id, snapshot_id=2, name=st.code + " Name"))
    for t in trains:
        db_session.add(TrainObservation(train_id=t.id, snapshot_id=2, name=t.number + " Name", type="EXP"))
    db_session.flush()

    def add_stops(t_idx: int, st_codes: list[str]) -> None:
        t = trains[t_idx]
        for seq, c in enumerate(st_codes, start=1):
            st = next(s for s in stations if s.code == c)
            db_session.add(TrainStopObservation(
                train_id=t.id,
                snapshot_id=2,
                station_id=st.id,
                stop_sequence=seq
            ))

    # Basic setup for Station S
    # N_in(S) = {A, B}
    # N_out(S) = {C, D}
    # Pairs: (A, C), (A, D), (B, C), (B, D)
    add_stops(0, ["A", "S", "C"])
    add_stops(1, ["B", "S", "D"])

    # Direct edge A -> D
    add_stops(2, ["A", "D"])

    # Alternate 2-hop B -> X -> C
    add_stops(3, ["B", "X", "C"])

    # Station E (zero valid pairs)
    # E only has inbound from F, no outbound
    add_stops(4, ["F", "E"])

    # Station Y: loop path Y -> S -> Y (O=D -> excluded)
    add_stops(5, ["Y", "S", "Y"])

    db_session.flush()


def test_transit_articulation_success(db_session: Session, setup_service_data: typing.Any) -> None:
    res = calculate_station_transit_articulation(db_session, "S")
    assert res["inbound_degree"] == 3  # A, B, Y
    assert res["outbound_degree"] == 3 # C, D, Y

    # Transit pairs:
    # A->C, A->D, A->Y
    # B->C, B->D, B->Y
    # Y->C, Y->D
    # (Y->Y is excluded)
    # So 8 valid transit pairs
    assert res["transit_pairs_count"] == 8

    # Direct edge A->D means A->D is NOT dependent
    # Alt path B->X->C means B->C is NOT dependent
    # Other pairs are dependent: A->C, A->Y, B->D, B->Y, Y->C, Y->D
    assert res["articulation_pairs_count"] == 6
    assert res["articulation_ratio"] == 6.0 / 8.0


def test_transit_articulation_zero_pairs(db_session: Session, setup_service_data: typing.Any) -> None:
    with pytest.raises(ValueError, match="transit_pairs_count == 0"):
        calculate_station_transit_articulation(db_session, "E")


def test_transit_articulation_unknown_station(db_session: Session, setup_service_data: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_station_transit_articulation(db_session, "UNKNOWN")


def test_transit_articulation_no_snapshot(db_session: Session) -> None:
    st = Station(code="S")
    db_session.add(st)
    db_session.flush()
    with pytest.raises(HTTPException) as exc:
        calculate_station_transit_articulation(db_session, "S")
    assert exc.value.status_code == 503


def test_transit_articulation_active_station_snapshot(db_session: Session, setup_service_data: typing.Any) -> None:
    stale_snap = DatasetSnapshot(id=99, source_id=1, status="INACTIVE")
    db_session.add(stale_snap)
    db_session.flush()

    st_x = Station(code="Z")
    db_session.add(st_x)
    db_session.flush()

    db_session.add(StationObservation(station_id=st_x.id, snapshot_id=99, name="Stale Name"))
    db_session.flush()

    with pytest.raises(ValueError, match="not found in active station snapshot"):
        calculate_station_transit_articulation(db_session, "Z")
