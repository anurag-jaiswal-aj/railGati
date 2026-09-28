import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_edge_traversal_dispersion


@pytest.fixture
def edge_dispersion_fixtures(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(
        name="test_dispersion", url="http://test", publisher="pub", license="MIT"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["X1", "X2", "A", "B", "Y1", "Y2", "UNKNOWN"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    # The target edge is A -> B.
    # Train T1: X1 -> A -> B -> Y1
    # Train T2: X1 -> A -> B -> Y2
    # Train T3: X2 -> A -> B -> Y1
    # Train T4: A -> B -> Y2 (Starts at A)
    # Train T5: X2 -> A -> B (Ends at B)
    # Train T6: B -> A (Reverse, shouldn't count for A->B)
    # Train T7: X1 -> A -> B -> Y1 (Duplicate of T1's routing to ensure DISTINCT works)

    trains_data = [
        ("T1", ["X1", "A", "B", "Y1"]),
        ("T2", ["X1", "A", "B", "Y2"]),
        ("T3", ["X2", "A", "B", "Y1"]),
        ("T4", ["A", "B", "Y2"]),
        ("T5", ["X2", "A", "B"]),
        ("T6", ["B", "A"]),
        ("T7", ["X1", "A", "B", "Y1"]),
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

def test_edge_dispersion_success(db_session: Session, edge_dispersion_fixtures: typing.Any) -> None:
    # A -> B has 6 distinct train occurrences traversing it: T1, T2, T3, T4, T5, T7.
    # Convergence stations (before A): X1 (from T1, T2, T7) and X2 (from T3, T5). Total = 2.
    # Originating at A: T4. Total = 1.
    # Bifurcation stations (after B): Y1 (from T1, T3, T7) and Y2 (from T2, T4). Total = 2.
    # Terminating at B: T5. Total = 1.

    result = calculate_edge_traversal_dispersion(db_session, edge_dispersion_fixtures["snapshot_id"], "A", "B")
    assert result["from_station_code"] == "A"
    assert result["to_station_code"] == "B"
    assert result["edge_volume"] == 6
    assert result["convergence_count"] == 2
    assert result["originating_count"] == 1
    assert result["bifurcation_count"] == 2
    assert result["terminating_count"] == 1

def test_edge_dispersion_reverse_edge(db_session: Session, edge_dispersion_fixtures: typing.Any) -> None:
    # B -> A has only T6 traversing it. It starts at B and ends at A.
    result = calculate_edge_traversal_dispersion(db_session, edge_dispersion_fixtures["snapshot_id"], "B", "A")
    assert result["from_station_code"] == "B"
    assert result["to_station_code"] == "A"
    assert result["edge_volume"] == 1
    assert result["convergence_count"] == 0
    assert result["originating_count"] == 1
    assert result["bifurcation_count"] == 0
    assert result["terminating_count"] == 1

def test_edge_dispersion_no_edge(db_session: Session, edge_dispersion_fixtures: typing.Any) -> None:
    # A -> Y1 has no direct edge in the database
    with pytest.raises(ValueError, match="No qualifying adjacent timetable edge found"):
        calculate_edge_traversal_dispersion(db_session, edge_dispersion_fixtures["snapshot_id"], "A", "Y1")

def test_edge_dispersion_unknown_station(db_session: Session, edge_dispersion_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="Station UNK1 not found"):
        calculate_edge_traversal_dispersion(db_session, edge_dispersion_fixtures["snapshot_id"], "UNK1", "B")

    with pytest.raises(ValueError, match="Station UNK2 not found"):
        calculate_edge_traversal_dispersion(db_session, edge_dispersion_fixtures["snapshot_id"], "A", "UNK2")

def test_edge_dispersion_active_snapshot_isolation(db_session: Session, edge_dispersion_fixtures: typing.Any) -> None:
    # Query with a non-existent snapshot
    with pytest.raises(ValueError, match="No qualifying adjacent timetable edge found"):
        calculate_edge_traversal_dispersion(db_session, 999, "A", "B")
