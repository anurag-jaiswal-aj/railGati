import typing
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train
from railgati.services.network import calculate_station_outbound_dominance


@pytest.fixture
def setup_service_data(db_session: Session) -> typing.Any:
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.flush()

    snapshot1 = DatasetSnapshot(id=1, source_id=1, status="OBSOLETE")
    snapshot2 = DatasetSnapshot(id=2, source_id=1, status="ACTIVE")
    db_session.add_all([snapshot1, snapshot2])
    db_session.flush()

    trains = []
    for num in ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12"]:
        t = Train(number=num)
        db_session.add(t)
        trains.append(t)
    db_session.flush()
    t_map = {t.number: t.id for t in trains}

    stations = []
    for code in ["BASIC", "B", "C", "SINGLE", "MULT", "TIE", "REP", "A", "UNKNOWN", "TERM"]:
        s = Station(code=code)
        db_session.add(s)
        stations.append(s)
    db_session.flush()
    s_map = {s.code: s.id for s in stations}
    for s in stations:
        db_session.add(StationObservation(snapshot_id=2, station_id=s.id, name=f"{s.code} Name"))
    db_session.flush()

    seq_counter = 1

    def add_edge(train_num: str, from_code: str, to_code: str, snap: int = 2) -> None:
        nonlocal seq_counter
        db_session.execute(
            text("""
                INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence) 
                VALUES (:snap, :t, :s1, :seq), (:snap, :t, :s2, :seq + 1)
            """),
            {
                "snap": snap,
                "t": t_map[train_num],
                "s1": s_map[from_code],
                "s2": s_map[to_code],
                "seq": seq_counter,
            },
        )
        seq_counter += 2

    # A. Basic dominance: BASIC -> B (6 times), BASIC -> C (4 times)
    for i in range(6):
        add_edge(f"T{i + 1}", "BASIC", "B")
    for i in range(4):
        add_edge(f"T{i + 7}", "BASIC", "C")

    # B. Single destination: SINGLE -> B (3 times)
    for i in range(3):
        add_edge(f"T{i + 1}", "SINGLE", "B")

    # D. Deterministic tie break: TIE -> C (5), TIE -> B (5)
    for i in range(5):
        add_edge(f"T{i + 1}", "TIE", "C")
    for i in range(5):
        add_edge(f"T{i + 6}", "TIE", "B")

    # E & F. Repeated / Distinct train
    # REP has T1 visiting twice all going to B.
    # Also T2 visiting once going to B. Total = 3 outbound occurrences to B.
    add_edge("T1", "REP", "B")
    add_edge("T1", "REP", "B")
    add_edge("T2", "REP", "B")

    # H. Empty / Terminus
    db_session.execute(
        text(
            "INSERT INTO train_stop_observations (snapshot_id, train_id, station_id, stop_sequence) VALUES (2, :t, :s, 500)"
        ),
        {"t": t_map["T1"], "s": s_map["TERM"]},
    )

    # I. Active snapshot exclusion
    add_edge("T1", "BASIC", "A", snap=1)  # Should not count for BASIC in snapshot 2

    db_session.commit()
    return snapshot2, s_map


def test_service_basic_dominance(db_session: Session, setup_service_data: typing.Any) -> None:
    # 6 to B, 4 to C. Total = 10, Max = 6 (B). Ratio = 0.6
    res = calculate_station_outbound_dominance(db_session, 2, "BASIC")
    assert res["station_code"] == "BASIC"
    assert res["timetable_snapshot_id"] == 2
    assert res["total_outbound_occurrences"] == 10
    assert res["max_outbound_occurrences"] == 6
    assert res["dominant_destination_station_code"] == "B"
    assert res["dominance_ratio"] == 0.6


def test_service_single_destination(db_session: Session, setup_service_data: typing.Any) -> None:
    res = calculate_station_outbound_dominance(db_session, 2, "SINGLE")
    assert res["total_outbound_occurrences"] == 3
    assert res["max_outbound_occurrences"] == 3
    assert res["dominant_destination_station_code"] == "B"
    assert res["dominance_ratio"] == 1.0


def test_service_tie_break(db_session: Session, setup_service_data: typing.Any) -> None:
    # 5 to C, 5 to B. 'B' should win deterministically via ASC sort.
    res = calculate_station_outbound_dominance(db_session, 2, "TIE")
    assert res["total_outbound_occurrences"] == 10
    assert res["max_outbound_occurrences"] == 5
    assert res["dominant_destination_station_code"] == "B"
    assert res["dominance_ratio"] == 0.5


def test_service_repeated_occurrences(db_session: Session, setup_service_data: typing.Any) -> None:
    # REP has 2 occurrences from T1, 1 from T2. Total = 3.
    res = calculate_station_outbound_dominance(db_session, 2, "REP")
    assert res["total_outbound_occurrences"] == 3
    assert res["max_outbound_occurrences"] == 3
    assert res["dominant_destination_station_code"] == "B"
    assert res["dominance_ratio"] == 1.0


def test_service_unknown_station(db_session: Session, setup_service_data: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_station_outbound_dominance(db_session, 2, "XXX")


def test_service_terminus_station(db_session: Session, setup_service_data: typing.Any) -> None:
    # TERM has no outbound edges
    with pytest.raises(ValueError, match="No qualifying outbound occurrences"):
        calculate_station_outbound_dominance(db_session, 2, "TERM")
