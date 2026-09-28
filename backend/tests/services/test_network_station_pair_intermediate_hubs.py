import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_pair_intermediate_hubs


@pytest.fixture
def hub_concentration_fixtures(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(name="test_source", url="http://test", publisher="pub", license="test")
    db_session.add(source)
    db_session.commit()

    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    # We will also use snap_id + 1 for station observations just to test snapshot isolation correctly.
    # The system uses the active station snapshot.
    station_snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(station_snap)
    db_session.commit()

    stations = {code: Station(code=code) for code in ["A", "B", "C", "D", "S", "X", "Y"]}
    for st in stations.values():
        db_session.add(st)
    db_session.commit()

    for code, st in stations.items():
        db_session.add(StationObservation(snapshot_id=station_snap.id, station_id=st.id, name=f"Name {code}"))
    db_session.commit()

    paths = [
        # 1. Simple one-path traversal
        ("T1", ["A", "B", "D"]),

        # 2. Multiple trains sharing intermediate stations
        ("T2", ["A", "B", "C", "D"]),
        ("T3", ["A", "X", "B", "D"]),

        # 3. Repeated origin & Repeated destination (A -> D -> A -> D)
        # Should create 3 valid O-D traversals
        ("T4", ["A", "D", "A", "D"]),

        # 4. Repeated intermediate station occurring multiple times in one traversal
        ("T5", ["A", "B", "S", "B", "S", "D"]),

        # 5. Multiple distinct routes between O/D
        ("T6", ["A", "Y", "D"]),
    ]

    for t_num, seq in paths:
        tr = Train(number=t_num)
        db_session.add(tr)
        db_session.commit()

        db_session.add(TrainObservation(snapshot_id=snap_id, train_id=tr.id, name=t_num, type="EXP"))
        for idx, scode in enumerate(seq):
            db_session.add(TrainStopObservation(
                snapshot_id=snap_id, train_id=tr.id, station_id=stations[scode].id, stop_sequence=idx + 1
            ))
    db_session.commit()

    return {"snapshot_id": snap_id, "stations": stations}

def test_hub_concentration_success(db_session: Session, hub_concentration_fixtures: typing.Any) -> None:
    res = calculate_station_pair_intermediate_hubs(db_session, "A", "D")

    assert res["from_station_code"] == "A"
    assert res["to_station_code"] == "D"

    # Valid traversal instances for A -> D:
    # T1: 1 (A:1, D:3) -> Intermediates: B
    # T2: 1 (A:1, D:4) -> Intermediates: B, C
    # T3: 1 (A:1, D:4) -> Intermediates: X, B
    # T4: 3 (A:1->D:2 (none), A:1->D:4 (D, A), A:3->D:4 (none))
    #     Wait, for T4: A(1)->D(2) = 0 inter
    #     A(1)->D(4) = inter: D(2), A(3)
    #     A(3)->D(4) = 0 inter
    # T5: 1 (A:1, D:6) -> Intermediates: B(2), S(3), B(4), S(5)
    # T6: 1 (A:1, D:3) -> Intermediates: Y
    # Total valid traversal instances = 1 + 1 + 1 + 3 + 1 + 1 = 8

    assert res["total_traversal_instances"] == 8

    hubs = res["intermediate_hubs"]

    # Hub evaluations:
    # B:
    #   T1: 1 traversal, 1 occurrence
    #   T2: 1 traversal, 1 occ
    #   T3: 1 traversal, 1 occ
    #   T5: 1 traversal, 2 occ
    #   Total: 4 traversals, 5 occurrences

    # S:
    #   T5: 1 traversal, 2 occ
    #   Total: 1 traversal, 2 occurrences

    # C:
    #   T2: 1 traversal, 1 occ

    # X:
    #   T3: 1 traversal, 1 occ

    # Y:
    #   T6: 1 traversal, 1 occ

    # A (intermediate for T4 A1->D4):
    #   T4: 1 traversal, 1 occ

    # D (intermediate for T4 A1->D4):
    #   T4: 1 traversal, 1 occ

    hub_map = {h["station_code"]: h for h in hubs}

    assert hub_map["B"]["traversal_instance_count"] == 4
    assert hub_map["B"]["occurrence_count"] == 5
    assert hub_map["B"]["station_name"] == "Name B"

    assert hub_map["S"]["traversal_instance_count"] == 1
    assert hub_map["S"]["occurrence_count"] == 2

    assert hub_map["C"]["traversal_instance_count"] == 1
    assert hub_map["C"]["occurrence_count"] == 1

    assert hub_map["X"]["traversal_instance_count"] == 1
    assert hub_map["X"]["occurrence_count"] == 1

    assert hub_map["A"]["traversal_instance_count"] == 1
    assert hub_map["A"]["occurrence_count"] == 1

    assert hub_map["D"]["traversal_instance_count"] == 1
    assert hub_map["D"]["occurrence_count"] == 1

    # Check ordering
    # B (4, 5) -> 1st
    # S (1, 2) -> 2nd
    # A (1, 1), C (1, 1), D (1, 1), X (1, 1), Y (1, 1) -> alphabetically
    assert hubs[0]["station_code"] == "B"
    assert hubs[1]["station_code"] == "S"
    assert hubs[2]["station_code"] == "A"
    assert hubs[3]["station_code"] == "C"
    assert hubs[4]["station_code"] == "D"
    assert hubs[5]["station_code"] == "X"
    assert hubs[6]["station_code"] == "Y"

def test_hub_concentration_zero_case(db_session: Session, hub_concentration_fixtures: typing.Any) -> None:
    res = calculate_station_pair_intermediate_hubs(db_session, "Y", "C")
    assert res["total_traversal_instances"] == 0
    assert len(res["intermediate_hubs"]) == 0

def test_hub_concentration_missing_station(db_session: Session, hub_concentration_fixtures: typing.Any) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_station_pair_intermediate_hubs(db_session, "UNKNOWN", "A")
