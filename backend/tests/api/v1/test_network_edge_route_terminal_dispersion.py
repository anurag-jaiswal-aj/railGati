import typing

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def api_terminal_dispersion_fixtures(db_session: Session) -> int:
    source = DataSource(
        name="test_api_dispersion", url="http://test", publisher="pub", license="MIT"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="TEST_API_DISP", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["A", "B", "O", "D"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    tr = Train(number="API_DISP")
    db_session.add(tr)
    db_session.commit()
    db_session.add(
        TrainObservation(snapshot_id=snap_id, train_id=tr.id, name="API_DISP", type="EXP")
    )
    for idx, s_code in enumerate(["O", "A", "B", "D"]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap_id,
                train_id=tr.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1,
            )
        )
    db_session.commit()
    return int(snap_id)


def test_api_edge_terminal_dispersion_success(
    client: TestClient, api_terminal_dispersion_fixtures: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from railgati.api.v1 import snapshots

    def mock_get_active(*args: typing.Any, **kwargs: typing.Any) -> int:
        return api_terminal_dispersion_fixtures

    monkeypatch.setattr(snapshots, "get_active_timetable_snapshot_id", mock_get_active)

    response = client.get("/api/v1/network/edges/A/B/route-terminal-dispersion")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "A"
    assert data["to_station_code"] == "B"
    assert data["traversing_train_count"] == 1
    assert data["distinct_origin_count"] == 1
    assert data["distinct_destination_count"] == 1


def test_api_edge_terminal_dispersion_404_station(
    client: TestClient, api_terminal_dispersion_fixtures: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from railgati.api.v1 import snapshots

    def mock_get_active(*args: typing.Any, **kwargs: typing.Any) -> int:
        return api_terminal_dispersion_fixtures

    monkeypatch.setattr(snapshots, "get_active_timetable_snapshot_id", mock_get_active)

    response = client.get("/api/v1/network/edges/INVALID/B/route-terminal-dispersion")
    assert response.status_code == 404


def test_api_edge_terminal_dispersion_404_edge(
    client: TestClient, api_terminal_dispersion_fixtures: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from railgati.api.v1 import snapshots

    def mock_get_active(*args: typing.Any, **kwargs: typing.Any) -> int:
        return api_terminal_dispersion_fixtures

    monkeypatch.setattr(snapshots, "get_active_timetable_snapshot_id", mock_get_active)

    response = client.get("/api/v1/network/edges/A/A/route-terminal-dispersion")
    assert response.status_code == 404
