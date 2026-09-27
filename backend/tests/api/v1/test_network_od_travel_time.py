from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation


def setup_data(db_session: Session) -> None:
    source = DataSource(name="test_api", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s_ndls = Station(code="NDLS")
    s_cnb = Station(code="CNB")
    s_mtd = Station(code="MTD")
    s_dna = Station(code="DNA")
    s_xx = Station(code="XX")
    db_session.add_all([s_ndls, s_cnb, s_mtd, s_dna, s_xx])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s_ndls.id, name="New Delhi"),
            StationObservation(snapshot_id=1, station_id=s_cnb.id, name="Kanpur"),
            StationObservation(snapshot_id=1, station_id=s_mtd.id, name="Merta"),
            StationObservation(snapshot_id=1, station_id=s_dna.id, name="Degana"),
            StationObservation(snapshot_id=1, station_id=s_xx.id, name="Unknown"),
        ]
    )

    t1 = Train(number="111")
    t2 = Train(number="222") # loops MTD->DNA
    t3 = Train(number="333") # missing timing
    db_session.add_all([t1, t2, t3])
    db_session.flush()

    db_session.add_all(
        [
            TrainObservation(snapshot_id=1, train_id=t1.id, name="T1", type="EXP"),
            TrainObservation(snapshot_id=1, train_id=t2.id, name="T2"),
            TrainObservation(snapshot_id=1, train_id=t3.id, name="T3"),
        ]
    )

    # Train 1: NDLS -> CNB (Day 1 to Day 1)
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=1, station_id=s_ndls.id, arrival_time=None, departure_time="10:00:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=2, station_id=s_xx.id, arrival_time="12:00:00", departure_time="12:10:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t1.id, stop_sequence=3, station_id=s_cnb.id, arrival_time="14:34:00", departure_time=None, source_day=1),
        ]
    )

    # Train 2: Loops MTD -> DNA -> MTD -> DNA
    # seq1: MTD (Day 1 10:00)
    # seq2: DNA (Day 1 11:00)
    # seq3: MTD (Day 1 12:00)
    # seq4: DNA (Day 2 01:00) - day crossing
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=1, station_id=s_mtd.id, departure_time="10:00:00", source_day=1, arrival_time=None),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=2, station_id=s_dna.id, arrival_time="11:00:00", departure_time="11:05:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=3, station_id=s_mtd.id, arrival_time="12:00:00", departure_time="12:10:00", source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t2.id, stop_sequence=4, station_id=s_dna.id, arrival_time="01:00:00", departure_time=None, source_day=2),
        ]
    )

    # Train 3: NDLS -> CNB with missing timing
    db_session.add_all(
        [
            TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=1, station_id=s_ndls.id, arrival_time=None, departure_time=None, source_day=1),
            TrainStopObservation(snapshot_id=1, train_id=t3.id, stop_sequence=2, station_id=s_cnb.id, arrival_time="15:00:00", departure_time=None, source_day=1),
        ]
    )

    db_session.commit()


def test_api_network_travel_time_success(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/NDLS/travel-time/CNB")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "NDLS"
    assert data["to_station_code"] == "CNB"
    assert data["qualifying_occurrence_count"] == 1
    assert data["distinct_train_count"] == 1
    assert data["min_duration_minutes"] == 274 # 10:00 to 14:34
    assert data["max_duration_minutes"] == 274
    assert data["avg_duration_minutes"] == 274.0

def test_api_network_travel_time_repeated_and_cross_day(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/MTD/travel-time/DNA")
    assert response.status_code == 200
    data = response.json()
    assert data["from_station_code"] == "MTD"
    assert data["to_station_code"] == "DNA"

    # Valid pairs for T2:
    # 1 -> 2: 10:00 to 11:00 (Day 1) = 60 min
    # 1 -> 4: 10:00 (Day 1) to 01:00 (Day 2) = (1*1440) + 60 - 600 = 1440 + 60 - 600 = 900 min
    # 3 -> 4: 12:10 (Day 1) to 01:00 (Day 2) = (1*1440) + 60 - 730 = 1440 + 60 - 730 = 770 min

    assert data["qualifying_occurrence_count"] == 3
    assert data["distinct_train_count"] == 1
    assert data["min_duration_minutes"] == 60
    assert data["max_duration_minutes"] == 900
    assert data["avg_duration_minutes"] == round((60 + 900 + 770) / 3, 1)

def test_api_network_travel_time_no_route(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/CNB/travel-time/NDLS") # reverse
    assert response.status_code == 200
    data = response.json()
    assert data["qualifying_occurrence_count"] == 0
    assert data["distinct_train_count"] == 0
    assert data["min_duration_minutes"] is None
    assert data["max_duration_minutes"] is None
    assert data["avg_duration_minutes"] is None

def test_api_network_travel_time_same_station(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/NDLS/travel-time/NDLS")
    assert response.status_code == 400
    assert "different" in response.json()["detail"]

def test_api_network_travel_time_unknown_station(client: TestClient, db_session: Session) -> None:
    setup_data(db_session)
    response = client.get("/api/v1/network/stations/XXX/travel-time/NDLS")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

    response = client.get("/api/v1/network/stations/NDLS/travel-time/YYY")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
