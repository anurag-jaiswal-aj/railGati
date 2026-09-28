import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_transfer_free_reach


@pytest.fixture
def tfr_fixtures(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(
        name="test_source", url="http://test", publisher="test_publisher", license="test_license"
    )
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stations = {
        "S1": Station(code="S1"),
        "S2": Station(code="S2"),
        "S3": Station(code="S3"),
        "S4": Station(code="S4"),
        "S5": Station(code="S5"),
        "S_TERM": Station(code="S_TERM")
    }
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    for s_code, st in stations.items():
        db_session.add(
            StationObservation(snapshot_id=snap_id, station_id=st.id, name=f"{s_code}_NAME")
        )
    db_session.commit()

    # Train 1: S1 -> S2 -> S3 -> S4 -> S5 (long distance)
    # Train 2: S1 -> S3 -> S4 (another train)
    # Train 3: S2 -> S1 -> S3 (tests directionality)
    # Train 4: S_TERM -> S1 (terminates at S1)

    trains_data = [
        ("T1", ["S1", "S2", "S3", "S4", "S5"]),
        ("T2", ["S1", "S3", "S4"]),
        ("T3", ["S2", "S1", "S3"]),
        ("T4", ["S_TERM", "S1"])
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

def test_tfr_normal(db_session: Session, tfr_fixtures: typing.Any) -> None:
    # S1 has outbound to S2 (from T1) and S3 (from T2, T3)
    # N1 = 2 (S2, S3)
    # TFOR downstream of S1:
    # From T1: S2, S3, S4, S5
    # From T2: S3, S4
    # From T3: S3
    # From T4: none (ends at S1)
    # Distinct TFOR = S2, S3, S4, S5 (4 stations)
    res = calculate_station_transfer_free_reach(db_session, tfr_fixtures["snapshot_id"], "S1")
    assert res["station_code"] == "S1"
    assert res["topological_outbound_degree"] == 2
    assert res["transfer_free_outbound_reach"] == 4
    assert res["reachability_span_ratio"] == 2.0

def test_tfr_directionality(db_session: Session, tfr_fixtures: typing.Any) -> None:
    # S2 -> S3 (T1), S2 -> S4 (T1), S2 -> S5 (T1)
    # S2 -> S1 (T3), S2 -> S3 (T3)
    # N1 = 2 (S3 from T1, S1 from T3)
    # TFOR downstream of S2: S3, S4, S5, S1
    # Distinct TFOR = 4
    res = calculate_station_transfer_free_reach(db_session, tfr_fixtures["snapshot_id"], "S2")
    assert res["topological_outbound_degree"] == 2
    assert res["transfer_free_outbound_reach"] == 4
    assert res["reachability_span_ratio"] == 2.0

def test_tfr_shuttle_or_terminal(db_session: Session, tfr_fixtures: typing.Any) -> None:
    # S5 has no outbound. N1=0 -> ValueError
    with pytest.raises(ValueError, match="n1_count == 0"):
        calculate_station_transfer_free_reach(db_session, tfr_fixtures["snapshot_id"], "S5")

    # S4 has outbound only to S5 (T1). N1=1, TFOR=1 (S5). Ratio = 1.0
    res = calculate_station_transfer_free_reach(db_session, tfr_fixtures["snapshot_id"], "S4")
    assert res["topological_outbound_degree"] == 1
    assert res["transfer_free_outbound_reach"] == 1
    assert res["reachability_span_ratio"] == 1.0

def test_tfr_unknown_station(db_session: Session, tfr_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_station_transfer_free_reach(db_session, tfr_fixtures["snapshot_id"], "UNKNOWN")

def test_tfr_missing_snapshot(db_session: Session, tfr_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="n1_count == 0"):
        calculate_station_transfer_free_reach(db_session, 999, "S1")
