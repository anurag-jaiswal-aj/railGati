import pytest
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge, RailwayServiceEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.train import Train, TrainObservation
from railgati.services.network import find_network_path_continuous_services


def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="t", url="http://test", publisher="Test", license="CC0")
    db_session.add(source)
    db_session.commit()
    return source


def test_continuous_path_normal(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()

    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)
    db_session.flush()

    ne1 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=1
    )
    ne2 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=1
    )
    db_session.add_all([ne1, ne2])
    db_session.flush()

    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Continuous Train"))
    db_session.flush()

    se1 = RailwayServiceEdge(
        timetable_snapshot_id=1,
        train_id=t1.id,
        from_stop_sequence=1,
        to_stop_sequence=2,
        from_station_id=s1.id,
        to_station_id=s2.id,
        departure_time="10:00",
        arrival_time="11:00",
        source_day_offset=0,
    )
    se2 = RailwayServiceEdge(
        timetable_snapshot_id=1,
        train_id=t1.id,
        from_stop_sequence=2,
        to_stop_sequence=3,
        from_station_id=s2.id,
        to_station_id=s3.id,
        departure_time="11:10",
        arrival_time="12:00",
        source_day_offset=0,
    )
    db_session.add_all([se1, se2])
    db_session.flush()

    res = find_network_path_continuous_services(db_session, 1, [s1.id, s2.id, s3.id])
    assert len(res) == 1
    assert res[0].train_number == "123"
    assert res[0].train_name == "Continuous Train"
    assert res[0].start_sequence == 1
    assert res[0].end_sequence == 3
    assert res[0].departure_time == "10:00"
    assert res[0].arrival_time == "12:00"
    assert res[0].total_duration_minutes == 120


def test_continuous_path_gap_excluded(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)

    ne1 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=1
    )
    ne2 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=1
    )
    db_session.add_all([ne1, ne2])

    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Broken Train"))

    # Notice the stop sequence gap (1->2 then 5->6)
    se1 = RailwayServiceEdge(
        timetable_snapshot_id=1,
        train_id=t1.id,
        from_stop_sequence=1,
        to_stop_sequence=2,
        from_station_id=s1.id,
        to_station_id=s2.id,
    )
    se2 = RailwayServiceEdge(
        timetable_snapshot_id=1,
        train_id=t1.id,
        from_stop_sequence=5,
        to_stop_sequence=6,
        from_station_id=s2.id,
        to_station_id=s3.id,
    )
    db_session.add_all([se1, se2])
    db_session.flush()

    res = find_network_path_continuous_services(db_session, 1, [s1.id, s2.id, s3.id])
    assert len(res) == 0


def test_continuous_path_station_mismatch_excluded(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    s4 = Station(code="D")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)

    ne1 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=1
    )
    ne2 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=1
    )
    db_session.add_all([ne1, ne2])

    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Broken Train"))

    se1 = RailwayServiceEdge(
        timetable_snapshot_id=1,
        train_id=t1.id,
        from_stop_sequence=1,
        to_stop_sequence=2,
        from_station_id=s1.id,
        to_station_id=s2.id,
    )
    # Train goes to D instead of B, then D to C.
    # But wait, we want to see if we can trick the query if we don't check station identity.
    # If the query only checks stop_sequence, it might match if we omit station_id.
    db_session.add_all([se1])
    db_session.flush()

    res = find_network_path_continuous_services(db_session, 1, [s1.id, s2.id, s3.id])
    assert len(res) == 0


def test_path_not_in_topology(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)
    db_session.flush()

    with pytest.raises(ValueError, match=r"Path segment .* does not exist"):
        find_network_path_continuous_services(db_session, 1, [s1.id, s2.id])


def test_continuous_path_different_trains(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1, s2, s3 = Station(code="A"), Station(code="B"), Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.add(RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE"))
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=1
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=1
            ),
        ]
    )

    t1, t2 = Train(number="1"), Train(number="2")
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            RailwayServiceEdge(
                timetable_snapshot_id=1,
                train_id=t1.id,
                from_stop_sequence=1,
                to_stop_sequence=2,
                from_station_id=s1.id,
                to_station_id=s2.id,
            ),
            RailwayServiceEdge(
                timetable_snapshot_id=1,
                train_id=t2.id,
                from_stop_sequence=2,
                to_stop_sequence=3,
                from_station_id=s2.id,
                to_station_id=s3.id,
            ),
        ]
    )
    db_session.flush()

    res = find_network_path_continuous_services(db_session, 1, [s1.id, s2.id, s3.id])
    assert len(res) == 0


def test_continuous_path_reverse_direction(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1, s2, s3 = Station(code="A"), Station(code="B"), Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.add(RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE"))

    # Valid forward edges
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=1
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=1
            ),
        ]
    )
    db_session.flush()

    with pytest.raises(ValueError, match="Path segment .* does not exist"):
        find_network_path_continuous_services(db_session, 1, [s3.id, s2.id, s1.id])


def test_continuous_path_missing_graph(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1, s2 = Station(code="A"), Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    # Missing RailwayGraphBuild
    with pytest.raises(ValueError, match="Active graph build unavailable"):
        find_network_path_continuous_services(db_session, 1, [s1.id, s2.id])


def test_continuous_path_cross_day(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1, s2, s3 = Station(code="A"), Station(code="B"), Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.add(RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE"))
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=1
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=1
            ),
        ]
    )
    t1 = Train(number="1")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Cross Day Train"))

    db_session.add_all(
        [
            RailwayServiceEdge(
                timetable_snapshot_id=1,
                train_id=t1.id,
                from_stop_sequence=1,
                to_stop_sequence=2,
                from_station_id=s1.id,
                to_station_id=s2.id,
                departure_time="23:00",
                arrival_time="23:55",
                source_day_offset=0,
            ),
            RailwayServiceEdge(
                timetable_snapshot_id=1,
                train_id=t1.id,
                from_stop_sequence=2,
                to_stop_sequence=3,
                from_station_id=s2.id,
                to_station_id=s3.id,
                departure_time="00:10",
                arrival_time="01:00",
                source_day_offset=1,
            ),
        ]
    )
    db_session.flush()

    res = find_network_path_continuous_services(db_session, 1, [s1.id, s2.id, s3.id])
    assert len(res) == 1
    assert res[0].total_duration_minutes == 120  # 23:00 day 0 to 01:00 day 1 -> 2 hours
