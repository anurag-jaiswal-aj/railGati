import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_edge_route_terminal_dispersion


@pytest.fixture
def terminal_dispersion_fixtures(db_session: Session) -> typing.Any:
    source = DataSource(name="test_dispersion", url="http://test", publisher="pub", license="MIT")
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="TEST_DISP", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = ["O1", "O2", "D1", "D2", "A", "B", "UNK"]
    for scode in stations:
        st = Station(code=scode)
        db_session.add(st)
        db_session.commit()
        db_session.add(
            StationObservation(snapshot_id=snap_id, station_id=st.id, name=scode, state="State")
        )
    db_session.commit()

    # Train 1: O1 -> A -> B -> D1
    # Train 2: O1 -> A -> B -> D2
    # Train 3: O2 -> A -> B -> D1
    # Train 4: O2 -> A -> B -> A -> B -> D2
    # Train 5: A -> B
    trains_data = [
        ("T1", ["O1", "A", "B", "D1"]),
        ("T2", ["O1", "A", "B", "D2"]),
        ("T3", ["O2", "A", "B", "D1"]),
        ("T4", ["O2", "A", "B", "A", "B", "D2"]),
        ("T5", ["A", "B"]),
    ]

    for t_num, route in trains_data:
        tr = Train(number=t_num)
        db_session.add(tr)
        db_session.commit()
        db_session.add(
            TrainObservation(snapshot_id=snap_id, train_id=tr.id, name=t_num, type="EXP")
        )
        for idx, s_code in enumerate(route):
            st = db_session.query(Station).filter_by(code=s_code).first()
            assert st is not None
            db_session.add(
                TrainStopObservation(
                    snapshot_id=snap_id, train_id=tr.id, station_id=st.id, stop_sequence=idx + 1
                )
            )
        db_session.commit()

    return {"snapshot_id": snap_id}


def test_dispersion_basic_cases(
    db_session: Session, terminal_dispersion_fixtures: typing.Any
) -> None:
    res = calculate_edge_route_terminal_dispersion(
        db_session, terminal_dispersion_fixtures["snapshot_id"], "A", "B"
    )

    assert res["traversing_train_count"] == 5
    assert res["distinct_origin_count"] == 3
    assert res["distinct_destination_count"] == 3


def test_dispersion_unknown_station(
    db_session: Session, terminal_dispersion_fixtures: typing.Any
) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_edge_route_terminal_dispersion(
            db_session, terminal_dispersion_fixtures["snapshot_id"], "INVALID", "B"
        )

    with pytest.raises(ValueError, match="not found"):
        calculate_edge_route_terminal_dispersion(
            db_session, terminal_dispersion_fixtures["snapshot_id"], "A", "INVALID"
        )


def test_dispersion_no_edge(db_session: Session, terminal_dispersion_fixtures: typing.Any) -> None:
    # B -> A is traversed by T4
    res = calculate_edge_route_terminal_dispersion(
        db_session, terminal_dispersion_fixtures["snapshot_id"], "B", "A"
    )
    assert res["traversing_train_count"] == 1
    assert res["distinct_origin_count"] == 1
    assert res["distinct_destination_count"] == 1

    with pytest.raises(ValueError, match="not found"):
        calculate_edge_route_terminal_dispersion(
            db_session, terminal_dispersion_fixtures["snapshot_id"], "B", "UNK"
        )


def test_dispersion_active_snapshot_isolation(
    db_session: Session, terminal_dispersion_fixtures: typing.Any
) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_edge_route_terminal_dispersion(db_session, 999, "A", "B")
