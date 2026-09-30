import typing

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_junction_through_service


def in_memory_oracle(db_session: Session, snap_id: int, station_code: str) -> dict:
    """Oracle validator for Phase 63."""
    st = db_session.execute(text("SELECT id FROM stations WHERE code = :c"), {"c": station_code}).scalar()
    if not st:
        raise ValueError("Station not found")
        
    edges = db_session.execute(text("SELECT from_station_id, to_station_id FROM railway_network_edges WHERE timetable_snapshot_id = :s"), {"s": snap_id}).fetchall()
    neighbors = set()
    for f, t in edges:
        if f == st:
            neighbors.add(t)
        if t == st:
            neighbors.add(f)
            
    k = len(neighbors)
    if k < 2:
        raise ValueError(f"degree = {k}")
        
    possible = k * (k - 1) // 2
    
    stops = db_session.execute(text("SELECT train_id, station_id FROM train_stop_observations WHERE snapshot_id = :s ORDER BY train_id, stop_sequence"), {"s": snap_id}).fetchall()
    train_paths = {}
    for t_id, s_id in stops:
        if t_id not in train_paths:
            train_paths[t_id] = []
        train_paths[t_id].append(s_id)
        
    bridged = {}
    for t_id, path in train_paths.items():
        for i in range(1, len(path) - 1):
            if path[i] == st:
                prev_st = path[i-1]
                next_st = path[i+1]
                if prev_st in neighbors and next_st in neighbors and prev_st != next_st:
                    pair = tuple(sorted([prev_st, next_st]))
                    if pair not in bridged:
                        bridged[pair] = set()
                    bridged[pair].add(t_id)
                    
    served_pairs = []
    for pair, t_ids in bridged.items():
        c1 = db_session.execute(text("SELECT code FROM stations WHERE id = :i"), {"i": pair[0]}).scalar()
        c2 = db_session.execute(text("SELECT code FROM stations WHERE id = :i"), {"i": pair[1]}).scalar()
        c1, c2 = sorted([c1, c2])
        served_pairs.append({
            "neighbor_a": c1,
            "neighbor_b": c2,
            "qualifying_train_count": len(t_ids)
        })
        
    served_pairs.sort(key=lambda x: (x["neighbor_a"], x["neighbor_b"]))
    return {
        "station_code": station_code,
        "neighbor_count": k,
        "possible_neighbor_pairs": possible,
        "served_neighbor_pairs": len(served_pairs),
        "through_service_pair_ratio": round(len(served_pairs) / possible, 4) if possible > 0 else None,
        "served_pairs": served_pairs
    }

@pytest.fixture
def mock_junction_data(db_session: Session) -> typing.Any:
    db_session.execute(text("DELETE FROM railway_network_edges"))
    db_session.execute(text("DELETE FROM train_stop_observations"))
    db_session.execute(text("DELETE FROM station_observations"))
    db_session.execute(text("DELETE FROM train_observations"))
    db_session.execute(text("DELETE FROM trains"))
    db_session.execute(text("DELETE FROM stations"))
    db_session.execute(text("DELETE FROM dataset_snapshots"))
    db_session.execute(text("DELETE FROM data_sources"))
    db_session.commit()

    source = DataSource(name="Source 63", publisher="pub", url="url", license="mit")
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(source_id=source.id, status="ACTIVE")
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    stn_codes = ["S", "A", "B", "C", "D", "E", "F", "X"]
    stations = {}
    for code in stn_codes:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()
    
    for code in stn_codes:
        db_session.add(StationObservation(station_id=stations[code].id, snapshot_id=snap_id, name=f"Stn {code}"))
    db_session.commit()

    db_session.execute(text("INSERT INTO railway_network_edges (from_station_id, to_station_id, timetable_snapshot_id, train_count) VALUES (:f, :t, :s, 1)"), [
        {"f": stations["A"].id, "t": stations["S"].id, "s": snap_id},
        {"f": stations["B"].id, "t": stations["S"].id, "s": snap_id},
        {"f": stations["C"].id, "t": stations["S"].id, "s": snap_id},
        {"f": stations["D"].id, "t": stations["S"].id, "s": snap_id},
        {"f": stations["A"].id, "t": stations["B"].id, "s": snap_id},
        {"f": stations["E"].id, "t": stations["F"].id, "s": snap_id},
    ])
    db_session.commit()

    def add_train(tr_num: str, path: list[str]):
        tr = Train(number=tr_num)
        db_session.add(tr)
        db_session.commit()
        for i, code in enumerate(path, 1):
            tso = TrainStopObservation(
                snapshot_id=snap_id,
                train_id=tr.id,
                station_id=stations[code].id,
                stop_sequence=i
            )
            db_session.add(tso)
        db_session.commit()

    add_train("T1", ["A", "S", "B"])
    add_train("T2", ["B", "S", "A"])
    add_train("T3", ["C", "S", "D"])
    add_train("T4", ["A", "S", "C"])
    add_train("T5", ["A", "S"])
    add_train("T6", ["S", "B"])
    add_train("T7", ["A", "S", "A"])
    # Train 8: visits S twice, bridges A-C, then B-C
    add_train("T8", ["A", "S", "C", "X", "B", "S", "C"])
    # Train 9: visits S twice, bridges A-B, then A-B again (checks multiple traverses by one train)
    add_train("T9", ["A", "S", "B", "X", "A", "S", "B"])

    return {"snap_id": snap_id}

def test_station_junction_success(db_session: Session, mock_junction_data: typing.Any) -> None:
    snap_id = mock_junction_data["snap_id"]
    res = calculate_station_junction_through_service(db_session, snap_id, "S")
    oracle = in_memory_oracle(db_session, snap_id, "S")
    
    assert res["station_code"] == oracle["station_code"]
    assert res["neighbor_count"] == oracle["neighbor_count"] == 4
    assert res["possible_neighbor_pairs"] == oracle["possible_neighbor_pairs"] == 6
    assert res["served_neighbor_pairs"] == oracle["served_neighbor_pairs"] == 4
    
    pairs = {(p["neighbor_a"], p["neighbor_b"]): p["qualifying_train_count"] for p in res["served_pairs"]}
    assert pairs[("A", "B")] == 3 # T1, T2, T9
    assert pairs[("C", "D")] == 1
    assert pairs[("A", "C")] == 2 # T4, T8
    assert pairs[("B", "C")] == 1 # T8

    # Assert deterministic ordering (already tested by oracle comparison, but check explicitly)
    assert res["served_pairs"] == sorted(res["served_pairs"], key=lambda x: (x["neighbor_a"], x["neighbor_b"]))

def test_station_junction_zero_served(db_session: Session, mock_junction_data: typing.Any) -> None:
    snap_id = mock_junction_data["snap_id"]
    # E and F are connected to each other, but no train visits E -> S -> F
    # Wait, S isn't connected to E and F. Let's create a new junction J with neighbors K, L, but no trains bridge them.
    from railgati.models.station import Station, StationObservation
    st_codes = ["J", "K", "L"]
    stations = {}
    for code in st_codes:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()
    for code in st_codes:
        db_session.add(StationObservation(station_id=stations[code].id, snapshot_id=snap_id, name=f"Stn {code}"))
    db_session.commit()
    db_session.execute(text("INSERT INTO railway_network_edges (from_station_id, to_station_id, timetable_snapshot_id, train_count) VALUES (:f, :t, :s, 1)"), [
        {"f": stations["K"].id, "t": stations["J"].id, "s": snap_id},
        {"f": stations["L"].id, "t": stations["J"].id, "s": snap_id},
    ])
    db_session.commit()
    
    # Trains visit K and L but not through J
    tr = Train(number="T_ZERO")
    db_session.add(tr)
    db_session.commit()
    db_session.add(TrainStopObservation(snapshot_id=snap_id, train_id=tr.id, station_id=stations["K"].id, stop_sequence=1))
    db_session.add(TrainStopObservation(snapshot_id=snap_id, train_id=tr.id, station_id=stations["L"].id, stop_sequence=2))
    db_session.commit()
    
    res = calculate_station_junction_through_service(db_session, snap_id, "J")
    assert res["neighbor_count"] == 2
    assert res["possible_neighbor_pairs"] == 1
    assert res["served_neighbor_pairs"] == 0
    assert res["through_service_pair_ratio"] == 0.0
    assert res["served_pairs"] == []

def test_station_junction_k1(db_session: Session, mock_junction_data: typing.Any) -> None:
    snap_id = mock_junction_data["snap_id"]
    with pytest.raises(ValueError, match="degree = 1"):
        calculate_station_junction_through_service(db_session, snap_id, "E")

def test_station_junction_unknown(db_session: Session, mock_junction_data: typing.Any) -> None:
    snap_id = mock_junction_data["snap_id"]
    with pytest.raises(ValueError, match="not found"):
        calculate_station_junction_through_service(db_session, snap_id, "UNKNOWN")
