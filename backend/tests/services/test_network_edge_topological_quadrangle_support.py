import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.graph_builder import build_graph_for_timetable_snapshot
from railgati.services.network import get_edge_topological_quadrangle_support


def _build_path(
    db_session: Session, snapshot_id: int, train: Train, station_codes: list[str]
) -> None:
    stations = []
    for code in station_codes:
        s = db_session.query(Station).filter_by(code=code).first()
        if not s:
            s = Station(code=code)
            db_session.add(s)
            db_session.flush()
        stations.append(s)

    for i, s in enumerate(stations):
        db_session.add(
            TrainStopObservation(
                snapshot_id=snapshot_id,
                train_id=train.id,
                stop_sequence=i + 1,
                station_id=s.id,
                departure_time="10:00:00",
                source_day=1,
            )
        )
    db_session.add(
        TrainObservation(snapshot_id=snapshot_id, train_id=train.id, name=f"Test {train.number}")
    )
    db_session.flush()


def test_quadrangle_support_various_topologies(db_session: Session) -> None:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    snapshot = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    train_path = Train(number="100")
    train_tri = Train(number="101")
    train_square = Train(number="102")
    train_square2 = Train(number="103")
    train_k4 = Train(number="104")
    db_session.add_all([train_path, train_tri, train_square, train_square2, train_k4])
    db_session.flush()

    # 1. Simple Path: P1-P2-P3 (Support should be 0)
    _build_path(db_session, snapshot.id, train_path, ["P1", "P2", "P3"])

    # 2. Triangle: T1-T2-T3-T1 (Support should be 0)
    _build_path(db_session, snapshot.id, train_tri, ["T1", "T2", "T3", "T1"])

    # 3. Chordless Square: S1-S2-S3-S4-S1 (Support should be 1 for all edges)
    _build_path(db_session, snapshot.id, train_square, ["S1", "S2", "S3", "S4", "S1"])

    # 4. K4: K1-K2-K3-K4-K1, plus K1-K3 and K2-K4 (Support should be 0 for all edges)
    _build_path(db_session, snapshot.id, train_k4, ["K1", "K2", "K3", "K4", "K1", "K3", "K2"])

    db_session.commit()

    build_record = build_graph_for_timetable_snapshot(db_session, snapshot.id)
    assert build_record.status == "ACTIVE"

    # Verify Path
    res = get_edge_topological_quadrangle_support(db_session, "P1", "P2")
    assert res is not None
    assert res["quadrangle_support"] == 0

    # Verify Triangle
    res = get_edge_topological_quadrangle_support(db_session, "T1", "T2")
    assert res is not None
    assert res["quadrangle_support"] == 0

    # Verify Chordless Square
    res = get_edge_topological_quadrangle_support(db_session, "S1", "S2")
    assert res is not None
    assert res["quadrangle_support"] == 1
    res = get_edge_topological_quadrangle_support(db_session, "S2", "S3")
    assert res is not None
    assert res["quadrangle_support"] == 1

    # Verify K4
    res = get_edge_topological_quadrangle_support(db_session, "K1", "K2")
    assert res is not None
    assert res["quadrangle_support"] == 0


def test_quadrangle_support_invalid_edge(db_session: Session) -> None:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    snapshot = DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE")
    db_session.add(snapshot)
    db_session.flush()

    t = Train(number="100")
    db_session.add(t)
    db_session.flush()
    _build_path(db_session, snapshot.id, t, ["A", "B"])
    db_session.commit()

    build_graph_for_timetable_snapshot(db_session, snapshot.id)

    # Unknown edge
    res = get_edge_topological_quadrangle_support(db_session, "A", "C")
    assert res is None

    # Missing station
    res = get_edge_topological_quadrangle_support(db_session, "C", "D")
    assert res is None

    # Self-loop
    with pytest.raises(ValueError, match="self-loop"):
        get_edge_topological_quadrangle_support(db_session, "A", "A")
