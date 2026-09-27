import typing
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation


@pytest.fixture
def setup_api_data(db_session: Session) -> typing.Any:
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.flush()

    snapshot = DatasetSnapshot(id=2, source_id=1, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    trains = []
    for num in range(1, 20):
        t = Train(number=f"T{num}")
        db_session.add(t)
        trains.append(t)
    db_session.flush()
    t_map = {t.number: t.id for t in trains}

    stations = []
    for code in ["API", "DEST", "TERM"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}
    for s in stations:
        db_session.add(StationObservation(snapshot_id=2, station_id=s.id, name=f"{s.code} Name"))
    db_session.flush()

    # API -> DEST (10 occurrences, using different trains)
    for i in range(1, 11):
        db_session.execute(
            text("""
                INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence) 
                VALUES (2, :t, :s1, 1), (2, :t, :s2, 2)
            """),
            {"t": t_map[f"T{i}"], "s1": s_map["API"], "s2": s_map["DEST"]},
        )

    # TERM -> (no next stop)
    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence) VALUES (2, :t, :s, 100)"
        ),
        {"t": t_map["T1"], "s": s_map["TERM"]},
    )

    db_session.add(TrainObservation(snapshot_id=2, train_id=1, name="Test"))
    db_session.commit()
    return snapshot


def test_api_station_outbound_dominance_success(
    client: typing.Any, setup_api_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/API/outbound-dominance")
    assert response.status_code == 200
    data = response.json()
    assert data["station_code"] == "API"
    assert data["timetable_snapshot_id"] == 2
    assert data["total_outbound_occurrences"] == 10
    assert data["max_outbound_occurrences"] == 10
    assert data["dominant_destination_station_code"] == "DEST"
    assert data["dominance_ratio"] == 1.0


def test_api_station_outbound_dominance_unknown(
    client: typing.Any, setup_api_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/XXX/outbound-dominance")
    assert response.status_code == 404


def test_api_station_outbound_dominance_empty(
    client: typing.Any, setup_api_data: typing.Any
) -> None:
    response = client.get("/api/v1/network/stations/TERM/outbound-dominance")
    assert response.status_code == 400
    assert "No qualifying outbound occurrences" in response.json()["detail"]
