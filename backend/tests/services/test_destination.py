"""Tests for direct destination discovery."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from railgati.api.v1.schemas import TimingConfidence
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainStopObservation
from railgati.services.destination import find_direct_destinations


@pytest.fixture
def destination_data(db_session: Session) -> dict[str, int]:
    """Fixture providing test data for destination discovery."""
    source = DataSource(name="Dest Source", url="http://test", publisher="Test", license="CC0")
    db_session.add(source)
    db_session.commit()

    snap1 = DatasetSnapshot(source_id=source.id, retrieved_at=datetime.now(UTC), status="ACTIVE")
    snap2 = DatasetSnapshot(source_id=source.id, retrieved_at=datetime.now(UTC), status="ACTIVE")
    db_session.add_all([snap1, snap2])
    db_session.commit()

    st_origin = Station(code="ORG")
    st_dest1 = Station(code="DST1")
    st_dest2 = Station(code="DST2")
    st_dest3 = Station(code="DST3")
    db_session.add_all([st_origin, st_dest1, st_dest2, st_dest3])
    db_session.commit()

    for st in [st_origin, st_dest1, st_dest2, st_dest3]:
        db_session.add(
            StationObservation(snapshot_id=snap1.id, station_id=st.id, name=f"Name {st.code}")
        )
        db_session.add(
            StationObservation(snapshot_id=snap2.id, station_id=st.id, name=f"Name {st.code}")
        )

    # T1: ORG -> DST1 -> DST2
    t1 = Train(number="101")
    # T2: ORG -> DST1 (missing timing)
    t2 = Train(number="102")
    # T3: ORG -> DST2 -> ORG -> DST1 (loop)
    t3 = Train(number="103")
    # T4: Snapshot 2 train: ORG -> DST3
    t4 = Train(number="104")
    # T5: ORG -> DST1 (fastest)
    t5 = Train(number="105")
    db_session.add_all([t1, t2, t3, t4, t5])
    db_session.commit()

    stops = []
    # T1
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t1.id,
                stop_sequence=1,
                station_id=st_origin.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t1.id,
                stop_sequence=2,
                station_id=st_dest1.id,
                arrival_time="12:00:00",
                source_day=1,
            ),  # 120 mins
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t1.id,
                stop_sequence=3,
                station_id=st_dest2.id,
                arrival_time="14:00:00",
                source_day=1,
            ),  # 240 mins
        ]
    )

    # T2 (missing timing)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t2.id,
                stop_sequence=1,
                station_id=st_origin.id,
                departure_time=None,
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t2.id,
                stop_sequence=2,
                station_id=st_dest1.id,
                arrival_time="13:00:00",
                source_day=1,
            ),
        ]
    )

    # T3 (loop) ORG -> DST2 -> ORG -> DST1
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t3.id,
                stop_sequence=1,
                station_id=st_origin.id,
                departure_time="08:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t3.id,
                stop_sequence=2,
                station_id=st_dest2.id,
                arrival_time="09:00:00",
                source_day=1,
            ),  # 60 mins
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t3.id,
                stop_sequence=3,
                station_id=st_origin.id,
                arrival_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t3.id,
                stop_sequence=4,
                station_id=st_dest1.id,
                arrival_time="11:00:00",
                source_day=1,
            ),  # 180 mins from stop 1
        ]
    )

    # T4 (Snapshot 2)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap2.id,
                train_id=t4.id,
                stop_sequence=1,
                station_id=st_origin.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap2.id,
                train_id=t4.id,
                stop_sequence=2,
                station_id=st_dest3.id,
                arrival_time="11:00:00",
                source_day=1,
            ),
        ]
    )

    # T5 (Fastest to DST1)
    stops.extend(
        [
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t5.id,
                stop_sequence=1,
                station_id=st_origin.id,
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=snap1.id,
                train_id=t5.id,
                stop_sequence=2,
                station_id=st_dest1.id,
                arrival_time="11:30:00",
                source_day=1,
            ),  # 90 mins
        ]
    )

    db_session.add_all(stops)
    db_session.commit()

    return {
        "snap1": snap1.id,
        "snap2": snap2.id,
        "org": st_origin.id,
        "d1": st_dest1.id,
        "d2": st_dest2.id,
        "d3": st_dest3.id,
    }


def test_direct_destinations_found(db_session: Session, destination_data: dict[str, int]) -> None:
    dests = find_direct_destinations(db_session, destination_data["snap1"], destination_data["org"])
    assert len(dests) == 2

    codes = {d.station_code for d in dests}
    assert "DST1" in codes
    assert "DST2" in codes


def test_origin_exclusion(db_session: Session, destination_data: dict[str, int]) -> None:
    dests = find_direct_destinations(db_session, destination_data["snap1"], destination_data["org"])
    codes = {d.station_code for d in dests}
    assert "ORG" not in codes


def test_downstream_semantics(db_session: Session, destination_data: dict[str, int]) -> None:
    # Query from DST2
    dests = find_direct_destinations(db_session, destination_data["snap1"], destination_data["d2"])
    # DST2 has downstream ORG and DST1 (on T3)
    codes = {d.station_code for d in dests}
    assert "ORG" in codes
    assert "DST1" in codes
    assert "DST2" not in codes


def test_multiple_trains_and_fastest_duration(
    db_session: Session, destination_data: dict[str, int]
) -> None:
    dests = find_direct_destinations(db_session, destination_data["snap1"], destination_data["org"])

    dst1 = next(d for d in dests if d.station_code == "DST1")
    # T1 (120m), T2 (None), T3 (180m), T5 (90m). Fastest is 90. Distinct trains = 4
    assert dst1.fastest_duration_minutes == 90
    assert dst1.direct_trains_count == 4
    assert dst1.timing_confidence == TimingConfidence.HIGH


def test_repeated_station_occurrence(db_session: Session, destination_data: dict[str, int]) -> None:
    # Test on a dataset where a train visits DST1 multiple times downstream
    from railgati.models.train import TrainStopObservation

    t_test = Train(number="TEST")
    db_session.add(t_test)
    db_session.commit()
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=destination_data["snap1"],
                train_id=t_test.id,
                stop_sequence=1,
                station_id=destination_data["org"],
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=destination_data["snap1"],
                train_id=t_test.id,
                stop_sequence=2,
                station_id=destination_data["d1"],
                arrival_time="11:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=destination_data["snap1"],
                train_id=t_test.id,
                stop_sequence=3,
                station_id=destination_data["d1"],
                arrival_time="12:00:00",
                source_day=1,
            ),
        ]
    )
    db_session.commit()

    dests = find_direct_destinations(db_session, destination_data["snap1"], destination_data["org"])
    dst1 = next(d for d in dests if d.station_code == "DST1")
    assert dst1.direct_trains_count == 5  # 4 old + 1 new


def test_missing_timing(db_session: Session, destination_data: dict[str, int]) -> None:
    from railgati.models.station import Station, StationObservation
    from railgati.models.train import TrainStopObservation

    st_missing = Station(code="MISSING")
    db_session.add(st_missing)
    db_session.commit()
    db_session.add(
        StationObservation(
            snapshot_id=destination_data["snap1"], station_id=st_missing.id, name="Missing"
        )
    )

    t_miss = Train(number="MISS")
    db_session.add(t_miss)
    db_session.commit()
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=destination_data["snap1"],
                train_id=t_miss.id,
                stop_sequence=1,
                station_id=destination_data["org"],
                departure_time="10:00:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=destination_data["snap1"],
                train_id=t_miss.id,
                stop_sequence=2,
                station_id=st_missing.id,
                arrival_time=None,
                source_day=1,
            ),
        ]
    )
    db_session.commit()

    dests = find_direct_destinations(db_session, destination_data["snap1"], destination_data["org"])
    missing_dest = next(d for d in dests if d.station_code == "MISSING")
    assert missing_dest.fastest_duration_minutes is None
    assert missing_dest.timing_confidence == TimingConfidence.MISSING_DATA


def test_maximum_duration_filter(db_session: Session, destination_data: dict[str, int]) -> None:
    # Without filter, DST1 (90m), DST2 (60m)
    # Filter 70m should only return DST2
    dests = find_direct_destinations(
        db_session, destination_data["snap1"], destination_data["org"], max_duration_minutes=70
    )
    assert len(dests) == 1
    assert dests[0].station_code == "DST2"


def test_max_duration_empty_result(db_session: Session, destination_data: dict[str, int]) -> None:
    dests = find_direct_destinations(
        db_session, destination_data["snap1"], destination_data["org"], max_duration_minutes=10
    )
    assert len(dests) == 0


def test_cross_day_timing(db_session: Session, destination_data: dict[str, int]) -> None:
    from railgati.models.station import Station, StationObservation
    from railgati.models.train import TrainStopObservation

    st_cross = Station(code="CROSS")
    db_session.add(st_cross)
    db_session.commit()
    db_session.add(
        StationObservation(
            snapshot_id=destination_data["snap1"], station_id=st_cross.id, name="Cross"
        )
    )

    t_cross = Train(number="CROSS")
    db_session.add(t_cross)
    db_session.commit()
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=destination_data["snap1"],
                train_id=t_cross.id,
                stop_sequence=1,
                station_id=destination_data["org"],
                departure_time="23:30:00",
                source_day=1,
            ),
            TrainStopObservation(
                snapshot_id=destination_data["snap1"],
                train_id=t_cross.id,
                stop_sequence=2,
                station_id=st_cross.id,
                arrival_time="01:30:00",
                source_day=2,
            ),
        ]
    )
    db_session.commit()

    dests = find_direct_destinations(db_session, destination_data["snap1"], destination_data["org"])
    cross = next(d for d in dests if d.station_code == "CROSS")
    assert cross.fastest_duration_minutes == 120


def test_invalid_inconsistent_timing(db_session: Session, destination_data: dict[str, int]) -> None:
    from railgati.models.station import Station, StationObservation
    from railgati.models.train import TrainStopObservation

    st_inv = Station(code="INV")
    db_session.add(st_inv)
    db_session.commit()
    db_session.add(
        StationObservation(snapshot_id=destination_data["snap1"], station_id=st_inv.id, name="Inv")
    )

    t_inv = Train(number="INV")
    db_session.add(t_inv)
    db_session.commit()
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=destination_data["snap1"],
                train_id=t_inv.id,
                stop_sequence=1,
                station_id=destination_data["org"],
                departure_time="23:30:00",
                source_day=2,
            ),
            TrainStopObservation(
                snapshot_id=destination_data["snap1"],
                train_id=t_inv.id,
                stop_sequence=2,
                station_id=st_inv.id,
                arrival_time="01:30:00",
                source_day=1,
            ),
        ]
    )
    db_session.commit()

    dests = find_direct_destinations(db_session, destination_data["snap1"], destination_data["org"])
    inv = next(d for d in dests if d.station_code == "INV")
    assert inv.fastest_duration_minutes is None
    assert inv.timing_confidence == TimingConfidence.MISSING_DATA


def test_no_destinations(db_session: Session, destination_data: dict[str, int]) -> None:
    # DST3 has no downstream destinations in snap1
    dests = find_direct_destinations(db_session, destination_data["snap1"], destination_data["d3"])
    assert len(dests) == 0


def test_snapshot_isolation(db_session: Session, destination_data: dict[str, int]) -> None:
    # Snap2 only has ORG -> DST3
    dests = find_direct_destinations(db_session, destination_data["snap2"], destination_data["org"])
    assert len(dests) == 1
    assert dests[0].station_code == "DST3"


def test_deterministic_ordering(db_session: Session, destination_data: dict[str, int]) -> None:
    dests1 = find_direct_destinations(
        db_session, destination_data["snap1"], destination_data["org"]
    )
    dests2 = find_direct_destinations(
        db_session, destination_data["snap1"], destination_data["org"]
    )

    assert [d.station_code for d in dests1] == [d.station_code for d in dests2]
    # Sorted by duration
    assert dests1[0].station_code == "DST2"  # 60m
    assert dests1[1].station_code == "DST1"  # 90m
