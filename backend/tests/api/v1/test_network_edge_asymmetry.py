from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation


def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_api_asym", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    snap2 = DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE")
    db_session.add_all([snap, snap2])
    db_session.flush()

    gb = RailwayGraphBuild(id=1, timetable_snapshot_id=snap.id, status="ACTIVE")
    db_session.add(gb)

    s1 = Station(code="AAA")
    s2 = Station(code="BBB")
    t1 = Train(number="12345")
    db_session.add_all([s1, s2, t1])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=2, station_id=s1.id, name="Stn AAA"),
            StationObservation(snapshot_id=2, station_id=s2.id, name="Stn BBB"),
            TrainObservation(snapshot_id=1, train_id=t1.id, name="Test Train"),
        ]
    )

    # 30 vs 0 -> 100% asymmetry
    db_session.add_all(
        [
            RailwayNetworkEdge(
                timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=30
            ),
        ]
    )
    db_session.commit()


def test_get_edge_asymmetry(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)

    response = client.get("/api/v1/network/edge-asymmetry?min_total_volume=0")
    assert response.status_code == 200
    data = response.json()

    assert data["timetable_snapshot_id"] == 1
    assert data["limit"] == 50
    assert data["min_total_volume"] == 0
    assert len(data["items"]) == 1

    assert data["items"][0]["station_a_code"] == "AAA"
    assert data["items"][0]["station_b_code"] == "BBB"
    assert data["items"][0]["asymmetry_pct"] == 100.0
    assert data["items"][0]["forward_volume"] == 30
    assert data["items"][0]["reverse_volume"] == 0


def test_get_edge_asymmetry_empty(client: TestClient, db_session: Session) -> None:
    source = DataSource(name="test_api2", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    snap2 = DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE")
    db_session.add_all([snap, snap2])
    db_session.flush()

    t1 = Train(number="111")
    s1 = Station(code="CCC")
    db_session.add_all([t1, s1])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="Test"),
            StationObservation(snapshot_id=2, station_id=s1.id, name="Stn"),
        ]
    )

    gb = RailwayGraphBuild(id=1, timetable_snapshot_id=snap.id, status="ACTIVE")
    db_session.add(gb)
    db_session.commit()

    response = client.get("/api/v1/network/edge-asymmetry")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_get_edge_asymmetry_no_graph(client: TestClient, db_session: Session) -> None:
    source = DataSource(name="test_api3", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()
    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    snap2 = DatasetSnapshot(id=2, source_id=source.id, status="ACTIVE")
    db_session.add_all([snap, snap2])
    db_session.flush()

    t1 = Train(number="111")
    s1 = Station(code="CCC")
    db_session.add_all([t1, s1])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="Test"),
            StationObservation(snapshot_id=2, station_id=s1.id, name="Stn"),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/network/edge-asymmetry")
    assert response.status_code == 503
    assert "No ACTIVE graph build found" in response.json()["detail"]


def test_get_edge_asymmetry_validation(client: TestClient) -> None:
    response = client.get("/api/v1/network/edge-asymmetry?limit=0")
    assert response.status_code == 422

    response = client.get("/api/v1/network/edge-asymmetry?limit=1000")
    assert response.status_code == 422

    response = client.get("/api/v1/network/edge-asymmetry?min_total_volume=-1")
    assert response.status_code == 422
