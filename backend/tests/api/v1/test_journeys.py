"""Tests for the Journeys API."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def compare_api_data(populated_db: Session) -> None:
    db_session = populated_db
    source = db_session.query(DataSource).first()
    if not source:
        source = DataSource(
            name="API Compare Source", url="http://test", publisher="Test", license="CC0"
        )
        db_session.add(source)
        db_session.commit()

    snap = DatasetSnapshot(source_id=source.id, retrieved_at=datetime.now(UTC), status="ACTIVE")
    db_session.add(snap)
    db_session.commit()

    s_a = Station(code="STA")
    s_b = Station(code="STB")
    s_c = Station(code="STC")
    db_session.add_all([s_a, s_b, s_c])
    db_session.commit()

    # Train 1: Direct A -> C
    t1 = Train(number="1001")
    db_session.add(t1)
    db_session.commit()
    db_session.add(
        TrainObservation(snapshot_id=snap.id, train_id=t1.id, name="Direct 1", type="Type")
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t1.id,
            station_id=s_a.id,
            stop_sequence=1,
            departure_time="08:00:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t1.id,
            station_id=s_c.id,
            stop_sequence=2,
            arrival_time="12:00:00",
            source_day=1,
        )
    )

    # Train 2 & 3: Transfer A -> B, B -> C
    t2 = Train(number="1002")
    t3 = Train(number="1003")
    db_session.add_all([t2, t3])
    db_session.commit()

    db_session.add(
        TrainObservation(snapshot_id=snap.id, train_id=t2.id, name="Trans 1", type="Type")
    )
    db_session.add(
        TrainObservation(snapshot_id=snap.id, train_id=t3.id, name="Trans 2", type="Type")
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t2.id,
            station_id=s_a.id,
            stop_sequence=1,
            departure_time="06:00:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t2.id,
            station_id=s_b.id,
            stop_sequence=2,
            arrival_time="08:00:00",
            source_day=1,
        )
    )

    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t3.id,
            station_id=s_b.id,
            stop_sequence=1,
            departure_time="10:00:00",
            source_day=1,
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap.id,
            train_id=t3.id,
            station_id=s_c.id,
            stop_sequence=2,
            arrival_time="14:00:00",
            source_day=1,
        )
    )

    db_session.commit()


def test_compare_journeys_default(client: TestClient, compare_api_data: None) -> None:
    response = client.get("/api/v1/journeys/compare?source=STA&destination=STC")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "STA"
    assert data["destination"] == "STC"
    assert data["max_transfers"] == 0
    assert len(data["journeys"]) == 1
    assert data["journeys"][0]["type"] == "DIRECT"
    assert data["journeys"][0]["legs"][0]["train_number"] == "1001"


def test_compare_journeys_max_transfers_1(client: TestClient, compare_api_data: None) -> None:
    response = client.get("/api/v1/journeys/compare?source=STA&destination=STC&max_transfers=1")
    assert response.status_code == 200
    data = response.json()
    assert data["max_transfers"] == 1
    assert len(data["journeys"]) == 2
    types = [j["type"] for j in data["journeys"]]
    assert "DIRECT" in types
    assert "ONE_TRANSFER" in types


def test_compare_journeys_unknown_source(client: TestClient, compare_api_data: None) -> None:
    response = client.get("/api/v1/journeys/compare?source=UNKNOWN&destination=STC")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_compare_journeys_unknown_destination(client: TestClient, compare_api_data: None) -> None:
    response = client.get("/api/v1/journeys/compare?source=STA&destination=UNKNOWN")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_compare_journeys_same_source_dest(client: TestClient, compare_api_data: None) -> None:
    response = client.get("/api/v1/journeys/compare?source=STA&destination=STA")
    assert response.status_code == 400


def test_compare_journeys_invalid_max_transfers(client: TestClient, compare_api_data: None) -> None:
    response = client.get("/api/v1/journeys/compare?source=STA&destination=STC&max_transfers=2")
    assert response.status_code == 422


def test_compare_journeys_negative_transfer_buffer(
    client: TestClient, compare_api_data: None
) -> None:
    response = client.get(
        "/api/v1/journeys/compare?source=STA&destination=STC&min_transfer_minutes=-10"
    )
    assert response.status_code == 422


def test_compare_journeys_negative_layover(client: TestClient, compare_api_data: None) -> None:
    response = client.get(
        "/api/v1/journeys/compare?source=STA&destination=STC&max_layover_minutes=-10"
    )
    assert response.status_code == 422


def test_compare_journeys_buffer_greater_than_layover(
    client: TestClient, compare_api_data: None
) -> None:
    response = client.get(
        "/api/v1/journeys/compare?source=STA&destination=STC&min_transfer_minutes=200&max_layover_minutes=100"
    )
    assert response.status_code == 422


def test_compare_journeys_no_matching_journeys(client: TestClient, compare_api_data: None) -> None:
    response = client.get("/api/v1/journeys/compare?source=STC&destination=STA&max_transfers=1")
    assert response.status_code == 200
    data = response.json()
    assert data["journeys"] == []


def test_compare_journeys_response_schema(client: TestClient, compare_api_data: None) -> None:
    response = client.get("/api/v1/journeys/compare?source=STA&destination=STC&max_transfers=1")
    assert response.status_code == 200
    data = response.json()

    journeys = data["journeys"]
    # Check direct
    direct = next(j for j in journeys if j["type"] == "DIRECT")
    assert direct["journey_id"] is not None
    assert direct["timing_confidence"] == "HIGH"
    assert direct["total_duration_minutes"] == 240
    assert len(direct["legs"]) == 1

    # Check transfer
    transfer = next(j for j in journeys if j["type"] == "ONE_TRANSFER")
    assert transfer["transfer_station"] == "STB"
    assert transfer["layover_minutes"] == 120
    assert len(transfer["legs"]) == 2
