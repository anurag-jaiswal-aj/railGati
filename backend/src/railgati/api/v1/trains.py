"""Trains API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from railgati.api.v1.schemas import TrainSearchEmptyState

router = APIRouter(prefix="/trains", tags=["Trains"])


@router.get("/between", response_model=TrainSearchEmptyState, status_code=status.HTTP_501_NOT_IMPLEMENTED)
def search_trains_between(
    source: Annotated[str, Query(min_length=1, max_length=10, description="Source station code")],
    destination: Annotated[str, Query(min_length=1, max_length=10, description="Destination station code")],
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
