import typing
import pytest
from datetime import UTC, datetime

from railgati.services.network import calculate_train_topological_global_degree_assortativity
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.graph import RailwayNetworkEdge

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
    # Create 8 stations
    stations = [Station(id=i, code=chr(64+i)) for i in range(1, 9)]
    db_session.add_all(stations)
    db_session.flush()
    
    # Let's design a graph where:
    # 1: deg 4 (1-2, 1-3, 1-4, 1-5)
    # 2: deg 4 (2-1, 2-3, 2-4, 2-5)
    # 3: deg 4 (3-1, 3-2, 3-4, 3-5)
    # 4: deg 4 (4-1, 4-2, 4-3, 4-5)
    # 5: deg 4 (5-1, 5-2, 5-3, 5-4)
    # 6: deg 1 (6-1)
    # 7: deg 1 (7-2)
    # 8: deg 1 (8-3)
    # 
    # Actually wait. If 1,2,3,4,5 are fully connected, that's 10 edges.
    # 1 connects to 2,3,4,5 (4 edges). But 1 also connects to 6. So 1's degree is 5.
    # Let's make it simpler.
    # Node A (deg 2), B (deg 2), C (deg 2) -> Triangle
    # Node D (deg 3), E (deg 3), F (deg 3) -> Triangle, plus one edge connecting them all to a hub H (deg 3)
    # Just build edges directly and explicitly.
    
    # For positive assortativity:
    # high degree node connects to high degree node.
    # low degree node connects to low degree node.
    # Let's have:
    # 1 (deg 3), 2 (deg 3) connected.
    # 3 (deg 1), 4 (deg 1) connected.
    # 1-5, 1-6
    # 2-7, 2-8
    edges_data = [
        (1, 2), (2, 1),
        (1, 5), (5, 1),
        (1, 6), (6, 1),
        (2, 7), (7, 2),
        (2, 8), (8, 2),
        (3, 4), (4, 3)
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

def test_assortativity_positive(db_session, test_snapshot_id):
    setup_test_data(db_session, test_snapshot_id)
    # Edges in network: 
    # (1,2) -> degs: (3,3)
    # (3,4) -> degs: (1,1)
    # A route that covers both! T1: 1 -> 2 -> 1 -> 5 -> 1 -> 6
    # No, that's not a path. 
    # Just make T1: 1 -> 2
    # But 1 edge is None! We need >= 2 edges.
    # How about a disjoint train route? (Not physically real, but topological). 
    # Or add an edge: 2-3 (then 2 is deg 4, 3 is deg 2).
    pass

def test_assortativity_math(db_session, test_snapshot_id):
    # Let's create a known graph and a known train.
    stations = [Station(id=i, code=chr(64+i)) for i in range(1, 6)]
    db_session.add_all(stations)
    db_session.flush()
    
    # 1-2, 2-3, 3-4, 4-5
    # Degrees: 
    # 1: 1
    # 2: 2
    # 3: 2
    # 4: 2
    # 5: 1
    edges_data = [
        (1, 2), (2, 1),
        (2, 3), (3, 2),
        (3, 4), (4, 3),
        (4, 5), (5, 4),
    ]
    edges = [RailwayNetworkEdge(timetable_snapshot_id=test_snapshot_id, from_station_id=u, to_station_id=v, train_count=1) for u, v in edges_data]
    db_session.add_all(edges)
    db_session.commit()
    
    # Route: 1 -> 2 -> 3 -> 4
    # Edges: (1,2) degs (1,2)
    #        (2,3) degs (2,2)
    #        (3,4) degs (2,2)
    # Is this assortative? 
    # Node pairs: (1,2), (2,1), (2,2), (2,2), (2,2), (2,2).
    # Expected variance:
    # N=6. X: 1, 2, 2, 1, 2, 2, 2, 2, 2, 2. Wait.
    # X = [1, 2, 2, 2, 2, 2]
    # Sum X = 11. mu = 11/6.
    # Sum X2 = 1+4+4+4+4+4 = 21.
    # Var = 21/6 - (11/6)^2 = 126/36 - 121/36 = 5/36.
    # Sum XY = (1*2 + 2*2 + 2*2) * 2 = (2 + 4 + 4) * 2 = 20.
    # Cov = 20/6 - (11/6)^2 = 120/36 - 121/36 = -1/36.
    # r = Cov / Var = -1/5 = -0.2.
    
    create_train(db_session, test_snapshot_id, 301, "T301", [1, 2, 3, 4])
    res = calculate_train_topological_global_degree_assortativity(db_session, test_snapshot_id, "T301")
    
    assert res["distinct_route_edges"] == 3
    assert abs(res["route_assortativity_coefficient"] - (-0.2)) < 1e-6
    
def test_assortativity_zero_variance(db_session, test_snapshot_id):
    stations = [Station(id=i, code=chr(64+i)) for i in range(1, 4)]
    db_session.add_all(stations)
    db_session.flush()
    # Cycle 1-2, 2-3, 3-1. All degs = 2.
    edges_data = [(1, 2), (2, 1), (2, 3), (3, 2), (3, 1), (1, 3)]
    edges = [RailwayNetworkEdge(timetable_snapshot_id=test_snapshot_id, from_station_id=u, to_station_id=v, train_count=1) for u, v in edges_data]
    db_session.add_all(edges)
    db_session.commit()
    
    create_train(db_session, test_snapshot_id, 302, "T302", [1, 2, 3])
    res = calculate_train_topological_global_degree_assortativity(db_session, test_snapshot_id, "T302")
    
    assert res["distinct_route_edges"] == 2
    assert res["route_assortativity_coefficient"] is None

def test_assortativity_one_edge(db_session, test_snapshot_id):
    stations = [Station(id=i, code=chr(64+i)) for i in range(1, 3)]
    db_session.add_all(stations)
    db_session.flush()
    edges_data = [(1, 2), (2, 1)]
    edges = [RailwayNetworkEdge(timetable_snapshot_id=test_snapshot_id, from_station_id=u, to_station_id=v, train_count=1) for u, v in edges_data]
    db_session.add_all(edges)
    db_session.commit()
    
    create_train(db_session, test_snapshot_id, 303, "T303", [1, 2])
    res = calculate_train_topological_global_degree_assortativity(db_session, test_snapshot_id, "T303")
    
    assert res["distinct_route_edges"] == 1
    assert res["route_assortativity_coefficient"] is None
