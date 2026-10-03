import typing
import pytest
from fastapi.testclient import TestClient

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.graph import RailwayNetworkEdge
from datetime import UTC, datetime

@pytest.fixture
def test_snapshot_id(db_session: typing.Any) -> int:
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
def api_bbtc_fixtures(db_session, test_snapshot_id):
    stations = [Station(id=991, code='X'), Station(id=992, code='Y')]
    db_session.add_all(stations)
    db_session.flush()

    edge = RailwayNetworkEdge(timetable_snapshot_id=test_snapshot_id, from_station_id=991, to_station_id=992, train_count=1)
    db_session.add(edge)
    
    train = Train(id=999, number='T999')
    db_session.add(train)
    db_session.flush()

    obs = TrainObservation(train_id=999, snapshot_id=test_snapshot_id, name="T999", type="EXP")
    db_session.add(obs)
    
    stop1 = TrainStopObservation(snapshot_id=test_snapshot_id, train_id=999, stop_sequence=0, station_id=991)
    stop2 = TrainStopObservation(snapshot_id=test_snapshot_id, train_id=999, stop_sequence=1, station_id=992)
    db_session.add_all([stop1, stop2])
    db_session.commit()

def test_api_bbtc_success(client: TestClient, monkeypatch: pytest.MonkeyPatch, test_snapshot_id: int, api_bbtc_fixtures: None) -> None:
    monkeypatch.setattr("railgati.api.v1.network.get_active_timetable_snapshot_id", lambda _: test_snapshot_id)

    response = client.get("/api/v1/network/trains/T999/topological-biconnected-block-traversal-count")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "T999"
    assert data["timetable_snapshot_id"] == test_snapshot_id
    assert data["biconnected_block_traversal_count"] == 1
    assert data["total_route_edges"] == 1

def test_api_bbtc_not_found(client: TestClient, monkeypatch: pytest.MonkeyPatch, test_snapshot_id: int, api_bbtc_fixtures: None) -> None:
    monkeypatch.setattr("railgati.api.v1.network.get_active_timetable_snapshot_id", lambda _: test_snapshot_id)
    response = client.get("/api/v1/network/trains/UNKNOWN/topological-biconnected-block-traversal-count")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
