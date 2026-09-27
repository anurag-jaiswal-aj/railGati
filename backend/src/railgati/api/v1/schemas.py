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


class NetworkPathStation(BaseModel):
    """A station in a network path."""

    station_code: str = Field(..., description="Canonical station code")
    station_name: str | None = Field(
        None, description="Canonical station name from active station snapshot"
    )


class NetworkPathItem(BaseModel):
    """A single topological path."""

    hop_count: int = Field(..., description="Number of network hops")
    stations: list[NetworkPathStation] = Field(
        ..., description="Ordered sequence of stations in the path"
    )


class NetworkPathResponse(BaseModel):
    """Response containing bounded topological paths between an origin and destination."""

    origin: str = Field(..., description="Canonical origin station code")
    destination: str = Field(..., description="Canonical destination station code")
    timetable_snapshot_id: int = Field(..., description="ID of the timetable snapshot used")
    max_hops: int = Field(..., description="Maximum applied network hops")
    max_paths: int = Field(..., description="Maximum number of paths to return")
    total_paths_returned: int = Field(..., description="Number of paths actually returned")
    paths: list[NetworkPathItem]


class NetworkServiceOccurrenceItem(BaseModel):
    """A single physical service-edge occurrence joining two stations."""

    train_number: str = Field(..., description="Canonical train number")
    train_name: str = Field(..., description="Canonical train name from active snapshot")
    train_type: str | None = Field(None, description="Train type classification")
    return_train_number: str | None = Field(None, description="Return train number if known")
    from_stop_sequence: int = Field(..., description="Sequence number at the from-station")
    to_stop_sequence: int = Field(..., description="Sequence number at the to-station")
    departure_time: str | None = Field(None, description="Departure time from origin")
    arrival_time: str | None = Field(None, description="Arrival time at destination")
    duration_minutes: int | None = Field(None, description="Duration in minutes")
    source_day_offset: int | None = Field(None, description="Source day offset at origin")


class NetworkServiceAttributionResponse(BaseModel):
    """Response containing bounded topological paths between an origin and destination."""

    origin: str = Field(..., description="Canonical origin station code")
    destination: str = Field(..., description="Canonical destination station code")
    timetable_snapshot_id: int = Field(..., description="ID of the timetable snapshot used")
    occurrences_returned: int = Field(..., description="Number of occurrences returned")
    occurrences: list[NetworkServiceOccurrenceItem]


class NetworkPathAttributionSegment(BaseModel):
    """Service occurrences for a specific segment of a topological path."""

    from_station: str = Field(..., description="Canonical from-station code")
    to_station: str = Field(..., description="Canonical to-station code")
    occurrences_returned: int = Field(
        ..., description="Number of occurrences returned for this segment"
    )
    occurrences: list[NetworkServiceOccurrenceItem]


class NetworkPathAttributionResponse(BaseModel):
    """Response containing service attribution for an entire topological path."""

    path: list[str] = Field(..., description="Canonical station codes representing the path")
    timetable_snapshot_id: int = Field(..., description="ID of the timetable snapshot used")
    segments: list[NetworkPathAttributionSegment]


class NetworkPathContinuousServiceItem(BaseModel):
    """A continuous historical train service covering an entire topological path."""

    train_number: str
    train_name: str | None = None
    train_type: str | None = None
    start_sequence: int
    end_sequence: int
    departure_time: str | None = None
    arrival_time: str | None = None
    start_day_offset: int | None = None
    end_day_offset: int | None = None
    total_duration_minutes: int | None = None


class NetworkPathContinuousServicesResponse(BaseModel):
    """Response containing continuous through-services for a topological path."""

    path: list[str] = Field(..., description="Canonical station codes representing the path")
    timetable_snapshot_id: int = Field(..., description="ID of the timetable snapshot used")
    total_services_returned: int = Field(..., description="Number of continuous services returned")
    services: list[NetworkPathContinuousServiceItem] = Field(..., description="Continuous services")


class CorridorItem(BaseModel):
    """A distinct structural corridor between an origin and destination."""

    path: list[str] = Field(..., description="Canonical station codes representing the path")
    occurrence_count: int = Field(..., description="Number of historical structural occurrences")
    fastest_duration_minutes: int | None = Field(
        None, description="Fastest valid occurrence duration"
    )


class CorridorResponse(BaseModel):
    """Response containing corridors between an origin and destination."""

    origin: str = Field(..., description="Canonical origin station code")
    destination: str = Field(..., description="Canonical destination station code")
    timetable_snapshot_id: int = Field(..., description="ID of the timetable snapshot used")
    corridors: list[CorridorItem]


class HubCentralityItem(BaseModel):
    station_code: str = Field(..., description="Canonical station code")
    station_name: str = Field(..., description="Canonical station name")
    out_degree: int = Field(
        ..., description="Number of unique stations physically reachable directly from this hub"
    )
    in_degree: int = Field(
        ..., description="Number of unique stations that can directly reach this hub"
    )
    total_topological_degree: int = Field(..., description="Sum of in-degree and out-degree")
    outbound_service_occurrence_volume: int = Field(
        ..., description="Sum of adjacent historical train occurrences departing this hub"
    )
    inbound_service_occurrence_volume: int = Field(
        ..., description="Sum of adjacent historical train occurrences arriving at this hub"
    )
    combined_occurrence_volume: int = Field(
        ...,
        description="Sum of inbound and outbound occurrences. Note: continuous trains passing through will be double-counted.",
    )


class HubCentralityResponse(BaseModel):
    timetable_snapshot_id: int = Field(
        ..., description="The ID of the dataset snapshot providing the active timetable data"
    )
    hubs: list[HubCentralityItem] = Field(..., description="List of stations ranked by centrality")

class EdgeVolumeItem(BaseModel):
    from_station_code: str = Field(..., description="Canonical source station code")
    from_station_name: str = Field(..., description="Canonical source station name")
    to_station_code: str = Field(..., description="Canonical destination station code")
    to_station_name: str = Field(..., description="Canonical destination station name")
    service_occurrence_volume: int = Field(
        ..., description="Aggregate historical train occurrences on this segment"
    )


class EdgeVolumeResponse(BaseModel):
    timetable_snapshot_id: int = Field(
        ..., description="The ID of the dataset snapshot providing the active timetable data"
    )
    edges: list[EdgeVolumeItem] = Field(..., description="List of segments ranked by volume")
