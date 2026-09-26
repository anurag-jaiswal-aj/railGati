"""Snapshot retrieval helpers."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from railgati.models.provenance import DatasetSnapshot
from railgati.models.station import StationObservation
from railgati.models.train import TrainObservation


def get_active_station_snapshot_id(db: Session) -> int:
    """Helper to get the current active station snapshot ID.
    Raises 503 if no active snapshot exists.
    """
    snapshot_id = db.scalar(
        select(DatasetSnapshot.id)
        .filter(
            DatasetSnapshot.status == "ACTIVE",
            DatasetSnapshot.id.in_(select(StationObservation.snapshot_id))
        )
        .order_by(DatasetSnapshot.retrieved_at.desc())
        .limit(1)
    )
    if not snapshot_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Railway data is currently unavailable. No active snapshot found.",
        )
    return snapshot_id


def get_active_timetable_snapshot_id(db: Session) -> int:
    """Helper to get the current active timetable snapshot ID.
    Raises 503 if no active timetable snapshot exists.
    """
    snapshot_id = db.scalar(
        select(DatasetSnapshot.id)
        .filter(
            DatasetSnapshot.status == "ACTIVE",
            DatasetSnapshot.id.in_(select(TrainObservation.snapshot_id)),
        )
        .order_by(DatasetSnapshot.retrieved_at.desc())
        .limit(1)
    )
    if not snapshot_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Historical timetable data is currently unavailable. No active snapshot found.",
        )
    return snapshot_id
