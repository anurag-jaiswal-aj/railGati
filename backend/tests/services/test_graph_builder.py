"""Tests for the railway network graph materialization service."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge, RailwayServiceEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainStopObservation
from railgati.services.graph_builder import build_graph_for_timetable_snapshot


@pytest.fixture
def graph_data(db_session: Session) -> dict[str, int]:
    """Fixture providing test data for graph materialization."""
    source = DataSource(name="Graph Source", url="http://test", publisher="Test", license="CC0")
    db_session.add(source)
    db_session.commit()

    snap1 = DatasetSnapshot(source_id=source.id, retrieved_at=datetime.now(UTC), status="ACTIVE")
    snap2 = DatasetSnapshot(source_id=source.id, retrieved_at=datetime.now(UTC), status="ACTIVE")
    db_session.add_all([snap1, snap2])
    db_session.commit()

    # Create stations
    st_a = Station(code="A")
    st_b = Station(code="B")
    st_c = Station(code="C")
    st_d = Station(code="D")
    db_session.add_all([st_a, st_b, st_c, st_d])
    db_session.commit()

    # Create trains
    # Train 1: A -> B -> C
    train1 = Train(number="111")
    # Train 2: A -> B -> D
    train2 = Train(number="222")
    # Train 3: C -> B -> A (Reverse)
    train3 = Train(number="333")
    # Train 4 (Looping)-> None: A -> B -> A
    train4 = Train(number="444")
    db_session.add_all([train1, train2, train3, train4])
    db_session.commit()

    # Train 1 observations in snap1
    obs = [
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train1.id,
            stop_sequence=1,
            station_id=st_a.id,
            arrival_time=None,
            departure_time="10:00",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train1.id,
            stop_sequence=2,
            station_id=st_b.id,
            arrival_time="11:00",
            departure_time="11:15",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train1.id,
            stop_sequence=3,
            station_id=st_c.id,
            arrival_time="12:00",
            departure_time=None,
            source_day=1,
        ),
        # Train 2 observations in snap1
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train2.id,
            stop_sequence=1,
            station_id=st_a.id,
            arrival_time=None,
            departure_time="10:30",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train2.id,
            stop_sequence=2,
            station_id=st_b.id,
            arrival_time="11:15",
            departure_time="11:30",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train2.id,
            stop_sequence=3,
            station_id=st_d.id,
            arrival_time="13:00",
            departure_time=None,
            source_day=1,
        ),
        # Train 3 (reverse) observations in snap1
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train3.id,
            stop_sequence=1,
            station_id=st_c.id,
            arrival_time=None,
            departure_time="14:00",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train3.id,
            stop_sequence=2,
            station_id=st_b.id,
            arrival_time="15:00",
            departure_time="15:15",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train3.id,
            stop_sequence=3,
            station_id=st_a.id,
            arrival_time="16:00",
            departure_time=None,
            source_day=1,
        ),
        # Train 4 (looping) observations in snap1
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train4.id,
            stop_sequence=1,
            station_id=st_a.id,
            arrival_time=None,
            departure_time="20:00",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train4.id,
            stop_sequence=2,
            station_id=st_b.id,
            arrival_time="21:00",
            departure_time="21:15",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap1.id,
            train_id=train4.id,
            stop_sequence=3,
            station_id=st_a.id,
            arrival_time="22:00",
            departure_time=None,
            source_day=1,
        ),
        # Missing timing edge for Train 1 in snap2
        TrainStopObservation(
            snapshot_id=snap2.id,
            train_id=train1.id,
            stop_sequence=1,
            station_id=st_a.id,
            arrival_time=None,
            departure_time=None,
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap2.id,
            train_id=train1.id,
            stop_sequence=2,
            station_id=st_b.id,
            arrival_time=None,
            departure_time=None,
            source_day=1,
        ),
    ]
    db_session.add_all(obs)
    db_session.commit()

    return {
        "snap1_id": snap1.id,
        "snap2_id": snap2.id,
        "st_a_id": st_a.id,
        "st_b_id": st_b.id,
        "st_c_id": st_c.id,
        "st_d_id": st_d.id,
        "train1_id": train1.id,
        "train2_id": train2.id,
        "train3_id": train3.id,
        "train4_id": train4.id,
    }


def test_build_graph_success(db_session: Session, graph_data: dict[str, int]) -> None:
    """Test successful generation of the graph layer."""
    snap1_id = graph_data["snap1_id"]
    st_a = graph_data["st_a_id"]
    st_b = graph_data["st_b_id"]

    build_record = build_graph_for_timetable_snapshot(db_session, snap1_id)
    assert build_record.status == "ACTIVE"
    assert build_record.timetable_snapshot_id == snap1_id

    # Check ServiceEdges
    service_edges = db_session.scalars(
        select(RailwayServiceEdge).filter(RailwayServiceEdge.timetable_snapshot_id == snap1_id)
    ).all()
    # T1(2), T2(2), T3(2), T4(2) -> 8 edges
    assert len(service_edges) == 8

    # A -> B should have 3 service edges (T1, T2, T4)
    ab_edges = [e for e in service_edges if e.from_station_id == st_a and e.to_station_id == st_b]
    assert len(ab_edges) == 3
    for e in ab_edges:
        assert e.duration_minutes is not None
        assert e.from_stop_sequence == 1
        assert e.to_stop_sequence == 2

    # Check NetworkEdges
    network_edges = db_session.scalars(
        select(RailwayNetworkEdge).filter(RailwayNetworkEdge.timetable_snapshot_id == snap1_id)
    ).all()
    # A->B, B->C, B->D, C->B, B->A -> 5 network edges
    assert len(network_edges) == 5

    # A -> B aggregate
    ab_net = next(
        (e for e in network_edges if e.from_station_id == st_a and e.to_station_id == st_b), None
    )
    assert ab_net is not None
    assert ab_net.train_count == 3
    # min duration is 45 mins (T2 10:30 -> 11:15)
    assert ab_net.min_duration_minutes == 45


def test_repeated_station_visits(db_session: Session, graph_data: dict[str, int]) -> None:
    """Test that trains looping through a station don't collapse invalidly."""
    snap1_id = graph_data["snap1_id"]
    st_a = graph_data["st_a_id"]
    st_b = graph_data["st_b_id"]
    train4_id = graph_data["train4_id"]

    build_graph_for_timetable_snapshot(db_session, snap1_id)

    # Train 4 goes A -> B -> A
    t4_edges = db_session.scalars(
        select(RailwayServiceEdge)
        .filter(RailwayServiceEdge.train_id == train4_id)
        .order_by(RailwayServiceEdge.from_stop_sequence)
    ).all()

    assert len(t4_edges) == 2
    # Edge 1: A -> B
    assert t4_edges[0].from_station_id == st_a
    assert t4_edges[0].to_station_id == st_b
    assert t4_edges[0].from_stop_sequence == 1
    assert t4_edges[0].to_stop_sequence == 2

    # Edge 2: B -> A
    assert t4_edges[1].from_station_id == st_b
    assert t4_edges[1].to_station_id == st_a
    assert t4_edges[1].from_stop_sequence == 2
    assert t4_edges[1].to_stop_sequence == 3


def test_missing_timing_edge(db_session: Session, graph_data: dict[str, int]) -> None:
    """Test that edges without timing data are still created, with null duration."""
    snap2_id = graph_data["snap2_id"]
    st_a = graph_data["st_a_id"]
    st_b = graph_data["st_b_id"]

    build_graph_for_timetable_snapshot(db_session, snap2_id)

    service_edges = db_session.scalars(
        select(RailwayServiceEdge).filter(RailwayServiceEdge.timetable_snapshot_id == snap2_id)
    ).all()
    assert len(service_edges) == 1
    edge = service_edges[0]
    assert edge.from_station_id == st_a
    assert edge.to_station_id == st_b
    assert edge.duration_minutes is None

    network_edges = db_session.scalars(
        select(RailwayNetworkEdge).filter(RailwayNetworkEdge.timetable_snapshot_id == snap2_id)
    ).all()
    assert len(network_edges) == 1
    net_edge = network_edges[0]
    assert net_edge.train_count == 1
    assert net_edge.min_duration_minutes is None


def test_idempotency_and_rebuild(db_session: Session, graph_data: dict[str, int]) -> None:
    """Test building graph multiple times preserves integrity and status."""
    snap1_id = graph_data["snap1_id"]

    # First build
    build1 = build_graph_for_timetable_snapshot(db_session, snap1_id)
    assert build1.status == "ACTIVE"

    count1 = db_session.scalar(
        select(func.count(RailwayServiceEdge.train_id)).filter(
            RailwayServiceEdge.timetable_snapshot_id == snap1_id
        )
    )
    assert count1 == 8

    # Second build
    build2 = build_graph_for_timetable_snapshot(db_session, snap1_id)
    assert build2.status == "ACTIVE"
    assert build2.id == build1.id

    count2 = db_session.scalar(
        select(func.count(RailwayServiceEdge.train_id)).filter(
            RailwayServiceEdge.timetable_snapshot_id == snap1_id
        )
    )
    # Count should remain 8 (not duplicated)
    assert count2 == 8


def test_failure_rollback(
    db_session: Session, graph_data: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a failed graph build rolls back and correctly sets FAILED status."""
    snap1_id = graph_data["snap1_id"]

    # Simulate a crash during network edge insert
    def mock_execute(*args: object, **kwargs: object) -> None:
        raise ValueError("Simulated DB Crash")

    # We patch inside the function block so it fails after deletes

    # Better to just use monkeypatch on db_session.flush or similar if possible.
    # Actually, we can just monkeypatch _parse_time_to_minutes to raise an exception.
    monkeypatch.setattr("railgati.services.graph_builder._parse_time_to_minutes", mock_execute)

    with pytest.raises(ValueError, match="Simulated DB Crash"):
        build_graph_for_timetable_snapshot(db_session, snap1_id)

    # We need to manually fetch the build_record to check its status since we caught the exception
    build_record = db_session.scalar(
        select(RailwayGraphBuild).filter_by(timetable_snapshot_id=snap1_id)
    )
    assert build_record is not None
    assert build_record.status == "FAILED"
    assert (
        build_record.error_message is not None
        and "Simulated DB Crash" in build_record.error_message
    )

    # Ensure no edges were committed
    count_service = db_session.scalar(
        select(func.count(RailwayServiceEdge.train_id)).filter(
            RailwayServiceEdge.timetable_snapshot_id == snap1_id
        )
    )
    assert count_service == 0
    count_network = db_session.scalar(
        select(func.count(RailwayNetworkEdge.from_station_id)).filter(
            RailwayNetworkEdge.timetable_snapshot_id == snap1_id
        )
    )
    assert count_network == 0


def test_active_rebuild_failure(
    db_session: Session, graph_data: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a failed rebuild of an ACTIVE graph rolls back and retains ACTIVE status."""
    snap1_id = graph_data["snap1_id"]

    # First build (successful)
    build_record = build_graph_for_timetable_snapshot(db_session, snap1_id)
    assert build_record.status == "ACTIVE"

    # Simulate a crash
    def mock_execute(*args: object, **kwargs: object) -> None:
        raise ValueError("Simulated DB Crash 2")

    monkeypatch.setattr("railgati.services.graph_builder._parse_time_to_minutes", mock_execute)

    # Rebuild
    with pytest.raises(ValueError, match="Simulated DB Crash 2"):
        build_graph_for_timetable_snapshot(db_session, snap1_id)

    # We need to fetch the build_record to check its status
    build_record_reloaded = db_session.scalar(
        select(RailwayGraphBuild).filter_by(timetable_snapshot_id=snap1_id)
    )
    assert build_record_reloaded is not None
    assert build_record_reloaded.status == "ACTIVE"
    assert (
        build_record_reloaded.error_message is not None
        and "Simulated DB Crash 2" in build_record_reloaded.error_message
    )

    # Ensure edges were preserved
    count_service = db_session.scalar(
        select(func.count(RailwayServiceEdge.train_id)).filter(
            RailwayServiceEdge.timetable_snapshot_id == snap1_id
        )
    )
    assert count_service == 8
    count_network = db_session.scalar(
        select(func.count(RailwayNetworkEdge.from_station_id)).filter(
            RailwayNetworkEdge.timetable_snapshot_id == snap1_id
        )
    )
    assert count_network == 5


def test_non_consecutive_stops(db_session: Session, graph_data: dict[str, int]) -> None:
    """Test that non-consecutive stops do not generate an edge."""
    snap1_id = graph_data["snap1_id"]
    st_a = graph_data["st_a_id"]
    st_b = graph_data["st_b_id"]
    st_c = graph_data["st_c_id"]

    # Add a train with missing stop 3 (1, 2, 4)
    train5 = Train(number="555")
    db_session.add(train5)
    db_session.commit()

    obs = [
        TrainStopObservation(
            snapshot_id=snap1_id,
            train_id=train5.id,
            stop_sequence=1,
            station_id=st_a,
            source_day=1,
            departure_time="10:00",
        ),
        TrainStopObservation(
            snapshot_id=snap1_id,
            train_id=train5.id,
            stop_sequence=2,
            station_id=st_b,
            arrival_time="11:00",
            departure_time="11:10",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap1_id,
            train_id=train5.id,
            stop_sequence=4,
            station_id=st_c,
            arrival_time="12:00",
            source_day=1,
        ),
    ]
    db_session.add_all(obs)
    db_session.commit()

    build_graph_for_timetable_snapshot(db_session, snap1_id)

    edges = db_session.scalars(
        select(RailwayServiceEdge)
        .filter(RailwayServiceEdge.train_id == train5.id)
        .order_by(RailwayServiceEdge.from_stop_sequence)
    ).all()

    # Only 1->2 should exist, not 2->4
    assert len(edges) == 1
    assert edges[0].from_stop_sequence == 1
    assert edges[0].to_stop_sequence == 2


def test_invalid_timing(db_session: Session, graph_data: dict[str, int]) -> None:
    """Test inconsistent timing is preserved as structural edge with NULL duration."""
    snap1_id = graph_data["snap1_id"]
    st_a = graph_data["st_a_id"]
    st_b = graph_data["st_b_id"]

    train6 = Train(number="666")
    db_session.add(train6)
    db_session.commit()

    # Negative duration (departs 10:00, arrives 09:00 on same day)
    obs = [
        TrainStopObservation(
            snapshot_id=snap1_id,
            train_id=train6.id,
            stop_sequence=1,
            station_id=st_a,
            departure_time="10:00",
            source_day=1,
        ),
        TrainStopObservation(
            snapshot_id=snap1_id,
            train_id=train6.id,
            stop_sequence=2,
            station_id=st_b,
            arrival_time="09:00",
            source_day=1,
        ),
    ]
    db_session.add_all(obs)
    db_session.commit()

    build_graph_for_timetable_snapshot(db_session, snap1_id)

    edges = db_session.scalars(
        select(RailwayServiceEdge).filter(RailwayServiceEdge.train_id == train6.id)
    ).all()

    assert len(edges) == 1
    assert edges[0].duration_minutes is None


def test_snapshot_isolation(db_session: Session, graph_data: dict[str, int]) -> None:
    """Test that building a graph for snapshot A only consumes snapshot A data."""
    snap1_id = graph_data["snap1_id"]
    snap2_id = graph_data["snap2_id"]

    # Build snap1
    build_graph_for_timetable_snapshot(db_session, snap1_id)

    # Check snap1 edges
    snap1_service = db_session.scalar(
        select(func.count(RailwayServiceEdge.train_id)).filter_by(timetable_snapshot_id=snap1_id)
    )
    assert (
        db_session.scalar(
            select(func.count(RailwayNetworkEdge.from_station_id)).filter_by(
                timetable_snapshot_id=snap1_id
            )
        )
        == 5
    )

    # Check snap2 edges (should be 0)
    snap2_service = db_session.scalar(
        select(func.count(RailwayServiceEdge.train_id)).filter_by(timetable_snapshot_id=snap2_id)
    )
    snap2_network = db_session.scalar(
        select(func.count(RailwayNetworkEdge.from_station_id)).filter_by(
            timetable_snapshot_id=snap2_id
        )
    )

    assert snap2_service == 0
    assert snap2_network == 0

    # Furthermore, verify snap1 doesn't include snap2 data
    # (snap2 has 1 train with 2 stops, but it was excluded from snap1)
    # So snap1_service should be exactly 8 (as established in test_build_graph_success)
    assert snap1_service == 8
