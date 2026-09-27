import pytest
from sqlalchemy.orm import Session

from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainStopObservation
from railgati.services.network import calculate_station_similarity


def setup_data(db_session: Session) -> tuple[int, Station, Station, Station, Station]:
    snap_id = 1
    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    s4 = Station(code="D")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=snap_id, station_id=s1.id, name="Station A"),
            StationObservation(snapshot_id=snap_id, station_id=s2.id, name="Station B"),
            StationObservation(snapshot_id=snap_id, station_id=s3.id, name="Station C"),
            StationObservation(snapshot_id=snap_id, station_id=s4.id, name="Station D"),
        ]
    )

    return snap_id, s1, s2, s3, s4


def test_calculate_station_similarity_perfect_match(db_session: Session) -> None:
    snap_id, s1, s2, _, _ = setup_data(db_session)
    t1 = Train(number="111")
    t2 = Train(number="222")
    db_session.add_all([t1, t2])
    db_session.flush()

    # Both Station A and Station B share Train 111 and 222
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=1, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=2, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=1, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=2, station_id=s1.id
            ),
        ]
    )
    db_session.commit()

    count, resolved_code, _, items = calculate_station_similarity(db_session, snap_id, "a")
    assert count == 2
    assert resolved_code == "A"
    assert len(items) == 1
    assert items[0].station_code == "B"
    assert items[0].overlap_train_count == 2
    assert items[0].compared_train_count == 2
    assert items[0].union_train_count == 2
    assert items[0].similarity_pct == 100.0


def test_calculate_station_similarity_partial(db_session: Session) -> None:
    snap_id, s1, s2, _s3, _ = setup_data(db_session)
    t1 = Train(number="111")
    t2 = Train(number="222")
    t3 = Train(number="333")
    db_session.add_all([t1, t2, t3])
    db_session.flush()

    # Station A has t1, t2
    # Station B has t2, t3
    # Overlap: t2 (1). Union: t1, t2, t3 (3). Jaccard: 1/3 = 33.3%
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=1, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=1, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=2, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t3.id, stop_sequence=1, station_id=s2.id
            ),
        ]
    )
    db_session.commit()

    _, _, _, items = calculate_station_similarity(db_session, snap_id, "A")
    assert len(items) == 1
    assert items[0].station_code == "B"
    assert items[0].overlap_train_count == 1
    assert items[0].compared_train_count == 2
    assert items[0].union_train_count == 3
    assert items[0].similarity_pct == 33.3


def test_calculate_station_similarity_repeated_visits(db_session: Session) -> None:
    snap_id, s1, s2, _, _ = setup_data(db_session)
    t1 = Train(number="111")
    db_session.add_all([t1])
    db_session.flush()

    # t1 loops A -> B -> A.
    # Distinct trains for A: 1. Distinct trains for B: 1.
    # Overlap: 1. Union: 1. Jaccard: 100%
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=1, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=2, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=3, station_id=s1.id
            ),
        ]
    )
    db_session.commit()

    count, _, _, items = calculate_station_similarity(db_session, snap_id, "A")
    assert count == 1  # distinct count!
    assert len(items) == 1
    assert items[0].overlap_train_count == 1
    assert items[0].compared_train_count == 1
    assert items[0].union_train_count == 1
    assert items[0].similarity_pct == 100.0


def test_calculate_station_similarity_ordering(db_session: Session) -> None:
    snap_id, s1, s2, s3, s4 = setup_data(db_session)
    t1 = Train(number="111")
    t2 = Train(number="222")
    db_session.add_all([t1, t2])
    db_session.flush()

    # Station A: t1, t2
    # Station B: t1, t2
    # Station C: t1, t2
    # Station D: t1
    # B and C have 100% similarity. Should break tie by code ASC.
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=1, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=2, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=3, station_id=s3.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=4, station_id=s3.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=5, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=6, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=7, station_id=s4.id
            ),
        ]
    )
    db_session.commit()

    _, _, _, items = calculate_station_similarity(db_session, snap_id, "A")
    assert len(items) == 3
    # Order: sim DESC, overlap DESC, union ASC, code ASC
    # B and C tie on sim(100), overlap(2), union(2). B comes before C.
    assert items[0].station_code == "B"
    assert items[1].station_code == "C"
    # D has sim(50), overlap(1), union(2).
    assert items[2].station_code == "D"


def test_calculate_station_similarity_not_found(db_session: Session) -> None:
    snap_id, _, _, _, _ = setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_station_similarity(db_session, snap_id, "XXX")
