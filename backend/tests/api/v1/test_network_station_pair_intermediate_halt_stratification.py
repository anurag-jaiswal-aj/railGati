import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def setup_mock_api(db_session: Session) -> tuple[str, str]:
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.flush()

    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=1, name="dummy"))
    db_session.commit()

    bct = Station(code="BCT")
    bvi = Station(code="BVI")
    mid = Station(code="MID")
    db_session.add_all([bct, bvi, mid])
    db_session.commit()

    t1 = Train(number="1001")
    t2 = Train(number="1002")
    db_session.add_all([t1, t2])
    db_session.commit()

    # Train 1: BCT -> MID -> BVI (1 halt)
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap_id, train_id=t1.id, station_id=bct.id, stop_sequence=1
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap_id, train_id=t1.id, station_id=mid.id, stop_sequence=2
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap_id, train_id=t1.id, station_id=bvi.id, stop_sequence=3
        )
    )

    # Train 2: BCT -> BVI (0 halts)
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap_id, train_id=t2.id, station_id=bct.id, stop_sequence=1
        )
    )
    db_session.add(
        TrainStopObservation(
            snapshot_id=snap_id, train_id=t2.id, station_id=bvi.id, stop_sequence=2
        )
    )
    db_session.commit()

    return "BCT", "BVI"


def test_api_stratification_success(
    client: TestClient, db_session: Session, setup_mock_api
) -> None:
    response = client.get("/api/v1/network/station-pairs/BCT/BVI/intermediate-halt-stratification")
    assert response.status_code == 200
    data = response.json()
    assert data["origin_station_code"] == "BCT"
    assert data["destination_station_code"] == "BVI"
    assert data["total_traversal_count"] == 2
    assert data["min_halts"] == 0
    assert data["max_halts"] == 1
    assert data["distinct_halt_strata_count"] == 2
    assert data["is_perfectly_homogeneous"] is False


def test_api_stratification_zero_results(
    client: TestClient, db_session: Session, setup_mock_api
) -> None:
    response = client.get("/api/v1/network/station-pairs/BVI/BCT/intermediate-halt-stratification")
    assert response.status_code == 200
    data = response.json()
    assert data["total_traversal_count"] == 0
    assert data["min_halts"] is None


def test_api_stratification_not_found(
    client: TestClient, db_session: Session, setup_mock_api
) -> None:
    response = client.get(
        "/api/v1/network/station-pairs/UNKNOWN/BVI/intermediate-halt-stratification"
    )
    assert response.status_code == 404


def test_api_stratification_same_station(
    client: TestClient, db_session: Session, setup_mock_api
) -> None:
    response = client.get("/api/v1/network/station-pairs/BCT/BCT/intermediate-halt-stratification")
    assert response.status_code == 400
