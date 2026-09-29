import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_pair_route_extension


@pytest.fixture
def extension_fixtures(db_session: Session) -> dict:
    source = DataSource(
        name="TEST_SRC_PHASE49", url="http://test", publisher="TEST", license="TEST"
    )
    db_session.add(source)
    db_session.commit()

    snapshot = DatasetSnapshot(
        source_id=source.id,
        status="ACTIVE",
    )
    db_session.add(snapshot)
    db_session.commit()

    return {
        "snapshot_id": snapshot.id,
    }


def test_calculate_route_extension_normal(db_session: Session, extension_fixtures: dict):
    snapshot_id = extension_fixtures["snapshot_id"]

    # Stations: S1, O, I1, D, S2
    s_s1 = Station(code="S1")
    s_o = Station(code="O")
    s_i1 = Station(code="I1")
    s_d = Station(code="D")
    s_s2 = Station(code="S2")
    db_session.add_all([s_s1, s_o, s_i1, s_d, s_s2])
    db_session.commit()

    # Train T1: S1(1) -> O(2) -> I1(3) -> D(4) -> S2(5)
    t1 = Train(number="T1")
    db_session.add(t1)
    db_session.commit()

    db_session.add(TrainObservation(snapshot_id=snapshot_id, train_id=t1.id, name="T1"))

    stops = [
        (s_s1, 1), (s_o, 2), (s_i1, 3), (s_d, 4), (s_s2, 5)
    ]
    for st, seq in stops:
        db_session.add(
            TrainStopObservation(
                snapshot_id=snapshot_id, train_id=t1.id, station_id=st.id, stop_sequence=seq
            )
        )
    db_session.commit()

    result = calculate_station_pair_route_extension(db_session, "O", "D", snapshot_id)
    assert result == {
        "origin_station": "O",
        "destination_station": "D",
        "traversal_occurrence_count": 1,
        "pre_origin_station_count": 1, # S1
        "post_destination_station_count": 1, # S2
        "total_extension_station_count": 2 # S1, S2
    }


def test_calculate_route_extension_cyclic(db_session: Session, extension_fixtures: dict):
    snapshot_id = extension_fixtures["snapshot_id"]

    # Fixture: O(1) -> A(2) -> D(3) -> B(4) -> O(5) -> C(6) -> D(7) -> E(8)
    stations = {code: Station(code=code) for code in ["O", "A", "D", "B", "C", "E"]}
    db_session.add_all(stations.values())
    db_session.commit()

    t_cyc = Train(number="TCYC")
    db_session.add(t_cyc)
    db_session.commit()

    db_session.add(TrainObservation(snapshot_id=snapshot_id, train_id=t_cyc.id, name="TCYC"))

    stops = [
        ("O", 1), ("A", 2), ("D", 3), ("B", 4),
        ("O", 5), ("C", 6), ("D", 7), ("E", 8)
    ]
    for code, seq in stops:
        db_session.add(
            TrainStopObservation(
                snapshot_id=snapshot_id,
                train_id=t_cyc.id,
                station_id=stations[code].id,
                stop_sequence=seq,
            )
        )
    db_session.commit()

    result = calculate_station_pair_route_extension(db_session, "O", "D", snapshot_id)

    # Valid traversals for O -> D:
    # 1. (1, 3): pre=[], post=[B, O, C, D, E]
    # 2. (1, 7): pre=[], post=[E]
    # 3. (5, 7): pre=[O, A, D, B], post=[E]
    # Note that (5, 3) is excluded because 5 > 3.

    # Pre-origin sets:
    # (1, 3) -> None
    # (1, 7) -> None
    # (5, 7) -> {O, A, D, B} -> distinct count = 4

    # Post-dest sets:
    # (1, 3) -> {B, O, C, D, E} -> distinct count = 5
    # (1, 7) -> {E} -> distinct count = 1
    # (5, 7) -> {E} -> distinct count = 1

    # Global Pre set = {O, A, D, B}
    # Global Post set = {B, O, C, D, E}
    # Global Union set = {O, A, D, B, C, E}

    assert result["traversal_occurrence_count"] == 3
    assert result["pre_origin_station_count"] == 4
    assert result["post_destination_station_count"] == 5
    assert result["total_extension_station_count"] == 6


def test_calculate_route_extension_no_direct_path(db_session: Session, extension_fixtures: dict):
    snapshot_id = extension_fixtures["snapshot_id"]
    s_x = Station(code="X")
    s_y = Station(code="Y")
    db_session.add_all([s_x, s_y])
    db_session.commit()

    result = calculate_station_pair_route_extension(db_session, "X", "Y", snapshot_id)
    assert result == {}


def test_calculate_route_extension_same_station(db_session: Session, extension_fixtures: dict):
    snapshot_id = extension_fixtures["snapshot_id"]
    with pytest.raises(ValueError, match=r"Origin and destination cannot be identical\."):
        calculate_station_pair_route_extension(db_session, "X", "X", snapshot_id)

