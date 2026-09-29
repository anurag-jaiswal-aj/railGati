import typing

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def terminal_incidence_api_fixtures(db_session: Session) -> typing.Any:
    source = DataSource(name="api_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.commit()
    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {}
    for code in ["A", "B", "C", "D"]:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()

    # Terminal Train: A -> B
    t1 = Train(number="T_TERM")
    db_session.add(t1)
    db_session.commit()
    db_session.add(TrainObservation(snapshot_id=snap_id, train_id=t1.id, name="T_TERM", type="EXP"))

    for idx, s_code in enumerate(["A", "B"]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap_id,
                train_id=t1.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1,
            )
        )

    # Target Train: C -> A -> D -> B
    # A and B are terminals (due to T_TERM).
    t2 = Train(number="T_TARGET")
    db_session.add(t2)
    db_session.commit()
    db_session.add(
        TrainObservation(snapshot_id=snap_id, train_id=t2.id, name="T_TARGET", type="EXP")
    )

    for idx, s_code in enumerate(["C", "A", "D", "B"]):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snap_id,
                train_id=t2.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1,
            )
        )

    db_session.commit()

    return {"snapshot_id": snap_id, "stations": stations}


def test_api_train_route_terminal_incidence_success(
    client: TestClient, db_session: Session, terminal_incidence_api_fixtures: typing.Any
) -> None:
    # Target Train: C -> A -> D -> B
    # Terminals: A, B, C, B (from T_TARGET it's C and B, from T_TERM it's A and B).
    # Wait, T_TARGET limits are C (start) and B (end).
    # So the global terminals are: A, B, C.
    # T_TARGET stops: C (terminal), A (terminal), D (non-terminal), B (terminal).
    # Expected: Total 4. Terminals: C, A, B (3). Distinct Terminals: 3.
    response = client.get("/api/v1/network/trains/T_TARGET/terminal-incidence")
    assert response.status_code == 200

    data = response.json()
    assert data["train_number"] == "T_TARGET"
    assert data["route_stop_occurrence_count"] == 4
    assert data["distinct_route_station_count"] == 4
    assert data["terminal_occurrence_count"] == 3
    assert data["distinct_terminal_station_count"] == 3
    assert data["incidence_ratio"] == round(3.0 / 4.0, 3)


def test_api_train_route_terminal_incidence_not_found(
    client: TestClient, db_session: Session, terminal_incidence_api_fixtures: typing.Any
) -> None:
    response = client.get("/api/v1/network/trains/INVALID/terminal-incidence")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
