import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def mock_api_data(db_session: Session) -> int:
    source = DataSource(
        name="test_api_co_traversal", url="http://test", publisher="pub", license="MIT"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snapshot_id = snap.id

    db_session.execute(
        Station.__table__.insert(),
        [
            {"id": 1, "code": "AAA", "zone": "NR"},
            {"id": 2, "code": "BBB", "zone": "NR"},
            {"id": 3, "code": "CCC", "zone": "NR"},
            {"id": 4, "code": "DDD", "zone": "NR"},
        ],
    )
    db_session.execute(
        StationObservation.__table__.insert(),
        [
            {"station_id": 1, "snapshot_id": snapshot_id, "name": "A", "latitude": 0, "longitude": 0, "state_id": 1},
            {"station_id": 2, "snapshot_id": snapshot_id, "name": "B", "latitude": 0, "longitude": 0, "state_id": 1},
            {"station_id": 3, "snapshot_id": snapshot_id, "name": "C", "latitude": 0, "longitude": 0, "state_id": 1},
            {"station_id": 4, "snapshot_id": snapshot_id, "name": "D", "latitude": 0, "longitude": 0, "state_id": 1},
        ],
    )

    stops = []
    # Train 100
    stops.extend([
        {"train_id": 100, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 1},
        {"train_id": 100, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 2},
        {"train_id": 100, "snapshot_id": snapshot_id, "station_id": 3, "stop_sequence": 3},
        {"train_id": 100, "snapshot_id": snapshot_id, "station_id": 4, "stop_sequence": 4},
    ])

    # Train 101
    stops.extend([
        {"train_id": 101, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 1},
        {"train_id": 101, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 2},
        {"train_id": 101, "snapshot_id": snapshot_id, "station_id": 3, "stop_sequence": 3},
        {"train_id": 101, "snapshot_id": snapshot_id, "station_id": 4, "stop_sequence": 4},
    ])

    # Train 102
    stops.extend([
        {"train_id": 102, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 1},
        {"train_id": 102, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 2},
    ])

    # Train 103 (does not traverse A->B)
    stops.extend([
        {"train_id": 103, "snapshot_id": snapshot_id, "station_id": 3, "stop_sequence": 1},
        {"train_id": 103, "snapshot_id": snapshot_id, "station_id": 4, "stop_sequence": 2},
    ])

    # Train 104 (looping A->B)
    stops.extend([
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 1},
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 2},
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 3},
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 4},
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 3, "stop_sequence": 5},
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 4, "stop_sequence": 6},
    ])

    db_session.execute(Train.__table__.insert(), [
        {"id": 100, "number": "100"},
        {"id": 101, "number": "101"},
        {"id": 102, "number": "102"},
        {"id": 103, "number": "103"},
        {"id": 104, "number": "104"},
    ])

    db_session.execute(TrainObservation.__table__.insert(), [
        {"train_id": 100, "snapshot_id": snapshot_id, "name": "T100", "type": "EXP"},
        {"train_id": 101, "snapshot_id": snapshot_id, "name": "T101", "type": "EXP"},
        {"train_id": 102, "snapshot_id": snapshot_id, "name": "T102", "type": "EXP"},
        {"train_id": 103, "snapshot_id": snapshot_id, "name": "T103", "type": "EXP"},
        {"train_id": 104, "snapshot_id": snapshot_id, "name": "T104", "type": "EXP"},
    ])

    db_session.execute(TrainStopObservation.__table__.insert(), stops)
    db_session.commit()
    return snapshot_id


def test_api_edge_route_co_traversal_affinity_success(
    client: TestClient,
    mock_api_data: int,
) -> None:
    """Test successful edge route co-traversal affinity API call."""
    response = client.get("/api/v1/network/edges/AAA/BBB/route-co-traversal-affinity")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "AAA"
    assert data["to_station_code"] == "BBB"
    assert data["timetable_snapshot_id"] == mock_api_data
    assert data["traversing_train_count"] == 4

    edges = data["shared_edges"]
    assert len(edges) == 3

    # Ordered by shared_train_count DESC, from ASC, to ASC
    assert edges[0]["from_station_code"] == "BBB"
    assert edges[0]["to_station_code"] == "CCC"
    assert edges[0]["shared_train_count"] == 3

    assert edges[1]["from_station_code"] == "CCC"
    assert edges[1]["to_station_code"] == "DDD"
    assert edges[1]["shared_train_count"] == 3

    assert edges[2]["from_station_code"] == "BBB"
    assert edges[2]["to_station_code"] == "AAA"
    assert edges[2]["shared_train_count"] == 1


def test_api_edge_route_co_traversal_affinity_404(
    client: TestClient,
    mock_api_data: int,
) -> None:
    """Test API 404 behavior for edge route co-traversal affinity."""
    response = client.get("/api/v1/network/edges/XXX/BBB/route-co-traversal-affinity")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

    response2 = client.get("/api/v1/network/edges/AAA/CCC/route-co-traversal-affinity")
    assert response2.status_code == 404
    assert "no active timetable trains" in response2.json()["detail"].lower()
