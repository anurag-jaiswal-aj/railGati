import pytest
from sqlalchemy.orm import Session

from railgati.models.station import Station, StationObservation
from railgati.models.train import TrainStopObservation
from railgati.services.network import calculate_edge_route_co_traversal_affinity


def setup_mock_data(db_session: Session, snapshot_id: int) -> None:
    # stations: A, B, C, D
    db_session.execute(
        Station.__table__.insert(),
        [
            {"id": 1, "code": "AAA", "zone": "NR"},
            {"id": 2, "code": "BBB", "zone": "NR"},
            {"id": 3, "code": "CCC", "zone": "NR"},
            {"id": 4, "code": "DDD", "zone": "NR"},
        ],
    )
    db_session.execute(
        StationObservation.__table__.insert(),
        [
            {"station_id": 1, "snapshot_id": snapshot_id, "name": "A", "latitude": 0, "longitude": 0, "state_id": 1},
            {"station_id": 2, "snapshot_id": snapshot_id, "name": "B", "latitude": 0, "longitude": 0, "state_id": 1},
            {"station_id": 3, "snapshot_id": snapshot_id, "name": "C", "latitude": 0, "longitude": 0, "state_id": 1},
            {"station_id": 4, "snapshot_id": snapshot_id, "name": "D", "latitude": 0, "longitude": 0, "state_id": 1},
        ],
    )

    # Trains
    # Train 100: AAA -> BBB -> CCC -> DDD
    # Train 101: AAA -> BBB -> CCC -> DDD
    # Train 102: AAA -> BBB (stops)
    # Train 103: (starts) CCC -> DDD
    # Train 104: AAA -> BBB -> AAA -> BBB (loop) -> CCC -> DDD

    stops = []
    # Train 100
    stops.extend([
        {"train_id": 100, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 1},
        {"train_id": 100, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 2},
        {"train_id": 100, "snapshot_id": snapshot_id, "station_id": 3, "stop_sequence": 3},
        {"train_id": 100, "snapshot_id": snapshot_id, "station_id": 4, "stop_sequence": 4},
    ])

    # Train 101
    stops.extend([
        {"train_id": 101, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 1},
        {"train_id": 101, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 2},
        {"train_id": 101, "snapshot_id": snapshot_id, "station_id": 3, "stop_sequence": 3},
        {"train_id": 101, "snapshot_id": snapshot_id, "station_id": 4, "stop_sequence": 4},
    ])

    # Train 102
    stops.extend([
        {"train_id": 102, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 1},
        {"train_id": 102, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 2},
    ])

    # Train 103 (does not traverse A->B)
    stops.extend([
        {"train_id": 103, "snapshot_id": snapshot_id, "station_id": 3, "stop_sequence": 1},
        {"train_id": 103, "snapshot_id": snapshot_id, "station_id": 4, "stop_sequence": 2},
    ])

    # Train 104 (looping A->B)
    stops.extend([
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 1},
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 2},
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 3},
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 4},
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 3, "stop_sequence": 5},
        {"train_id": 104, "snapshot_id": snapshot_id, "station_id": 4, "stop_sequence": 6},
    ])

    db_session.execute(TrainStopObservation.__table__.insert(), stops)
    db_session.commit()

def test_service_edge_route_co_traversal_affinity(db_session: Session) -> None:
    snapshot_id = 1
    setup_mock_data(db_session, snapshot_id)

    # Target: AAA -> BBB
    # Traversing trains: 100, 101, 102, 104 (4 distinct trains)
    # T(E) = {100, 101, 102, 104}
    # Other edges:
    # BBB -> CCC: traversed by 100, 101, 104. |T(E) ∩ T(BBB->CCC)| = 3
    # CCC -> DDD: traversed by 100, 101, 103, 104. |T(E) ∩ T(CCC->DDD)| = 3 (103 is not in T(E))
    # BBB -> AAA: traversed by 104. |T(E) ∩ T(BBB->AAA)| = 1

    result = calculate_edge_route_co_traversal_affinity(db_session, snapshot_id, "AAA", "BBB")

    assert result["from_station_code"] == "AAA"
    assert result["to_station_code"] == "BBB"
    assert result["timetable_snapshot_id"] == snapshot_id
    assert result["traversing_train_count"] == 4

    edges = result["shared_edges"]
    assert len(edges) == 3

    # Sort order: shared_train_count DESC, from ASC, to ASC
    # 1. BBB -> CCC (3)
    # 2. CCC -> DDD (3)
    # 3. BBB -> AAA (1)

    assert edges[0]["from_station_code"] == "BBB"
    assert edges[0]["to_station_code"] == "CCC"
    assert edges[0]["shared_train_count"] == 3

    assert edges[1]["from_station_code"] == "CCC"
    assert edges[1]["to_station_code"] == "DDD"
    assert edges[1]["shared_train_count"] == 3

    assert edges[2]["from_station_code"] == "BBB"
    assert edges[2]["to_station_code"] == "AAA"
    assert edges[2]["shared_train_count"] == 1


def test_service_edge_route_co_traversal_affinity_not_found(db_session: Session) -> None:
    setup_mock_data(db_session, 1)

    with pytest.raises(ValueError, match="Station not found"):
        calculate_edge_route_co_traversal_affinity(db_session, 1, "XXX", "BBB")

    with pytest.raises(ValueError, match="Directed edge not found"):
        calculate_edge_route_co_traversal_affinity(db_session, 1, "AAA", "CCC")

def test_service_edge_route_co_traversal_affinity_no_limit(db_session: Session) -> None:
    snapshot_id = 2

    # 62 stations: A, B, and S1..S60
    stations = [
        {"id": 1, "code": "AAA", "zone": "NR"},
        {"id": 2, "code": "BBB", "zone": "NR"},
    ]
    for i in range(1, 61):
        stations.append({"id": i+2, "code": f"S{i:02d}", "zone": "NR"})

    db_session.execute(Station.__table__.insert(), stations)

    station_obs = []
    for st in stations:
        station_obs.append({
            "station_id": st["id"], "snapshot_id": snapshot_id, "name": st["code"],
            "latitude": 0, "longitude": 0, "state_id": 1
        })
    db_session.execute(StationObservation.__table__.insert(), station_obs)

    # Train 200: AAA -> BBB -> S1 -> S2 -> ... -> S60
    stops = [
        {"train_id": 200, "snapshot_id": snapshot_id, "station_id": 1, "stop_sequence": 1},
        {"train_id": 200, "snapshot_id": snapshot_id, "station_id": 2, "stop_sequence": 2},
    ]
    for i in range(1, 61):
        stops.append({
            "train_id": 200,
            "snapshot_id": snapshot_id,
            "station_id": i+2,
            "stop_sequence": i+2
        })

    db_session.execute(TrainStopObservation.__table__.insert(), stops)
    db_session.commit()

    result = calculate_edge_route_co_traversal_affinity(db_session, snapshot_id, "AAA", "BBB")

    edges = result["shared_edges"]
    assert len(edges) == 60  # > 50 proving no arbitrary truncation

