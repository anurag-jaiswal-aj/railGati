from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from railgati.api.v1.schemas import JourneyType, TimingConfidence
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.journey import find_one_transfer_journeys


@pytest.fixture
def transfer_data(db_session: Session) -> dict[str, int]:
    # Provenance
    src = DataSource(name="Transfer Source", url="http://test", publisher="Test", license="CC0")
    db_session.add(src)
    db_session.commit()

    snap1 = DatasetSnapshot(source_id=src.id, retrieved_at=datetime.now(UTC), status="ACTIVE")
    snap2 = DatasetSnapshot(source_id=src.id, retrieved_at=datetime.now(UTC), status="ACTIVE")
    db_session.add_all([snap1, snap2])
    db_session.commit()

    # Stations
    s_a = Station(code="STA")
    s_b = Station(code="STB")
    s_c = Station(code="STC")
    s_d = Station(code="STD")
    db_session.add_all([s_a, s_b, s_c, s_d])
    db_session.commit()

    # Trains
    def create_train(num: str, name: str) -> Train:
        t = Train(number=num)
        db_session.add(t)
        db_session.commit()
        tobs = TrainObservation(snapshot_id=snap1.id, train_id=t.id, name=name, type="Type")
        db_session.add(tobs)
        return t

    t1 = create_train("1001", "Train 1")
    t2 = create_train("1002", "Train 2")
    t3 = create_train("1003", "Train 3")
    t4 = create_train("1004", "Train 4")
    t5 = create_train("1005", "Train 5")
    t6 = create_train("1006", "Train 6")

    # Snapshot 2 train
    t_snap2 = Train(number="2001")
    db_session.add(t_snap2)
    db_session.commit()
    db_session.add(
        TrainObservation(snapshot_id=snap2.id, train_id=t_snap2.id, name="Snap 2", type="Type")
    )

    db_session.commit()

    def add_stop(
        t: Train,
        st: Station,
        seq: int,
        arr: str | None,
        dep: str | None,
        day: int | None,
        snap_id: int = snap1.id,
    ) -> None:
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap_id,
                train_id=t.id,
                station_id=st.id,
                stop_sequence=seq,
                arrival_time=arr,
                departure_time=dep,
                source_day=day,
            )
        )

    add_stop(t1, s_a, 1, None, "08:00:00", 1)
    add_stop(t1, s_b, 2, "10:00:00", "10:10:00", 1)

    add_stop(t2, s_b, 1, "11:50:00", "12:00:00", 1)
    add_stop(t2, s_d, 2, "14:00:00", None, 1)

    add_stop(t3, s_b, 1, None, "11:00:00", 1)
    add_stop(t3, s_d, 2, "13:00:00", None, 1)

    add_stop(t4, s_b, 1, None, "12:00:00", 3)
    add_stop(t4, s_d, 2, "14:00:00", None, 3)

    add_stop(t5, s_a, 1, None, "08:00:00", 1)
    add_stop(t5, s_c, 2, None, "10:10:00", 1)

    add_stop(t6, s_c, 1, "11:50:00", "12:00:00", None)
    add_stop(t6, s_d, 2, "14:00:00", None, 1)

    add_stop(t_snap2, s_b, 1, "11:50:00", "12:00:00", 1, snap_id=snap2.id)
    add_stop(t_snap2, s_d, 2, "14:00:00", None, 1, snap_id=snap2.id)

    db_session.commit()

    return {
        "snap1": snap1.id,
        "snap2": snap2.id,
        "st_a": s_a.id,
        "st_b": s_b.id,
        "st_c": s_c.id,
        "st_d": s_d.id,
        "t1": t1.id,
        "t2": t2.id,
    }


def test_valid_one_transfer(db_session: Session, transfer_data: dict[str, int]) -> None:
    opts = find_one_transfer_journeys(
        db_session, transfer_data["snap1"], transfer_data["st_a"], transfer_data["st_d"]
    )

    valid_opts = [
        o for o in opts if o.legs[0].train_number == "1001" and o.legs[1].train_number == "1002"
    ]
    assert len(valid_opts) == 1
    opt = valid_opts[0]

    assert opt.type == JourneyType.ONE_TRANSFER
    assert opt.transfer_station == "STB"
    assert opt.layover_minutes == 120
    assert opt.total_duration_minutes == 360
    assert opt.timing_confidence == TimingConfidence.HIGH
    assert opt.number_of_stops == 2
    assert len(opt.legs) == 2


def test_minimum_buffer_rejection(db_session: Session, transfer_data: dict[str, int]) -> None:
    opts = find_one_transfer_journeys(
        db_session, transfer_data["snap1"], transfer_data["st_a"], transfer_data["st_d"]
    )
    t1_t3 = [
        o for o in opts if o.legs[0].train_number == "1001" and o.legs[1].train_number == "1003"
    ]
    assert len(t1_t3) == 0


def test_maximum_layover_rejection(db_session: Session, transfer_data: dict[str, int]) -> None:
    opts = find_one_transfer_journeys(
        db_session, transfer_data["snap1"], transfer_data["st_a"], transfer_data["st_d"]
    )
    t1_t4 = [
        o for o in opts if o.legs[0].train_number == "1001" and o.legs[1].train_number == "1004"
    ]
    assert len(t1_t4) == 0


def test_missing_data_rejection(db_session: Session, transfer_data: dict[str, int]) -> None:
    opts = find_one_transfer_journeys(
        db_session, transfer_data["snap1"], transfer_data["st_a"], transfer_data["st_d"]
    )
    t5_t6 = [
        o for o in opts if o.legs[0].train_number == "1005" and o.legs[1].train_number == "1006"
    ]
    assert len(t5_t6) == 0


def test_snapshot_isolation(db_session: Session, transfer_data: dict[str, int]) -> None:
    opts = find_one_transfer_journeys(
        db_session, transfer_data["snap1"], transfer_data["st_a"], transfer_data["st_d"]
    )
    cross_snap = [o for o in opts if o.legs[1].train_number == "2001"]
    assert len(cross_snap) == 0


def test_same_train_exclusion(db_session: Session, transfer_data: dict[str, int]) -> None:
    t = Train(number="1007")
    db_session.add(t)
    db_session.commit()
    db_session.add(
        TrainObservation(
            snapshot_id=transfer_data["snap1"], train_id=t.id, name="Same", type="Type"
        )
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t.id,
            station_id=transfer_data["st_a"],
            stop_sequence=1,
            departure_time="08:00:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t.id,
            station_id=transfer_data["st_b"],
            stop_sequence=2,
            arrival_time="09:00:00",
            departure_time="12:00:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t.id,
            station_id=transfer_data["st_d"],
            stop_sequence=3,
            arrival_time="14:00:00",
            source_day=1,
        )
    )
    db_session.commit()

    opts = find_one_transfer_journeys(
        db_session, transfer_data["snap1"], transfer_data["st_a"], transfer_data["st_d"]
    )
    same_train = [
        o for o in opts if o.legs[0].train_number == "1007" and o.legs[1].train_number == "1007"
    ]
    assert len(same_train) == 0


def test_transfer_at_origin_destination_rejected(
    db_session: Session, transfer_data: dict[str, int]
) -> None:
    opts = find_one_transfer_journeys(
        db_session, transfer_data["snap1"], transfer_data["st_a"], transfer_data["st_b"]
    )
    assert len([o for o in opts if o.transfer_station == "STB"]) == 0


def test_cross_day_validation(db_session: Session, transfer_data: dict[str, int]) -> None:
    t1 = Train(number="1008")
    t2 = Train(number="1009")
    db_session.add_all([t1, t2])
    db_session.commit()
    db_session.add(
        TrainObservation(snapshot_id=transfer_data["snap1"], train_id=t1.id, name="T8", type="Type")
    )
    db_session.add(
        TrainObservation(snapshot_id=transfer_data["snap1"], train_id=t2.id, name="T9", type="Type")
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t1.id,
            station_id=transfer_data["st_a"],
            stop_sequence=1,
            departure_time="20:00:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t1.id,
            station_id=transfer_data["st_b"],
            stop_sequence=2,
            arrival_time="23:00:00",
            source_day=1,
        )
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t2.id,
            station_id=transfer_data["st_b"],
            stop_sequence=1,
            departure_time="01:00:00",
            source_day=2,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t2.id,
            station_id=transfer_data["st_d"],
            stop_sequence=2,
            arrival_time="03:00:00",
            source_day=2,
        )
    )
    db_session.commit()

    opts = find_one_transfer_journeys(
        db_session, transfer_data["snap1"], transfer_data["st_a"], transfer_data["st_d"]
    )
    cross = [
        o for o in opts if o.legs[0].train_number == "1008" and o.legs[1].train_number == "1009"
    ]
    assert len(cross) == 1
    assert cross[0].layover_minutes == 120
    assert cross[0].total_duration_minutes == 420


def test_exact_minimum_buffer_acceptance(
    db_session: Session, transfer_data: dict[str, int]
) -> None:
    opts = find_one_transfer_journeys(
        db_session,
        transfer_data["snap1"],
        transfer_data["st_a"],
        transfer_data["st_d"],
        minimum_transfer_minutes=120,
    )
    val = len(
        [o for o in opts if o.legs[0].train_number == "1001" and o.legs[1].train_number == "1002"]
    )
    assert val == 1


def test_cross_day_invalid_transfer(db_session: Session, transfer_data: dict[str, int]) -> None:
    t3 = Train(number="1010")
    db_session.add(t3)
    db_session.commit()
    db_session.add(
        TrainObservation(
            snapshot_id=transfer_data["snap1"], train_id=t3.id, name="T10", type="Type"
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t3.id,
            station_id=transfer_data["st_b"],
            stop_sequence=1,
            departure_time="00:30:00",
            source_day=2,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t3.id,
            station_id=transfer_data["st_d"],
            stop_sequence=2,
            arrival_time="03:00:00",
            source_day=2,
        )
    )
    db_session.commit()

    opts = find_one_transfer_journeys(
        db_session,
        transfer_data["snap1"],
        transfer_data["st_a"],
        transfer_data["st_d"],
        minimum_transfer_minutes=120,
    )
    cross_invalid = [
        o for o in opts if o.legs[0].train_number == "1008" and o.legs[1].train_number == "1010"
    ]
    assert len(cross_invalid) == 0


def test_deterministic_ordering_and_multiple_stations(
    db_session: Session, transfer_data: dict[str, int]
) -> None:
    t4 = Train(number="1011")
    t5 = Train(number="1012")
    db_session.add_all([t4, t5])
    db_session.commit()
    db_session.add(
        TrainObservation(
            snapshot_id=transfer_data["snap1"], train_id=t4.id, name="T11", type="Type"
        )
    )
    db_session.add(
        TrainObservation(
            snapshot_id=transfer_data["snap1"], train_id=t5.id, name="T12", type="Type"
        )
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t4.id,
            station_id=transfer_data["st_a"],
            stop_sequence=1,
            departure_time="07:00:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t4.id,
            station_id=transfer_data["st_c"],
            stop_sequence=2,
            arrival_time="09:00:00",
            source_day=1,
        )
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t5.id,
            station_id=transfer_data["st_c"],
            stop_sequence=1,
            departure_time="11:30:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=transfer_data["snap1"],
            train_id=t5.id,
            station_id=transfer_data["st_d"],
            stop_sequence=2,
            arrival_time="13:30:00",
            source_day=1,
        )
    )
    db_session.commit()

    opts = find_one_transfer_journeys(
        db_session, transfer_data["snap1"], transfer_data["st_a"], transfer_data["st_d"]
    )

    idx_1_2 = -1
    idx_4_5 = -1
    for i, o in enumerate(opts):
        if o.legs[0].train_number == "1001" and o.legs[1].train_number == "1002":
            idx_1_2 = i
        if o.legs[0].train_number == "1011" and o.legs[1].train_number == "1012":
            idx_4_5 = i

    assert idx_1_2 < idx_4_5
