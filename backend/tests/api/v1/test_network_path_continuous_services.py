import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdge, RailwayServiceEdge
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation


@pytest.fixture
def test_data(db_session: Session) -> tuple[Station, Station, Station]:
    source = DataSource(name="t", url="http://test", publisher="Test", license="CC0")
    db_session.add(source)
    db_session.commit()

    s1 = Station(code="AAA")
    s2 = Station(code="BBB")
    s3 = Station(code="CCC")
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    snap = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.flush()

    gb = RailwayGraphBuild(timetable_snapshot_id=1, status="ACTIVE")
    db_session.add(gb)
    db_session.flush()

    ne1 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s1.id, to_station_id=s2.id, train_count=1
    )
    ne2 = RailwayNetworkEdge(
        timetable_snapshot_id=1, from_station_id=s2.id, to_station_id=s3.id, train_count=1
    )
    db_session.add_all([ne1, ne2])
    db_session.flush()

    t1 = Train(number="123")
    db_session.add(t1)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t1.id, name="Continuous Train"))
    db_session.flush()

    se1 = RailwayServiceEdge(
        timetable_snapshot_id=1,
        train_id=t1.id,
        from_stop_sequence=1,
        to_stop_sequence=2,
        from_station_id=s1.id,
        to_station_id=s2.id,
        departure_time="10:00",
        arrival_time="11:00",
        source_day_offset=0,
    )
    se2 = RailwayServiceEdge(
        timetable_snapshot_id=1,
        train_id=t1.id,
        from_stop_sequence=2,
        to_stop_sequence=3,
        from_station_id=s2.id,
        to_station_id=s3.id,
        departure_time="11:10",
        arrival_time="12:00",
        source_day_offset=0,
    )
    db_session.add_all([se1, se2])
    db_session.commit()
    return s1, s2, s3


def test_api_continuous_path_valid(
    client: TestClient, test_data: tuple[Station, Station, Station]
) -> None:
    s1, s2, s3 = test_data
    path = f"{s1.code},{s2.code},{s3.code}"
    response = client.get(f"/api/v1/network/path/continuous-services?path={path}")
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == [s1.code, s2.code, s3.code]
    assert data["total_services_returned"] == 1
    assert data["services"][0]["train_number"] == "123"
    assert data["services"][0]["train_name"] == "Continuous Train"
    assert data["services"][0]["start_sequence"] == 1
    assert data["services"][0]["end_sequence"] == 3
    assert data["services"][0]["total_duration_minutes"] == 120


def test_api_invalid_path_length(client: TestClient) -> None:
    response = client.get("/api/v1/network/path/continuous-services?path=AAA")
    assert response.status_code == 422


def test_api_invalid_duplicate_stations(client: TestClient) -> None:
    response = client.get("/api/v1/network/path/continuous-services?path=AAA,AAA,BBB")
    assert response.status_code == 422


def test_api_unknown_station(client: TestClient) -> None:
    response = client.get("/api/v1/network/path/continuous-services?path=FAKE1,FAKE2")
    assert response.status_code == 404
