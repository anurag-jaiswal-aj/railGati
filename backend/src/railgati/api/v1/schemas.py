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


class TerminusItem(BaseModel):
    """Historical timetable occurrence boundaries for a terminus station."""

    station_code: str
    station_name: str
    originating_count: int
    terminating_count: int
    total_terminus_volume: int


class TerminusResponse(BaseModel):
    """Network terminus analytics for the active timetable snapshot."""

    timetable_snapshot_id: int
    termini: list[TerminusItem]


class FlowItem(BaseModel):
    """Historical Origin-Destination timetable flow boundaries."""

    origin_station_code: str
    origin_station_name: str
    destination_station_code: str
    destination_station_name: str
    flow_volume: int


class FlowResponse(BaseModel):
    """Network O-D flow analytics for the active timetable snapshot."""

    timetable_snapshot_id: int
    flows: list[FlowItem]


class DwellItem(BaseModel):
    """Historical scheduled station transit dwell duration."""

    station_code: str
    station_name: str
    avg_dwell_minutes: float
    transit_count: int


class DwellResponse(BaseModel):
    """Network station dwell analytics for the active timetable snapshot."""

    timetable_snapshot_id: int
    limit: int
    min_transit_count: int
    items: list[DwellItem]


class ComplexityItem(BaseModel):
    """Historical scheduled route complexity for a station."""

    station_code: str
    station_name: str
    avg_route_stops: float
    service_count: int


class ComplexityResponse(BaseModel):
    """Network station route complexity analytics for the active timetable snapshot."""

    timetable_snapshot_id: int
    limit: int
    min_service_count: int
    items: list[ComplexityItem]


class TemporalConcentrationItem(BaseModel):
    """Historical scheduled calendar-hour occurrence concentration for a station."""

    station_code: str
    station_name: str
    peak_hour_val: int
    peak_hour_volume: int
    total_volume: int
    concentration_pct: float


class TemporalConcentrationResponse(BaseModel):
    """Network station temporal concentration analytics for the active timetable snapshot."""

    timetable_snapshot_id: int
    limit: int
    min_service_count: int
    items: list[TemporalConcentrationItem]


class EdgeAsymmetryItem(BaseModel):
    """Historical scheduled directional edge flow imbalance for a station pair."""

    station_a_code: str
    station_a_name: str
    station_b_code: str
    station_b_name: str
    forward_volume: int
    reverse_volume: int
    total_volume: int
    asymmetry_pct: float


class EdgeAsymmetryResponse(BaseModel):
    """Network directional edge asymmetry analytics for the active graph build."""

    timetable_snapshot_id: int
    limit: int
    min_total_volume: int
    items: list[EdgeAsymmetryItem]


class TrainSimilarityItem(BaseModel):
    """Historical timetable route-set similarity for a compared train."""

    train_number: str
    train_name: str
    train_type: str | None = None
    return_train_number: str | None = None
    overlap_station_count: int
    compared_station_count: int
    union_station_count: int
    similarity_pct: float


class TrainSimilarityResponse(BaseModel):
    """Network train route similarity analytics for the active timetable snapshot."""

    timetable_snapshot_id: int
    target_train_number: str
    target_train_name: str
    target_station_count: int
    limit: int
    min_overlap_stations: int
    items: list[TrainSimilarityItem]


class StationSimilarityItem(BaseModel):
    """Historical timetable service-set similarity for a compared station."""

    station_code: str
    station_name: str | None = None
    compared_train_count: int
    overlap_train_count: int
    union_train_count: int
    similarity_pct: float


class StationSimilarityResponse(BaseModel):
    """Network station service similarity analytics for the active timetable snapshot."""

    timetable_snapshot_id: int
    target_station_code: str
    target_station_name: str | None = None
    target_train_count: int
    limit: int
    min_overlap_trains: int
    items: list[StationSimilarityItem]


class TravelTimeResponse(BaseModel):
    """Network O-D travel time analytics for the active timetable snapshot."""

    timetable_snapshot_id: int
    from_station_code: str
    from_station_name: str | None = None
    to_station_code: str
    to_station_name: str | None = None
    qualifying_occurrence_count: int
    distinct_train_count: int
    min_duration_minutes: int | None = None
    max_duration_minutes: int | None = None
    avg_duration_minutes: float | None = None


class PairedServiceItem(BaseModel):
    arriving_train_number: str
    departing_train_number: str
    arrival_time: str
    departure_time: str
    clock_gap_minutes: int


class PairedServiceResponse(BaseModel):
    station_code: str
    station_name: str | None
    timetable_snapshot_id: int
    paired_service_count: int
    avg_clock_gap_minutes: float | None
    paired_services: list[PairedServiceItem]


class ReversingTrainItem(BaseModel):
    train_number: str
    adjoining_station_code: str
    arrival_time: str | None
    departure_time: str | None


class ReversalResponse(BaseModel):
    station_code: str
    station_name: str | None
    timetable_snapshot_id: int
    reversal_count: int
    reversing_trains: list[ReversingTrainItem]


class OutboundEdgeItem(BaseModel):
    next_station_code: str
    next_station_name: str | None
    train_volume: int
    min_duration_minutes: float
    max_duration_minutes: float
    avg_duration_minutes: float


class OutboundEdgeTransitResponse(BaseModel):
    station_code: str
    station_name: str | None
    timetable_snapshot_id: int
    outbound_edges: list[OutboundEdgeItem]
