import pytest
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.services.network import calculate_network_edge_asymmetry


def setup_data(db_session: Session) -> tuple[Station, Station, Station]:
    source = DataSource(
        name="test_source_asym", url="http://test", publisher="test", license="test"
    )
    db_session.add(source)
    db_session.flush()

    # Create Snapshot
    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()

    # Create Graph Build
    gb = RailwayGraphBuild(id=1, timetable_snapshot_id=snap.id, status="ACTIVE")
    db_session.add(gb)

    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    s4 = Station(code="D")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=snap.id, station_id=s1.id, name="Station A"),
            StationObservation(snapshot_id=snap.id, station_id=s2.id, name="Station B"),
            StationObservation(snapshot_id=snap.id, station_id=s3.id, name="Station C"),
            StationObservation(snapshot_id=snap.id, station_id=s4.id, name="Station D"),
        ]
    )

    # 1. Balanced pair (A <-> B)
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=snap.id,
                from_station_id=s1.id,
                to_station_id=s2.id,
                train_count=10,
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=snap.id,
                from_station_id=s2.id,
                to_station_id=s1.id,
                train_count=10,
            ),
        ]
    )

    # 2. Completely asymmetric pair (B -> C)
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=snap.id,
                from_station_id=s2.id,
                to_station_id=s3.id,
                train_count=46,
            ),
            # Missing C -> B
        ]
    )

    # 3. Reverse-only pair (D -> A). A < D, so forward is A->D (0) and reverse is D->A (30)
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=snap.id,
                from_station_id=s4.id,
                to_station_id=s1.id,
                train_count=30,
            ),
        ]
    )

    # 4. Partial imbalance (C <-> D)
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=snap.id,
                from_station_id=s3.id,
                to_station_id=s4.id,
                train_count=30,
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=snap.id,
                from_station_id=s4.id,
                to_station_id=s3.id,
                train_count=10,
            ),
        ]
    )

    db_session.commit()
    return s1, s2, s3, s4


def test_calculate_edge_asymmetry(db_session: Session) -> None:
    s1, s2, s3, s4 = setup_data(db_session)

    items = calculate_network_edge_asymmetry(db_session, 1, 1, min_total_volume=0)
    assert len(items) == 4

    # The order should be by asymmetry_pct DESC, then total_volume DESC, station_a ASC, station_b ASC
    # B <-> C (Asym 100, Vol 46) -> A: B, B: C
    assert items[0].station_a_code == "B"
    assert items[0].station_b_code == "C"
    assert items[0].asymmetry_pct == 100.0
    assert items[0].forward_volume == 46
    assert items[0].reverse_volume == 0
    assert items[0].total_volume == 46

    # A <-> D (Asym 100, Vol 30) -> A: A, B: D (because D -> A exists, but A is alphabetically first)
    assert items[1].station_a_code == "A"
    assert items[1].station_b_code == "D"
    assert items[1].asymmetry_pct == 100.0
    assert items[1].forward_volume == 0
    assert items[1].reverse_volume == 30
    assert items[1].total_volume == 30

    # C <-> D (Asym 50, Vol 40)
    assert items[2].station_a_code == "C"
    assert items[2].station_b_code == "D"
    assert items[2].asymmetry_pct == 50.0
    assert items[2].forward_volume == 30
    assert items[2].reverse_volume == 10
    assert items[2].total_volume == 40

    # A <-> B (Asym 0, Vol 20)
    assert items[3].station_a_code == "A"
    assert items[3].station_b_code == "B"
    assert items[3].asymmetry_pct == 0.0
    assert items[3].forward_volume == 10
    assert items[3].reverse_volume == 10
    assert items[3].total_volume == 20


def test_calculate_edge_asymmetry_min_volume(db_session: Session) -> None:
    setup_data(db_session)
    items = calculate_network_edge_asymmetry(db_session, 1, 1, min_total_volume=45)
    assert len(items) == 1
    assert items[0].station_a_code == "B"
    assert items[0].station_b_code == "C"


def test_calculate_edge_asymmetry_no_graph(db_session: Session) -> None:
    source = DataSource(name="err_source", url="err", publisher="err", license="err")
    db_session.add(source)
    db_session.flush()
    snap = DatasetSnapshot(id=99, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()

    with pytest.raises(ValueError, match="No ACTIVE graph build found"):
        calculate_network_edge_asymmetry(db_session, 99, 99)
