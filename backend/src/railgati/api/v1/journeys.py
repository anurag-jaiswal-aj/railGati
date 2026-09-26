"""Journeys API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from railgati.api.v1.schemas import JourneyCompareResponse
from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
from railgati.db import get_db
from railgati.models.station import Station
from railgati.services.journey import compare_journeys

router = APIRouter(prefix="/journeys", tags=["Journeys"])


@router.get("/compare", response_model=JourneyCompareResponse)
def compare_journeys_endpoint(
    source: str = Query(..., description="Canonical origin station code"),
    destination: str = Query(..., description="Canonical destination station code"),
    max_transfers: int = Query(0, ge=0, le=1, description="Maximum allowed transfers (0 or 1)"),
    min_transfer_minutes: int = Query(120, ge=0, description="Minimum transfer buffer in minutes"),
    max_layover_minutes: int = Query(1440, ge=0, description="Maximum layover time in minutes"),
    db: Session = Depends(get_db),  # noqa: B008
) -> JourneyCompareResponse:
    """Compare historical journeys between two stations.

    This endpoint searches the current historical timetable for valid routing paths.
    It does not provide live running status, date-specific guarantees, or fare/seat
    information.
    """
    if source.lower() == destination.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination stations cannot be the same.",
        )

    if min_transfer_minutes > max_layover_minutes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="min_transfer_minutes cannot be greater than max_layover_minutes.",
        )

    source_station = db.scalar(select(Station).filter(func.lower(Station.code) == source.lower()))
    if not source_station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{source.upper()}' not found.",
        )

    destination_station = db.scalar(
        select(Station).filter(func.lower(Station.code) == destination.lower())
    )
    if not destination_station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{destination.upper()}' not found.",
        )

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    options = compare_journeys(
        db=db,
        timetable_snapshot_id=timetable_snapshot_id,
        origin_station_id=source_station.id,
        destination_station_id=destination_station.id,
        max_transfers=max_transfers,
        minimum_transfer_minutes=min_transfer_minutes,
        maximum_layover_minutes=max_layover_minutes,
    )

    return JourneyCompareResponse(
        source=source_station.code,
        destination=destination_station.code,
        timetable_snapshot_id=timetable_snapshot_id,
        max_transfers=max_transfers,
        journeys=options,
    )
