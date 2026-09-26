import pytest
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge, RailwayServiceEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.train import Train, TrainObservation
from railgati.services.network import find_network_path_service_occurrences


def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="t", url="http://test", publisher="Test", license="CC0")
    db_session.add(source)
    db_session.commit()
    return source


def test_path_attribution_normal(db_session: Session) -> None:
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

    # Network Edges A->B and B->C
    ne1 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=1
    )
    ne2 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=1
    )
    db_session.add_all([ne1, ne2])
    db_session.flush()

    # Train
    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Train 1"))
    db_session.flush()

    # Service Edges
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
        from_stop_sequence=2,
        to_stop_sequence=3,
        from_station_id=s2.id,
        to_station_id=s3.id,
    )
    db_session.add_all([se1, se2])
    db_session.flush()

    res = find_network_path_service_occurrences(db_session, 1, [s1.id, s2.id, s3.id])
    assert len(res) == 2
    assert res[0].from_station_id == s1.id
    assert res[0].to_station_id == s2.id
    assert len(res[0].occurrences) == 1
    assert res[0].occurrences[0].train_name == "Train 1"

    assert res[1].from_station_id == s2.id
    assert res[1].to_station_id == s3.id
    assert len(res[1].occurrences) == 1
    assert res[1].occurrences[0].train_name == "Train 1"


def test_path_attribution_missing_segment(db_session: Session) -> None:
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
    db_session.flush()

    # Only A->B is in topology
    ne1 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=1
    )
    db_session.add(ne1)
    db_session.flush()

    with pytest.raises(ValueError, match="does not exist in the active network topology"):
        find_network_path_service_occurrences(db_session, 1, [s1.id, s2.id, s3.id])


def test_path_attribution_ordering_and_repeated(db_session: Session) -> None:
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
    ne1 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=3
    )
    db_session.add(ne1)
    db_session.flush()

    t1 = Train(number="123")  # repeated
    t2 = Train(number="055")
    db_session.add_all([t1, t2])
    db_session.flush()
    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
        ]
    )
    db_session.flush()

    db_session.add_all(
        [
            RailwayServiceEdge(
                timetable_snapshot_id=1,
                train_id=t1.id,
                from_stop_sequence=5,
                to_stop_sequence=6,
                from_station_id=s1.id,
                to_station_id=s2.id,
            ),
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
                from_stop_sequence=1,
                to_stop_sequence=2,
                from_station_id=s1.id,
                to_station_id=s2.id,
            ),
        ]
    )
    db_session.flush()

    res = find_network_path_service_occurrences(db_session, 1, [s1.id, s2.id])
    assert len(res) == 1
    occ = res[0].occurrences
    assert len(occ) == 3
    assert occ[0].train_number == "055"
    assert occ[1].train_number == "123"
    assert occ[1].from_stop_sequence == 1
    assert occ[2].train_number == "123"
    assert occ[2].from_stop_sequence == 5


def test_path_attribution_limit(db_session: Session) -> None:
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
    ne1 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=10
    )
    db_session.add(ne1)
    db_session.flush()

    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Train"))
    db_session.flush()

    edges = []
    for i in range(1, 10):
        edges.append(
            RailwayServiceEdge(
                timetable_snapshot_id=1,
                train_id=t1.id,
                from_stop_sequence=i * 10,
                to_stop_sequence=i * 10 + 1,
                from_station_id=s1.id,
                to_station_id=s2.id,
            )
        )
    db_session.add_all(edges)
    db_session.flush()

    res = find_network_path_service_occurrences(db_session, 1, [s1.id, s2.id], limit=5)
    assert len(res[0].occurrences) == 5
