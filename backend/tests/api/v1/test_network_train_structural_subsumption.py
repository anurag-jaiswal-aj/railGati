import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture
def api_subsumption_fixtures(db_session: Session) -> None:
    source = DataSource(
        name="test_api_source", url="http://test", publisher="pub", license="MIT"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["A", "B", "C", "X", "Y"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    for s_code, st in stations.items():
        db_session.add(
            StationObservation(snapshot_id=snap_id, station_id=st.id, name=f"{s_code}_NAME")
        )
    db_session.commit()

    trains_data = [
        ("T1", ["A", "B", "C"]),
        ("T2", ["X", "A", "B", "C", "Y"]),
    ]

    for t_num, route in trains_data:
        tr = Train(number=t_num)
        db_session.add(tr)
        db_session.commit()
        db_session.add(
            TrainObservation(snapshot_id=snap_id, train_id=tr.id, name=t_num, type="EXP")
        )
        for idx, s_code in enumerate(route):
            db_session.add(TrainStopObservation(
                snapshot_id=snap_id,
                train_id=tr.id,
                station_id=stations[s_code].id,
                stop_sequence=idx + 1
            ))
        db_session.commit()


def test_get_train_structural_subsumption(
    client: TestClient, api_subsumption_fixtures: None
) -> None:
    response = client.get("/api/v1/network/trains/T1/structural-subsumption")
    assert response.status_code == 200
    data = response.json()

    assert data["train_number"] == "T1"
    assert data["subsuming_train_count"] == 1
    assert data["is_structurally_subsumed"] is True


def test_get_train_structural_subsumption_not_found(
    client: TestClient, api_subsumption_fixtures: None
) -> None:
    response = client.get("/api/v1/network/trains/UNKNOWN/structural-subsumption")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
