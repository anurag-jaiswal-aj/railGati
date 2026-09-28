import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_route_edge_exclusivity


@pytest.fixture
def edge_exclusivity_fixtures(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(
        name="test_exclusivity", url="http://test", publisher="pub", license="MIT"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["A", "B", "C", "D", "E", "F", "G", "X", "Y", "Z", "U", "V"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    # Train definitions:
    # TARGET_ALL_EXC: X -> Y -> Z. No other train traverses these edges.
    # TARGET_ALL_SHARED: D -> E -> F.
    # OTHER_SHARED: D -> E -> F -> G. (Divergent route sharing edges).
    # TARGET_MIXED: A -> B -> C -> F -> G.
    # OTHER_MIXED: C -> F -> G.
    # TARGET_DUP_1: A -> E.
    # TARGET_DUP_2: A -> E. (Identical to 1).
    # TARGET_REPEATED: U -> V -> U.

    trains_data = [
        ("TARGET_ALL_EXC", ["X", "Y", "Z"]),
        ("TARGET_ALL_SHARED", ["D", "E", "F"]),
        ("OTHER_SHARED", ["D", "E", "F", "G"]),
        ("TARGET_MIXED", ["A", "B", "C", "F", "G"]),
        ("OTHER_MIXED", ["C", "F", "G"]),
        ("TARGET_DUP_1", ["A", "E"]),
        ("TARGET_DUP_2", ["A", "E"]),
        ("TARGET_REPEATED", ["U", "V", "U"]),
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


def test_edge_exclusivity_all_exclusive(db_session: Session, edge_exclusivity_fixtures: typing.Any) -> None:
    res = calculate_train_route_edge_exclusivity(db_session, edge_exclusivity_fixtures["snapshot_id"], "TARGET_ALL_EXC")
    assert res["train_number"] == "TARGET_ALL_EXC"
    assert res["route_length"] == 3
    assert res["route_edge_count"] == 2
    assert res["exclusive_edge_count"] == 2
    assert res["shared_edge_count"] == 0
    assert res["exclusivity_ratio"] == 1.0


def test_edge_exclusivity_all_shared(db_session: Session, edge_exclusivity_fixtures: typing.Any) -> None:
    res = calculate_train_route_edge_exclusivity(db_session, edge_exclusivity_fixtures["snapshot_id"], "TARGET_ALL_SHARED")
    assert res["train_number"] == "TARGET_ALL_SHARED"
    assert res["route_length"] == 3
    assert res["route_edge_count"] == 2
    assert res["exclusive_edge_count"] == 0
    assert res["shared_edge_count"] == 2
    assert res["exclusivity_ratio"] == 0.0


def test_edge_exclusivity_mixed(db_session: Session, edge_exclusivity_fixtures: typing.Any) -> None:
    # TARGET_MIXED (A->B->C->F->G). 4 edges.
    # A->B and B->C are shared with TARGET_ALL_EXC? Wait!
    # TARGET_ALL_EXC is A->B->C. This differs from TARGET_MIXED! So A->B and B->C are shared.
    # C->F and F->G are shared with OTHER_MIXED (C->F->G).
    # Wait, ALL edges of TARGET_MIXED are shared.
    res = calculate_train_route_edge_exclusivity(db_session, edge_exclusivity_fixtures["snapshot_id"], "TARGET_MIXED")
    assert res["exclusive_edge_count"] == 2
    assert res["shared_edge_count"] == 2


def test_edge_exclusivity_duplicates(db_session: Session, edge_exclusivity_fixtures: typing.Any) -> None:
    # TARGET_DUP_1 and TARGET_DUP_2 are identical (A->E).
    # They should both be exclusive.
    res = calculate_train_route_edge_exclusivity(db_session, edge_exclusivity_fixtures["snapshot_id"], "TARGET_DUP_1")
    assert res["exclusive_edge_count"] == 1
    assert res["shared_edge_count"] == 0


def test_edge_exclusivity_repeated_stations(db_session: Session, edge_exclusivity_fixtures: typing.Any) -> None:
    res = calculate_train_route_edge_exclusivity(db_session, edge_exclusivity_fixtures["snapshot_id"], "TARGET_REPEATED")
    assert res["route_length"] == 3
    assert res["route_edge_count"] == 2
    assert res["exclusive_edge_count"] == 2
    assert res["shared_edge_count"] == 0


def test_edge_exclusivity_not_found(db_session: Session, edge_exclusivity_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_route_edge_exclusivity(db_session, edge_exclusivity_fixtures["snapshot_id"], "UNKNOWN")


def test_edge_exclusivity_active_snapshot_isolation(db_session: Session, edge_exclusivity_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_route_edge_exclusivity(db_session, 999, "TARGET_ALL_EXC")
