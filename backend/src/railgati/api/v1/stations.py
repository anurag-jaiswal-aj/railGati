"""Stations API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from railgati.api.v1.schemas import (
    PaginatedResponse,
    ProvenanceInfo,
    StationDetail,
    StationSearchItem,
    TrainSearchItem,
)
from railgati.api.v1.snapshots import get_active_station_snapshot_id
from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
from railgati.db import get_db
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation

router = APIRouter(prefix="/stations", tags=["Stations"])


@router.get("/search", response_model=PaginatedResponse[StationSearchItem])
def search_stations(
    q: Annotated[str, Query(min_length=1, max_length=50, description="Search query")],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),  # noqa: B008
) -> PaginatedResponse[StationSearchItem]:
    """Search for railway stations by code or name."""
    snapshot_id = get_active_station_snapshot_id(db)

    query = (
        select(StationObservation, Station.code)
        .join(Station, Station.id == StationObservation.station_id)
        .filter(StationObservation.snapshot_id == snapshot_id)
    )

    search_term = f"%{q.lower()}%"

    # Simple deterministic search: ILIKE on code or name
    query = query.filter(
        or_(
            func.lower(Station.code).like(search_term),
            func.lower(StationObservation.name).like(search_term),
        )
    )

    # Sorting: exact code first, then prefix, then exact name, then alphabetical
    query = query.order_by(
        (func.lower(Station.code) == q.lower()).desc(),
        func.lower(Station.code).startswith(q.lower()).desc(),
        (func.lower(StationObservation.name) == q.lower()).desc(),
        StationObservation.name.asc(),
    )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    results = db.execute(query).all()

    items = [
        StationSearchItem(
            code=code,
            name=obs.name,
            state=obs.state,
            zone=obs.zone,
            latitude=obs.latitude,
            longitude=obs.longitude,
        )
        for obs, code in results
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        size=size,
    )


@router.get("/{station_code}", response_model=StationDetail)
def get_station_detail(
    station_code: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> StationDetail:
    """Get canonical details for a specific station."""
    snapshot_id = get_active_station_snapshot_id(db)

    query = (
        select(StationObservation, Station, DatasetSnapshot, DataSource)
        .join(Station, Station.id == StationObservation.station_id)
        .join(DatasetSnapshot, DatasetSnapshot.id == StationObservation.snapshot_id)
        .join(DataSource, DataSource.id == DatasetSnapshot.source_id)
        .filter(
            StationObservation.snapshot_id == snapshot_id,
            func.lower(Station.code) == station_code.lower(),
        )
    )

    result = db.execute(query).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{station_code.upper()}' not found.",
        )

    obs, station, snapshot, source = result

    return StationDetail(
        id=station.id,
        code=station.code,
        name=obs.name,
        state=obs.state,
        zone=obs.zone,
        latitude=obs.latitude,
        longitude=obs.longitude,
        provenance=ProvenanceInfo(
            snapshot_id=snapshot.id,
            source_name=source.name,
            retrieved_at=snapshot.retrieved_at,
        ),
    )


@router.get("/{station_code}/trains", response_model=PaginatedResponse[TrainSearchItem])
def get_station_trains(
    station_code: str,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),  # noqa: B008
) -> PaginatedResponse[TrainSearchItem]:
    """Return historical trains serving a station in the latest ACTIVE timetable snapshot."""
    # Ensure station code exists
    station = db.execute(
        select(Station).filter(func.lower(Station.code) == station_code.lower())
    ).first()
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station '{station_code.upper()}' not found.",
        )

    snapshot_id = get_active_timetable_snapshot_id(db)

    # Use distinct to avoid duplicates if a train theoretically visits a station multiple times
    query = (
        select(TrainObservation, Train.number)
        .join(Train, Train.id == TrainObservation.train_id)
        .join(TrainStopObservation, TrainStopObservation.train_id == Train.id)
        .filter(
            TrainStopObservation.snapshot_id == snapshot_id,
            TrainObservation.snapshot_id == snapshot_id,
            TrainStopObservation.station_id == station[0].id,
        )
        .distinct()
        .order_by(Train.number.asc())
    )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    results = db.execute(query).all()

    items = [
        TrainSearchItem(
            train_number=train_num,
            name=obs.name,
            type=obs.type,
            return_train_number=obs.return_train_number,
        )
        for obs, train_num in results
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        size=size,
    )
