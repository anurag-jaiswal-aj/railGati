import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayNetworkEdgeTopologicalBiconnectedComponent, RailwayGraphBuild
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
import pytest

@pytest.fixture
def snapshot(db_session: Session) -> DatasetSnapshot:
    source = DataSource(name="test_api_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()
    return snap

@pytest.fixture
def graph_build(db_session: Session, snapshot: DatasetSnapshot) -> RailwayGraphBuild:
    build = RailwayGraphBuild(timetable_snapshot_id=snapshot.id, status="ACTIVE")
    db_session.add(build)
    db_session.commit()
    return build



def test_api_biconnected_component_success(
    client: TestClient, db_session: Session, snapshot: DatasetSnapshot, graph_build: RailwayGraphBuild
) -> None:
    stna = Station(code="STNA")
    stnb = Station(code="STNB")
    db_session.add(stna)
    db_session.add(stnb)
    db_session.flush()

    comp = RailwayNetworkEdgeTopologicalBiconnectedComponent(
        graph_build_id=graph_build.id,
        timetable_snapshot_id=snapshot.id,
        station_a_id=min(stna.id, stnb.id),
        station_b_id=max(stna.id, stnb.id),
        block_edge_count=10,
    )
    db_session.add(comp)
    db_session.commit()

    # Forward
    resp = client.get(
        f"/api/v1/network/edges/STNA/STNB/biconnected-component?timetable_snapshot_id={snapshot.id}",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["from_station_code"] == "STNA"
    assert data["to_station_code"] == "STNB"
    assert data["block_edge_count"] == 10

    # Reverse
    resp_rev = client.get(
        f"/api/v1/network/edges/STNB/STNA/biconnected-component?timetable_snapshot_id={snapshot.id}",
    )
    assert resp_rev.status_code == 200
    data_rev = resp_rev.json()
    assert data_rev["from_station_code"] == "STNB"
    assert data_rev["to_station_code"] == "STNA"
    assert data_rev["block_edge_count"] == 10


def test_api_biconnected_component_not_found(
    client: TestClient, db_session: Session, snapshot: DatasetSnapshot, graph_build: RailwayGraphBuild
) -> None:
    db_session.add(Station(code="STNA"))
    db_session.add(Station(code="STNB"))
    db_session.commit()
    
    resp = client.get(
        f"/api/v1/network/edges/STNA/STNB/biconnected-component?timetable_snapshot_id={snapshot.id}",
    )
    assert resp.status_code == 404
    assert "not found in the active topological graph" in resp.json()["detail"]


def test_api_biconnected_component_unknown_station(
    client: TestClient, db_session: Session, snapshot: DatasetSnapshot, graph_build: RailwayGraphBuild
) -> None:
    db_session.add(Station(code="STNA"))
    db_session.commit()
    
    resp = client.get(
        f"/api/v1/network/edges/STNA/UNKNOWN/biconnected-component?timetable_snapshot_id={snapshot.id}",
    )
    assert resp.status_code == 404


def test_api_biconnected_component_self_loop(
    client: TestClient, db_session: Session, snapshot: DatasetSnapshot, graph_build: RailwayGraphBuild
) -> None:
    resp = client.get(
        f"/api/v1/network/edges/STNA/stna/biconnected-component?timetable_snapshot_id={snapshot.id}",
    )
    assert resp.status_code == 400
    assert "self-loops are not structural" in resp.json()["detail"].lower()


def test_api_biconnected_component_no_build(
    client: TestClient, db_session: Session
) -> None:
    # Snapshot 2 without a graph build
    source = DataSource(name="test_source2", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    snapshot = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    
    db_session.add(Station(code="STNA"))
    db_session.add(Station(code="STNB"))
    db_session.commit()

    resp = client.get(
        f"/api/v1/network/edges/STNA/STNB/biconnected-component?timetable_snapshot_id={snapshot.id}",
    )
    assert resp.status_code == 503
    assert "No ACTIVE RailwayGraphBuild" in resp.json()["detail"]
