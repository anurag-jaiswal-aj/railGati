"""Pydantic schemas for the v1 API."""

from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse[T](BaseModel):
    """Generic paginated response."""

    items: list[T]
    total: int
    page: int
    size: int


class ProvenanceInfo(BaseModel):
    """Source provenance metadata."""

    snapshot_id: int
    source_name: str
    retrieved_at: datetime


class StationBase(BaseModel):
    """Base station fields."""

    code: str = Field(..., description="Canonical station code")
    name: str = Field(..., description="Station name from latest snapshot")
    state: str | None = Field(None, description="State/Province")
    zone: str | None = Field(None, description="Railway zone")
    latitude: float | None = Field(None, description="Latitude if available")
    longitude: float | None = Field(None, description="Longitude if available")


class StationDetail(StationBase):
    """Detailed station response including provenance."""

    id: int = Field(..., description="Internal canonical station ID")
    provenance: ProvenanceInfo = Field(..., description="Data provenance information")


class StationSearchItem(StationBase):
    """Station summary for search/autocomplete."""

    pass


class TrainSearchEmptyState(BaseModel):
    """Graceful empty state for missing train data."""

    message: str
    available: bool = False


class TrainBase(BaseModel):
    """Base train fields."""

    train_number: str = Field(..., description="Canonical train number")
    name: str = Field(..., description="Train name from latest snapshot")
    type: str | None = Field(None, description="Train type classification")
    return_train_number: str | None = Field(None, description="Return train number if known")


class TrainSearchItem(TrainBase):
    """Train summary for search results."""
    pass


class TrainDetail(TrainBase):
    """Detailed train response including provenance."""

    provenance: ProvenanceInfo = Field(..., description="Data provenance information")


class TrainStopResponse(BaseModel):
    """A single stop on a train's route."""

    stop_sequence: int = Field(..., description="Ordered stop sequence starting at 1")
    station_code: str = Field(..., description="Canonical station code")
    station_name: str = Field(..., description="Canonical station name")
    arrival_time: str | None = Field(None, description="Arrival time (HH:MM:SS) if applicable")
    departure_time: str | None = Field(None, description="Departure time (HH:MM:SS) if applicable")
    source_day: int | None = Field(None, description="Relative day of journey")
