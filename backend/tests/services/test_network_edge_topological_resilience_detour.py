import pytest
from sqlalchemy.orm import Session
from fastapi import HTTPException

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.graph_builder import build_graph_for_timetable_snapshot
from railgati.services.network import get_edge_resilience_detour

@pytest.fixture
def test_data(db_session: Session) -> dict:
    source = DataSource(name="test_source", url="http://test", publisher="Test", license="Test")
    db_session.add(source)
    db_session.commit()

    snapshot = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    db_session.commit()
    
    stations = {
        code: Station(code=code) for code in ["A", "B", "C", "D", "E"]
    }
    db_session.add_all(stations.values())
    db_session.commit()

    for code, st in stations.items():
        db_session.add(StationObservation(station_id=st.id, snapshot_id=snapshot.id, name=f"St {code}"))
    db_session.commit()

    return {"snapshot": snapshot, "stations": stations}

def create_train(db_session: Session, snapshot_id: int, train_num: str, stops: list[str], stations: dict) -> Train:
    tr = Train(number=train_num)
    db_session.add(tr)
    db_session.commit()
    
    db_session.add(TrainObservation(train_id=tr.id, snapshot_id=snapshot_id, name=train_num))
    db_session.commit()
    
    for i, code in enumerate(stops, 1):
        db_session.add(
            TrainStopObservation(
                train_id=tr.id,
                snapshot_id=snapshot_id,
                station_id=stations[code].id,
                stop_sequence=i,
            )
        )
    db_session.commit()
    return tr

def test_structural_bridge(db_session: Session, test_data: dict):
    # A-B with no alternative
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)
    
    res = get_edge_resilience_detour(db_session, "A", "B")
    
    assert res["from_station_code"] == "A"
    assert res["to_station_code"] == "B"
    assert res["detour_distance"] is None
    assert res["is_structural_bridge"] is True

def test_triangle(db_session: Session, test_data: dict):
    # A-B, B-C, A-C. Target A-B
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T2", ["B", "C"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T3", ["A", "C"], test_data["stations"])
    
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)
    
    res = get_edge_resilience_detour(db_session, "A", "B")
    assert res["detour_distance"] == 2
    assert res["is_structural_bridge"] is False

def test_longer_alternative(db_session: Session, test_data: dict):
    # A-B, and A-C-D-B
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T2", ["A", "C", "D", "B"], test_data["stations"])
    
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)
    
    res = get_edge_resilience_detour(db_session, "A", "B")
    assert res["detour_distance"] == 3
    assert res["is_structural_bridge"] is False

def test_disconnected_edge_is_bridge(db_session: Session, test_data: dict):
    # A-B and C-D. They are separate components.
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T2", ["C", "D"], test_data["stations"])
    
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)
    
    res = get_edge_resilience_detour(db_session, "A", "B")
    assert res["is_structural_bridge"] is True
    assert res["detour_distance"] is None

def test_reciprocal_directed_rows(db_session: Session, test_data: dict):
    # A->B and B->A
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T2", ["B", "A"], test_data["stations"])
    
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)
    
    res = get_edge_resilience_detour(db_session, "A", "B")
    assert res["is_structural_bridge"] is True
    assert res["detour_distance"] is None

def test_unknown_station(db_session: Session, test_data: dict):
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)
    
    res = get_edge_resilience_detour(db_session, "X", "B")
    assert res is None

def test_valid_station_pair_not_edge(db_session: Session, test_data: dict):
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "B"], test_data["stations"])
    build_graph_for_timetable_snapshot(db_session, test_data["snapshot"].id)
    
    res = get_edge_resilience_detour(db_session, "A", "C")
    assert res is None

def test_self_edge_invalid(db_session: Session, test_data: dict):
    with pytest.raises(ValueError) as exc:
        get_edge_resilience_detour(db_session, "A", "A")
    assert "self-loops" in str(exc.value)
