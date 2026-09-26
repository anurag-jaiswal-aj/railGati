import pytest
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayServiceEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.train import Train, TrainObservation
from railgati.services.network import find_network_service_occurrences


def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="t", url="http://test", publisher="Test", license="CC0")
    db_session.add(source)
    db_session.commit()
    return source


def test_attribution_snapshot_isolation(db_session: Session) -> None:
    source = create_deps(db_session)
    # Setup base stations
    from railgati.models.station import Station

    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    # Create two snapshots
    snap1 = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    snap2 = DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE")
    db_session.add_all([snap1, snap2])
    db_session.flush()

    # Create active graph builds for both
    gb1 = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    gb2 = RailwayGraphBuild(timetable_snapshot_id=2, status="ACTIVE")
    db_session.add_all([gb1, gb2])
    db_session.flush()

    # Trains
    t1 = Train(number="123")
    t2 = Train(number="456")
    db_session.add_all([t1, t2])
    db_session.flush()

    # Train Observations isolated per snapshot
    to1 = TrainObservation(snapshot_id=1, train_id=t1.id, name="Train 1 Snap 1")
    to2 = TrainObservation(snapshot_id=2, train_id=t2.id, name="Train 2 Snap 2")
    db_session.add_all([to1, to2])
    db_session.flush()

    # Service edges per snapshot
    se1 = RailwayServiceEdge(
        timetable_snapshot_id=1,
        train_id=t1.id,
        from_stop_sequence=1,
        to_stop_sequence=2,
        from_station_id=s1.id,
        to_station_id=s2.id,
    )
    se2 = RailwayServiceEdge(
        timetable_snapshot_id=2,
        train_id=t2.id,
        from_stop_sequence=1,
        to_stop_sequence=2,
        from_station_id=s1.id,
        to_station_id=s2.id,
    )
    db_session.add_all([se1, se2])
    db_session.flush()

    # Query snapshot 1
    res1 = find_network_service_occurrences(db_session, 1, s1.id, s2.id)
    assert len(res1) == 1
    assert res1[0].train_name == "Train 1 Snap 1"

    # Query snapshot 2
    res2 = find_network_service_occurrences(db_session, 2, s1.id, s2.id)
    assert len(res2) == 1
    assert res2[0].train_name == "Train 2 Snap 2"


def test_attribution_ordering_and_repeated(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()

    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)
    db_session.flush()

    t1 = Train(number="123")  # Will appear twice
    t2 = Train(number="055")  # Lexicographically first
    db_session.add_all([t1, t2])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="Looping Train"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="Other Train"),
        ]
    )
    db_session.flush()

    # Add edges
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

    res = find_network_service_occurrences(db_session, 1, s1.id, s2.id)
    assert len(res) == 3
    # Ordered by Train.number ASC, from_stop_sequence ASC
    assert res[0].train_number == "055"
    assert res[1].train_number == "123"
    assert res[1].from_stop_sequence == 1
    assert res[2].train_number == "123"
    assert res[2].from_stop_sequence == 5


def test_attribution_reverse_edge_and_nonexistent(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()
    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()
    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)
    db_session.flush()

    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Train"))
    db_session.add(
        RailwayServiceEdge(
            timetable_snapshot_id=1,
            train_id=t1.id,
            from_stop_sequence=1,
            to_stop_sequence=2,
            from_station_id=s1.id,
            to_station_id=s2.id,
        )
    )
    db_session.flush()

    # Query A->B
    res = find_network_service_occurrences(db_session, 1, s1.id, s2.id)
    assert len(res) == 1

    # Query B->A (reverse)
    res_reverse = find_network_service_occurrences(db_session, 1, s2.id, s1.id)
    assert len(res_reverse) == 0


def test_attribution_graph_build_unavailable(db_session: Session) -> None:
    source = create_deps(db_session)
    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()

    with pytest.raises(ValueError, match="Active graph build unavailable"):
        find_network_service_occurrences(db_session, 1, 1, 2)


def test_attribution_limit(db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.station import Station

    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()
    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()
    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)
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

    res = find_network_service_occurrences(db_session, 1, s1.id, s2.id, limit=5)
    assert len(res) == 5
