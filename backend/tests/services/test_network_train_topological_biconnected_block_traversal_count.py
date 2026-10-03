import typing
import pytest

from railgati.services.network import calculate_train_topological_biconnected_block_traversal_count
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.graph import RailwayNetworkEdge
from datetime import UTC, datetime

@pytest.fixture
def test_snapshot_id(db_session: typing.Any) -> int:
    source = DataSource(name="api_test", url="http", publisher="pub", license="MIT")
    db_session.add(source)
    db_session.flush()

    snapshot = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime.now(UTC),
        status="ACTIVE",
    )
    db_session.add(snapshot)
    db_session.flush()
    return snapshot.id

def setup_test_data(db_session, snapshot_id):
    stations = [Station(id=i, code=chr(64+i)) for i in range(1, 9)]
    db_session.add_all(stations)
    db_session.flush()
    
    edges_data = [
        (1, 2), (2, 1), (2, 3), (3, 2), (3, 1), (1, 3),
        (3, 4), (4, 3), (4, 5), (5, 4), (5, 6), (6, 5),
        (6, 4), (4, 6),
        (3, 7), (7, 3), (7, 8), (8, 7), (8, 3), (3, 8)
    ]
    edges = [RailwayNetworkEdge(timetable_snapshot_id=snapshot_id, from_station_id=u, to_station_id=v, train_count=1) for u, v in edges_data]
    db_session.add_all(edges)
    db_session.commit()

def create_train(db_session, snapshot_id, train_id, train_number, stops):
    train = Train(id=train_id, number=train_number)
    db_session.add(train)
    db_session.flush()
    
    obs = TrainObservation(train_id=train_id, snapshot_id=snapshot_id, name=train_number, type="EXP")
    db_session.add(obs)
    
    stop_obs = []
    for i, st in enumerate(stops):
        stop_obs.append(TrainStopObservation(snapshot_id=snapshot_id, train_id=train_id, stop_sequence=i, station_id=st))
    db_session.add_all(stop_obs)
    db_session.commit()

def test_bbtc_one_block_triangle(db_session, test_snapshot_id):
    setup_test_data(db_session, test_snapshot_id)
    create_train(db_session, test_snapshot_id, 101, "T101", [1, 2, 3, 1])
    res = calculate_train_topological_biconnected_block_traversal_count(db_session, test_snapshot_id, "T101")
    assert res["biconnected_block_traversal_count"] == 1
    assert res["total_route_edges"] == 3

def test_bbtc_multiple_blocks(db_session, test_snapshot_id):
    setup_test_data(db_session, test_snapshot_id)
    create_train(db_session, test_snapshot_id, 102, "T102", [1, 3, 4, 5])
    res = calculate_train_topological_biconnected_block_traversal_count(db_session, test_snapshot_id, "T102")
    assert res["biconnected_block_traversal_count"] == 3
    assert res["total_route_edges"] == 3

def test_bbtc_vertex_vs_edge_biconnectivity(db_session, test_snapshot_id):
    setup_test_data(db_session, test_snapshot_id)
    # Train traverses A->C->G.
    # Triangle 1: A-B-C. Triangle 3: C-G-H.
    # They share articulation C. 
    # Edge-biconnected components would group them. Vertex-biconnected components correctly separate them!
    create_train(db_session, test_snapshot_id, 105, "T105", [1, 3, 7])
    res = calculate_train_topological_biconnected_block_traversal_count(db_session, test_snapshot_id, "T105")
    assert res["biconnected_block_traversal_count"] == 2
    assert res["total_route_edges"] == 2

def test_bbtc_repeated_edge_and_self_loops(db_session, test_snapshot_id):
    setup_test_data(db_session, test_snapshot_id)
    create_train(db_session, test_snapshot_id, 103, "T103", [3, 4, 4, 3, 4])
    res = calculate_train_topological_biconnected_block_traversal_count(db_session, test_snapshot_id, "T103")
    assert res["biconnected_block_traversal_count"] == 1
    assert res["total_route_edges"] == 3

def test_bbtc_zero_edges(db_session, test_snapshot_id):
    setup_test_data(db_session, test_snapshot_id)
    create_train(db_session, test_snapshot_id, 104, "T104", [1])
    res = calculate_train_topological_biconnected_block_traversal_count(db_session, test_snapshot_id, "T104")
    assert res["biconnected_block_traversal_count"] == 0
    assert res["total_route_edges"] == 0

def test_bbtc_unknown_train(db_session, test_snapshot_id):
    setup_test_data(db_session, test_snapshot_id)
    with pytest.raises(ValueError, match="Train UNK not found"):
        calculate_train_topological_biconnected_block_traversal_count(db_session, test_snapshot_id, "UNK")
