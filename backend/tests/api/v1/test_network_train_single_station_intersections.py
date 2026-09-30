import pytest
from starlette.testclient import TestClient
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation

@pytest.fixture
def mock_intersections_api_data(db_session):
    source = DataSource(name="Source 61 API", publisher="pub", url="url", license="mit")
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stn_codes = ["A", "B", "C", "D", "X", "Y", "Z"]
    stations = {}
    for code in stn_codes:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()
    
    for code in stn_codes:
        db_session.add(StationObservation(station_id=stations[code].id, snapshot_id=snap_id, name=f"Stn {code}"))
    db_session.commit()

    def add_train(num: str, sequence: list[str]) -> None:
        t = Train(number=num)
        db_session.add(t)
        db_session.commit()
        db_session.add(TrainObservation(train_id=t.id, snapshot_id=snap_id, name=f"Train {num}", type="EXP"))
        for idx, code in enumerate(sequence):
            db_session.add(TrainStopObservation(
                train_id=t.id,
                snapshot_id=snap_id,
                station_id=stations[code].id,
                stop_sequence=idx + 1
            ))
        db_session.commit()

    add_train("T1", ["A", "B", "C"])
    add_train("U1", ["X", "B", "Y"])
    add_train("U2", ["X", "Y", "Z"])
    return None

def test_api_single_station_intersection_success(client: TestClient, mock_intersections_api_data):
    response = client.get("/api/v1/network/trains/T1/single-station-intersections")
    if response.status_code != 200:
        print("ERROR:", response.text)
    assert response.status_code == 200
    data = response.json()

    assert data["target_train_number"] == "T1"
    assert data["total_intersecting_trains"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["other_train_number"] == "U1"
    assert data["items"][0]["shared_station_code"] == "B"

def test_api_single_station_intersection_not_found(client: TestClient, mock_intersections_api_data):
    response = client.get("/api/v1/network/trains/UNKNOWN/single-station-intersections")
    assert response.status_code == 404
