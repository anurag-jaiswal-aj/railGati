"""Tests for the ingestion pipeline."""

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from railgati.ingestion.datameet import DatameetParser
from railgati.ingestion.pipeline import Pipeline
from railgati.ingestion.schema import ParsedStation
from railgati.models import Base
from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import Station


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provides a clean in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


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
    assert result2.records_accepted == 0  # all skipped as duplicates
    assert result2.duplicates == 3

    stations_count_2 = db_session.query(Station).count()
    assert stations_count_2 == 2  # Count should not change


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
    """Test that fatal pipeline errors rollback and record failure."""
    fixture_path = Path(__file__).parent / "fixtures" / "datameet_test.json"

    # Mock a parser that raises an exception
    def bad_parser() -> Generator[ParsedStation, None, None]:
        yield from []
        raise RuntimeError("Fake database or parsing error")

    pipeline = Pipeline(db_session, dry_run=False)
    result = pipeline.run(str(fixture_path), bad_parser())

    assert result.status == "FAILED"

    # Verify rollback
    stations = db_session.query(Station).all()
    assert len(stations) == 0

    # Verify failed snapshot was recorded
    snapshot = db_session.query(DatasetSnapshot).first()
    assert snapshot is not None
    assert snapshot.status == "FAILED"
    assert snapshot.error_message is not None
    assert "Fake database or parsing error" in snapshot.error_message
