"""Tests for network reachability service."""

from collections.abc import Generator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.services.network import find_reachable_stations


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
def network_data(db_session: Session) -> dict[str, int]:
    """Fixture providing a deterministic test graph."""
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
    stations = {
        code: Station(code=code) for code in ["A", "B", "C", "D", "E", "F", "G", "ZZZ", "AAA"]
    }
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
        # Empty origin neighbor logic: E has no other outgoing
        # Order test edges: G -> ZZZ and G -> AAA (both 1 hop)
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["G"], to_station_id=st["ZZZ"]
        ),
        RailwayNetworkEdge(
            timetable_snapshot_id=snap1.id, from_station_id=st["G"], to_station_id=st["AAA"]
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
        "ZZZ": st["ZZZ"],
        "AAA": st["AAA"],
    }


def test_direct_neighbor(db_session: Session, network_data: dict[str, int]) -> None:
    res = find_reachable_stations(
        db_session, network_data["A"], max_hops=1, timetable_snapshot_id=network_data["snap1"]
    )
    # A->B, A->C
    assert len(res) == 2
    ids = {r.station_id: r.min_hops for r in res}
    assert ids[network_data["B"]] == 1
    assert ids[network_data["C"]] == 1


def test_two_hop_reachability(db_session: Session, network_data: dict[str, int]) -> None:
    # A -> B -> C -> D
    res = find_reachable_stations(
        db_session, network_data["B"], max_hops=2, timetable_snapshot_id=network_data["snap1"]
    )
    assert len(res) == 3
    ids = {r.station_id: r.min_hops for r in res}
    assert ids[network_data["C"]] == 1
    assert ids[network_data["D"]] == 2
    assert ids[network_data["A"]] == 2


def test_depth_bound(db_session: Session, network_data: dict[str, int]) -> None:
    # From A, D is reachable at depth 2 (A->C->D) or depth 3 (A->B->C->D)
    # If max_hops=1, D should not be reachable.
    res = find_reachable_stations(
        db_session, network_data["A"], max_hops=1, timetable_snapshot_id=network_data["snap1"]
    )
    ids = [r.station_id for r in res]
    assert network_data["D"] not in ids


def test_origin_exclusion(db_session: Session, network_data: dict[str, int]) -> None:
    # A -> C -> A
    res = find_reachable_stations(
        db_session, network_data["A"], max_hops=2, timetable_snapshot_id=network_data["snap1"]
    )
    ids = [r.station_id for r in res]
    assert network_data["A"] not in ids


def test_cycle_prevention(db_session: Session, network_data: dict[str, int]) -> None:
    # A -> C -> A shouldn't recurse forever
    res = find_reachable_stations(
        db_session, network_data["A"], max_hops=10, timetable_snapshot_id=network_data["snap1"]
    )
    # Reachable from A: B, C, D
    assert len(res) == 3


def test_multiple_paths_deduplication(db_session: Session, network_data: dict[str, int]) -> None:
    # A -> C (1 hop)
    # A -> B -> C (2 hops)
    res = find_reachable_stations(
        db_session, network_data["A"], max_hops=3, timetable_snapshot_id=network_data["snap1"]
    )
    ids = {r.station_id: r.min_hops for r in res}
    assert ids[network_data["C"]] == 1


def test_deterministic_ordering(db_session: Session, network_data: dict[str, int]) -> None:
    # Rely on the specific test_code_ordering for the rigorous ordering check
    pass


def test_code_ordering(db_session: Session, network_data: dict[str, int]) -> None:
    # G -> ZZZ and G -> AAA
    # IDs: ZZZ is inserted before AAA, so ZZZ.id < AAA.id
    # Codes: AAA < ZZZ
    # Result should be AAA then ZZZ
    res = find_reachable_stations(
        db_session, network_data["G"], max_hops=10, timetable_snapshot_id=network_data["snap1"]
    )
    assert len(res) == 2
    assert res[0].station_id == network_data["AAA"]
    assert res[1].station_id == network_data["ZZZ"]


def test_max_hops_bounds(db_session: Session, network_data: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        find_reachable_stations(
            db_session, network_data["A"], max_hops=0, timetable_snapshot_id=network_data["snap1"]
        )

    with pytest.raises(ValueError, match="between 1 and 10"):
        find_reachable_stations(
            db_session, network_data["A"], max_hops=11, timetable_snapshot_id=network_data["snap1"]
        )

    # 10 succeeds
    res = find_reachable_stations(
        db_session, network_data["A"], max_hops=10, timetable_snapshot_id=network_data["snap1"]
    )
    assert isinstance(res, list)


def test_snapshot_isolation(db_session: Session, network_data: dict[str, int]) -> None:
    # snap2 only has A -> F
    res = find_reachable_stations(
        db_session, network_data["A"], max_hops=10, timetable_snapshot_id=network_data["snap2"]
    )
    assert len(res) == 1
    assert res[0].station_id == network_data["F"]


def test_missing_graph_build(db_session: Session, network_data: dict[str, int]) -> None:
    source = DataSource(name="temp", url="test", publisher="x", license="cc")
    db_session.add(source)
    db_session.commit()
    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()

    with pytest.raises(ValueError, match="Active graph build unavailable"):
        find_reachable_stations(
            db_session, network_data["A"], max_hops=10, timetable_snapshot_id=snap.id
        )


def test_failed_pending_graph_build(db_session: Session, network_data: dict[str, int]) -> None:
    # Change snap2 build to FAILED
    build = db_session.scalar(
        select(RailwayGraphBuild).filter_by(timetable_snapshot_id=network_data["snap2"])
    )
    assert build is not None
    build.status = "FAILED"
    db_session.commit()

    with pytest.raises(ValueError, match="Active graph build unavailable"):
        find_reachable_stations(
            db_session, network_data["A"], max_hops=10, timetable_snapshot_id=network_data["snap2"]
        )

    build.status = "PENDING"
    db_session.commit()
    with pytest.raises(ValueError, match="Active graph build unavailable"):
        find_reachable_stations(
            db_session, network_data["A"], max_hops=10, timetable_snapshot_id=network_data["snap2"]
        )


def test_empty_origin(db_session: Session, network_data: dict[str, int]) -> None:
    # F has no outgoing edges in snap1
    res = find_reachable_stations(
        db_session, network_data["F"], max_hops=10, timetable_snapshot_id=network_data["snap1"]
    )
    assert res == []


def test_self_loop(db_session: Session, network_data: dict[str, int]) -> None:
    # E -> E exists. Should not return E.
    res = find_reachable_stations(
        db_session, network_data["E"], max_hops=10, timetable_snapshot_id=network_data["snap1"]
    )
    assert res == []
