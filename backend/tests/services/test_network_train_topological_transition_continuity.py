import pytest
from sqlalchemy import text
from railgati.models.train import Train, TrainStopObservation
from railgati.models.station import Station
from railgati.services.network import calculate_train_sequence_topological_transition_continuity
from railgati.models.provenance import DatasetSnapshot, DataSource

@pytest.fixture
def mock_transition_data(db_session):
    src = DataSource(name="TEST_SRC", publisher="TEST_PUB", url="TEST_URL", license="MIT")
    db_session.add(src)
    db_session.flush()
    snap = DatasetSnapshot(status="ACTIVE", source_id=src.id)
    db_session.add(snap)
    db_session.flush()
    s_a = Station(code="STN_A")
    s_b = Station(code="STN_B")
    s_c = Station(code="STN_C")
    s_d = Station(code="STN_D")
    
    db_session.add_all([s_a, s_b, s_c, s_d])
    db_session.flush()

    # Create trains
    t_target = Train(number="12345")
    t_perfect = Train(number="22222")
    t_fractured = Train(number="33333")
    t_short = Train(number="44444")
    t_cyclic = Train(number="55555")
    t_regression = Train(number="66666")
    t_regression_partial = Train(number="77777")
    
    db_session.add_all([t_target, t_perfect, t_fractured, t_short, t_cyclic, t_regression, t_regression_partial])
    db_session.flush()

    snap_id = snap.id

    obs = []
    
    # Target Train: A -> B -> C -> D
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_target.id, station_id=s_a.id, stop_sequence=1))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_target.id, station_id=s_b.id, stop_sequence=2))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_target.id, station_id=s_c.id, stop_sequence=3))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_target.id, station_id=s_d.id, stop_sequence=4))

    # Another train does A -> B -> C
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_perfect.id, station_id=s_a.id, stop_sequence=1))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_perfect.id, station_id=s_b.id, stop_sequence=2))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_perfect.id, station_id=s_c.id, stop_sequence=3))

    # A third train does A -> B -> D (fractures A->B->C)
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_fractured.id, station_id=s_a.id, stop_sequence=1))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_fractured.id, station_id=s_b.id, stop_sequence=2))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_fractured.id, station_id=s_d.id, stop_sequence=3))

    # Short train: A -> B
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_short.id, station_id=s_a.id, stop_sequence=1))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_short.id, station_id=s_b.id, stop_sequence=2))

    # Cyclic train: A -> B -> A -> B -> C
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_cyclic.id, station_id=s_a.id, stop_sequence=1))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_cyclic.id, station_id=s_b.id, stop_sequence=2))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_cyclic.id, station_id=s_a.id, stop_sequence=3))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_cyclic.id, station_id=s_b.id, stop_sequence=4))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_cyclic.id, station_id=s_c.id, stop_sequence=5))

    # Regression Train: A -> B -> C -> A -> B -> C
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression.id, station_id=s_a.id, stop_sequence=1))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression.id, station_id=s_b.id, stop_sequence=2))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression.id, station_id=s_c.id, stop_sequence=3))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression.id, station_id=s_a.id, stop_sequence=4))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression.id, station_id=s_b.id, stop_sequence=5))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression.id, station_id=s_c.id, stop_sequence=6))

    # Regression Partial: A -> B -> C -> A -> B -> D
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression_partial.id, station_id=s_a.id, stop_sequence=1))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression_partial.id, station_id=s_b.id, stop_sequence=2))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression_partial.id, station_id=s_c.id, stop_sequence=3))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression_partial.id, station_id=s_a.id, stop_sequence=4))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression_partial.id, station_id=s_b.id, stop_sequence=5))
    obs.append(TrainStopObservation(snapshot_id=snap_id, train_id=t_regression_partial.id, station_id=s_d.id, stop_sequence=6))

    db_session.add_all(obs)
    db_session.commit()
    return snap_id

def test_service_basic_continuity(db_session, mock_transition_data):
    snap_id = mock_transition_data
    # For Target Train (12345): A -> B -> C -> D
    # Triplets: (A, B, C) and (B, C, D)
    # A->B traverses: 12345, 22222, 33333, 44444, 55555 = 5 distinct trains
    # A->B->C traverses: 12345, 22222, 55555 = 3 distinct trains
    # Ratio 1 = 3 / 5 = 0.6
    
    # B->C traverses: 12345, 22222, 55555 = 3 distinct trains
    # B->C->D traverses: 12345 = 1 train
    # Ratio 2 = 1 / 3 = 0.3333...

    res = calculate_train_sequence_topological_transition_continuity(db_session, snap_id, "12345")
    
    assert res["train_number"] == "12345"
    assert res["total_transition_count"] == 2
    assert len(res["transitions"]) == 2
    
    t1 = res["transitions"][0]
    assert t1["from_station_code"] == "STN_A"
    assert t1["via_station_code"] == "STN_B"
    assert t1["to_station_code"] == "STN_C"
    assert t1["first_edge_occurrence_count"] == 10
    assert t1["transition_occurrence_count"] == 6
    assert t1["continuity_ratio"] == 0.6
    
    t2 = res["transitions"][1]
    assert t2["from_station_code"] == "STN_B"
    assert t2["via_station_code"] == "STN_C"
    assert t2["to_station_code"] == "STN_D"
    assert t2["first_edge_occurrence_count"] == 6
    assert t2["transition_occurrence_count"] == 1
    assert abs(t2["continuity_ratio"] - (1/6)) < 0.001
    
    assert abs(res["average_continuity_ratio"] - ((0.6 + (1/6))/2)) < 0.001
    assert abs(res["minimum_continuity_ratio"] - (1/6)) < 0.001
    assert res["maximum_continuity_ratio"] == 0.6

def test_service_cyclic_route(db_session, mock_transition_data):
    snap_id = mock_transition_data
    # Cyclic: A -> B -> A -> B -> C
    # T1: A -> B -> A
    # A->B traverses: 5 distinct trains
    # A->B->A traverses: 55555 (1 train)
    # Ratio: 1 / 5 = 0.2
    
    # T2: B -> A -> B
    # B->A traverses: 55555 (1 train)
    # B->A->B traverses: 55555 (1 train)
    # Ratio: 1.0
    
    # T3: A -> B -> C
    # A->B traverses: 5 trains
    # A->B->C traverses: 3 trains
    # Ratio: 0.6
    
    res = calculate_train_sequence_topological_transition_continuity(db_session, snap_id, "55555")
    assert res["total_transition_count"] == 3
    
    t1 = res["transitions"][0]
    assert t1["from_station_code"] == "STN_A"
    assert t1["to_station_code"] == "STN_A"
    # Wait, A->B has 9 total occurrences now across all trains. Let's just check ratio for the first one manually, but better to test the new isolated train.

@pytest.fixture
def isolated_transition_data(db_session):
    src = DataSource(name="ISO_SRC", publisher="ISO_PUB", url="ISO_URL", license="MIT")
    db_session.add(src)
    db_session.flush()
    snap = DatasetSnapshot(status="ACTIVE", source_id=src.id)
    db_session.add(snap)
    db_session.flush()
    
    s_a = Station(code="STN_A")
    s_b = Station(code="STN_B")
    s_c = Station(code="STN_C")
    s_d = Station(code="STN_D")
    db_session.add_all([s_a, s_b, s_c, s_d])
    db_session.flush()

    t_reg = Train(number="66666")
    db_session.add(t_reg)
    db_session.flush()

    obs = []
    # Train 66666: A -> B -> C -> A -> B -> C
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_a.id, stop_sequence=1))
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_b.id, stop_sequence=2))
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_c.id, stop_sequence=3))
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_a.id, stop_sequence=4))
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_b.id, stop_sequence=5))
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_c.id, stop_sequence=6))
    
    db_session.add_all(obs)
    db_session.commit()
    return snap.id

@pytest.fixture
def isolated_partial_transition_data(db_session):
    src = DataSource(name="ISO_SRC2", publisher="ISO_PUB2", url="ISO_URL2", license="MIT")
    db_session.add(src)
    db_session.flush()
    snap = DatasetSnapshot(status="ACTIVE", source_id=src.id)
    db_session.add(snap)
    db_session.flush()
    
    s_a = Station(code="STN_A")
    s_b = Station(code="STN_B")
    s_c = Station(code="STN_C")
    s_d = Station(code="STN_D")
    db_session.add_all([s_a, s_b, s_c, s_d])
    db_session.flush()

    t_reg = Train(number="77777")
    db_session.add(t_reg)
    db_session.flush()

    obs = []
    # Train 77777: A -> B -> C -> A -> B -> D
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_a.id, stop_sequence=1))
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_b.id, stop_sequence=2))
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_c.id, stop_sequence=3))
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_a.id, stop_sequence=4))
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_b.id, stop_sequence=5))
    obs.append(TrainStopObservation(snapshot_id=snap.id, train_id=t_reg.id, station_id=s_d.id, stop_sequence=6))
    
    db_session.add_all(obs)
    db_session.commit()
    return snap.id

def test_service_regression_cyclic(db_session, isolated_transition_data):
    snap_id = isolated_transition_data
    res = calculate_train_sequence_topological_transition_continuity(db_session, snap_id, "66666")
    
    t_abc = [t for t in res["transitions"] if t["from_station_code"] == "STN_A" and t["via_station_code"] == "STN_B" and t["to_station_code"] == "STN_C"][0]
    
    assert t_abc["first_edge_occurrence_count"] == 2
    assert t_abc["transition_occurrence_count"] == 2
    assert t_abc["continuity_ratio"] == 1.0

def test_service_regression_partial(db_session, isolated_partial_transition_data):
    snap_id = isolated_partial_transition_data
    res = calculate_train_sequence_topological_transition_continuity(db_session, snap_id, "77777")
    
    t_abc = [t for t in res["transitions"] if t["from_station_code"] == "STN_A" and t["via_station_code"] == "STN_B" and t["to_station_code"] == "STN_C"][0]
    assert t_abc["first_edge_occurrence_count"] == 2
    assert t_abc["transition_occurrence_count"] == 1
    assert t_abc["continuity_ratio"] == 0.5


def test_service_short_train(db_session, mock_transition_data):
    snap_id = mock_transition_data
    # Train 44444 only has 2 stops. Should return empty structure.
    res = calculate_train_sequence_topological_transition_continuity(db_session, snap_id, "44444")
    assert res["total_transition_count"] == 0
    assert res["average_continuity_ratio"] is None
    assert res["transitions"] == []

def test_service_unknown_train(db_session, mock_transition_data):
    snap_id = mock_transition_data
    with pytest.raises(ValueError, match="not found"):
        calculate_train_sequence_topological_transition_continuity(db_session, snap_id, "99999")
