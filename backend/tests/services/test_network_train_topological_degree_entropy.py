import typing
import pytest
import math
from datetime import UTC, datetime

from railgati.services.network import calculate_train_topological_degree_entropy
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.graph import RailwayGraphBuild, RailwayStationTopologicalCoreness

def compute_entropy_oracle(y_vals: list[int]) -> float | None:
    """Independent oracle for Shannon Entropy computation."""
    n = len(y_vals)
    if n < 2:
        return None

    counts = {}
    for d in y_vals:
        counts[d] = counts.get(d, 0) + 1
        
    entropy = 0.0
    for count in counts.values():
        p = count / n
        entropy -= p * math.log2(p)

    return entropy

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

@pytest.fixture
def test_graph_build_id(db_session: typing.Any, test_snapshot_id: int) -> int:
    build = RailwayGraphBuild(
        timetable_snapshot_id=test_snapshot_id,
        status="ACTIVE"
    )
    db_session.add(build)
    db_session.flush()
    return build.id

def create_train(db_session, snapshot_id, train_id, train_number, stops, train_name=None):
    train = Train(id=train_id, number=train_number)
    db_session.add(train)
    db_session.flush()
    
    if not train_name:
        train_name = train_number

    obs = TrainObservation(train_id=train_id, snapshot_id=snapshot_id, name=train_name, type="EXP")
    db_session.add(obs)

    stop_obs = []
    for i, st in enumerate(stops):
        stop_obs.append(TrainStopObservation(snapshot_id=snapshot_id, train_id=train_id, stop_sequence=i, station_id=st))
    db_session.add_all(stop_obs)
    db_session.commit()

def setup_degrees(db_session, snapshot_id, build_id, degrees_dict):
    stations = []
    coreness = []
    for st_id, deg in degrees_dict.items():
        stations.append(Station(id=st_id, code=f"ST{st_id}"))
        coreness.append(RailwayStationTopologicalCoreness(
            graph_build_id=build_id,
            timetable_snapshot_id=snapshot_id,
            station_id=st_id,
            coreness=1,
            degree=deg
        ))
    db_session.add_all(stations)
    db_session.flush()
    db_session.add_all(coreness)
    db_session.commit()

def test_homogeneous_degrees_entropy_zero(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:5, 2:5, 3:5, 4:5})
    create_train(db_session, test_snapshot_id, 101, "T101", [1, 2, 3, 4])
    res = calculate_train_topological_degree_entropy(db_session, test_snapshot_id, "T101")
    assert res["total_sequence_stops"] == 4
    assert res["distinct_degree_count"] == 1
    assert abs(res["topological_degree_entropy"] - 0.0) < 1e-6

def test_multiple_degrees(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:1, 3:3, 4:3})
    create_train(db_session, test_snapshot_id, 102, "T102", [1, 2, 3, 4])
    res = calculate_train_topological_degree_entropy(db_session, test_snapshot_id, "T102")
    assert res["total_sequence_stops"] == 4
    assert res["distinct_degree_count"] == 2
    
    oracle = compute_entropy_oracle([1, 1, 3, 3]) # exactly 1.0 bit
    assert abs(res["topological_degree_entropy"] - oracle) < 1e-6
    assert abs(res["topological_degree_entropy"] - 1.0) < 1e-6

def test_short_routes(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:2, 3:1})

    # 1 stop (L < 2)
    create_train(db_session, test_snapshot_id, 104, "T104", [1])
    res = calculate_train_topological_degree_entropy(db_session, test_snapshot_id, "T104")
    assert res["total_sequence_stops"] == 1
    assert res["distinct_degree_count"] == 0
    assert res["topological_degree_entropy"] is None

    # 2 stops, distinct degrees.
    create_train(db_session, test_snapshot_id, 105, "T105", [1, 2])
    res = calculate_train_topological_degree_entropy(db_session, test_snapshot_id, "T105")
    assert res["total_sequence_stops"] == 2
    assert res["distinct_degree_count"] == 2
    assert abs(res["topological_degree_entropy"] - 1.0) < 1e-6
    
    # 2 stops, same degrees.
    create_train(db_session, test_snapshot_id, 106, "T106", [1, 3])
    res = calculate_train_topological_degree_entropy(db_session, test_snapshot_id, "T106")
    assert res["total_sequence_stops"] == 2
    assert res["distinct_degree_count"] == 1
    assert abs(res["topological_degree_entropy"] - 0.0) < 1e-6

def test_repeated_station_counts_independently(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:2, 3:3})
    create_train(db_session, test_snapshot_id, 109, "T109", [1, 2, 1, 3, 2, 1])
    res = calculate_train_topological_degree_entropy(db_session, test_snapshot_id, "T109")
    
    assert res["total_sequence_stops"] == 6
    assert res["distinct_degree_count"] == 3
    oracle = compute_entropy_oracle([1, 2, 1, 3, 2, 1])
    assert abs(res["topological_degree_entropy"] - oracle) < 1e-6

def test_missing_degree_defaults_to_zero(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1})
    # Station 2 is not in setup_degrees, so it will have degree 0
    create_train(db_session, test_snapshot_id, 110, "T110", [1, 2])
    res = calculate_train_topological_degree_entropy(db_session, test_snapshot_id, "T110")
    oracle = compute_entropy_oracle([1, 0])
    assert abs(res["topological_degree_entropy"] - oracle) < 1e-6

def test_train_identity_collision(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:2, 3:3, 4:4, 5:5})
    # Two distinct trains sharing the identical generic name "Passenger"
    create_train(db_session, test_snapshot_id, 111, "T111", [1, 2, 3], train_name="Passenger")
    create_train(db_session, test_snapshot_id, 112, "T112", [4, 5], train_name="Passenger")
    
    res111 = calculate_train_topological_degree_entropy(db_session, test_snapshot_id, "T111")
    assert res111["total_sequence_stops"] == 3
    
    res112 = calculate_train_topological_degree_entropy(db_session, test_snapshot_id, "T112")
    assert res112["total_sequence_stops"] == 2

def test_missing_train(db_session, test_snapshot_id, test_graph_build_id):
    with pytest.raises(ValueError, match="not found"):
        calculate_train_topological_degree_entropy(db_session, test_snapshot_id, "UNK")
