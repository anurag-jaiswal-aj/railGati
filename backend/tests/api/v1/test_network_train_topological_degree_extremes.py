import pytest
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.train import Train, TrainStopObservation
from railgati.models.station import Station

@pytest.fixture
def mock_api_degree_extremes(db_session):
    source = DataSource(name="API_EXTREMES_SRC", url="http://test", publisher="Test", license="Test")
    db_session.add(source)
    db_session.commit()
    
    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()

    s_a = Station(code="E1")
    s_b = Station(code="E2")
    s_c = Station(code="E3")
    db_session.add_all([s_a, s_b, s_c])
    
    t_obs = Train(number="OBS_TRAIN")
    db_session.add(t_obs)
    db_session.commit()

    from railgati.models.train import TrainObservation
    db_session.add(TrainObservation(snapshot_id=snap.id, train_id=t_obs.id, name="Test"))
    db_session.commit()
    db_session.commit()
    
    # Target Train: E1 -> E2 -> E3
    t = Train(number="API_EXTREMES_TEST")
    db_session.add(t)
    db_session.commit()
    
    db_session.add(TrainStopObservation(snapshot_id=snap.id, train_id=t.id, station_id=s_a.id, stop_sequence=1))
    db_session.add(TrainStopObservation(snapshot_id=snap.id, train_id=t.id, station_id=s_b.id, stop_sequence=2))
    db_session.add(TrainStopObservation(snapshot_id=snap.id, train_id=t.id, station_id=s_c.id, stop_sequence=3))
    db_session.commit()

    # Inflate E2 to have degree 5. E1 and E3 already have degree 1 from this train.
    for i in range(4):
        dummy = Station(code=f"DUMMY_E2_{i}")
        dt = Train(number=f"DUMMY_T_{i}")
        db_session.add_all([dummy, dt])
        db_session.commit()
        db_session.add(TrainStopObservation(snapshot_id=snap.id, train_id=dt.id, station_id=s_b.id, stop_sequence=1))
        db_session.add(TrainStopObservation(snapshot_id=snap.id, train_id=dt.id, station_id=dummy.id, stop_sequence=2))
        db_session.commit()

    return snap.id

def test_api_degree_extremes_success(client, mock_api_degree_extremes):
    response = client.get("/api/v1/network/trains/API_EXTREMES_TEST/topological-degree-extremes")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "API_EXTREMES_TEST"
    assert data["total_stops"] == 3
    assert data["local_maxima_count"] == 1
    assert data["local_minima_count"] == 0
    assert data["transit_count"] == 0
    assert len(data["sequence_classification"]) == 3
    
    assert data["sequence_classification"][0]["classification_type"] == "TERMINAL"
    assert data["sequence_classification"][1]["classification_type"] == "LOCAL_MAXIMUM"
    assert data["sequence_classification"][1]["global_degree"] == 6 # E1, E3, + 4 dummies = 6
    assert data["sequence_classification"][2]["classification_type"] == "TERMINAL"

def test_api_degree_extremes_not_found(client, mock_api_degree_extremes):
    response = client.get("/api/v1/network/trains/UNKNOWN_TRAIN/topological-degree-extremes")
    assert response.status_code == 404
