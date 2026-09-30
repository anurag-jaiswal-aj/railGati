import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.graph_builder import build_graph_for_timetable_snapshot


@pytest.fixture
def api_quadrangle_fixtures(db_session: Session) -> None:
    source = DataSource(name="test_api", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    snapshot = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    s_a = Station(code="A")
    s_b = Station(code="B")
    s_c = Station(code="C")
    s_d = Station(code="D")
    db_session.add_all([s_a, s_b, s_c, s_d])
    db_session.flush()

    t = Train(number="100")
    db_session.add(t)
    db_session.flush()

    # Square A-B-C-D-A
    for i, s in enumerate([s_a, s_b, s_c, s_d, s_a]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snapshot.id,
                train_id=t.id,
                stop_sequence=i + 1,
                station_id=s.id,
                departure_time="10:00:00",
                source_day=1,
            )
        )
    db_session.add(TrainObservation(snapshot_id=snapshot.id, train_id=t.id, name="Test Train"))
    db_session.commit()

    build_graph_for_timetable_snapshot(db_session, snapshot.id)


def test_api_quadrangle_support_success(client: TestClient, api_quadrangle_fixtures: None) -> None:
    response = client.get("/api/v1/network/edges/A/B/topological-quadrangle-support")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "A"
    assert data["to_station_code"] == "B"
    assert data["quadrangle_support"] == 1


def test_api_quadrangle_support_not_found(
    client: TestClient, api_quadrangle_fixtures: None
) -> None:
    response = client.get("/api/v1/network/edges/A/Z/topological-quadrangle-support")
    assert response.status_code == 404


def test_api_quadrangle_support_self_loop(
    client: TestClient, api_quadrangle_fixtures: None
) -> None:
    response = client.get("/api/v1/network/edges/A/A/topological-quadrangle-support")
    assert response.status_code == 400
