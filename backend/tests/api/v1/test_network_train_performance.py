from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation

def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_api", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s_orig = Station(code="ORG")
    s_mid1 = Station(code="MD1")
    s_mid2 = Station(code="MD2")
    s_dest = Station(code="DST")
    db_session.add_all([s_orig, s_mid1, s_mid2, s_dest])
    db_session.flush()

    t_slow = Train(number="12345")
    t_fast = Train(number="54321")
    t_miss = Train(number="04601")
    db_session.add_all([t_slow, t_fast, t_miss])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t_slow.id, name="Test Slow"),
            TrainObservation(snapshot_id=1, train_id=t_fast.id, name="Test Fast"),
            TrainObservation(snapshot_id=1, train_id=t_miss.id, name="Test Miss"),
        ]
    )

    db_session.add_all(
        [
            # t_slow: MD1 dwell = 20 mins, Edge ORG->MD1 = 60 mins
            TrainStopObservation(snapshot_id=1, train_id=t_slow.id, stop_sequence=1, station_id=s_orig.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_slow.id, stop_sequence=2, station_id=s_mid1.id, arrival_time="11:00:00", departure_time="11:20:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_slow.id, stop_sequence=3, station_id=s_mid2.id, arrival_time="12:20:00", departure_time="12:30:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_slow.id, stop_sequence=4, station_id=s_dest.id, arrival_time="13:30:00", source_day=1),

            # t_fast: MD1 dwell = 5 mins, Edge ORG->MD1 = 30 mins
            TrainStopObservation(snapshot_id=1, train_id=t_fast.id, stop_sequence=1, station_id=s_orig.id, departure_time="10:30:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_fast.id, stop_sequence=2, station_id=s_mid1.id, arrival_time="11:00:00", departure_time="11:05:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_fast.id, stop_sequence=3, station_id=s_mid2.id, arrival_time="11:35:00", departure_time="11:40:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_fast.id, stop_sequence=4, station_id=s_dest.id, arrival_time="12:10:00", source_day=1),

            # t_miss: Missing timing
            TrainStopObservation(snapshot_id=1, train_id=t_miss.id, stop_sequence=1, station_id=s_orig.id, source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_miss.id, stop_sequence=2, station_id=s_dest.id, source_day=1),
        ]
    )
    db_session.commit()

def test_get_structural_halts_valid(client: TestClient, db_session: Session):
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/12345/structural-halts")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "12345"
    assert "timetable_snapshot_id" in data
    assert "halts" in data
    
    halts = data["halts"]
    assert len(halts) == 2
    # 20 min dwell at MD1, 10 min dwell at MD2
    # Should be descending: MD1 (20) then MD2 (10)
    assert halts[0]["station_code"] == "MD1"
    assert halts[0]["dwell_minutes"] == 20.0
    assert halts[1]["station_code"] == "MD2"
    assert halts[1]["dwell_minutes"] == 10.0

def test_get_structural_halts_unknown_train(client: TestClient, db_session: Session):
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/99999/structural-halts")
    assert response.status_code == 404

def test_get_relative_edge_slowness_valid(client: TestClient, db_session: Session):
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/12345/relative-edge-slowness")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "12345"
    assert "timetable_snapshot_id" in data
    assert "slow_edges" in data
    
    edges = data["slow_edges"]
    assert len(edges) > 0
    # ORG->MD1: t_slow takes 60 mins. Average = (60+30)/2 = 45 mins. 60/45 = 1.333
    # MD1->MD2: t_slow takes 60 mins. Average = (60+30)/2 = 45 mins. 60/45 = 1.333
    # MD2->DST: t_slow takes 60 mins. Average = (60+30)/2 = 45 mins. 60/45 = 1.333
    
    assert edges[0]["slowness_ratio"] > 1.0
    assert edges[0]["target_duration_minutes"] == 60.0
    assert edges[0]["network_average_minutes"] == 45.0

def test_get_relative_edge_slowness_unknown_train(client: TestClient, db_session: Session):
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/99999/relative-edge-slowness")
    assert response.status_code == 404

def test_network_limits_validation(client: TestClient, db_session: Session):
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/12345/structural-halts?limit=0")
    assert response.status_code == 422
    
    response = client.get("/api/v1/network/trains/12345/structural-halts?limit=100")
    assert response.status_code == 422
    
    response = client.get("/api/v1/network/trains/12345/relative-edge-slowness?limit=-5")
    assert response.status_code == 422

def test_missing_timing_train(client: TestClient, db_session: Session):
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/04601/structural-halts")
    assert response.status_code == 200
    assert response.json()["halts"] == []
    
    response = client.get("/api/v1/network/trains/04601/relative-edge-slowness")
    assert response.status_code == 200
    assert response.json()["slow_edges"] == []

def test_empty_results_behavior(client: TestClient, db_session: Session):
    setup_data(db_session)
    # fast train has halts but they might not be long?
    # Actually fast train slowness ratio = 30 / 45 = 0.66, so it's not > 1.0
    response = client.get("/api/v1/network/trains/54321/relative-edge-slowness")
    assert response.status_code == 200
    assert response.json()["slow_edges"] == []
