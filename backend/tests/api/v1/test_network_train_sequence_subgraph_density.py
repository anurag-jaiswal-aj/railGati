import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.db import get_db
from railgati.main import app
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation

client = TestClient(app)


@pytest.fixture
def api_density_fixtures(db_session: Session) -> dict[str, int]:
    source = DataSource(name="test_p55_api", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s1 = Station(code="S1")
    s2 = Station(code="S2")
    s3 = Station(code="S3")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    t_api = Train(number="T_API")
    db_session.add(t_api)
    db_session.flush()

    db_session.add(TrainObservation(snapshot_id=1, train_id=t_api.id, name="T_API"))

    stops = [
        TrainStopObservation(snapshot_id=1, train_id=t_api.id, station_id=s1.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=1, train_id=t_api.id, station_id=s2.id, stop_sequence=2),
        TrainStopObservation(snapshot_id=1, train_id=t_api.id, station_id=s3.id, stop_sequence=3),
    ]
    db_session.add_all(stops)
    db_session.commit()

    return {"snap_id": 1}


def test_api_sequence_subgraph_density_success(
    db_session: Session, api_density_fixtures: dict[str, int]
) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    response = client.get("/api/v1/network/trains/T_API/sequence-subgraph-density")
    if response.status_code != 200:
        print(response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "T_API"
    assert data["total_sequence_occurrences"] == 3
    assert data["forward_max_possible_chords"] == 1
    assert data["backward_max_possible_chords"] == 3


def test_api_sequence_subgraph_density_not_found(
    db_session: Session, api_density_fixtures: dict[str, int]
) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    response = client.get("/api/v1/network/trains/UNKNOWN/sequence-subgraph-density")
    assert response.status_code == 404
