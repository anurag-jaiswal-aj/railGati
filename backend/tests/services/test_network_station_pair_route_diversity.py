import typing

import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_station_pair_route_diversity


@pytest.fixture
def route_diversity_fixtures(db_session: Session) -> typing.Any:
    source = DataSource(name="test_source", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.commit()
    snap = DatasetSnapshot(status="ACTIVE", source_id=source.id)
    db_session.add(snap)
    db_session.commit()
    snap_id = snap.id

    # Create stations
    stations = {}
    for code in ["A", "B", "C", "D", "E", "F", "X", "Y"]:
        st = Station(code=code)
        db_session.add(st)
        stations[code] = st
    db_session.commit()

    # Create trains with diverse paths
    # Train 1: A -> B -> C -> D
    # Train 2: A -> B -> C -> D
    # Train 3: A -> X -> Y -> D
    # Train 4: A -> D (direct)
    # Train 5: A -> B -> A -> D (loop)

    paths = [
        ("T1", ["A", "B", "C", "D"]),
        ("T2", ["A", "B", "C", "D"]),
        ("T3", ["A", "X", "Y", "D"]),
        ("T4", ["A", "D"]),
        ("T5", ["A", "B", "A", "D"]),
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

def test_calculate_station_pair_route_diversity_success(db_session: Session, route_diversity_fixtures: typing.Any) -> None:
    res = calculate_station_pair_route_diversity(db_session, "A", "D")

    assert res["from_station_code"] == "A"
    assert res["to_station_code"] == "D"
    assert res["distinct_path_count"] == 4

    paths = res["paths"]
    assert len(paths) == 4

    # Should be sorted by traversal_count DESC, path_length DESC
    assert paths[0]["station_sequence"] == ["A", "B", "C", "D"]
    assert paths[0]["path_length"] == 4
    assert paths[0]["traversal_count"] == 2

    # Path 1 is A->D
    assert paths[1]["station_sequence"] == ["A", "D"]
    assert paths[1]["path_length"] == 2
    assert paths[1]["traversal_count"] == 2

    # Path 2 is A->B->A->D
    assert paths[2]["station_sequence"] == ["A", "B", "A", "D"]
    assert paths[2]["path_length"] == 4
    assert paths[2]["traversal_count"] == 1

    # Path 3 is A->X->Y->D
    assert paths[3]["station_sequence"] == ["A", "X", "Y", "D"]
    assert paths[3]["path_length"] == 4
    assert paths[3]["traversal_count"] == 1
