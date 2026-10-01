import typing
import pytes
import math
from datetime import UTC, datetime

from railgati.services.network import calculate_train_topological_structural_gradien
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.graph import RailwayGraphBuild, RailwayStationTopologicalCoreness

def compute_tau_b_oracle(y_vals: list[int]) -> float | None:
    """Independent oracle for Kendall's Tau-b computation."""
    n = len(y_vals)
    if n < 2:
        return None

    concordant = 0
    discordant = 0
    ties_y = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            if y_vals[i] < y_vals[j]:
                concordant += 1
            elif y_vals[i] > y_vals[j]:
                discordant += 1
            else:
                ties_y += 1

    total_pairs = n * (n - 1) // 2
    denom = total_pairs * (total_pairs - ties_y)

    if denom == 0:
        return None

    return (concordant - discordant) / math.sqrt(denom)

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

def test_strictly_increasing(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:2, 3:3, 4:4})
    create_train(db_session, test_snapshot_id, 101, "T101", [1, 2, 3, 4])
    res = calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "T101")
    assert res["total_sequence_stops"] == 4
    assert abs(res["topological_structural_gradient_tau"] - 1.0) < 1e-6

def test_strictly_decreasing(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:2, 3:3, 4:4})
    create_train(db_session, test_snapshot_id, 102, "T102", [4, 3, 2, 1])
    res = calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "T102")
    assert res["total_sequence_stops"] == 4
    assert abs(res["topological_structural_gradient_tau"] - (-1.0)) < 1e-6

def test_constant_degrees(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:2, 2:2, 3:2})
    create_train(db_session, test_snapshot_id, 103, "T103", [1, 2, 3])
    res = calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "T103")
    assert res["total_sequence_stops"] == 3
    assert res["topological_structural_gradient_tau"] is None

def test_short_routes(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:2, 3:1})

    # 1 stop
    create_train(db_session, test_snapshot_id, 104, "T104", [1])
    res = calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "T104")
    assert res["total_sequence_stops"] == 1
    assert res["topological_structural_gradient_tau"] is None

    # 2 stops, distinct degrees. 1:1, 2:2
    create_train(db_session, test_snapshot_id, 105, "T105", [1, 2])
    res = calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "T105")
    assert res["total_sequence_stops"] == 2
    assert abs(res["topological_structural_gradient_tau"] - 1.0) < 1e-6

def test_tied_degrees_increasing(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:2, 3:2, 4:3})
    create_train(db_session, test_snapshot_id, 106, "T106", [1, 2, 3, 4])
    res = calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "T106")
    oracle = compute_tau_b_oracle([1, 2, 2, 3])
    assert abs(res["topological_structural_gradient_tau"] - oracle) < 1e-6
    assert res["topological_structural_gradient_tau"] > 0.9

def test_mixed_discordant_concordant(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:3, 3:2, 4:4, 5:1})
    create_train(db_session, test_snapshot_id, 107, "T107", [1, 2, 3, 4, 5])
    res = calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "T107")
    oracle = compute_tau_b_oracle([1, 3, 2, 4, 1])
    assert abs(res["topological_structural_gradient_tau"] - oracle) < 1e-6

def test_tied_degrees_decreasing(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:2, 3:2, 4:3})
    create_train(db_session, test_snapshot_id, 108, "T108", [4, 3, 2, 1])
    res = calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "T108")
    oracle = compute_tau_b_oracle([3, 2, 2, 1])
    assert abs(res["topological_structural_gradient_tau"] - oracle) < 1e-6
    assert res["topological_structural_gradient_tau"] < -0.9

def test_repeated_station_counts_independently(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:2, 3:2})
    create_train(db_session, test_snapshot_id, 109, "T109", [1, 2, 3, 2, 1])
    res = calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "T109")
    oracle = compute_tau_b_oracle([1, 2, 2, 2, 1])
    assert abs(res["topological_structural_gradient_tau"] - oracle) < 1e-6
    assert abs(res["topological_structural_gradient_tau"] - 0.0) < 1e-6

def test_genuinely_zero_tau(db_session, test_snapshot_id, test_graph_build_id):
    setup_degrees(db_session, test_snapshot_id, test_graph_build_id, {1:1, 2:2, 3:1})
    create_train(db_session, test_snapshot_id, 110, "T110", [1, 2, 3])
    res = calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "T110")
    oracle = compute_tau_b_oracle([1, 2, 1])
    assert res["topological_structural_gradient_tau"] == 0.0

def test_missing_train(db_session, test_snapshot_id, test_graph_build_id):
    with pytest.raises(ValueError, match="not found"):
        calculate_train_topological_structural_gradient(db_session, test_snapshot_id, "UNK")
