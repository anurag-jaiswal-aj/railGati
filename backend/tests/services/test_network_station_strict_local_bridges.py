import pytest
from sqlalchemy.orm import Session
from fastapi import HTTPException

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_strict_local_bridges


from railgati.models.provenance import DatasetSnapshot, DataSource

@pytest.fixture
def test_data(db_session: Session) -> dict:
    source = DataSource(name="test_source", url="http://test", publisher="Test", license="Test")
    db_session.add(source)
    db_session.commit()

    snapshot = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    db_session.commit()
    
    dummy_train = Train(number="DUMMY")
    db_session.add(dummy_train)
    db_session.commit()

    db_session.add(TrainObservation(snapshot_id=snapshot.id, train_id=dummy_train.id, name="DUMMY"))
    db_session.commit()
    
    stations = {
        code: Station(code=code) for code in ["S", "A", "B", "X", "Y"]
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


def test_basic_qualifying_bridge(db_session: Session, test_data: dict):
    # A-S-B with no A-B and no A-X-B
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "S", "B"], test_data["stations"])
    
    res = calculate_station_strict_local_bridges(db_session, "S")
    
    assert res["station_code"] == "S"
    assert res["total_neighbor_pairs"] == 1
    pair = res["evaluated_pairs"][0]
    # Check unordered pair correctness
    assert set([pair["neighbor_a"], pair["neighbor_b"]]) == {"A", "B"}
    assert pair["has_direct_adjacency"] is False
    assert pair["alternative_bridge_count"] == 0
    assert pair["is_strict_local_bridge"] is True


def test_direct_edge_rejection(db_session: Session, test_data: dict):
    # A-S-B plus A-B
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "S", "B"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T2", ["A", "B"], test_data["stations"])
    
    res = calculate_station_strict_local_bridges(db_session, "S")
    
    pair = res["evaluated_pairs"][0]
    assert pair["has_direct_adjacency"] is True
    assert pair["is_strict_local_bridge"] is False


def test_alternative_x_rejection(db_session: Session, test_data: dict):
    # A-S-B plus A-X-B
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "S", "B"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T2", ["A", "X", "B"], test_data["stations"])
    
    res = calculate_station_strict_local_bridges(db_session, "S")
    
    pair = res["evaluated_pairs"][0]
    assert pair["has_direct_adjacency"] is False
    assert pair["alternative_bridge_count"] == 1
    assert pair["is_strict_local_bridge"] is False


def test_multiple_alternatives(db_session: Session, test_data: dict):
    # A-S-B plus A-X-B and A-Y-B
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "S", "B"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T2", ["A", "X", "B"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T3", ["A", "Y", "B"], test_data["stations"])
    
    res = calculate_station_strict_local_bridges(db_session, "S")
    
    pair = res["evaluated_pairs"][0]
    assert pair["has_direct_adjacency"] is False
    assert pair["alternative_bridge_count"] == 2
    assert pair["is_strict_local_bridge"] is False


def test_longer_detour_non_effect(db_session: Session, test_data: dict):
    # A-S-B plus A-X-Y-B, but no A-X-B
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "S", "B"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T2", ["A", "X", "Y", "B"], test_data["stations"])
    
    res = calculate_station_strict_local_bridges(db_session, "S")
    
    pair = res["evaluated_pairs"][0]
    assert pair["has_direct_adjacency"] is False
    assert pair["alternative_bridge_count"] == 0
    assert pair["is_strict_local_bridge"] is True


def test_reciprocal_directional_edges(db_session: Session, test_data: dict):
    # S -> A, A -> S
    # B -> S, S -> B
    create_train(db_session, test_data["snapshot"].id, "T1", ["S", "A"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T2", ["A", "S"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T3", ["B", "S"], test_data["stations"])
    create_train(db_session, test_data["snapshot"].id, "T4", ["S", "B"], test_data["stations"])
    
    res = calculate_station_strict_local_bridges(db_session, "S")
    assert res["total_neighbor_pairs"] == 1
    pair = res["evaluated_pairs"][0]
    assert pair["is_strict_local_bridge"] is True


def test_cyclic_and_repeated_occurrences(db_session: Session, test_data: dict):
    # T1: A-S-B-S-A
    create_train(db_session, test_data["snapshot"].id, "T1", ["A", "S", "B", "S", "A"], test_data["stations"])
    
    res = calculate_station_strict_local_bridges(db_session, "S")
    assert res["total_neighbor_pairs"] == 1
    pair = res["evaluated_pairs"][0]
    assert pair["is_strict_local_bridge"] is True


def test_degree_less_than_2(db_session: Session, test_data: dict):
    # Degree 1
    create_train(db_session, test_data["snapshot"].id, "T1", ["S", "A"], test_data["stations"])
    res = calculate_station_strict_local_bridges(db_session, "S")
    assert res["total_neighbor_pairs"] == 0
    assert len(res["evaluated_pairs"]) == 0
    
    # Degree 0
    res_y = calculate_station_strict_local_bridges(db_session, "Y")
    assert res_y["total_neighbor_pairs"] == 0


def test_unknown_station(db_session: Session, test_data: dict):
    with pytest.raises(HTTPException) as exc:
        calculate_station_strict_local_bridges(db_session, "Z")
    assert exc.value.status_code == 404
