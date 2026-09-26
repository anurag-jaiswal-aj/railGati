"""Trains API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from railgati.api.v1.schemas import (
    PaginatedResponse,
    ProvenanceInfo,
    TrainDetail,
    TrainSearchEmptyState,
    TrainSearchItem,
    TrainStopResponse,
)
from railgati.api.v1.snapshots import get_active_station_snapshot_id
from railgati.db import get_db
from railgati.models.provenance import DatasetSnapshot, DataSource
from railgati.models.station import Station, StationObservation
from railgati.models.train import Train, TrainObservation, TrainStopObservation

from railgati.api.v1.snapshots import get_active_timetable_snapshot_id

router = APIRouter(prefix="/trains", tags=["Trains"])


@router.get("/search", response_model=PaginatedResponse[TrainSearchItem])
def search_trains(
    db: Session = Depends(get_db),  # noqa: B008
    q: Annotated[str | None, Query(max_length=50, description="Search query")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[TrainSearchItem]:
    """Search canonical railway trains by train number and/or name using the historical timetable."""
    snapshot_id = get_active_timetable_snapshot_id(db)

    query = (
        select(TrainObservation, Train.number)
        .join(Train, Train.id == TrainObservation.train_id)
        .filter(TrainObservation.snapshot_id == snapshot_id)
    )

    if q and q.strip():
        search_term = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Train.number).like(search_term),
                func.lower(TrainObservation.name).like(search_term),
            )
        )

        query = query.order_by(
            (func.lower(Train.number) == q.strip().lower()).desc(),
            func.lower(Train.number).startswith(q.strip().lower()).desc(),
            (func.lower(TrainObservation.name) == q.strip().lower()).desc(),
            func.lower(TrainObservation.name).startswith(q.strip().lower()).desc(),
            Train.number.asc(),
        )
    else:
        query = query.order_by(Train.number.asc())

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


@router.get(
    "/between", response_model=TrainSearchEmptyState, status_code=status.HTTP_501_NOT_IMPLEMENTED
)
def search_trains_between(
    source: Annotated[str, Query(min_length=1, max_length=10, description="Source station code")],
    destination: Annotated[
        str, Query(min_length=1, max_length=10, description="Destination station code")
    ],
) -> TrainSearchEmptyState:
    """Discover trains running between two stations.

    Currently unsupported in v1.0 due to ₹0 open-data constraint on train timetables.
    """
    return TrainSearchEmptyState(
        message=(
            "Train timetable and discovery data is currently unavailable. "
            "Responsible inclusion of a verified, open, and £0-compliant train schedule dataset "
            "is pending investigation."
        ),
        available=False,
    )


@router.get("/{train_number}", response_model=TrainDetail)
def get_train_detail(
    train_number: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> TrainDetail:
    """Return historical timetable information for one canonical train."""
    snapshot_id = get_active_timetable_snapshot_id(db)

    query = (
        select(TrainObservation, Train, DatasetSnapshot, DataSource)
        .join(Train, Train.id == TrainObservation.train_id)
        .join(DatasetSnapshot, DatasetSnapshot.id == TrainObservation.snapshot_id)
        .join(DataSource, DataSource.id == DatasetSnapshot.source_id)
        .filter(
            TrainObservation.snapshot_id == snapshot_id,
            func.lower(Train.number) == train_number.lower(),
        )
    )

    result = db.execute(query).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Historical train timetable for '{train_number}' not found.",
        )

    obs, train, snapshot, source = result

    return TrainDetail(
        train_number=train.number,
        name=obs.name,
        type=obs.type,
        return_train_number=obs.return_train_number,
        provenance=ProvenanceInfo(
            snapshot_id=snapshot.id,
            source_name=source.name,
            retrieved_at=snapshot.retrieved_at,
        ),
    )





@router.get("/{train_number}/route", response_model=list[TrainStopResponse])
def get_train_route(
    train_number: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[TrainStopResponse]:
    """Return the ordered historical station stops for one canonical train."""
    snapshot_id = get_active_timetable_snapshot_id(db)
    station_snapshot_id = get_active_station_snapshot_id(db)

    # First verify the train actually exists in this snapshot
    train = db.execute(
        select(TrainObservation)
        .join(Train, Train.id == TrainObservation.train_id)
        .filter(
            TrainObservation.snapshot_id == snapshot_id,
            func.lower(Train.number) == train_number.lower(),
        )
    ).first()

    if not train:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Historical train route for '{train_number}' not found.",
        )

    query = (
        select(TrainStopObservation, Station, StationObservation)
        .join(Station, Station.id == TrainStopObservation.station_id)
        .outerjoin(
            StationObservation,
            (StationObservation.station_id == Station.id) &
            (StationObservation.snapshot_id == station_snapshot_id)
        )
        .join(Train, Train.id == TrainStopObservation.train_id)
        .filter(
            TrainStopObservation.snapshot_id == snapshot_id,
            func.lower(Train.number) == train_number.lower(),
        )
        .order_by(TrainStopObservation.stop_sequence.asc())
    )

    results = db.execute(query).all()

    return [
        TrainStopResponse(
            stop_sequence=obs.stop_sequence,
            station_code=station.code,
            station_name=station_obs.name if station_obs else station.code,
            arrival_time=obs.arrival_time,
            departure_time=obs.departure_time,
            source_day=obs.source_day,
        )
        for obs, station, station_obs in results
    ]




