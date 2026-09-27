from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainStopObservation, TrainObservation

def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_api", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s_orig = Station(code="ORG")
    s_mid1 = Station(code="MD1")
    s_mid2 = Station(code="MD2")
    db_session.add_all([s_orig, s_mid1, s_mid2])
    db_session.flush()

    t_loop = Train(number="12345")
    t_linear = Train(number="54321")
    db_session.add_all([t_loop, t_linear])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t_loop.id, name="Test1"),
            TrainObservation(snapshot_id=1, train_id=t_linear.id, name="Test2"),
        ]
    )

    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t_loop.id, stop_sequence=1, station_id=s_orig.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_loop.id, stop_sequence=2, station_id=s_mid1.id, arrival_time="11:00:00", departure_time="11:10:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_loop.id, stop_sequence=3, station_id=s_mid2.id, arrival_time="12:00:00", departure_time="12:10:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_loop.id, stop_sequence=4, station_id=s_mid1.id, arrival_time="13:00:00", departure_time="13:10:00", source_day=1),
            
            TrainStopObservation(snapshot_id=1, train_id=t_linear.id, stop_sequence=1, station_id=s_orig.id, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_linear.id, stop_sequence=2, station_id=s_mid1.id, arrival_time="11:00:00", departure_time="11:10:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t_linear.id, stop_sequence=3, station_id=s_mid2.id, arrival_time="12:00:00", departure_time="12:10:00", source_day=1),
        ]
    )
    db_session.commit()

def test_api_network_topology_loops_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/12345/topology-loops")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "12345"
    assert data["has_loops"] is True
    assert data["loop_count"] == 1
    
    loop = data["loops"][0]
    assert loop["station_code"] == "MD1"
    assert loop["visit_count"] == 2
    assert loop["max_sequence_span"] == 2

def test_api_network_topology_loops_linear(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/54321/topology-loops")
    assert response.status_code == 200
    data = response.json()
    assert data["train_number"] == "54321"
    assert data["has_loops"] is False
    assert data["loop_count"] == 0
    assert data["loops"] == []

def test_api_network_topology_loops_unknown_train(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/trains/99999/topology-loops")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_api_network_topology_loops_isolation(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    db_session.execute(DatasetSnapshot.__table__.update().values(status="ARCHIVED"))
    db_session.commit()
    
    response = client.get("/api/v1/network/trains/12345/topology-loops")
    assert response.status_code == 503
