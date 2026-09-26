from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from railgati.api.v1.schemas import JourneyType, TimingConfidence
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.journey import find_direct_journeys


@pytest.fixture
def test_data(db_session: Session) -> dict[str, int]:
    """Fixture providing deterministic test data."""
    # 1. Provenance
    source = DataSource(
        name="Test Source", url="http://test", publisher="Test Publisher", license="CC0"
    )
    db_session.add(source)
    db_session.commit()

    snap1 = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime.now(UTC),
        record_count=100,
        status="ACTIVE",
    )
    snap2 = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime.now(UTC),
        record_count=100,
        status="ACTIVE",
    )
    db_session.add_all([snap1, snap2])
    db_session.commit()

    # 2. Stations
    st_a = Station(code="A")
    st_b = Station(code="B")
    st_c = Station(code="C")
    st_d = Station(code="D")
    db_session.add_all([st_a, st_b, st_c, st_d])
    db_session.commit()

    # Station Observations
    for st in [st_a, st_b, st_c, st_d]:
        db_session.add(
            StationObservation(snapshot_id=snap1.id, station_id=st.id, name=f"Station {st.code}")
        )
        db_session.add(
            StationObservation(snapshot_id=snap2.id, station_id=st.id, name=f"Station {st.code}")
        )
    db_session.commit()

    # 3. Trains
    t1 = Train(number="10001")  # A -> B -> C
    t2 = Train(number="10002")  # C -> B -> A (Reverse)
    t3 = Train(number="10003")  # A -> B -> C -> B -> D (Multi-visit)
    t4 = Train(number="10004")  # A -> B (Missing Dep)
    t5 = Train(number="10005")  # A -> B (Missing Arr)
    t6 = Train(number="10006")  # A -> B (Missing Day)
    t7 = Train(number="10007")  # A -> B (Cross-day Day1 23:30 -> Day2 01:30)
    t8 = Train(number="10008")  # A -> B (Invalid Temporal: Day 2 -> Day 1)
    t9 = Train(number="10009")  # A -> B (Snapshot 2 Isolation)
    t10 = Train(number="10010")  # A -> B (Duplicate Train, Earliest valid)

    db_session.add_all([t1, t2, t3, t4, t5, t6, t7, t8, t9, t10])
    db_session.commit()

    # Observations
    for t in [t1, t2, t3, t4, t5, t6, t7, t8, t10]:
        db_session.add(
            TrainObservation(
                snapshot_id=snap1.id, train_id=t.id, name=f"Train {t.number}", type="Exp"
            )
        )
    db_session.add(
        TrainObservation(snapshot_id=snap2.id, train_id=t9.id, name="Train 10009", type="Exp")
    )

    # Stops
    stops = []

    # t1: A -> B -> C
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t1.id,
                stop_sequence=1,
                station_id=st_a.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t1.id,
                stop_sequence=2,
                station_id=st_b.id,
                arrival_time="11:30:00",
                departure_time="11:35:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t1.id,
                stop_sequence=3,
                station_id=st_c.id,
                arrival_time="13:00:00",
                source_day=1,
            ),
        ]
    )

    # t2: C -> B -> A (Reverse)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t2.id,
                stop_sequence=1,
                station_id=st_c.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t2.id,
                stop_sequence=2,
                station_id=st_b.id,
                arrival_time="11:30:00",
                departure_time="11:35:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t2.id,
                stop_sequence=3,
                station_id=st_a.id,
                arrival_time="13:00:00",
                source_day=1,
            ),
        ]
    )

    # t3: A -> B -> C -> B -> D (Multi-visit)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t3.id,
                stop_sequence=1,
                station_id=st_a.id,
                departure_time="08:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t3.id,
                stop_sequence=2,
                station_id=st_b.id,
                arrival_time="09:00:00",
                departure_time="09:10:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t3.id,
                stop_sequence=3,
                station_id=st_c.id,
                arrival_time="10:00:00",
                departure_time="10:10:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t3.id,
                stop_sequence=4,
                station_id=st_b.id,
                arrival_time="11:00:00",
                departure_time="11:10:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t3.id,
                stop_sequence=5,
                station_id=st_d.id,
                arrival_time="12:00:00",
                source_day=1,
            ),
        ]
    )

    # t4: Missing Dep (A -> B)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t4.id,
                stop_sequence=1,
                station_id=st_a.id,
                departure_time=None,
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t4.id,
                stop_sequence=2,
                station_id=st_b.id,
                arrival_time="11:30:00",
                source_day=1,
            ),
        ]
    )

    # t5: Missing Arr (A -> B)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t5.id,
                stop_sequence=1,
                station_id=st_a.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t5.id,
                stop_sequence=2,
                station_id=st_b.id,
                arrival_time=None,
                source_day=1,
            ),
        ]
    )

    # t6: Missing Day (A -> B)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t6.id,
                stop_sequence=1,
                station_id=st_a.id,
                departure_time="10:00:00",
                source_day=None,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t6.id,
                stop_sequence=2,
                station_id=st_b.id,
                arrival_time="11:30:00",
                source_day=1,
            ),
        ]
    )

    # t7: Cross Day (A -> B)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t7.id,
                stop_sequence=1,
                station_id=st_a.id,
                departure_time="23:30:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t7.id,
                stop_sequence=2,
                station_id=st_b.id,
                arrival_time="01:30:00",
                source_day=2,
            ),
        ]
    )

    # t8: Invalid Temporal (A -> B)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t8.id,
                stop_sequence=1,
                station_id=st_a.id,
                departure_time="23:30:00",
                source_day=2,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t8.id,
                stop_sequence=2,
                station_id=st_b.id,
                arrival_time="01:30:00",
                source_day=1,
            ),
        ]
    )

    # t9: Snapshot 2 (A -> B)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap2.id,
                train_id=t9.id,
                stop_sequence=1,
                station_id=st_a.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap2.id,
                train_id=t9.id,
                stop_sequence=2,
                station_id=st_b.id,
                arrival_time="11:30:00",
                source_day=1,
            ),
        ]
    )

    # t10: A -> B (Better departure time)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t10.id,
                stop_sequence=1,
                station_id=st_a.id,
                departure_time="09:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t10.id,
                stop_sequence=2,
                station_id=st_b.id,
                arrival_time="10:30:00",
                source_day=1,
            ),
        ]
    )

    db_session.add_all(stops)
    db_session.commit()

    return {
        "snap1": snap1.id,
        "snap2": snap2.id,
        "st_a": st_a.id,
        "st_b": st_b.id,
        "st_c": st_c.id,
        "st_d": st_d.id,
    }


def test_direct_journey_found_and_correct_metrics(
    db_session: Session, test_data: dict[str, int]
) -> None:
    """Test standard direct journey A -> B yields correct output."""
    journeys = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_a"], test_data["st_b"]
    )
    assert len(journeys) >= 1

    # 10001 should be one of them
    t1_journey = next(j for j in journeys if j.legs[0].train_number == "10001")
    assert t1_journey.type == JourneyType.DIRECT
    assert t1_journey.number_of_stops == 1
    assert t1_journey.total_duration_minutes == 90  # 10:00 to 11:30
    assert t1_journey.timing_confidence == TimingConfidence.HIGH
    assert t1_journey.provenance.snapshot_id == test_data["snap1"]
    assert t1_journey.legs[0].origin_station == "A"
    assert t1_journey.legs[0].destination_station == "B"


def test_direct_journey_not_found(db_session: Session, test_data: dict[str, int]) -> None:
    """Test unlinked stations yield empty."""
    journeys = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_d"], test_data["st_a"]
    )
    assert len(journeys) == 0


def test_destination_before_origin_rejected(db_session: Session, test_data: dict[str, int]) -> None:
    """Train 10001 goes A -> B -> C. C -> A should not match 10001."""
    journeys = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_c"], test_data["st_a"]
    )
    # 10001 should NOT be in there
    assert not any(j.legs[0].train_number == "10001" for j in journeys)
    # However, 10002 goes C -> A
    assert any(j.legs[0].train_number == "10002" for j in journeys)


def test_missing_departure_null_duration(db_session: Session, test_data: dict[str, int]) -> None:
    journeys = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_a"], test_data["st_b"]
    )
    t4 = next(j for j in journeys if j.legs[0].train_number == "10004")
    assert t4.total_duration_minutes is None
    assert t4.timing_confidence == TimingConfidence.MISSING_DATA


def test_missing_arrival_null_duration(db_session: Session, test_data: dict[str, int]) -> None:
    journeys = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_a"], test_data["st_b"]
    )
    t5 = next(j for j in journeys if j.legs[0].train_number == "10005")
    assert t5.total_duration_minutes is None
    assert t5.timing_confidence == TimingConfidence.MISSING_DATA


def test_missing_source_day_null_duration(db_session: Session, test_data: dict[str, int]) -> None:
    journeys = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_a"], test_data["st_b"]
    )
    t6 = next(j for j in journeys if j.legs[0].train_number == "10006")
    assert t6.total_duration_minutes is None
    assert t6.timing_confidence == TimingConfidence.MISSING_DATA


def test_cross_day_duration(db_session: Session, test_data: dict[str, int]) -> None:
    journeys = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_a"], test_data["st_b"]
    )
    t7 = next(j for j in journeys if j.legs[0].train_number == "10007")
    # 23:30 Day 1 to 01:30 Day 2 = 120 mins
    assert t7.total_duration_minutes == 120
    assert t7.timing_confidence == TimingConfidence.HIGH


def test_invalid_temporal_ordering_null_duration(
    db_session: Session, test_data: dict[str, int]
) -> None:
    journeys = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_a"], test_data["st_b"]
    )
    t8 = next(j for j in journeys if j.legs[0].train_number == "10008")
    assert t8.total_duration_minutes is None
    assert t8.timing_confidence == TimingConfidence.MISSING_DATA


def test_multiple_station_visits_handled_correctly(
    db_session: Session, test_data: dict[str, int]
) -> None:
    # 10003 visits B twice (stops 2 and 4). A is stop 1.
    # It should pick A -> first B (stop 2).
    journeys = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_a"], test_data["st_b"]
    )
    t3 = next(j for j in journeys if j.legs[0].train_number == "10003")
    assert t3.number_of_stops == 1  # Stop 2 - Stop 1 = 1
    assert t3.total_duration_minutes == 60  # 08:00 to 09:00


def test_snapshot_isolation(db_session: Session, test_data: dict[str, int]) -> None:
    journeys1 = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_a"], test_data["st_b"]
    )
    journeys2 = find_direct_journeys(
        db_session, test_data["snap2"], test_data["st_a"], test_data["st_b"]
    )

    assert any(j.legs[0].train_number == "10001" for j in journeys1)
    assert not any(j.legs[0].train_number == "10009" for j in journeys1)

    assert any(j.legs[0].train_number == "10009" for j in journeys2)
    assert not any(j.legs[0].train_number == "10001" for j in journeys2)


def test_deterministic_ordering(db_session: Session, test_data: dict[str, int]) -> None:
    journeys = find_direct_journeys(
        db_session, test_data["snap1"], test_data["st_a"], test_data["st_b"]
    )
    # 10003 Dep: 08:00
    # 10010 Dep: 09:00
    # 10001 Dep: 10:00
    # etc...
    # Should be sorted by departure time first
    assert len(journeys) >= 3

    # Remove nulls for check and verify sorted
    assert journeys[0].legs[0].train_number == "10003"  # 08:00
    assert journeys[1].legs[0].train_number == "10010"  # 09:00
    assert journeys[2].legs[0].train_number == "10001"  # 10:00
