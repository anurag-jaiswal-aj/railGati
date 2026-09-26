"""Tests for the ingestion pipeline."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy.orm import Session

from railgati.ingestion.datameet import DatameetParser
from railgati.ingestion.pipeline import Pipeline
from railgati.ingestion.schema import ParsedStation
from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station, StationObservation

# db_session fixture is now in conftest.py


def test_datameet_parser() -> None:
    """Test parsing the raw GeoJSON fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "datameet_test.json"
    parser = DatameetParser(fixture_path)
    stations = list(parser.parse())

    assert len(stations) == 5
    assert stations[0].code == "BDHL"
    assert stations[0].name == "Badhal"
    assert stations[0].latitude == 27.2520587
    assert stations[0].longitude == 75.4516454


def test_ingestion_pipeline_success(db_session: Session) -> None:
    """Test successful ingestion, validation, and snapshot creation."""
    fixture_path = Path(__file__).parent / "fixtures" / "datameet_test.json"
    parser = DatameetParser(fixture_path)
    pipeline = Pipeline(db_session, dry_run=False)

    result = pipeline.run(str(fixture_path), parser.parse())

    assert result.status == "SUCCESS"
    assert result.records_read == 5
    assert result.records_parsed == 5

    # 1 duplicate, 1 missing name, 1 invalid coords
    assert result.records_accepted == 2
    assert result.records_rejected == 3
    assert result.duplicates == 1
    assert result.missing_required_fields == 1
    assert result.invalid_coordinates == 1

    # Check DB
    stations = db_session.query(Station).all()
    assert len(stations) == 2
    observations = db_session.query(StationObservation).all()
    assert len(observations) == 2

    snapshot = db_session.query(DatasetSnapshot).first()
    assert snapshot is not None
    assert snapshot.status == "ACTIVE"
    assert snapshot.record_count == 2


def test_ingestion_idempotency(db_session: Session) -> None:
    """Test that running ingestion twice does not create duplicate stations."""
    fixture_path = Path(__file__).parent / "fixtures" / "datameet_test.json"

    # Run 1
    parser1 = DatameetParser(fixture_path)
    pipeline1 = Pipeline(db_session, dry_run=False)
    result1 = pipeline1.run(str(fixture_path), parser1.parse())
    assert result1.records_accepted == 2

    stations_count_1 = db_session.query(Station).count()
    assert stations_count_1 == 2

    # Run 2
    parser2 = DatameetParser(fixture_path)
    pipeline2 = Pipeline(db_session, dry_run=False)
    result2 = pipeline2.run(str(fixture_path), parser2.parse())

    assert result2.status == "SUCCESS"
    assert result2.records_accepted == 2  # New observations for new snapshot
    assert result2.duplicates == 1  # Only the intra-dataset duplicate

    # Explicit Snapshot Completeness verification
    snapshots = db_session.query(DatasetSnapshot).order_by(DatasetSnapshot.id).all()
    assert len(snapshots) == 2
    snapshot_a = snapshots[0]
    snapshot_b = snapshots[1]

    stations_count_2 = db_session.query(Station).count()
    assert stations_count_2 == 2  # Canonical count should not change

    obs_a = db_session.query(StationObservation).filter_by(snapshot_id=snapshot_a.id).all()
    obs_b = db_session.query(StationObservation).filter_by(snapshot_id=snapshot_b.id).all()

    assert len(obs_a) == 2
    assert len(obs_b) == 2

    # Verify both snapshots reference the same canonical stations
    obs_a_station_ids = {o.station_id for o in obs_a}
    obs_b_station_ids = {o.station_id for o in obs_b}
    assert obs_a_station_ids == obs_b_station_ids
    assert len(obs_a_station_ids) == 2


def test_ingestion_dry_run(db_session: Session) -> None:
    """Test that dry run does not commit anything."""
    fixture_path = Path(__file__).parent / "fixtures" / "datameet_test.json"
    parser = DatameetParser(fixture_path)
    pipeline = Pipeline(db_session, dry_run=True)

    result = pipeline.run(str(fixture_path), parser.parse())

    assert result.status == "DRY-RUN (Rolled back)"
    assert result.records_accepted == 2

    # Check DB
    stations = db_session.query(Station).all()
    assert len(stations) == 0


def test_ingestion_failure_safety(db_session: Session) -> None:
    """Test that fatal errors rollback and leave previous active snapshots intact."""
    fixture_path = Path(__file__).parent / "fixtures" / "datameet_test.json"

    # 1. Successful run
    parser1 = DatameetParser(fixture_path)
    pipeline1 = Pipeline(db_session, dry_run=False)
    result1 = pipeline1.run(str(fixture_path), parser1.parse())
    assert result1.status == "SUCCESS"

    snapshot_a_id = result1.snapshot_id
    assert snapshot_a_id is not None

    # 2. Failing run
    def bad_parser() -> Generator[ParsedStation, None, None]:
        yield from []
        raise RuntimeError("Fake database or parsing error")

    pipeline2 = Pipeline(db_session, dry_run=False)
    result2 = pipeline2.run(str(fixture_path), bad_parser())

    assert result2.status == "FAILED"

    # 3. Verify Snapshot A is intact and ACTIVE
    snapshot_a = db_session.query(DatasetSnapshot).filter_by(id=snapshot_a_id).one()
    assert snapshot_a.status == "ACTIVE"

    obs_a = db_session.query(StationObservation).filter_by(snapshot_id=snapshot_a_id).all()
    assert len(obs_a) == 2

    # 4. Verify Snapshot B is FAILED and has no observations
    snapshot_b_id = result2.snapshot_id
    if snapshot_b_id:
        # If the pipeline failed after creating the snapshot record but before the final try block
        # we expect the snapshot record was created, but then rolled back in the main try-except.
        # However, the exception handler explicitly inserts a FAILED snapshot!
        pass

    failed_snapshots = db_session.query(DatasetSnapshot).filter_by(status="FAILED").all()
    assert len(failed_snapshots) == 1
    snapshot_b = failed_snapshots[0]

    assert snapshot_b.error_message is not None
    assert "Fake database or parsing error" in snapshot_b.error_message

    obs_b = db_session.query(StationObservation).filter_by(snapshot_id=snapshot_b.id).all()
    assert len(obs_b) == 0


def test_ingestion_rejections(db_session: Session) -> None:
    """Test that rejections are populated with correct identifiers."""
    fixture_path = Path(__file__).parent / "fixtures" / "datameet_test.json"
    parser = DatameetParser(fixture_path)
    pipeline = Pipeline(db_session, dry_run=False)

    result = pipeline.run(str(fixture_path), parser.parse())
    assert result.status == "SUCCESS"

    # In datameet_test.json we have:
    # Index 2: duplicate of BDHL
    # Index 3: missing name (code=MISSINGNAME)
    # Index 4: invalid coords (code=INVCOORD)

    assert len(result.rejections) == 3

    # Sort rejections by source_index to assert deterministically
    rejections = sorted(result.rejections, key=lambda x: int(str(x["source_index"])))

    r_coords = rejections[0]
    assert r_coords["code"] == "INVCOORD"
    assert "Coordinates out of bounds" in str(r_coords["reason"])
    assert r_coords["source_index"] == 2

    r_missing = rejections[1]
    assert r_missing["code"] == "MISSINGNAME"
    assert "Missing required fields" in str(r_missing["reason"])
    assert r_missing["source_index"] == 3

    r_dup = rejections[2]
    assert r_dup["code"] == "BDHL"
    assert "Duplicate code in dataset" in str(r_dup["reason"])
    assert r_dup["source_index"] == 4

    # Verify snapshot_id is present
    assert r_coords["snapshot_id"] == result.snapshot_id
