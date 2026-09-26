import pytest
from typing import Any
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge, RailwayServiceEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation


def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="t", url="http://test", publisher="Test", license="CC0")
    db_session.add(source)
    db_session.commit()
    return source


@pytest.fixture
def path_attribution_data(db_session: Session) -> dict[str, Any]:
    source = create_deps(db_session)
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

    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()

    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)
    db_session.flush()

    ne1 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=1
    )
    ne2 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=1
    )
    db_session.add_all([ne1, ne2])
    db_session.flush()

    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Train 1"))
    db_session.flush()

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
    db_session.commit()
    return {"s1": s1, "s2": s2, "s3": s3, "snap": snap}


def test_get_path_attribution_success(client: TestClient, path_attribution_data: dict[str, Any]) -> None:
    response = client.get("/api/v1/network/path/attribution", params={"path": "A,B,C"})
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == ["A", "B", "C"]
    assert data["timetable_snapshot_id"] == 1
    assert len(data["segments"]) == 2
    seg1 = data["segments"][0]
    assert seg1["from_station"] == "A"
    assert seg1["to_station"] == "B"
    assert seg1["occurrences_returned"] == 1
    assert seg1["occurrences"][0]["train_number"] == "123"


def test_get_path_attribution_invalid_length(
    client: TestClient, path_attribution_data: dict[str, Any]
) -> None:
    # 1 station
    response = client.get("/api/v1/network/path/attribution", params={"path": "A"})
    assert response.status_code == 422

    # 11 stations
    path_11 = ",".join(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"])
    response = client.get("/api/v1/network/path/attribution", params={"path": path_11})
    assert response.status_code == 422


def test_get_path_attribution_invalid_station(
    client: TestClient, path_attribution_data: dict[str, Any]
) -> None:
    response = client.get("/api/v1/network/path/attribution", params={"path": "A,Z"})
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_path_attribution_missing_topology(
    client: TestClient, path_attribution_data: dict[str, Any]
) -> None:
    response = client.get("/api/v1/network/path/attribution", params={"path": "A,C"})
    assert response.status_code == 400
    assert "does not exist in the active network topology" in response.json()["detail"]


def test_get_path_attribution_consecutive_duplicates(
    client: TestClient, path_attribution_data: dict[str, Any]
) -> None:
    response = client.get("/api/v1/network/path/attribution", params={"path": "A,A,C"})
    assert response.status_code == 422
    assert "consecutive identical stations" in response.json()["detail"]
