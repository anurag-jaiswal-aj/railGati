
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DataSource


def create_deps(db_session: Session) -> DataSource:
    source = DataSource(name="t", url="http://test", publisher="Test", license="CC0")
    db_session.add(source)
    db_session.commit()
    return source


def test_get_network_attribution_valid(client: TestClient, db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.graph import RailwayGraphBuild, RailwayServiceEdge
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station
    from railgati.models.train import Train, TrainObservation

    s1 = Station(code="NDLS")
    s2 = Station(code="AGC")
    db_session.add_all([s1, s2])
    db_session.flush()

    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()
    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)
    db_session.flush()

    t1 = Train(number="12137")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="PUNJAB MAIL", type="SF"))
    db_session.flush()

    db_session.add(
        RailwayServiceEdge(
            timetable_snapshot_id=1,
            train_id=t1.id,
            from_stop_sequence=5,
            to_stop_sequence=6,
            from_station_id=s1.id,
            to_station_id=s2.id,
            duration_minutes=175,
        )
    )
    db_session.commit()

    response = client.get("/api/v1/network/attribution?origin=ndls&destination=AgC")
    assert response.status_code == 200
    data = response.json()
    assert data["origin"] == "NDLS"
    assert data["destination"] == "AGC"
    assert data["timetable_snapshot_id"] == 1
    assert data["occurrences_returned"] == 1
    assert data["occurrences"][0]["train_number"] == "12137"
    assert data["occurrences"][0]["train_name"] == "PUNJAB MAIL"
    assert data["occurrences"][0]["train_type"] == "SF"
    assert data["occurrences"][0]["duration_minutes"] == 175


def test_get_network_attribution_unknown_station(client: TestClient, db_session: Session) -> None:
    from railgati.models.station import Station

    s1 = Station(code="NDLS")
    db_session.add(s1)
    db_session.commit()

    response = client.get("/api/v1/network/attribution?origin=NDLS&destination=UNKNOWN")
    assert response.status_code == 404
    assert "Destination station 'UNKNOWN' not found" in response.json()["detail"]


def test_get_network_attribution_nonexistent_edge(client: TestClient, db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.graph import RailwayGraphBuild
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station
    from railgati.models.train import Train, TrainObservation

    s1 = Station(code="NDLS")
    s2 = Station(code="AGC")
    db_session.add_all([s1, s2])
    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()
    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)
    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Test"))
    db_session.commit()

    response = client.get("/api/v1/network/attribution?origin=NDLS&destination=AGC")
    assert response.status_code == 200
    data = response.json()
    assert data["occurrences_returned"] == 0
    assert data["occurrences"] == []


def test_get_network_attribution_graph_unavailable(client: TestClient, db_session: Session) -> None:
    source = create_deps(db_session)
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station
    from railgati.models.train import Train, TrainObservation

    s1 = Station(code="NDLS")
    s2 = Station(code="AGC")
    db_session.add_all([s1, s2])
    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()
    # Missing RailwayGraphBuild
    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Test"))
    db_session.commit()

    response = client.get("/api/v1/network/attribution?origin=NDLS&destination=AGC")
    assert response.status_code == 503
    assert "Active graph build unavailable" in response.json()["detail"]
