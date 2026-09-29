import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def extension_api_fixtures(db_session: Session) -> dict:
    source = DataSource(
        name="TEST_API_PHASE49", url="http://test", publisher="TEST", license="TEST"
    )
    db_session.add(source)
    db_session.commit()

    snapshot = DatasetSnapshot(
        source_id=source.id,
        status="ACTIVE",
    )
    db_session.add(snapshot)
    db_session.commit()

    s_pre = Station(code="PRE")
    s_o = Station(code="O")
    s_d = Station(code="D")
    s_post = Station(code="POST")
    db_session.add_all([s_pre, s_o, s_d, s_post])
    db_session.commit()

    t1 = Train(number="T1")
    db_session.add(t1)
    db_session.commit()

    db_session.add(TrainObservation(snapshot_id=snapshot.id, train_id=t1.id, name="T1"))

    stops = [
        (s_pre, 1), (s_o, 2), (s_d, 3), (s_post, 4)
    ]
    for st, seq in stops:
        db_session.add(
            TrainStopObservation(
                snapshot_id=snapshot.id, train_id=t1.id, station_id=st.id, stop_sequence=seq
            )
        )
    db_session.commit()

    return {
        "snapshot_id": snapshot.id,
    }

def test_api_route_extension_success(client: TestClient, extension_api_fixtures: dict) -> None:
    response = client.get("/api/v1/network/station-pairs/O/D/route-extension")
    assert response.status_code == 200
    data = response.json()
    assert data["origin_station"] == "O"
    assert data["destination_station"] == "D"
    assert data["traversal_occurrence_count"] == 1
    assert data["pre_origin_station_count"] == 1
    assert data["post_destination_station_count"] == 1
    assert data["total_extension_station_count"] == 2

def test_api_route_extension_ordered_direction(
    client: TestClient, extension_api_fixtures: dict
) -> None:
    # Reverse direction has no valid traversals
    response = client.get("/api/v1/network/station-pairs/D/O/route-extension")
    assert response.status_code == 404

def test_api_route_extension_missing_station(
    client: TestClient, extension_api_fixtures: dict
) -> None:
    response = client.get("/api/v1/network/station-pairs/MISSING/D/route-extension")
    assert response.status_code == 404

def test_api_route_extension_same_station(client: TestClient, extension_api_fixtures: dict) -> None:
    response = client.get("/api/v1/network/station-pairs/O/O/route-extension")
    assert response.status_code == 400
