import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def api_strict_local_bridges_fixtures(db_session):
    from railgati.models.provenance import DataSource, DatasetSnapshot
    from railgati.models.station import Station, StationObservation
    from railgati.models.train import Train, TrainStopObservation, TrainObservation
    
    source = DataSource(name="API_BR_SRC", url="http://test", publisher="Test", license="Test")
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

    add_train("T1", ["A", "S", "B"])


def test_station_strict_local_bridges_success(client: TestClient, api_strict_local_bridges_fixtures):
    response = client.get("/api/v1/network/stations/S/strict-local-bridges")
    assert response.status_code == 200
    data = response.json()
    
    assert data["station_code"] == "S"
    assert data["total_neighbor_pairs"] == 1
    assert len(data["evaluated_pairs"]) == 1
    
    pair = data["evaluated_pairs"][0]
    assert pair["has_direct_adjacency"] is False
    assert pair["alternative_bridge_count"] == 0
    assert pair["is_strict_local_bridge"] is True


def test_station_strict_local_bridges_not_found(client: TestClient, api_strict_local_bridges_fixtures):
    response = client.get("/api/v1/network/stations/UNKNOWN/strict-local-bridges")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
