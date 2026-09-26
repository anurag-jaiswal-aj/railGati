"""Destinations API endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from railgati.api.v1.schemas import DestinationItem, DestinationResponse
from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
from railgati.db import get_db
from railgati.models.station import Station
from railgati.services.destination import find_direct_destinations

router = APIRouter(prefix="/destinations", tags=["Destinations"])


@router.get(
    "",
    response_model=DestinationResponse,
    summary="Discover reachable direct destinations",
    description=(
        "Returns canonical destination stations reachable via direct historical train routes from "
        "the requested origin based on the active static timetable snapshot. This does not "
        "represent live connectivity or currently operating services."
    ),
)
def get_destinations(
    origin: Annotated[
        str,
        Query(
            description="Canonical origin station code.",
            min_length=1,
            max_length=50,
        ),
    ],
    max_duration_minutes: Annotated[
        int | None,
        Query(
            description="Maximum historical travel duration in minutes.",
            ge=0,
        ),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number for pagination")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Number of results per page")] = 50,
    db: Session = Depends(get_db),  # noqa: B008
) -> DestinationResponse:
    """Discover valid destinations from an origin station."""
    # 1. Resolve Origin Station
    origin_station = db.scalar(select(Station).filter(func.lower(Station.code) == origin.lower()))
    if not origin_station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Origin station '{origin.upper()}' not found.",
        )

    # 2. Get Active Timetable Snapshot
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    # 3. Call the Discovery Service
    service_results = find_direct_destinations(
        db=db,
        timetable_snapshot_id=timetable_snapshot_id,
        origin_station_id=origin_station.id,
        max_duration_minutes=max_duration_minutes,
    )

    total = len(service_results)

    # 4. Paginate Results
    start_idx = (page - 1) * size
    end_idx = start_idx + size
    paginated_results = service_results[start_idx:end_idx]

    # 5. Resolve Station Names safely via API layer
    station_names: dict[int, str] = {}
    if paginated_results:
        # Get active station snapshot
        from railgati.api.v1.snapshots import get_active_station_snapshot_id
        from railgati.models.station import StationObservation

        station_snapshot_id = get_active_station_snapshot_id(db)

        # Collect target station IDs for the paginated slice
        dest_station_ids = [res.station_id for res in paginated_results]

        # Batch lookup station names within the active station snapshot
        observations = db.execute(
            select(StationObservation.station_id, StationObservation.name).filter(
                StationObservation.snapshot_id == station_snapshot_id,
                StationObservation.station_id.in_(dest_station_ids),
            )
        ).all()

        station_names = {obs.station_id: obs.name for obs in observations}

    # 6. Map to Response Schema
    items = [
        DestinationItem(
            station_code=res.station_code,
            station_name=station_names.get(res.station_id),
            fastest_duration_minutes=res.fastest_duration_minutes,
            direct_train_count=res.direct_trains_count,
            timing_confidence=res.timing_confidence,
        )
        for res in paginated_results
    ]

    return DestinationResponse(
        origin=origin_station.code,
        timetable_snapshot_id=timetable_snapshot_id,
        max_duration_minutes=max_duration_minutes,
        total=total,
        page=page,
        size=size,
        destinations=items,
    )
