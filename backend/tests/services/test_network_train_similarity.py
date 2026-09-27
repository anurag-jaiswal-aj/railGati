import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_similarity


def setup_data(db_session: Session) -> tuple[int, Station, Station, Station, Station]:
    source = DataSource(name="test_api", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    s4 = Station(code="D")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    return 1, s1, s2, s3, s4


def test_calculate_train_similarity_perfect_match(db_session: Session) -> None:
    snap_id, s1, s2, s3, _ = setup_data(db_session)
    t1 = Train(number="111")
    t2 = Train(number="222")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=snap_id, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=snap_id, train_id=t2.id, name="T2"),
        ]
    )

    # t1: A, B, C
    # t2: C, B, A
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=1, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=2, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=3, station_id=s3.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=1, station_id=s3.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=2, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=3, station_id=s1.id
            ),
        ]
    )
    db_session.commit()

    count, resolved_num, _, items = calculate_train_similarity(db_session, snap_id, "111")
    assert count == 3
    assert resolved_num == "111"
    assert len(items) == 1
    assert items[0].train_number == "222"
    assert items[0].overlap_station_count == 3
    assert items[0].compared_station_count == 3
    assert items[0].union_station_count == 3
    assert items[0].similarity_pct == 100.0


def test_calculate_train_similarity_partial(db_session: Session) -> None:
    snap_id, s1, s2, s3, s4 = setup_data(db_session)
    t1 = Train(number="111")
    t2 = Train(number="222")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=snap_id, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=snap_id, train_id=t2.id, name="T2"),
        ]
    )

    # t1: A, B
    # t2: B, C, D
    # Overlap: B (1). Union: A, B, C, D (4). Jaccard: 1/4 = 25%
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
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=2, station_id=s3.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=3, station_id=s4.id
            ),
        ]
    )
    db_session.commit()

    _, _, _, items = calculate_train_similarity(db_session, snap_id, "111")
    assert len(items) == 1
    assert items[0].overlap_station_count == 1
    assert items[0].compared_station_count == 3
    assert items[0].union_station_count == 4
    assert items[0].similarity_pct == 25.0


def test_calculate_train_similarity_repeated_visits(db_session: Session) -> None:
    snap_id, s1, s2, _, _ = setup_data(db_session)
    t1 = Train(number="111")
    t2 = Train(number="222")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=snap_id, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=snap_id, train_id=t2.id, name="T2"),
        ]
    )

    # t1: A, B, A
    # t2: B, A, B
    # Both have distinct set {A, B}. Overlap 2. Union 2. Jaccard 100%.
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
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=1, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=2, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=3, station_id=s2.id
            ),
        ]
    )
    db_session.commit()

    count, _, _, items = calculate_train_similarity(db_session, snap_id, "111")
    assert count == 2  # distinct count!
    assert len(items) == 1
    assert items[0].overlap_station_count == 2
    assert items[0].compared_station_count == 2
    assert items[0].union_station_count == 2
    assert items[0].similarity_pct == 100.0


def test_calculate_train_similarity_ordering(db_session: Session) -> None:
    snap_id, s1, s2, s3, _ = setup_data(db_session)
    t1 = Train(number="111")
    t2 = Train(number="222")
    t3 = Train(number="333")
    t4 = Train(number="444")
    db_session.add_all([t1, t2, t3, t4])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=snap_id, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=snap_id, train_id=t2.id, name="T2"),
            TrainObservation(snapshot_id=snap_id, train_id=t3.id, name="T3"),
            TrainObservation(snapshot_id=snap_id, train_id=t4.id, name="T4"),
        ]
    )

    # t1: A, B
    # t2: A, B
    # t3: A, B, C
    # t4: A, B (same as t2 but diff number)
    db_session.add_all(
        [
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=1, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t1.id, stop_sequence=2, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=1, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t2.id, stop_sequence=2, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t3.id, stop_sequence=1, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t3.id, stop_sequence=2, station_id=s2.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t3.id, stop_sequence=3, station_id=s3.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t4.id, stop_sequence=1, station_id=s1.id
            ),
            TrainStopObservation(
                snapshot_id=snap_id, train_id=t4.id, stop_sequence=2, station_id=s2.id
            ),
        ]
    )
    db_session.commit()

    _, _, _, items = calculate_train_similarity(db_session, snap_id, "111")
    assert len(items) == 3
    # Order: sim DESC, overlap DESC, union ASC, number ASC
    assert items[0].train_number == "222"
    assert items[1].train_number == "444"
    assert items[2].train_number == "333"


def test_calculate_train_similarity_not_found(db_session: Session) -> None:
    snap_id, _, _, _, _ = setup_data(db_session)
    with pytest.raises(ValueError, match="not found"):
        calculate_train_similarity(db_session, snap_id, "999")
