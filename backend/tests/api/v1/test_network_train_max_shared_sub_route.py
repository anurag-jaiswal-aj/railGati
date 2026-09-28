import typing

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def api_max_shared_sub_route_fixtures(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(
        name="test_source", url="http://test", publisher="test_publisher", license="test_license"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["A", "B", "C"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    for st in stations.values():
        db_session.add(
            StationObservation(
                station_id=st.id, snapshot_id=snap_id, name=st.code
            )
        )
    db_session.commit()

    trains_data = [
        ("TARGET_API", ["A", "B", "C"]),
        ("MATCH_API", ["A", "B", "C"]),
    ]

    for t_num, route in trains_data:
        tr = Train(number=t_num)
        db_session.add(tr)
        db_session.commit()
        db_session.add(
            TrainObservation(snapshot_id=snap_id, train_id=tr.id, name=t_num, type="EXP")
        )
        for idx, s_code in enumerate(route):
            db_session.add(TrainStopObservation(
                snapshot_id=snap_id,
                train_id=tr.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1
            ))
        db_session.commit()

    return {"snapshot_id": snap_id, "stations": stations}


def test_api_max_shared_sub_route_success(client: TestClient, api_max_shared_sub_route_fixtures: typing.Any) -> None:
    response = client.get("/api/v1/network/trains/TARGET_API/maximum-shared-sub-route")
    assert response.status_code == 200
    data = response.json()
    assert data["target_train_number"] == "TARGET_API"
    assert len(data["top_shared_sub_routes"]) == 1
    assert data["top_shared_sub_routes"][0]["other_train_number"] == "MATCH_API"
    assert data["top_shared_sub_routes"][0]["shared_station_count"] == 3
    assert data["top_shared_sub_routes"][0]["start_station_code"] == "A"
    assert data["top_shared_sub_routes"][0]["end_station_code"] == "C"


def test_api_max_shared_sub_route_not_found(client: TestClient, api_max_shared_sub_route_fixtures: typing.Any) -> None:
    response = client.get("/api/v1/network/trains/INVALID/maximum-shared-sub-route")
    assert response.status_code == 404
