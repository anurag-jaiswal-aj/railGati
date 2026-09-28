import typing

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def api_od_exclusivity_fixtures(db_session: Session) -> typing.Any:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.commit()
    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {}
    for code in ["A", "B", "C"]:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()

    # Target: A -> B -> C
    tr = Train(number="T_API")
    db_session.add(tr)
    db_session.commit()
    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=tr.id, name="T_API", type="EXP"))

    for idx, s_code in enumerate(["A", "B", "C"]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap_id,
                train_id=tr.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1,
            )
        )

    # Candidate: A -> B
    cand = Train(number="C_API")
    db_session.add(cand)
    db_session.commit()
    db_session.add(
        TrainObservation(snapshot_id=snap_id, train_id=cand.id, name="C_API", type="EXP")
    )

    for idx, s_code in enumerate(["A", "B"]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap_id,
                train_id=cand.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1,
            )
        )

    db_session.commit()

    return {"snapshot_id": snap_id}


def test_api_od_exclusivity_success(
    client: TestClient, api_od_exclusivity_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/trains/T_API/od-exclusivity")
    assert response.status_code == 200
    data = response.json()

    assert data["target_train_number"] == "T_API"
    assert data["exclusive_od_pair_count"] == 2
    pairs = data["exclusive_od_pairs"]

    assert pairs[0]["origin_station_code"] == "A"
    assert pairs[0]["destination_station_code"] == "C"

    assert pairs[1]["origin_station_code"] == "B"
    assert pairs[1]["destination_station_code"] == "C"


def test_api_od_exclusivity_not_found(
    client: TestClient, api_od_exclusivity_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/trains/INVALID/od-exclusivity")
    assert response.status_code == 404
