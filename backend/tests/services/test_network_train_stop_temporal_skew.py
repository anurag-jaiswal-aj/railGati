import pytest
import typing
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation
from railgati.services.network import calculate_train_stop_temporal_skew

def setup_data(db_session: Session) -> dict[str, typing.Any]:
    source = DataSource(name="test_srv_p54", url="http://test", publisher="test", license="test")
    db_session.add(source)
    db_session.flush()

    db_session.add(DatasetSnapshot(id=1, source_id=source.id, status="ACTIVE"))

    s1 = Station(code="S1")
    s2 = Station(code="S2")
    s3 = Station(code="S3")
    s4 = Station(code="S4")
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    db_session.add_all([
        StationObservation(snapshot_id=1, station_id=s1.id, name="S1"),
        StationObservation(snapshot_id=1, station_id=s2.id, name="S2"),
        StationObservation(snapshot_id=1, station_id=s3.id, name="S3"),
        StationObservation(snapshot_id=1, station_id=s4.id, name="S4"),
    ])

    t_cross = Train(number="CROSS")
    db_session.add(t_cross)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t_cross.id, name="Cross"))

    # Midnight crossover: starts at 23:00 Day 1, ends at 09:00 Day 1 (which means next day relative)
    # T_start = 23:00 (1380 mins). T_end = 09:00 next day (1440 + 540 = 1980 mins). Total T = 600 mins (10h).
    # Stop 1 at 00:00 (1440 mins). Offset = 1440 - 1380 = 60 mins (1h). Fraction = 0.1
    # Stop 2 at 01:00 (1500 mins). Offset = 1500 - 1380 = 120 mins (2h). Fraction = 0.2
    # Mean = 0.15. Skew = -0.35 (FRONT LOADED)
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t_cross.id, station_id=s1.id, stop_sequence=1, arrival_time=None, departure_time="23:00:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t_cross.id, station_id=s2.id, stop_sequence=2, arrival_time="23:50:00", departure_time="00:10:00", source_day=1), # mid=00:00
        TrainStopObservation(snapshot_id=1, train_id=t_cross.id, station_id=s3.id, stop_sequence=3, arrival_time="00:50:00", departure_time="01:10:00", source_day=1), # mid=01:00
        TrainStopObservation(snapshot_id=1, train_id=t_cross.id, station_id=s4.id, stop_sequence=4, arrival_time="09:00:00", departure_time=None, source_day=1),
    ])

    t_bal = Train(number="BAL1")
    db_session.add(t_bal)
    db_session.flush()
    db_session.add(TrainObservation(snapshot_id=1, train_id=t_bal.id, name="Bal"))
    
    # Balanced case: 0 to 10h. Stops at 4h, 5h, 6h. Mean fraction = 0.5. Skew = 0.
    db_session.add_all([
        TrainStopObservation(snapshot_id=1, train_id=t_bal.id, station_id=s1.id, stop_sequence=1, arrival_time=None, departure_time="00:00:00", source_day=1),
        TrainStopObservation(snapshot_id=1, train_id=t_bal.id, station_id=s2.id, stop_sequence=2, arrival_time="04:00:00", departure_time="04:00:00", source_day=1), 
        TrainStopObservation(snapshot_id=1, train_id=t_bal.id, station_id=s3.id, stop_sequence=3, arrival_time="05:00:00", departure_time="05:00:00", source_day=1), 
        TrainStopObservation(snapshot_id=1, train_id=t_bal.id, station_id=s2.id, stop_sequence=4, arrival_time="06:00:00", departure_time="06:00:00", source_day=1), # cyclic stop
        TrainStopObservation(snapshot_id=1, train_id=t_bal.id, station_id=s4.id, stop_sequence=5, arrival_time="10:00:00", departure_time=None, source_day=1),
    ])

    db_session.commit()
    return {}

def test_service_midnight_crossover(db_session: Session) -> None:
    setup_data(db_session)
    res = calculate_train_stop_temporal_skew(db_session, 1, "CROSS")
    assert res["train_number"] == "CROSS"
    assert res["intermediate_stop_occurrence_count"] == 2
    assert res["valid_intermediate_timing_occurrence_count"] == 2
    assert res["classification"] == "FRONT_LOADED"
    assert res["mean_fraction"] == pytest.approx(0.15)
    assert res["temporal_skew"] == pytest.approx(-0.35)

def test_service_balanced_cyclic(db_session: Session) -> None:
    setup_data(db_session)
    res = calculate_train_stop_temporal_skew(db_session, 1, "BAL1")
    assert res["classification"] == "BALANCED"
    assert res["temporal_skew"] == 0.0
    assert res["intermediate_stop_occurrence_count"] == 3
