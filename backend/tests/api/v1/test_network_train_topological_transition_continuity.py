import pytest
from fastapi.testclient import TestClient
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.models.station import Station
from railgati.models.provenance import DatasetSnapshot, DataSource
from datetime import datetime, UTC

@pytest.fixture
def mock_transition_data(db_session):
    src = DataSource(name="TEST_SRC", publisher="TEST_PUB", url="TEST_URL", license="MIT")
    db_session.add(src)
    db_session.flush()
    snap = DatasetSnapshot(status="ACTIVE", source_id=src.id, retrieved_at=datetime.now(UTC))
    db_session.add(snap)
    db_session.flush()
    s_a = Station(code="STN_A")
    s_b = Station(code="STN_B")
    s_c = Station(code="STN_C")
    s_d = Station(code="STN_D")
    db_session.add_all([s_a, s_b, s_c, s_d])
    db_session.flush()

    t_target = Train(number="12345")
    t_perfect = Train(number="22222")
    t_fractured = Train(number="33333")
    t_short = Train(number="44444")
    t_cyclic = Train(number="55555")
    db_session.add_all([t_target, t_perfect, t_fractured, t_short, t_cyclic])
    db_session.flush()

    snap_id = snap.id
    obs = []
    
    for t in [t_target, t_perfect, t_fractured, t_short, t_cyclic]:
        obs.append(TrainObservation(snapshot_id=snap.id, train_id=t.id, name=t.number, type="EXP"))
    
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

    db_session.add_all(obs)
    db_session.commit()
    return snap_id


def test_api_get_train_sequence_topological_transition_continuity_success(
    client: TestClient, db_session, mock_transition_data
):
    # Train 12345 exists and has transitions from mock_transition_data
    response = client.get("/api/v1/network/trains/12345/topological-transition-continuity")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "12345"
    assert data["total_transition_count"] == 2
    assert len(data["transitions"]) == 2
    assert data["transitions"][0]["first_edge_occurrence_count"] == 6

def test_api_get_train_sequence_topological_transition_continuity_short(
    client: TestClient, db_session, mock_transition_data
):
    # Train 44444 exists but has < 3 stops
    response = client.get("/api/v1/network/trains/44444/topological-transition-continuity")
    assert response.status_code == 200
    data = response.json()
    assert data["total_transition_count"] == 0
    assert data["average_continuity_ratio"] is None

def test_api_get_train_sequence_topological_transition_continuity_not_found(
    client: TestClient, db_session, mock_transition_data
):
    response = client.get("/api/v1/network/trains/99999/topological-transition-continuity")
    assert response.status_code == 404
