"""Tests for network path exploration service."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.services.network import find_network_paths


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provides a clean PostgreSQL database for testing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from railgati.models import Base

    engine = create_engine(
        "postgresql+psycopg2://railgati:railgati_dev@localhost:5433/railgati_test"
    )
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def path_data(db_session: Session) -> dict[str, int]:
    """Fixture providing a deterministic test graph for path exploration."""
    source = DataSource(name="Net Source", url="http://test", publisher="Test", license="CC0")
    db_session.add(source)
    db_session.commit()

    snap1 = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    snap2 = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add_all([snap1, snap2])
    db_session.commit()

    # Active builds
    build1 = RailwayGraphBuild(timetable_snapshot_id=snap1.id, status="ACTIVE")
    build2 = RailwayGraphBuild(timetable_snapshot_id=snap2.id, status="ACTIVE")
    db_session.add_all([build1, build2])
    db_session.commit()

    # Stations
    stations = {code: Station(code=code) for code in ["A", "B", "C", "D", "E", "F", "G", "H", "I"]}
    db_session.add_all(stations.values())
    db_session.commit()
    st = {k: v.id for k, v in stations.items()}

    # Graph Edges for snap1
    edges1 = [
        # A -> B
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["A"], to_station_id=st["B"]
        ),
        # B -> C
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["B"], to_station_id=st["C"]
        ),
        # C -> D
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["C"], to_station_id=st["D"]
        ),
        # Cycle: C -> A
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["C"], to_station_id=st["A"]
        ),
        # Multiple paths: A -> C (directly)
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["A"], to_station_id=st["C"]
        ),
        # Self loop: E -> E
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["E"], to_station_id=st["E"]
        ),
        # A -> E
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["A"], to_station_id=st["E"]
        ),
        # E -> B
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["E"], to_station_id=st["B"]
        ),
        # H -> I, but no back edge (reverse direction test)
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["H"], to_station_id=st["I"]
        ),
    ]
    db_session.add_all(edges1)

    # Edges for snap2 (isolation)
    edges2 = [
        RailwayNetworkEdge(
            timetable_snapshot_id=snap2.id, from_station_id=st["A"], to_station_id=st["F"]
        ),
    ]
    db_session.add_all(edges2)
    db_session.commit()

    return {
        "snap1": snap1.id,
        "snap2": snap2.id,
        "A": st["A"],
        "B": st["B"],
        "C": st["C"],
        "D": st["D"],
        "E": st["E"],
        "F": st["F"],
        "G": st["G"],
        "H": st["H"],
        "I": st["I"],
    }


def test_direct_one_hop_path(db_session: Session, path_data: dict[str, int]) -> None:
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["A"], path_data["C"], max_hops=3, max_paths=10
    )
    # A -> C directly (1 hop), A -> B -> C (2 hops), A -> E -> B -> C (3 hops)
    assert len(res) == 3
    assert res[0].hop_count == 1
    assert res[0].station_ids == [path_data["A"], path_data["C"]]
    assert res[1].hop_count == 2
    assert res[1].station_ids == [path_data["A"], path_data["B"], path_data["C"]]
    assert res[2].hop_count == 3
    assert res[2].station_ids == [path_data["A"], path_data["E"], path_data["B"], path_data["C"]]


def test_multi_hop_path(db_session: Session, path_data: dict[str, int]) -> None:
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["A"], path_data["D"], max_hops=4, max_paths=10
    )
    # A -> C -> D (2 hops)
    # A -> B -> C -> D (3 hops)
    # A -> E -> B -> C -> D (4 hops)
    assert len(res) == 3
    assert res[0].hop_count == 2


def test_no_path(db_session: Session, path_data: dict[str, int]) -> None:
    # A -> G (not connected)
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["A"], path_data["G"], max_hops=3, max_paths=10
    )
    assert len(res) == 0


def test_reverse_direction(db_session: Session, path_data: dict[str, int]) -> None:
    # H -> I exists. I -> H should not.
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["I"], path_data["H"], max_hops=3, max_paths=10
    )
    assert len(res) == 0


def test_cycle_prevention(db_session: Session, path_data: dict[str, int]) -> None:
    # A -> B -> C -> A (cycle). If we look for paths from A to D, it shouldn't get stuck in the cycle.
    # It should naturally find the simple paths without looping.
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["A"], path_data["D"], max_hops=10, max_paths=10
    )
    # Ensure no path repeats stations
    for p in res:
        assert len(p.station_ids) == len(set(p.station_ids))


def test_repeated_station_prevention(db_session: Session, path_data: dict[str, int]) -> None:
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["A"], path_data["D"], max_hops=5, max_paths=10
    )
    for path in res:
        assert len(path.station_ids) == len(set(path.station_ids))


def test_self_loop_exclusion(db_session: Session, path_data: dict[str, int]) -> None:
    # E -> E is a self loop. E -> B is an edge.
    # Path A -> E -> B shouldn't have A -> E -> E -> B
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["A"], path_data["B"], max_hops=5, max_paths=10
    )
    # Only A -> B and A -> E -> B
    assert len(res) == 2
    for path in res:
        assert len(path.station_ids) == len(set(path.station_ids))


def test_origin_equals_destination(db_session: Session, path_data: dict[str, int]) -> None:
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["A"], path_data["A"], max_hops=3, max_paths=10
    )
    assert len(res) == 1
    assert res[0].hop_count == 0
    assert res[0].station_ids == [path_data["A"]]


def test_max_hops_bounds(db_session: Session, path_data: dict[str, int]) -> None:
    # A -> B -> C -> D
    # depth 2 gives A -> C -> D
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["A"], path_data["D"], max_hops=2, max_paths=10
    )
    assert len(res) == 1
    assert res[0].hop_count == 2

    with pytest.raises(ValueError, match="max_hops must be between 1 and 10"):
        find_network_paths(
            db_session, path_data["snap1"], path_data["A"], path_data["D"], max_hops=0, max_paths=10
        )


def test_max_paths_bounds(db_session: Session, path_data: dict[str, int]) -> None:
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["A"], path_data["C"], max_hops=3, max_paths=1
    )
    assert len(res) == 1

    with pytest.raises(ValueError, match="max_paths must be between 1 and 50"):
        find_network_paths(
            db_session, path_data["snap1"], path_data["A"], path_data["C"], max_hops=3, max_paths=51
        )


def test_deterministic_ordering(db_session: Session, path_data: dict[str, int]) -> None:
    # Path order should be strictly deterministic based on hop count and path string
    res = find_network_paths(
        db_session, path_data["snap1"], path_data["A"], path_data["C"], max_hops=3, max_paths=10
    )
    assert res[0].hop_count == 1  # A->C
    assert res[1].hop_count == 2  # A->B->C
    assert res[2].hop_count == 3  # A->E->B->C


def test_timetable_snapshot_isolation(db_session: Session, path_data: dict[str, int]) -> None:
    # snap2 only has A->F
    res = find_network_paths(
        db_session, path_data["snap2"], path_data["A"], path_data["F"], max_hops=3, max_paths=10
    )
    assert len(res) == 1

    res_b = find_network_paths(
        db_session, path_data["snap2"], path_data["A"], path_data["B"], max_hops=3, max_paths=10
    )
    assert len(res_b) == 0


def test_missing_or_inactive_graph(db_session: Session, path_data: dict[str, int]) -> None:
    db_session.query(DatasetSnapshot).filter_by(id=path_data["snap1"]).first()

    build = (
        db_session.query(RailwayGraphBuild)
        .filter_by(timetable_snapshot_id=path_data["snap1"])
        .first()
    )
    if build:
        build.status = "PENDING"
        db_session.commit()

    with pytest.raises(ValueError, match="Active graph build unavailable for this snapshot"):
        find_network_paths(
            db_session, path_data["snap1"], path_data["A"], path_data["C"], max_hops=3, max_paths=10
        )
