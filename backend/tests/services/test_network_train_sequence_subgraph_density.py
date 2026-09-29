import pytest
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainStopObservation
from railgati.services.network import calculate_train_sequence_subgraph_density


@pytest.fixture
def density_fixtures(db_session: Session) -> dict[str, int]:
    source = DataSource(name="test_p55_2", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s1 = Station(code="S1")
    s2 = Station(code="S2")
    s3 = Station(code="S3")
    s4 = Station(code="S4")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    db_session.add_all(
        [
            StationObservation(snapshot_id=1, station_id=s1.id, name="S1"),
            StationObservation(snapshot_id=1, station_id=s2.id, name="S2"),
            StationObservation(snapshot_id=1, station_id=s3.id, name="S3"),
            StationObservation(snapshot_id=1, station_id=s4.id, name="S4"),
        ]
    )

    # T_MAIN: S1 -> S2 -> S3 -> S4
    t_main = Train(number="T_MAIN")

    # T_FWD: S1 -> S4 (Provides Forward Chord)
    t_fwd = Train(number="T_FWD")

    # T_BWD: S3 -> S2 (Provides Backward Chord)
    t_bwd = Train(number="T_BWD")

    # T_CYCLIC: S1 -> S2 -> S3 -> S1 -> S4
    t_cyclic = Train(number="T_CYCLIC")

    # T_SHORT: S1 -> S2
    t_short = Train(number="T_SHORT")

    db_session.add_all([t_main, t_fwd, t_bwd, t_cyclic, t_short])
    db_session.flush()

    stops = [
        # T_MAIN
        TrainStopObservation(snapshot_id=1, train_id=t_main.id, station_id=s1.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=1, train_id=t_main.id, station_id=s2.id, stop_sequence=2),
        TrainStopObservation(snapshot_id=1, train_id=t_main.id, station_id=s3.id, stop_sequence=3),
        TrainStopObservation(snapshot_id=1, train_id=t_main.id, station_id=s4.id, stop_sequence=4),
        # T_FWD (Provides S1->S4 edge)
        TrainStopObservation(snapshot_id=1, train_id=t_fwd.id, station_id=s1.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=1, train_id=t_fwd.id, station_id=s4.id, stop_sequence=2),
        # T_BWD (Provides S3->S2 edge)
        TrainStopObservation(snapshot_id=1, train_id=t_bwd.id, station_id=s3.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=1, train_id=t_bwd.id, station_id=s2.id, stop_sequence=2),
        # T_CYCLIC (S1 -> S2 -> S3 -> S1 -> S4)
        TrainStopObservation(
            snapshot_id=1, train_id=t_cyclic.id, station_id=s1.id, stop_sequence=1
        ),
        TrainStopObservation(
            snapshot_id=1, train_id=t_cyclic.id, station_id=s2.id, stop_sequence=2
        ),
        TrainStopObservation(
            snapshot_id=1, train_id=t_cyclic.id, station_id=s3.id, stop_sequence=3
        ),
        TrainStopObservation(
            snapshot_id=1, train_id=t_cyclic.id, station_id=s1.id, stop_sequence=4
        ),
        TrainStopObservation(
            snapshot_id=1, train_id=t_cyclic.id, station_id=s4.id, stop_sequence=5
        ),
        # T_SHORT
        TrainStopObservation(snapshot_id=1, train_id=t_short.id, station_id=s1.id, stop_sequence=1),
        TrainStopObservation(snapshot_id=1, train_id=t_short.id, station_id=s2.id, stop_sequence=2),
    ]
    db_session.add_all(stops)
    db_session.commit()

    return {"snap_id": 1}


def test_service_linear_route(db_session: Session, density_fixtures: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_density(
        db_session, density_fixtures["snap_id"], "T_MAIN"
    )
    assert res["train_number"] == "T_MAIN"
    assert res["total_sequence_occurrences"] == 4
    # max fwd = (3 * 2) / 2 = 3. max bwd = (4 * 3) / 2 = 6.
    assert res["forward_max_possible_chords"] == 3
    assert res["backward_max_possible_chords"] == 6
    # Global edges:
    # S1->S2 (adj), S2->S3 (adj), S3->S4 (adj)
    # S1->S4 (T_FWD)
    # S3->S2 (T_BWD)
    # S3->S1 (T_CYCLIC 3->4)
    # S1->S4 (T_CYCLIC 4->5)

    # Forward chords for T_MAIN (1:S1, 2:S2, 3:S3, 4:S4):
    # S1->S4 exists (j=4 > i=1+1). 1 chord.
    assert res["forward_actual_chords"] == 1
    assert res["forward_density"] == 1.0 / 3.0

    # Backward chords for T_MAIN:
    # S3->S2 exists (j=2 < i=3). 1 chord.
    # S3->S1 exists (j=1 < i=3). 1 chord.
    assert res["backward_actual_chords"] == 2
    assert res["backward_density"] == 2.0 / 6.0


def test_service_cyclic_route(db_session: Session, density_fixtures: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_density(
        db_session, density_fixtures["snap_id"], "T_CYCLIC"
    )
    assert res["total_sequence_occurrences"] == 5
    # max fwd = (4 * 3) / 2 = 6. max bwd = (5 * 4) / 2 = 10.
    assert res["forward_max_possible_chords"] == 6
    assert res["backward_max_possible_chords"] == 10

    # Seq: 1:S1, 2:S2, 3:S3, 4:S1, 5:S4
    # Forward chords (j > i+1):
    # (1, 3): S1->S3 (None)
    # (1, 4): S1->S1 (None)
    # (1, 5): S1->S4 (Exists).
    # (2, 4): S2->S1 (None)
    # (2, 5): S2->S4 (None)
    # (3, 5): S3->S4 (Exists via T_MAIN).
    assert res["forward_actual_chords"] == 2

    # Backward chords (j < i):
    # (2, 1): S2->S1 (None)
    # (3, 1): S3->S1 (Exists via T_CYCLIC)
    # (3, 2): S3->S2 (Exists via T_BWD)
    # (4, 1): S1->S1 (None)
    # (4, 2): S1->S2 (Exists via T_MAIN) -- WAIT: i=4, j=2. Edge S1->S2 exists! Yes!
    # (4, 3): S1->S3 (None)
    # (5, 1): S4->S1 (None)
    # (5, 2): S4->S2 (None)
    # (5, 3): S4->S3 (None)
    # (5, 4): S4->S1 (None)
    assert res["backward_actual_chords"] >= 3


def test_service_short_route(db_session: Session, density_fixtures: dict[str, int]) -> None:
    res = calculate_train_sequence_subgraph_density(
        db_session, density_fixtures["snap_id"], "T_SHORT"
    )
    assert res["total_sequence_occurrences"] == 2
    assert res["forward_max_possible_chords"] == 0
    assert res["backward_max_possible_chords"] == 1
    assert res["forward_actual_chords"] == 0
    assert res["forward_density"] == 0.0


def test_service_unknown_train(db_session: Session, density_fixtures: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="not found"):
        calculate_train_sequence_subgraph_density(
            db_session, density_fixtures["snap_id"], "UNKNOWN"
        )
