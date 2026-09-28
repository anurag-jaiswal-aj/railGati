import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_topological_bypasses


@pytest.fixture
def bypass_fixtures(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(
        name="test_bypasses", url="http://test", publisher="pub", license="MIT"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    trains_data = [
        ("NO_BYPASS", ["S6", "S7", "S8"]),
        ("SHORT", ["S1", "S2"]),
        ("HAS_BYPASS", ["S1", "S2", "S3", "S4", "S5"]),
        ("BYPASS_PROVIDER", ["S1", "S3", "S5"]),  # Provides bypasses S1->S3, S3->S5
        ("DUP_BYPASS_PROVIDER", ["S1", "S3"]),    # Duplicate provider for S1->S3
        ("REVERSE_BYPASS", ["S4", "S1"]),         # Does NOT bypass HAS_BYPASS
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

    return {"snapshot_id": snap_id, "stations": stations}

def test_topological_bypasses_no_bypasses(db_session: Session, bypass_fixtures: typing.Any) -> None:
    result = calculate_train_topological_bypasses(db_session, bypass_fixtures["snapshot_id"], "NO_BYPASS")
    assert result["train_number"] == "NO_BYPASS"
    assert result["route_length"] == 3
    assert result["bypass_edge_count"] == 0
    assert result["has_topological_bypasses"] is False

def test_topological_bypasses_short_train(db_session: Session, bypass_fixtures: typing.Any) -> None:
    result = calculate_train_topological_bypasses(db_session, bypass_fixtures["snapshot_id"], "SHORT")
    assert result["train_number"] == "SHORT"
    assert result["route_length"] == 2
    assert result["bypass_edge_count"] == 0
    assert result["has_topological_bypasses"] is False

def test_topological_bypasses_with_bypasses(db_session: Session, bypass_fixtures: typing.Any) -> None:
    result = calculate_train_topological_bypasses(db_session, bypass_fixtures["snapshot_id"], "HAS_BYPASS")
    assert result["train_number"] == "HAS_BYPASS"
    assert result["route_length"] == 5
    # Bypasses: S1->S3, S3->S5 provided by BYPASS_PROVIDER.
    # DUP_BYPASS_PROVIDER also provides S1->S3 but counted once.
    # REVERSE_BYPASS provides S4->S1 which is opposite order, so 0.
    assert result["bypass_edge_count"] == 2
    assert result["has_topological_bypasses"] is True

def test_topological_bypasses_not_found(db_session: Session, bypass_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_topological_bypasses(db_session, bypass_fixtures["snapshot_id"], "UNKNOWN")

def test_topological_bypasses_active_snapshot_isolation(db_session: Session, bypass_fixtures: typing.Any) -> None:
    # Query with a non-existent snapshot
    # Since the train exists, it will run the query but find 0 candidates in snapshot 999.
    result = calculate_train_topological_bypasses(db_session, 999, "HAS_BYPASS")
    assert result["bypass_edge_count"] == 0
    assert result["has_topological_bypasses"] is False
