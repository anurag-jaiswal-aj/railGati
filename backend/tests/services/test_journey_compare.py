from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from railgati.api.v1.schemas import JourneyType, TimingConfidence
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.journey import compare_journeys


@pytest.fixture
def compare_data(db_session: Session) -> dict[str, int]:
    src = DataSource(name="Compare Source", url="http://test", publisher="Test", license="CC0")
    db_session.add(src)
    db_session.commit()

    snap = DatasetSnapshot(source_id=src.id, retrieved_at=datetime.now(UTC), status="ACTIVE")
    db_session.add(snap)
    db_session.commit()

    s_a = Station(code="STA")
    s_b = Station(code="STB")
    s_c = Station(code="STC")
    db_session.add_all([s_a, s_b, s_c])
    db_session.commit()

    # Train 1: Direct A -> C
    t1 = Train(number="1001")
    db_session.add(t1)
    db_session.commit()
    db_session.add(
        TrainObservation(snapshot_id=snap.id, train_id=t1.id, name="Direct 1", type="Type")
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t1.id,
            station_id=s_a.id,
            stop_sequence=1,
            departure_time="08:00:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t1.id,
            station_id=s_c.id,
            stop_sequence=2,
            arrival_time="12:00:00",
            source_day=1,
        )
    )

    # Train 2 & 3: Transfer A -> B, B -> C
    t2 = Train(number="1002")
    t3 = Train(number="1003")
    db_session.add_all([t2, t3])
    db_session.commit()

    db_session.add(
        TrainObservation(snapshot_id=snap.id, train_id=t2.id, name="Trans 1", type="Type")
    )
    db_session.add(
        TrainObservation(snapshot_id=snap.id, train_id=t3.id, name="Trans 2", type="Type")
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t2.id,
            station_id=s_a.id,
            stop_sequence=1,
            departure_time="06:00:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t2.id,
            station_id=s_b.id,
            stop_sequence=2,
            arrival_time="08:00:00",
            source_day=1,
        )
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t3.id,
            station_id=s_b.id,
            stop_sequence=1,
            departure_time="10:00:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t3.id,
            station_id=s_c.id,
            stop_sequence=2,
            arrival_time="14:00:00",
            source_day=1,
        )
    )

    # Train 4: Direct A -> C (Missing Data)
    t4 = Train(number="1004")
    db_session.add(t4)
    db_session.commit()
    db_session.add(
        TrainObservation(snapshot_id=snap.id, train_id=t4.id, name="Direct 2", type="Type")
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t4.id,
            station_id=s_a.id,
            stop_sequence=1,
            departure_time=None,
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t4.id,
            station_id=s_c.id,
            stop_sequence=2,
            arrival_time="16:00:00",
            source_day=1,
        )
    )

    db_session.commit()

    return {
        "snap": snap.id,
        "st_a": s_a.id,
        "st_b": s_b.id,
        "st_c": s_c.id,
    }


def test_max_transfers_0(db_session: Session, compare_data: dict[str, int]) -> None:
    opts = compare_journeys(
        db_session,
        compare_data["snap"],
        compare_data["st_a"],
        compare_data["st_c"],
        max_transfers=0,
    )

    assert len(opts) > 0
    assert all(o.type == JourneyType.DIRECT for o in opts)
    # T1 and T4 are direct
    trains = {o.legs[0].train_number for o in opts}
    assert "1001" in trains
    assert "1004" in trains
    assert "1002" not in trains


def test_max_transfers_1(db_session: Session, compare_data: dict[str, int]) -> None:
    opts = compare_journeys(
        db_session,
        compare_data["snap"],
        compare_data["st_a"],
        compare_data["st_c"],
        max_transfers=1,
    )

    assert len(opts) == 3
    types = [o.type for o in opts]
    assert JourneyType.DIRECT in types
    assert JourneyType.ONE_TRANSFER in types


def test_invalid_max_transfers(db_session: Session, compare_data: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        compare_journeys(
            db_session,
            compare_data["snap"],
            compare_data["st_a"],
            compare_data["st_c"],
            max_transfers=-1,
        )

    with pytest.raises(ValueError):
        compare_journeys(
            db_session,
            compare_data["snap"],
            compare_data["st_a"],
            compare_data["st_c"],
            max_transfers=2,
        )


def test_no_direct_journey(db_session: Session, compare_data: dict[str, int]) -> None:
    # A -> B only has direct, let's verify.
    # Actually, A -> B has T2 direct. C -> A has nothing.
    opts = compare_journeys(
        db_session,
        compare_data["snap"],
        compare_data["st_c"],
        compare_data["st_a"],
        max_transfers=1,
    )
    assert len(opts) == 0


def test_missing_duration_sorting(db_session: Session, compare_data: dict[str, int]) -> None:
    opts = compare_journeys(
        db_session,
        compare_data["snap"],
        compare_data["st_a"],
        compare_data["st_c"],
        max_transfers=1,
    )

    # 1. T1: 08:00 - 12:00 = 4h = 240m (DIRECT)
    # 2. T2->T3: 06:00 - 14:00 = 8h = 480m (TRANSFER)
    # 3. T4: None - 16:00 = None (DIRECT)

    assert opts[0].legs[0].train_number == "1001"
    assert opts[0].total_duration_minutes == 240

    assert opts[1].legs[0].train_number == "1002"
    assert opts[1].total_duration_minutes == 480

    assert opts[2].legs[0].train_number == "1004"
    assert opts[2].total_duration_minutes is None
    assert opts[2].timing_confidence == TimingConfidence.MISSING_DATA


def test_deterministic_ordering(db_session: Session, compare_data: dict[str, int]) -> None:
    opts1 = compare_journeys(
        db_session,
        compare_data["snap"],
        compare_data["st_a"],
        compare_data["st_c"],
        max_transfers=1,
    )
    opts2 = compare_journeys(
        db_session,
        compare_data["snap"],
        compare_data["st_a"],
        compare_data["st_c"],
        max_transfers=1,
    )

    assert [o.journey_id for o in opts1] == [o.journey_id for o in opts2]


def test_journey_identity(db_session: Session, compare_data: dict[str, int]) -> None:
    opts = compare_journeys(
        db_session,
        compare_data["snap"],
        compare_data["st_a"],
        compare_data["st_c"],
        max_transfers=1,
    )
    ids = [o.journey_id for o in opts]
    assert len(ids) == len(set(ids))


def test_neither_direct_nor_one_transfer_returns_empty(
    db_session: Session, compare_data: dict[str, int]
) -> None:
    # Station C to Station A has no direct trains and no transfer possibilities
    opts1 = compare_journeys(
        db_session,
        compare_data["snap"],
        compare_data["st_c"],
        compare_data["st_a"],
        max_transfers=1,
    )
    assert len(opts1) == 0
    assert opts1 == []

    # Verify deterministic empty result
    opts2 = compare_journeys(
        db_session,
        compare_data["snap"],
        compare_data["st_c"],
        compare_data["st_a"],
        max_transfers=1,
    )
    assert opts1 == opts2
