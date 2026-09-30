import typing

import pytest
from fastapi.testclient import TestClient

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.graph import RailwayNetworkEdge
from railgati.models.station import Station


@pytest.fixture
def test_snapshot_id(db_session: typing.Any) -> int:
    from datetime import UTC, datetime
    source = DataSource(name="api_test", url="http", publisher="pub", license="MIT")
    db_session.add(source)
    db_session.flush()

    snapshot = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime.now(UTC),
        status="ACTIVE",
    )
    db_session.add(snapshot)
    db_session.flush()
    return snapshot.id


@pytest.fixture
def api_farness_fixtures(db_session: typing.Any, test_snapshot_id: int) -> None:
    stations = [
        Station(id=1, code="A"),
        Station(id=2, code="B"),
        Station(id=3, code="ISO"),
    ]
    db_session.add_all(stations)
    db_session.flush()

    edges = [
        RailwayNetworkEdge(
            timetable_snapshot_id=test_snapshot_id,
            from_station_id=1,
            to_station_id=2,
            train_count=1,
        ),
    ]
    db_session.add_all(edges)
    db_session.commit()


def test_api_topological_farness_success(client: TestClient, monkeypatch: pytest.MonkeyPatch, test_snapshot_id: int, api_farness_fixtures: None) -> None:
    monkeypatch.setattr(
        "railgati.api.v1.network.get_active_timetable_snapshot_id", lambda _: test_snapshot_id
    )
    response = client.get("/api/v1/network/stations/A/topological-farness")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "A"
    assert data["topological_farness"] == 1
    assert data["reachable_station_count"] == 2


def test_api_topological_farness_isolated(client: TestClient, monkeypatch: pytest.MonkeyPatch, test_snapshot_id: int, api_farness_fixtures: None) -> None:
    monkeypatch.setattr(
        "railgati.api.v1.network.get_active_timetable_snapshot_id", lambda _: test_snapshot_id
    )
    response = client.get("/api/v1/network/stations/ISO/topological-farness")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "ISO"
    assert data["topological_farness"] == 0
    assert data["reachable_station_count"] == 1


def test_api_topological_farness_unknown_station(client: TestClient, monkeypatch: pytest.MonkeyPatch, test_snapshot_id: int, api_farness_fixtures: None) -> None:
    monkeypatch.setattr(
        "railgati.api.v1.network.get_active_timetable_snapshot_id", lambda _: test_snapshot_id
    )
    response = client.get("/api/v1/network/stations/UNKNOWN/topological-farness")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
