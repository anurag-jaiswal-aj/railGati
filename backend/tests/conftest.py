"""Pytest configuration and fixtures."""

import typing
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from railgati.db import get_db
from railgati.main import app
from railgati.models import Base
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provides a clean in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=sqlalchemy.pool.StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provides a TestClient with overridden DB dependency."""

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def populated_db(db_session: Session) -> Session:
    """Provides a database populated with test data."""
    # 1. Source
    source = DataSource(
        name="Test Source",
        publisher="Test Publisher",
        url="http://test.com",
        license="Test",
    )
    db_session.add(source)
    db_session.commit()

    # 2. Snapshot
    snapshot = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime.now(UTC),
        record_count=3,
        status="ACTIVE",
    )
    db_session.add(snapshot)
    db_session.commit()

    # 3. Stations and Observations
    # Station 1: Exact code match candidate
    s1 = Station(code="NDLS")
    db_session.add(s1)
    db_session.commit()
    obs1 = StationObservation(
        snapshot_id=snapshot.id,
        station_id=s1.id,
        name="New Delhi",
        state="Delhi",
        zone="NR",
        latitude=28.642,
        longitude=77.220,
    )
    db_session.add(obs1)

    # Station 2: Prefix code match candidate
    s2 = Station(code="NDLSP")
    db_session.add(s2)
    db_session.commit()
    obs2 = StationObservation(
        snapshot_id=snapshot.id,
        station_id=s2.id,
        name="New Delhi South",
        state="Delhi",
        zone="NR",
    )
    db_session.add(obs2)

    # Station 3: Exact name match candidate
    s3 = Station(code="BCT")
    db_session.add(s3)
    db_session.commit()
    obs3 = StationObservation(
        snapshot_id=snapshot.id,
        station_id=s3.id,
        name="Mumbai Central",
        state="Maharashtra",
        zone="WR",
    )
    db_session.add(obs3)

    # Add a FAILED snapshot with a different station to ensure we don't return it
    failed_snapshot = DatasetSnapshot(
        source_id=source.id,
        retrieved_at=datetime.now(UTC),
        record_count=1,
        status="FAILED",
    )
    db_session.add(failed_snapshot)
    db_session.commit()

    s4 = Station(code="FAIL")
    db_session.add(s4)
    db_session.commit()
    obs4 = StationObservation(
        snapshot_id=failed_snapshot.id,
        station_id=s4.id,
        name="Failed Station",
    )
    db_session.add(obs4)

    db_session.commit()
    return db_session


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

        db_session.add(
            TrainObservation(snapshot_id=snap_id, train_id=tr.id, name=t_num, type="EXP")
        )
        for idx, scode in enumerate(seq):
            db_session.add(
                TrainStopObservation(
                    snapshot_id=snap_id,
                    train_id=tr.id,
                    station_id=stations[scode].id,
                    stop_sequence=idx + 1,
                )
            )
    db_session.commit()

    return {"snapshot_id": snap_id, "stations": stations}
