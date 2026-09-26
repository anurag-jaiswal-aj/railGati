import pytest
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.services.network import calculate_hub_centrality


def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    return source


def setup_hubs_graph(db_session: Session, source_id: int, snapshot_id: int = 1) -> None:
    db_session.add(DatasetSnapshot(id=snapshot_id, source_id=source_id, status="ACTIVE"))
    db_session.add(RailwayGraphBuild(timetable_snapshot_id=snapshot_id, status="ACTIVE"))
    db_session.flush()


def setup_stations(db_session: Session) -> tuple[Station, Station, Station, Station]:
    s1 = Station(code="A")
    s2 = Station(code="B")
    s3 = Station(code="C")
    s4 = Station(code="D")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    # Needs StationObservation to be active snapshot
    db_session.add(DatasetSnapshot(id=999, source_id=1, status="ACTIVE"))
    db_session.flush()
    db_session.add_all(
        [
            StationObservation(snapshot_id=999, station_id=s1.id, name="A"),
            StationObservation(snapshot_id=999, station_id=s2.id, name="B"),
            StationObservation(snapshot_id=999, station_id=s3.id, name="C"),
            StationObservation(snapshot_id=999, station_id=s4.id, name="D"),
        ]
    )
    db_session.flush()
    return s1, s2, s3, s4


def test_hub_centrality_basic(db_session: Session) -> None:
    source = create_deps(db_session)
    setup_hubs_graph(db_session, source.id)
    s1, s2, s3, s4 = setup_stations(db_session)

    # A -> B (train_count: 5)
    # A -> C (train_count: 10)
    # B -> C (train_count: 3)
    # C -> D (train_count: 7)

    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=5
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s3.id, train_count=10
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=3
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s3.id, to_station_id=s4.id, train_count=7
            ),
        ]
    )
    db_session.flush()

    res = calculate_hub_centrality(db_session, 1, limit=10, sort_by="service_volume")
    assert len(res) == 4

    # Expected stats:
    # A: out: 2, in: 0, outbound: 15, inbound: 0, total: 15
    # B: out: 1, in: 1, outbound: 3, inbound: 5, total: 8
    # C: out: 1, in: 2, outbound: 7, inbound: 13, total: 20
    # D: out: 0, in: 1, outbound: 0, inbound: 7, total: 7

    # Sort order (service_volume DESC, total_topological_degree DESC, station_code ASC)
    # 1. C (20)
    # 2. A (15)
    # 3. B (8)
    # 4. D (7)

    assert res[0].station_code == "C"
    assert res[0].out_degree == 1
    assert res[0].in_degree == 2
    assert res[0].outbound_service_occurrence_volume == 7
    assert res[0].inbound_service_occurrence_volume == 13
    assert res[0].combined_occurrence_volume == 20
    assert res[0].total_topological_degree == 3

    assert res[1].station_code == "A"
    assert res[1].combined_occurrence_volume == 15
    assert res[1].in_degree == 0
    assert res[1].out_degree == 2

    assert res[2].station_code == "B"
    assert res[3].station_code == "D"


def test_hub_centrality_sort_out_degree(db_session: Session) -> None:
    source = create_deps(db_session)
    setup_hubs_graph(db_session, source.id)
    s1, s2, s3, s4 = setup_stations(db_session)

    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=5
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s3.id, train_count=10
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=3
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s3.id, to_station_id=s4.id, train_count=7
            ),
        ]
    )
    db_session.flush()

    res = calculate_hub_centrality(db_session, 1, limit=10, sort_by="out_degree")
    # A (out=2), B (out=1, in=1, tot=2), C (out=1, in=2, tot=3), D (out=0)
    # Sort out_degree DESC, total_degree DESC, combined_occurrence DESC, code ASC
    assert res[0].station_code == "A"  # out=2
    assert res[1].station_code == "C"  # out=1, total=3
    assert res[2].station_code == "B"  # out=1, total=2
    assert res[3].station_code == "D"  # out=0


def test_hub_centrality_sort_in_degree(db_session: Session) -> None:
    source = create_deps(db_session)
    setup_hubs_graph(db_session, source.id)
    s1, s2, s3, s4 = setup_stations(db_session)

    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=5
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s3.id, train_count=10
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=3
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s3.id, to_station_id=s4.id, train_count=7
            ),
        ]
    )
    db_session.flush()

    res = calculate_hub_centrality(db_session, 1, limit=10, sort_by="in_degree")
    # C (in=2)
    # B (in=1, tot=2, vol=8)
    # D (in=1, tot=1, vol=7)
    # A (in=0)
    assert res[0].station_code == "C"
    assert res[1].station_code == "B"
    assert res[2].station_code == "D"
    assert res[3].station_code == "A"


def test_hub_centrality_isolated_stations(db_session: Session) -> None:
    source = create_deps(db_session)
    setup_hubs_graph(db_session, source.id)
    s1, s2, s3, s4 = setup_stations(db_session)

    # Only one edge A -> B
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=5
            ),
        ]
    )
    db_session.flush()

    res = calculate_hub_centrality(db_session, 1, limit=10, sort_by="service_volume")
    # C and D are isolated, should NOT be returned
    assert len(res) == 2
    codes = {r.station_code for r in res}
    assert "A" in codes
    assert "B" in codes
    assert "C" not in codes
    assert "D" not in codes


def test_hub_centrality_limit(db_session: Session) -> None:
    source = create_deps(db_session)
    setup_hubs_graph(db_session, source.id)
    s1, s2, s3, s4 = setup_stations(db_session)

    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=5
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s3.id, train_count=10
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=3
            ),
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s3.id, to_station_id=s4.id, train_count=7
            ),
        ]
    )
    db_session.flush()

    res = calculate_hub_centrality(db_session, 1, limit=2, sort_by="service_volume")
    assert len(res) == 2
    assert res[0].station_code == "C"
    assert res[1].station_code == "A"


def test_hub_centrality_invalid_sort(db_session: Session) -> None:
    source = create_deps(db_session)
    setup_hubs_graph(db_session, source.id)
    setup_stations(db_session)
    with pytest.raises(ValueError, match="Invalid sort_by"):
        calculate_hub_centrality(db_session, 1, sort_by="unknown")


def test_hub_centrality_missing_build(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.flush()
    with pytest.raises(ValueError, match="Active graph build unavailable"):
        calculate_hub_centrality(db_session, 1)


def test_hub_centrality_failed_build(db_session: Session) -> None:
    source = create_deps(db_session)
    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))
    db_session.add(RailwayGraphBuild(timetable_snapshot_id=1, status="FAILED"))
    db_session.flush()
    with pytest.raises(ValueError, match="Active graph build unavailable"):
        calculate_hub_centrality(db_session, 1)
