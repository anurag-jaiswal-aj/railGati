"""Network reachability API endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from railgati.api.v1.schemas import NetworkReachabilityItem, NetworkReachabilityResponse
from railgati.api.v1.snapshots import (
    get_active_station_snapshot_id,
    get_active_timetable_snapshot_id,
)
from railgati.db import get_db
from railgati.models.station import Station, StationObservation
from railgati.services.network import find_reachable_stations

router = APIRouter(prefix="/network", tags=["Network"])


@router.get(
    "/reachable",
    response_model=NetworkReachabilityResponse,
    summary="Discover bounded network reachability",
    description=(
        "Returns the topological subgraph reachable within max_hops from the origin "
        "using the currently active historical graph. This does not represent passenger "
        "routing, live timings, or viable travel itineraries."
    ),
)
def get_reachable_stations(
    origin: Annotated[
        str,
        Query(
            description="Canonical origin station code.",
            min_length=1,
            max_length=50,
        ),
    ],
    max_hops: Annotated[
        int,
        Query(
            description="Maximum network traversal depth.",
            ge=1,
            le=10,
        ),
    ] = 3,
    db: Session = Depends(get_db),  # noqa: B008
) -> NetworkReachabilityResponse:
    """Discover reachable stations from an origin."""
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
    try:
        service_results = find_reachable_stations(
            db=db,
            origin_station_id=origin_station.id,
            max_hops=max_hops,
            timetable_snapshot_id=timetable_snapshot_id,
        )
    except ValueError as e:
        # Phase 2A raises ValueError if build is missing, PENDING, or FAILED.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e

    # 4. Resolve Station Names safely via API layer
    station_meta: dict[int, tuple[str, str | None]] = {}
    if service_results:
        # Get active station snapshot
        station_snapshot_id = get_active_station_snapshot_id(db)

        # Collect target station IDs
        dest_station_ids = [res.station_id for res in service_results]

        # Batch lookup station codes and names within the active station snapshot
        observations = db.execute(
            select(Station.id, Station.code, StationObservation.name)
            .outerjoin(
                StationObservation,
                (Station.id == StationObservation.station_id)
                & (StationObservation.snapshot_id == station_snapshot_id),
            )
            .filter(Station.id.in_(dest_station_ids))
        ).all()

        station_meta = {row.id: (row.code, row.name) for row in observations}

    # 5. Map to Response Schema
    items = [
        NetworkReachabilityItem(
            station_code=station_meta[res.station_id][0],
            station_name=station_meta[res.station_id][1],
            min_hops=res.min_hops,
        )
        for res in service_results
    ]

    return NetworkReachabilityResponse(
        origin=origin_station.code,
        timetable_snapshot_id=timetable_snapshot_id,
        max_hops=max_hops,
        total=len(items),
        stations=items,
    )
