import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainStopObservation
from railgati.services.network import calculate_station_peak_simultaneous_presence


def setup_data(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(name="test_svc", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.add(DatasetSnapshot(id=2, source_id=source.id, status="ARCHIVED"))

    s1 = Station(code="STA")
    s2 = Station(code="STB")
    s_miss = Station(code="N_TRAINS")
    db_session.add_all([s1, s2, s_miss])
    db_session.flush()

    db_session.add_all([
        StationObservation(snapshot_id=1, station_id=s1.id, name="Station A"),
        StationObservation(snapshot_id=1, station_id=s2.id, name="Station B"),
        StationObservation(snapshot_id=1, station_id=s_miss.id, name="Station No Trains"),
    ])

    # t1: normal interval
    # t2: identical exact interval boundary
    # t3: cross midnight
    # t4: missing arrival (origin) -> skipped
    # t5: missing departure (dest) -> skipped
    # t6: identical arrival before departure ordering
    t1 = Train(number="111")
    t2 = Train(number="222")
    t3 = Train(number="333")
    t4 = Train(number="444")
    t5 = Train(number="555")
    t6 = Train(number="666")
    db_session.add_all([t1, t2, t3, t4, t5, t6])
    db_session.flush()

    # Active snapshot
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t1.id, station_id=s1.id, stop_sequence=2, arrival_time="10:00:00", departure_time="10:15:00", source_day=1),
        # Arrives exactly as T1 departs. Arrival (+1) comes before Dep (-1), so they overlap. Peak should hit 2 momentarily.
        TrainStopObservation(snapshot_id=1, train_id=t2.id, station_id=s1.id, stop_sequence=2, arrival_time="10:15:00", departure_time="10:20:00", source_day=1),
        # Cross midnight. Arrive 23:50 Day 1, Depart 00:10 Day 1 (cross logic applies)
        TrainStopObservation(snapshot_id=1, train_id=t3.id, station_id=s1.id, stop_sequence=2, arrival_time="23:50:00", departure_time="00:10:00", source_day=1),
        # Origin missing arrival (will be skipped by logic)
        TrainStopObservation(snapshot_id=1, train_id=t4.id, station_id=s1.id, stop_sequence=1, arrival_time=None, departure_time="08:00:00", source_day=1),
        # Dest missing departure (will be skipped by logic)
        TrainStopObservation(snapshot_id=1, train_id=t5.id, station_id=s1.id, stop_sequence=99, arrival_time="09:00:00", departure_time=None, source_day=1),
    ])

    # t6 overlaps with t3
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t6.id, station_id=s1.id, stop_sequence=2, arrival_time="23:55:00", departure_time="23:59:00", source_day=1),
    ])

    # Archived snapshot train (should be ignored)
    t_arch = Train(number="999")
    db_session.add(t_arch)
    db_session.flush()
    db_session.add_all([
        TrainStopObservation(snapshot_id=2, train_id=t_arch.id, station_id=s1.id, stop_sequence=2, arrival_time="10:05:00", departure_time="10:10:00", source_day=1),
    ])

    db_session.commit()
    return {"snap_id": 1, "s1": s1.code, "s2": s2.code, "s_miss": s_miss.code}

def test_service_simultaneous_presence_normal(db_session: Session) -> None:
    data = setup_data(db_session)
    res = calculate_station_peak_simultaneous_presence(db_session, data["snap_id"], data["s1"])
    # Qualifying: t1, t2, t3, t6 (4 trains)
    # T1 [10:00-10:15], T2 [10:15-10:20] -> Overlap at 10:15 => peak 2
    # T3 [23:50-00:10(+1)], T6 [23:55-23:59] -> Overlap at 23:55 => peak 2
    # So max peak is 2.
    assert res["station_code"] == "STA"
    assert res["qualifying_occurrence_count"] == 4
    assert res["peak_simultaneous_presence"] == 2

def test_service_simultaneous_presence_zero_occurrences(db_session: Session) -> None:
    data = setup_data(db_session)
    res = calculate_station_peak_simultaneous_presence(db_session, data["snap_id"], data["s_miss"])
    assert res["station_code"] == "N_TRAINS"
    assert res["qualifying_occurrence_count"] == 0
    assert res["peak_simultaneous_presence"] is None

def test_service_simultaneous_presence_not_found(db_session: Session) -> None:
    data = setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_station_peak_simultaneous_presence(db_session, data["snap_id"], "XXX")

def test_service_simultaneous_presence_snapshot_isolation(db_session: Session) -> None:
    data = setup_data(db_session)
    # The archived snapshot #2 only has t_arch
    res = calculate_station_peak_simultaneous_presence(db_session, 2, data["s1"])
    assert res["qualifying_occurrence_count"] == 1
    assert res["peak_simultaneous_presence"] == 1

def test_service_simultaneous_presence_repeated_occurrence(db_session: Session) -> None:
    data = setup_data(db_session)
    # Add a train that visits S1 twice on different sequences/days
    s1_code = data["s1"]
    s1 = db_session.query(Station).filter_by(code=s1_code).first()
    assert s1 is not None
    t3 = Train(number="T3")
    db_session.add(t3)
    db_session.flush()
    db_session.add_all([
        # Visit 1
        TrainStopObservation(snapshot_id=1, train_id=t3.id, station_id=s1.id, stop_sequence=1, arrival_time="05:00:00", departure_time="05:30:00", source_day=1),
        # Visit 2 (e.g. return journey on the same train ID)
        TrainStopObservation(snapshot_id=1, train_id=t3.id, station_id=s1.id, stop_sequence=5, arrival_time="18:00:00", departure_time="18:30:00", source_day=1)
    ])
    db_session.commit()

    # We should have 6 total occurrences now (4 from setup, 2 from T3)
    result = calculate_station_peak_simultaneous_presence(db_session, 1, s1_code)
    assert result["qualifying_occurrence_count"] == 6
    # Peak shouldn't change, they don't overlap with the peak of 2 at 10:15
    assert result["peak_simultaneous_presence"] == 2
