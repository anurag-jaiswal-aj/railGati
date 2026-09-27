import typing

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def setup_service_data(db_session: Session) -> typing.Any:
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.flush()

    snapshot = DatasetSnapshot(id=2, source_id=1, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    trains = []
    for num in ["T1", "T2", "T3", "T4", "T5", "T6"]:
        t = Train(number=num)
        db_session.add(t)
        trains.append(t)
    db_session.flush()
    t_map = {t.number: t.id for t in trains}

    for num in ["T1", "T2", "T3", "T4", "T5", "T6"]:
        to = TrainObservation(snapshot_id=2, train_id=t_map[num], name=f"{num}_NAME")
        db_session.add(to)
    db_session.flush()

    stations = []
    for code in ["SYM", "ASYM", "ISOLATED", "A", "B", "C", "D"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}

    for code in ["SYM", "ASYM", "ISOLATED", "A", "B", "C", "D"]:
        so = StationObservation(
            snapshot_id=2, station_id=s_map[code], name=f"{code}_NAME", state="N/A", zone="N/A"
        )
        db_session.add(so)
    db_session.flush()

    def add_edge(train_num, from_st, to_st, base_seq):
        tso1 = TrainStopObservation(
            snapshot_id=2,
            train_id=t_map[train_num],
            stop_sequence=base_seq,
            station_id=s_map[from_st],
        )
        tso2 = TrainStopObservation(
            snapshot_id=2,
            train_id=t_map[train_num],
            stop_sequence=base_seq + 1,
            station_id=s_map[to_st],
        )
        db_session.add_all([tso1, tso2])

    add_edge("T1", "SYM", "A", 1)
    add_edge("T2", "SYM", "B", 1)
    add_edge("T3", "SYM", "C", 1)
    add_edge("T4", "A", "SYM", 3)
    add_edge("T5", "B", "SYM", 3)
    add_edge("T6", "C", "SYM", 3)

    add_edge("T1", "ASYM", "A", 10)
    add_edge("T2", "B", "ASYM", 10)

    db_session.commit()
    return None


def test_get_station_neighborhood_symmetry_success(
    client: TestClient, setup_service_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/SYM/neighborhood-symmetry")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "SYM"
    assert data["outbound_destinations_count"] == 3
    assert data["inbound_origins_count"] == 3
    assert data["symmetric_neighbors_count"] == 3
    assert data["total_neighborhood_size"] == 3
    assert data["symmetry_ratio"] == 1.0


def test_get_station_neighborhood_symmetry_asymmetric(
    client: TestClient, setup_service_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/ASYM/neighborhood-symmetry")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "ASYM"
    assert data["outbound_destinations_count"] == 1
    assert data["inbound_origins_count"] == 1
    assert data["symmetric_neighbors_count"] == 0
    assert data["total_neighborhood_size"] == 2
    assert data["symmetry_ratio"] == 0.0


def test_get_station_neighborhood_symmetry_unknown_station(
    client: TestClient, setup_service_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/UNKNOWN/neighborhood-symmetry")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_station_neighborhood_symmetry_isolated_station(
    client: TestClient, setup_service_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/ISOLATED/neighborhood-symmetry")
    assert response.status_code == 400
    assert "has no adjacent scheduled timetable occurrences" in response.json()["detail"].lower()
