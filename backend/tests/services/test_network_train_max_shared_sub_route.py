import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_max_shared_sub_route


@pytest.fixture
def max_shared_sub_route_fixtures(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(
        name="test_source", url="http://test", publisher="test_publisher", license="test_license"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {code: Station(code=code) for code in ["A", "B", "C", "D", "E", "F", "X", "Y"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    for st in stations.values():
        db_session.add(
            StationObservation(
                station_id=st.id, snapshot_id=snap_id, name=st.code
            )
        )
    db_session.commit()

    trains_data = [
        ("TARGET", ["A", "B", "C", "D", "E"]),
        ("MATCH_3_1", ["X", "B", "C", "D", "Y"]),  # Length 3 (B, C, D)
        ("MATCH_3_2", ["A", "B", "C", "X"]),       # Length 3 (A, B, C)
        ("MATCH_2", ["X", "C", "D", "Y"]),         # Length 2 (C, D)
        ("NON_CONTIGUOUS", ["A", "X", "B", "C", "Y", "D", "E"]), # Length 2 is max contiguous (B, C) or (D, E) but overall shares 5
        ("REVERSE", ["E", "D", "C", "B", "A"]),    # Reverse direction, length 1 (only intersections)
        ("NO_MATCH", ["X", "Y"]),
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

    # Duplicate stop test
    # Target 2: A, B, A, B
    # Match: X, A, B, A, B, Y (length 4)
    # Match short: A, B (length 2)
    trains_data_2 = [
        ("T2", ["A", "B", "A", "B"]),
        ("M_4", ["X", "A", "B", "A", "B", "Y"]),
        ("M_2", ["A", "B"])
    ]
    for t_num, route in trains_data_2:
        tr = Train(number=t_num)
        db_session.add(tr)
        db_session.commit()
        db_session.add(TrainObservation(snapshot_id=snap_id, train_id=tr.id, name=t_num, type="EXP"))
        for idx, s_code in enumerate(route):
            db_session.add(TrainStopObservation(
                snapshot_id=snap_id, train_id=tr.id, station_id=stations[s_code].id, stop_sequence=idx + 1
            ))
        db_session.commit()

    return {"snapshot_id": snap_id, "stations": stations}


def test_calculate_train_max_shared_sub_route_success(db_session: Session, max_shared_sub_route_fixtures: typing.Any) -> None:
    res = calculate_train_max_shared_sub_route(db_session, max_shared_sub_route_fixtures["snapshot_id"], "TARGET")
    assert res["target_train_number"] == "TARGET"

    routes = res["top_shared_sub_routes"]
    # New logic: returns max segment PER train, ordered by length DESC, train_number ASC

    assert len(routes) == 8 # 8 trains share at least 1 station

    assert routes[0]["other_train_number"] == "MATCH_3_1"
    assert routes[0]["shared_station_count"] == 3

    assert routes[1]["other_train_number"] == "MATCH_3_2"
    assert routes[1]["shared_station_count"] == 3

    assert routes[2]["other_train_number"] == "MATCH_2"
    assert routes[2]["shared_station_count"] == 2

    assert routes[3]["other_train_number"] == "M_2"
    assert routes[3]["shared_station_count"] == 2

    assert routes[4]["other_train_number"] == "M_4"
    assert routes[4]["shared_station_count"] == 2

    assert routes[5]["other_train_number"] == "NON_CONTIGUOUS"
    assert routes[5]["shared_station_count"] == 2

    assert routes[6]["other_train_number"] == "T2"
    assert routes[6]["shared_station_count"] == 2

    assert routes[7]["other_train_number"] == "REVERSE"
    assert routes[7]["shared_station_count"] == 1


def test_calculate_train_max_shared_sub_route_repeated_stations(db_session: Session, max_shared_sub_route_fixtures: typing.Any) -> None:
    res = calculate_train_max_shared_sub_route(db_session, max_shared_sub_route_fixtures["snapshot_id"], "T2")
    routes = res["top_shared_sub_routes"]

    assert len(routes) == 7
    assert routes[0]["other_train_number"] == "M_4"
    assert routes[0]["shared_station_count"] == 4

    assert routes[1]["other_train_number"] == "MATCH_3_2"
    assert routes[1]["shared_station_count"] == 2

    assert routes[2]["other_train_number"] == "M_2"
    assert routes[2]["shared_station_count"] == 2


def test_calculate_train_max_shared_sub_route_not_found(db_session: Session, max_shared_sub_route_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_max_shared_sub_route(db_session, max_shared_sub_route_fixtures["snapshot_id"], "INVALID")


def test_calculate_train_max_shared_sub_route_no_matches(db_session: Session, max_shared_sub_route_fixtures: typing.Any) -> None:
    res = calculate_train_max_shared_sub_route(db_session, max_shared_sub_route_fixtures["snapshot_id"], "NO_MATCH")
    # NO_MATCH shares X and Y with some candidates, wait, MATCH_3_1 has X and Y.
    # So it DOES share length 1!
    # Let's verify: NO_MATCH is X, Y.
    # MATCH_3_1 has X. MATCH_3_1 has Y. But not X, Y contiguous.
    # So max length is 1.
    assert len(res["top_shared_sub_routes"]) > 0
    for r in res["top_shared_sub_routes"]:
        assert r["shared_station_count"] == 1
