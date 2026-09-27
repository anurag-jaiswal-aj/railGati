import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation
from railgati.services.network import calculate_edge_paired_route_symmetry


@pytest.fixture
def setup_service_data(db_session: Session) -> None:
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.flush()

    snapshot = DatasetSnapshot(id=2, source_id=1, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    stations = []
    for code in ["MGS", "JEP", "GOGH", "GBY", "NDLS", "CNB"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}
    
    for s in stations:
        db_session.add(StationObservation(snapshot_id=2, station_id=s.id, name=f"{s.code} Name"))
    db_session.flush()

    trains = []
    for num in ["F1", "R1", "F2", "R2", "F3", "F4", "F5"]:
        t = Train(number=num)
        db_session.add(t)
        trains.append(t)
    db_session.flush()
    t_map = {t.number: t.id for t in trains}

    def add_train(train_num: str, return_num: str, stops: list[str]) -> None:
        db_session.add(TrainObservation(snapshot_id=2, train_id=t_map[train_num], name=f"{train_num} Name", type="EXP", return_train_number=return_num))
        db_session.flush()
        seq = 1
        for code in stops:
            db_session.execute(
                text("INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence) VALUES (2, :t, :s, :seq)"),
                {"t": t_map[train_num], "s": s_map[code], "seq": seq}
            )
            seq += 1

    # MGS -> JEP has 2 forward trains, both have reciprocal
    add_train("F1", "R1", ["MGS", "JEP", "CNB"])
    add_train("R1", "F1", ["CNB", "JEP", "MGS"])
    add_train("F2", "R2", ["MGS", "JEP"])
    add_train("R2", "F2", ["JEP", "MGS", "JEP", "MGS"]) # Duplicate reciprocal edge, should only count once

    # GOGH -> GBY has forward trains, but no reciprocal
    add_train("F3", "R1", ["GOGH", "GBY"]) # R1 doesn't go GBY -> GOGH
    add_train("F4", None, ["GOGH", "GBY"]) # No return train

    # NDLS -> CNB has no forward trains
    add_train("F5", None, ["NDLS", "JEP", "CNB"]) # Not adjacent

    db_session.flush()


def test_calculate_edge_paired_route_symmetry_normal(db_session: Session, setup_service_data):
    result = calculate_edge_paired_route_symmetry(db_session, "MGS", "JEP")
    
    assert result["from_station_code"] == "MGS"
    assert result["to_station_code"] == "JEP"
    assert result["timetable_snapshot_id"] == 2
    assert result["total_forward_trains"] == 3
    assert result["symmetrical_return_trains"] == 2
    assert result["symmetry_ratio"] == 2 / 3


def test_calculate_edge_paired_route_symmetry_zero_reciprocal(db_session: Session, setup_service_data):
    result = calculate_edge_paired_route_symmetry(db_session, "GOGH", "GBY")
    
    assert result["from_station_code"] == "GOGH"
    assert result["to_station_code"] == "GBY"
    assert result["total_forward_trains"] == 2
    assert result["symmetrical_return_trains"] == 0
    assert result["symmetry_ratio"] == 0.0


def test_calculate_edge_paired_route_symmetry_zero_forward(db_session: Session, setup_service_data):
    with pytest.raises(ValueError) as excinfo:
        calculate_edge_paired_route_symmetry(db_session, "NDLS", "CNB")
    assert "No qualifying forward" in str(excinfo.value)


def test_calculate_edge_paired_route_symmetry_unknown_station(db_session: Session, setup_service_data):
    with pytest.raises(ValueError) as excinfo:
        calculate_edge_paired_route_symmetry(db_session, "FAKE", "MGS")
    assert "not found" in str(excinfo.value).lower()

    with pytest.raises(ValueError) as excinfo:
        calculate_edge_paired_route_symmetry(db_session, "MGS", "FAKE")
    assert "not found" in str(excinfo.value).lower()
