import pytest
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.services.network import calculate_edge_volume


def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    return source


def setup_stations(db_session: Session) -> tuple[Station, Station, Station]:
    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s1.id, name="Station A"),
            StationObservation(snapshot_id=1, station_id=s2.id, name="Station B"),
            StationObservation(snapshot_id=1, station_id=s3.id, name="Station C"),
        ]
    )
    db_session.flush()
    return s1, s2, s3


def setup_edges_graph(db_session: Session, source_id: int) -> None:
    db_session.add(DatasetSnapshot(id=1, source_id=source_id, status="ACTIVE"))
    db_session.flush()
    db_session.add(DatasetSnapshot(id=2, source_id=source_id, status="ACTIVE"))
    db_session.flush()

    db_session.add(RailwayGraphBuild(timetable_snapshot_id=2, status="ACTIVE"))
    db_session.flush()


@pytest.fixture
def edge_test_data(db_session: Session) -> None:
    source = create_deps(db_session)
    setup_edges_graph(db_session, source.id)
    s1, s2, s3 = setup_stations(db_session)

    # Add edges
    # A -> B: volume 100
    # B -> C: volume 200
    # C -> A: volume 50
    # B -> A: volume 150
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=2,
                from_station_id=s1.id,
                to_station_id=s2.id,
                train_count=100,
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=2,
                from_station_id=s2.id,
                to_station_id=s3.id,
                train_count=200,
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=2,
                from_station_id=s3.id,
                to_station_id=s1.id,
                train_count=50,
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=2,
                from_station_id=s2.id,
                to_station_id=s1.id,
                train_count=150,
            ),
        ]
    )
    db_session.flush()


def test_edge_volume_basic(db_session: Session, edge_test_data: None) -> None:
    edges = calculate_edge_volume(db_session, 2)
    assert len(edges) == 4

    # Expected order: 200, 150, 100, 50
    assert edges[0].service_occurrence_volume == 200
    assert edges[0].from_station_code == "B"
    assert edges[0].to_station_code == "C"

    assert edges[1].service_occurrence_volume == 150
    assert edges[1].from_station_code == "B"
    assert edges[1].to_station_code == "A"

    assert edges[2].service_occurrence_volume == 100
    assert edges[2].from_station_code == "A"
    assert edges[2].to_station_code == "B"

    assert edges[3].service_occurrence_volume == 50
    assert edges[3].from_station_code == "C"
    assert edges[3].to_station_code == "A"


def test_edge_volume_limit(db_session: Session, edge_test_data: None) -> None:
    edges = calculate_edge_volume(db_session, 2, limit=2)
    assert len(edges) == 2
    assert edges[0].service_occurrence_volume == 200
    assert edges[1].service_occurrence_volume == 150


def test_edge_volume_tie_break(db_session: Session) -> None:
    source = create_deps(db_session)
    setup_edges_graph(db_session, source.id)
    s1, s2, s3 = setup_stations(db_session)

    # Tie volume = 100
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=2,
                from_station_id=s2.id,  # B
                to_station_id=s3.id,    # C
                train_count=100,
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=2,
                from_station_id=s1.id,  # A
                to_station_id=s2.id,    # B
                train_count=100,
            ),
        ]
    )
    db_session.flush()

    edges = calculate_edge_volume(db_session, 2)
    assert len(edges) == 2

    # A->B should sort before B->C
    assert edges[0].from_station_code == "A"
    assert edges[0].to_station_code == "B"
    assert edges[1].from_station_code == "B"
    assert edges[1].to_station_code == "C"


def test_edge_volume_missing_build(db_session: Session) -> None:
    source = create_deps(db_session)
    # no graph build
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    with pytest.raises(ValueError, match="No ACTIVE RailwayGraphBuild"):
        calculate_edge_volume(db_session, 1)


def test_edge_volume_empty_network(db_session: Session) -> None:
    source = create_deps(db_session)
    setup_edges_graph(db_session, source.id)
    s1, s2, s3 = setup_stations(db_session)

    # No edges added
    edges = calculate_edge_volume(db_session, 2)
    assert len(edges) == 0


def test_edge_volume_snapshot_isolation(db_session: Session) -> None:
    source = create_deps(db_session)
    # 2 snapshots
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()
    db_session.add(DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    # Build only for snapshot 2
    db_session.add(RailwayGraphBuild(timetable_snapshot_id=2, status="ACTIVE"))
    db_session.flush()

    s1, s2, s3 = setup_stations(db_session)

    # Add edge for snapshot 1 (Should be ignored)
    db_session.add(
        RailwayNetworkEdge(
            timetable_snapshot_id=1,
            from_station_id=s1.id,
            to_station_id=s2.id,
            train_count=500,
        )
    )
    # Add edge for snapshot 2 (Should be included)
    db_session.add(
        RailwayNetworkEdge(
            timetable_snapshot_id=2,
            from_station_id=s1.id,
            to_station_id=s3.id,
            train_count=100,
        )
    )
    db_session.flush()

    edges = calculate_edge_volume(db_session, 2)
    assert len(edges) == 1
    assert edges[0].service_occurrence_volume == 100
    assert edges[0].to_station_code == "C"


def test_edge_volume_active_station_metadata(db_session: Session) -> None:
    source = create_deps(db_session)

    # Old snapshot (inactive)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="INACTIVE"))
    db_session.flush()
    # Active snapshot
    db_session.add(DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE"))
    db_session.flush()

    db_session.add(RailwayGraphBuild(timetable_snapshot_id=2, status="ACTIVE"))
    db_session.flush()

    s1 = Station(code="A")
    s2 = Station(code="B")
    db_session.add_all([s1, s2])
    db_session.flush()

    # Snapshot 1 station names
    db_session.add_all([
        StationObservation(snapshot_id=1, station_id=s1.id, name="Old Name A"),
        StationObservation(snapshot_id=1, station_id=s2.id, name="Old Name B"),
    ])

    # Snapshot 2 station names
    db_session.add_all([
        StationObservation(snapshot_id=2, station_id=s1.id, name="Active Name A"),
        StationObservation(snapshot_id=2, station_id=s2.id, name="Active Name B"),
    ])
    db_session.flush()

    db_session.add(
        RailwayNetworkEdge(
            timetable_snapshot_id=2,
            from_station_id=s1.id,
            to_station_id=s2.id,
            train_count=10,
        )
    )
    db_session.flush()

    edges = calculate_edge_volume(db_session, 2)
    assert len(edges) == 1
    assert edges[0].from_station_name == "Active Name A"
    assert edges[0].to_station_name == "Active Name B"
