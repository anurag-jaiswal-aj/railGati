"""Tests for the Network Path API endpoint."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station


@pytest.fixture
def network_path_api_data(db_session: Session) -> dict[str, Any]:
    """Setup minimal data for network path API testing."""
    src = DataSource(
        name="Test API Network Path Source",
        publisher="test publisher",
        url="http://test",
        license="MIT",
    )
    db_session.add(src)
    db_session.commit()

    snap_active = DatasetSnapshot(
        source_id=src.id,
        status="ACTIVE",
    )
    db_session.add(snap_active)
    db_session.commit()

    from railgati.models.train import Train, TrainObservation

    dummy_train = Train(number="000")
    db_session.add(dummy_train)
    db_session.commit()

    dummy_obs = TrainObservation(
        snapshot_id=snap_active.id,
        train_id=dummy_train.id,
        name="Dummy",
    )
    db_session.add(dummy_obs)
    db_session.commit()

    org = Station(code="API_ORG")
    dst1 = Station(code="API_DST1")
    dst2 = Station(code="API_DST2")
    db_session.add_all([org, dst1, dst2])
    db_session.commit()

    from railgati.models.station import StationObservation

    snap_station = DatasetSnapshot(
        source_id=src.id,
        status="ACTIVE",
    )
    db_session.add(snap_station)
    db_session.commit()

    obs_org = StationObservation(
        snapshot_id=snap_station.id, station_id=org.id, name="Origin Station"
    )
    obs_dst1 = StationObservation(
        snapshot_id=snap_station.id, station_id=dst1.id, name="Destination One"
    )
    db_session.add_all([obs_org, obs_dst1])
    db_session.commit()

    return {
        "org_code": org.code,
        "dst1_code": dst1.code,
        "dst2_code": dst2.code,
        "snap_id": snap_active.id,
    }


def test_get_network_path_success(
    client: TestClient, network_path_api_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from railgati.services.network import NetworkPath

    def mock_find(*args: Any, **kwargs: Any) -> list[NetworkPath]:
        return [
            NetworkPath(
                hop_count=1,
                station_ids=[1, 2],  # Assuming IDs align with org and dst1
            )
        ]

    monkeypatch.setattr("railgati.api.v1.network.find_network_paths", mock_find)

    response = client.get(
        f"/api/v1/network/path?origin={network_path_api_data['org_code']}&destination={network_path_api_data['dst1_code']}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["origin"] == network_path_api_data["org_code"]
    assert data["destination"] == network_path_api_data["dst1_code"]
    assert data["total_paths_returned"] == 1
    assert len(data["paths"]) == 1

    path_res = data["paths"][0]
    assert path_res["hop_count"] == 1
    assert len(path_res["stations"]) == 2


def test_get_network_path_no_path(
    client: TestClient, network_path_api_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("railgati.api.v1.network.find_network_paths", lambda *a, **kw: [])

    response = client.get(
        f"/api/v1/network/path?origin={network_path_api_data['org_code']}&destination={network_path_api_data['dst1_code']}"
    )
    assert response.status_code == 200
    assert response.json()["total_paths_returned"] == 0
    assert response.json()["paths"] == []


def test_get_network_path_case_insensitive(
    client: TestClient, network_path_api_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("railgati.api.v1.network.find_network_paths", lambda *a, **kw: [])

    response = client.get(
        f"/api/v1/network/path?origin={network_path_api_data['org_code'].lower()}&destination={network_path_api_data['dst1_code'].lower()}"
    )
    assert response.status_code == 200
    assert response.json()["origin"] == network_path_api_data["org_code"]
    assert response.json()["destination"] == network_path_api_data["dst1_code"]


def test_get_network_path_unknown_origin(
    client: TestClient, network_path_api_data: dict[str, Any]
) -> None:
    response = client.get(
        f"/api/v1/network/path?origin=UNKNOWN&destination={network_path_api_data['dst1_code']}"
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_network_path_unknown_destination(
    client: TestClient, network_path_api_data: dict[str, Any]
) -> None:
    response = client.get(
        f"/api/v1/network/path?origin={network_path_api_data['org_code']}&destination=UNKNOWN"
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_network_path_invalid_max_hops(
    client: TestClient, network_path_api_data: dict[str, Any]
) -> None:
    response = client.get(
        f"/api/v1/network/path?origin={network_path_api_data['org_code']}&destination={network_path_api_data['dst1_code']}&max_hops=11"
    )
    assert response.status_code == 422


def test_get_network_path_invalid_max_paths(
    client: TestClient, network_path_api_data: dict[str, Any]
) -> None:
    response = client.get(
        f"/api/v1/network/path?origin={network_path_api_data['org_code']}&destination={network_path_api_data['dst1_code']}&max_paths=51"
    )
    assert response.status_code == 422


def test_get_network_path_origin_equals_destination(
    client: TestClient, network_path_api_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from railgati.services.network import NetworkPath

    def mock_find(*args: Any, **kwargs: Any) -> list[NetworkPath]:
        return [
            NetworkPath(
                hop_count=0,
                station_ids=[1],
            )
        ]

    monkeypatch.setattr("railgati.api.v1.network.find_network_paths", mock_find)

    response = client.get(
        f"/api/v1/network/path?origin={network_path_api_data['org_code']}&destination={network_path_api_data['org_code']}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_paths_returned"] == 1
    assert data["paths"][0]["hop_count"] == 0
    assert len(data["paths"][0]["stations"]) == 1
    assert data["paths"][0]["stations"][0]["station_code"] == network_path_api_data["org_code"]


def test_get_network_path_graph_unavailable(
    client: TestClient, network_path_api_data: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def mock_find_raises(*args: Any, **kwargs: Any) -> list[Any]:
        raise ValueError("Active graph build unavailable for this snapshot")

    monkeypatch.setattr("railgati.api.v1.network.find_network_paths", mock_find_raises)

    response = client.get(
        f"/api/v1/network/path?origin={network_path_api_data['org_code']}&destination={network_path_api_data['dst1_code']}"
    )
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()


def test_station_metadata_snapshot_isolation_path(
    client: TestClient,
    db_session: Session,
    network_path_api_data: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station, StationObservation
    from railgati.services.network import NetworkPath

    test_station = Station(code="TEST_META_PATH")
    db_session.add(test_station)
    db_session.commit()

    old_snap = DatasetSnapshot(
        source_id=db_session.query(DatasetSnapshot).first().source_id,
        status="SUPERSEDED",
    )
    db_session.add(old_snap)
    db_session.commit()

    active_snap = DatasetSnapshot(
        source_id=old_snap.source_id,
        status="ACTIVE",
    )
    db_session.add(active_snap)
    db_session.commit()

    station_snaps = (
        db_session.query(DatasetSnapshot)
        .filter(
            DatasetSnapshot.status == "ACTIVE",
            DatasetSnapshot.id.in_(db_session.query(StationObservation.snapshot_id)),
        )
        .all()
    )
    for snap in station_snaps:
        if snap.id != active_snap.id:
            snap.status = "SUPERSEDED"
    db_session.commit()

    obs_old = StationObservation(
        snapshot_id=old_snap.id, station_id=test_station.id, name="Old Name"
    )
    obs_active = StationObservation(
        snapshot_id=active_snap.id, station_id=test_station.id, name="Active Name"
    )
    db_session.add_all([obs_old, obs_active])
    db_session.commit()

    def mock_find(*args: Any, **kwargs: Any) -> list[NetworkPath]:
        return [
            NetworkPath(
                hop_count=1,
                station_ids=[1, test_station.id],
            )
        ]

    monkeypatch.setattr("railgati.api.v1.network.find_network_paths", mock_find)

    response = client.get(
        f"/api/v1/network/path?origin={network_path_api_data['org_code']}&destination=TEST_META_PATH"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["paths"][0]["stations"][1]["station_name"] == "Active Name"
