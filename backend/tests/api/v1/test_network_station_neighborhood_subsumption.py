import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def api_subsumption_fixtures(db_session):
    from railgati.models.provenance import DataSource, DatasetSnapshot
    from railgati.models.station import Station, StationObservation
    from railgati.models.train import Train, TrainStopObservation, TrainObservation
    
    source = DataSource(name="API_SUB_SRC", url="http://test", publisher="Test", license="Test")
    db_session.add(source)
    db_session.commit()
    
    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()
    
    def create_station(code):
        s = Station(code=code)
        db_session.add(s)
        db_session.commit()
        db_session.add(StationObservation(snapshot_id=snap.id, station_id=s.id, name=code))
        db_session.commit()
        return s

    def add_train(number, seq):
        t = Train(number=number)
        db_session.add(t)
        db_session.commit()
        
        db_session.add(TrainObservation(snapshot_id=snap.id, train_id=t.id, name=number))
        
        for i, code in enumerate(seq, 1):
            s = db_session.query(Station).filter_by(code=code).first()
            if not s:
                s = create_station(code)
            db_session.add(TrainStopObservation(
                snapshot_id=snap.id, train_id=t.id, station_id=s.id, stop_sequence=i
            ))
        db_session.commit()

    # S_SUB has {H_SUB, A_SUB}
    # H_SUB has {S_SUB, A_SUB, B_SUB}
    add_train("T_SUB_1", ["A_SUB", "S_SUB", "H_SUB", "B_SUB"])
    add_train("T_SUB_2", ["H_SUB", "A_SUB"])
    
    # S_EMPTY has leaf
    add_train("T_SUB_3", ["S_EMPTY", "H_EMPTY"])

def test_api_subsumption_success(client: TestClient, api_subsumption_fixtures) -> None:
    response = client.get("/api/v1/network/stations/S_SUB/neighborhood-subsumption")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "S_SUB"
    assert data["total_neighbors"] == 2
    assert len(data["subsuming_neighbors"]) == 1
    assert data["subsuming_neighbors"][0]["station_code"] == "H_SUB"
    assert data["subsuming_neighbors"][0]["neighbor_degree"] == 3

def test_api_subsumption_empty(client: TestClient, api_subsumption_fixtures) -> None:
    response = client.get("/api/v1/network/stations/S_EMPTY/neighborhood-subsumption")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "S_EMPTY"
    assert data["total_neighbors"] == 1
    assert len(data["subsuming_neighbors"]) == 0

def test_api_subsumption_not_found(client: TestClient, api_subsumption_fixtures) -> None:
    response = client.get("/api/v1/network/stations/INVALID_STATION/neighborhood-subsumption")
    assert response.status_code == 404
