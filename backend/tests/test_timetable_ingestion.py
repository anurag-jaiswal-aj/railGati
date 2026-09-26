"""Tests for the timetable ingestion pipeline."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy.orm import Session

from railgati.ingestion.datameet import DatameetParser
from railgati.ingestion.pipeline import Pipeline
from railgati.ingestion.schema import ParsedTrain
from railgati.ingestion.timetable_pipeline import TimetablePipeline
from railgati.models.provenance import DatasetSnapshot
from railgati.models.train import Train, TrainObservation, TrainStopObservation


def test_timetable_parser() -> None:
    """Test parsing the raw timetable JSON fixtures."""
    trains_fixture = Path(__file__).parent / "fixtures" / "trains_test.json"
    schedules_fixture = Path(__file__).parent / "fixtures" / "schedules_test.json"

    trains_parser = DatameetParser(trains_fixture)
    trains = list(trains_parser.parse_trains())

    assert len(trains) == 4
    assert trains[0].number == "12101"
    assert trains[0].name == "MUMBAI LTT - HOWRAH Janeswari Super Deluxe Exp"
    assert trains[0].type == "SF"
    assert trains[0].return_train_number == "12102"

    # Missing number handling
    assert trains[3].number == ""

    schedules_parser = DatameetParser(schedules_fixture)
    schedules = list(schedules_parser.parse_schedules())

    assert len(schedules) == 4
    assert schedules[0].train_number == "12101"
    assert schedules[0].arrival_time is None
    assert schedules[0].departure_time == "20:35:00"
    assert schedules[0].day == 1

    # Missing day parsing
    assert schedules[3].day is None


def test_timetable_ingestion_success(db_session: Session) -> None:
    """Test successful timetable ingestion, validation, and snapshot creation."""
    # First ingest stations so that station matching succeeds
    stations_fixture = Path(__file__).parent / "fixtures" / "datameet_test.json"
    stations_parser = DatameetParser(stations_fixture)
    Pipeline(db_session, dry_run=False).run(str(stations_fixture), stations_parser.parse())

    trains_fixture = Path(__file__).parent / "fixtures" / "trains_test.json"
    schedules_fixture = Path(__file__).parent / "fixtures" / "schedules_test.json"

    trains_parser = DatameetParser(trains_fixture)
    schedules_parser = DatameetParser(schedules_fixture)

    pipeline = TimetablePipeline(db_session, dry_run=False)
    result = pipeline.run_timetable(
        str(trains_fixture),
        str(schedules_fixture),
        trains_parser.parse_trains(),
        schedules_parser.parse_schedules(),
    )

    assert result.status == "SUCCESS"

    # Trains: 4 parsed. 1 invalid (no number), 1 duplicate ("12101"), 2 valid.
    # Schedules: 4 parsed. 1 unknown station, 3 valid (but one is for 04601 and two for 12101).

    assert db_session.query(Train).count() == 2
    assert db_session.query(TrainObservation).count() == 2

    print("REJECTIONS:", result.rejections)

    assert db_session.query(TrainStopObservation).count() == 3

    snapshot = db_session.query(DatasetSnapshot).order_by(DatasetSnapshot.id.desc()).first()
    assert snapshot is not None
    assert snapshot.status == "ACTIVE"

    # Verify sequence order for train 12101
    train = db_session.query(Train).filter_by(number="12101").one()
    stops = (
        db_session.query(TrainStopObservation)
        .filter_by(train_id=train.id)
        .order_by(TrainStopObservation.stop_sequence)
        .all()
    )
    assert len(stops) == 2
    assert stops[0].stop_sequence == 1
    assert stops[0].station.code == "BDHL"
    assert stops[1].stop_sequence == 2
    assert stops[1].station.code == "CPM"

    # Verify rejections contain the unknown station code
    unknown_rejections = [r for r in result.rejections if r.get("station_code") == "UNKNOWN"]
    assert len(unknown_rejections) == 1
    assert "Unknown station code: UNKNOWN" in str(unknown_rejections[0]["reason"])


def test_timetable_ingestion_idempotency(db_session: Session) -> None:
    """Test that running ingestion twice does not create duplicate canonical entities."""
    stations_fixture = Path(__file__).parent / "fixtures" / "datameet_test.json"
    Pipeline(db_session, dry_run=False).run(
        str(stations_fixture), DatameetParser(stations_fixture).parse()
    )

    trains_fixture = Path(__file__).parent / "fixtures" / "trains_test.json"
    schedules_fixture = Path(__file__).parent / "fixtures" / "schedules_test.json"

    # Run 1
    pipeline1 = TimetablePipeline(db_session, dry_run=False)
    pipeline1.run_timetable(
        str(trains_fixture),
        str(schedules_fixture),
        DatameetParser(trains_fixture).parse_trains(),
        DatameetParser(schedules_fixture).parse_schedules(),
    )

    trains_count_1 = db_session.query(Train).count()
    assert trains_count_1 == 2

    # Run 2
    pipeline2 = TimetablePipeline(db_session, dry_run=False)
    pipeline2.run_timetable(
        str(trains_fixture),
        str(schedules_fixture),
        DatameetParser(trains_fixture).parse_trains(),
        DatameetParser(schedules_fixture).parse_schedules(),
    )

    trains_count_2 = db_session.query(Train).count()
    assert trains_count_2 == 2  # Canonical count should not change

    # But two distinct snapshots exist for timetables
    snapshots = db_session.query(DatasetSnapshot).all()
    timetable_snapshots = [s for s in snapshots if s.checksum and "_" in s.checksum]
    assert len(timetable_snapshots) == 2

    obs_1 = (
        db_session.query(TrainObservation).filter_by(snapshot_id=timetable_snapshots[0].id).count()
    )
    obs_2 = (
        db_session.query(TrainObservation).filter_by(snapshot_id=timetable_snapshots[1].id).count()
    )
    assert obs_1 == 2
    assert obs_2 == 2

    stops_1 = (
        db_session.query(TrainStopObservation)
        .filter_by(snapshot_id=timetable_snapshots[0].id)
        .count()
    )
    stops_2 = (
        db_session.query(TrainStopObservation)
        .filter_by(snapshot_id=timetable_snapshots[1].id)
        .count()
    )
    assert stops_1 == 3
    assert stops_2 == 3


def test_timetable_ingestion_failure_safety(db_session: Session) -> None:
    """Test that fatal errors rollback and leave canonical entities intact."""
    stations_fixture = Path(__file__).parent / "fixtures" / "datameet_test.json"
    Pipeline(db_session, dry_run=False).run(
        str(stations_fixture), DatameetParser(stations_fixture).parse()
    )

    trains_fixture = Path(__file__).parent / "fixtures" / "trains_test.json"
    schedules_fixture = Path(__file__).parent / "fixtures" / "schedules_test.json"

    # 1. Successful run
    pipeline1 = TimetablePipeline(db_session, dry_run=False)
    result1 = pipeline1.run_timetable(
        str(trains_fixture),
        str(schedules_fixture),
        DatameetParser(trains_fixture).parse_trains(),
        DatameetParser(schedules_fixture).parse_schedules(),
    )
    assert result1.status == "SUCCESS"

    snapshot_a_id = result1.snapshot_id
    assert snapshot_a_id is not None

    # 2. Failing run
    def bad_trains_parser() -> Generator[ParsedTrain, None, None]:
        yield ParsedTrain(source_index=0, number="99999", name="Bad Train")
        raise RuntimeError("Fake database or parsing error")

    pipeline2 = TimetablePipeline(db_session, dry_run=False)
    result2 = pipeline2.run_timetable(
        str(trains_fixture),
        str(schedules_fixture),
        bad_trains_parser(),
        DatameetParser(schedules_fixture).parse_schedules(),
    )

    assert result2.status == "FAILED"

    # 3. Verify Snapshot A is intact and ACTIVE
    snapshot_a = db_session.query(DatasetSnapshot).filter_by(id=snapshot_a_id).one()
    assert snapshot_a.status == "ACTIVE"

    obs_a = db_session.query(TrainObservation).filter_by(snapshot_id=snapshot_a_id).all()
    assert len(obs_a) == 2

    # 4. Verify canonical train 99999 was NOT persisted due to rollback
    bad_train = db_session.query(Train).filter_by(number="99999").one_or_none()
    assert bad_train is None

    # 5. Verify failed snapshot behavior
    failed_snapshots = db_session.query(DatasetSnapshot).filter_by(status="FAILED").all()
    assert len(failed_snapshots) == 1
    assert (
        failed_snapshots[0].error_message
        and "Fake database or parsing error" in failed_snapshots[0].error_message
    )
