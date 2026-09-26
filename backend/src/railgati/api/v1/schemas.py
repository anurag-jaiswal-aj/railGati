"""Pydantic schemas for the v1 API."""

from datetime import datetime
from enum import StrEnum
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


class JourneyType(StrEnum):
    """Types of historical journeys."""

    DIRECT = "DIRECT"
    ONE_TRANSFER = "ONE_TRANSFER"


class TimingConfidence(StrEnum):
    """Confidence level of the calculated timing."""

    HIGH = "HIGH"
    MISSING_DATA = "MISSING_DATA"


class JourneyLeg(BaseModel):
    """A segment of a journey on a single train."""

    train_number: str
    train_name: str
    train_type: str | None
    origin_station: str
    destination_station: str
    departure_time: str | None
    arrival_time: str | None
    source_day_offset: int | None
    duration_minutes: int | None


class JourneyOption(BaseModel):
    """A viable historical journey between two stations."""

    journey_id: str
    type: JourneyType
    legs: list[JourneyLeg]
    total_duration_minutes: int | None
    timing_confidence: TimingConfidence
    number_of_stops: int
    transfer_station: str | None = None
    layover_minutes: int | None = None
    provenance: ProvenanceInfo


class JourneyCompareResponse(BaseModel):
    """Response containing journey comparison options."""

    source: str = Field(..., description="Canonical origin station code")
    destination: str = Field(..., description="Canonical destination station code")
    timetable_snapshot_id: int = Field(..., description="ID of the timetable snapshot used")
    max_transfers: int = Field(..., description="Maximum allowed transfers")
    journeys: list[JourneyOption]


class DestinationItem(BaseModel):
    """A direct destination station reachable from the origin."""

    station_code: str = Field(..., description="Canonical station code")
    station_name: str | None = Field(
        None, description="Canonical station name from active station snapshot"
    )
    fastest_duration_minutes: int | None = Field(
        None, description="Fastest known historical travel time in minutes"
    )
    direct_train_count: int = Field(
        ..., description="Number of distinct direct trains to this destination"
    )
    timing_confidence: TimingConfidence = Field(
        ..., description="Confidence of the calculated travel time"
    )


class DestinationResponse(BaseModel):
    """Response containing reachable destinations from an origin."""

    origin: str = Field(..., description="Canonical origin station code")
    timetable_snapshot_id: int = Field(..., description="ID of the timetable snapshot used")
    max_duration_minutes: int | None = Field(None, description="Maximum travel duration applied")
    total: int = Field(..., description="Total number of reachable destinations")
    page: int = Field(..., description="Current page number")
    size: int = Field(..., description="Number of results per page")
    destinations: list[DestinationItem]


class NetworkReachabilityItem(BaseModel):
    """A canonical station topologically reachable from the origin."""

    station_code: str = Field(..., description="Canonical station code")
    station_name: str | None = Field(
        None, description="Canonical station name from active station snapshot"
    )
    min_hops: int = Field(..., description="Minimum network hops to reach this station")


class NetworkReachabilityResponse(BaseModel):
    """Response containing bounded topological reachability from an origin."""

    origin: str = Field(..., description="Canonical origin station code")
    timetable_snapshot_id: int = Field(..., description="ID of the timetable snapshot used")
    max_hops: int = Field(..., description="Maximum applied network hops")
    total: int = Field(..., description="Total number of reachable stations returned")
    stations: list[NetworkReachabilityItem]
