"""Network reachability API endpoint."""

import typing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from railgati.api.v1 import schemas
from railgati.api.v1.schemas import (
    ComplexityResponse,
    DwellResponse,
    EdgeAsymmetryResponse,
    EdgePairedSymmetryResponse,
    FlowResponse,
    NetworkPathAttributionResponse,
    NetworkPathItem,
    NetworkPathResponse,
    NetworkPathStation,
    NetworkReachabilityItem,
    NetworkReachabilityResponse,
    NetworkServiceAttributionResponse,
    RelativeEdgeSlownessResponse,
    RelativeStationDwellResponse,
    StationNeighborhoodSymmetryResponse,
    StationNeighborhoodTriadicClosureResponse,
    StationOutboundDominanceResponse,
    StationReachabilityExpansionResponse,
    StationSimilarityResponse,
    StationTransitArticulationResponse,
    StructuralHaltResponse,
    TemporalConcentrationResponse,
    TerminusResponse,
    TrainSimilarityResponse,
    TravelTimeResponse,
)
from railgati.api.v1.snapshots import (
    get_active_station_snapshot_id,
    get_active_timetable_snapshot_id,
)
from railgati.db import get_db
from railgati.models.station import Station, StationObservation
from railgati.services.network import (
    calculate_edge_volume,
    calculate_network_complexities,
    calculate_network_edge_asymmetry,
    calculate_network_temporal_concentration,
    calculate_station_pair_route_boundary_confinement,
    find_network_paths,
    find_reachable_stations,
)

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


@router.get(
    "/path",
    response_model=NetworkPathResponse,
    summary="Explore bounded network topology paths",
    description=(
        "Returns simple topological paths between an origin and destination within max_hops. "
        "This does not represent passenger routing or viability of transfers."
    ),
)
def get_network_path(
    origin: Annotated[
        str,
        Query(
            description="Canonical origin station code.",
            min_length=1,
            max_length=50,
        ),
    ],
    destination: Annotated[
        str,
        Query(
            description="Canonical destination station code.",
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
    max_paths: Annotated[
        int,
        Query(
            description="Maximum number of paths to return.",
            ge=1,
            le=50,
        ),
    ] = 10,
    db: Session = Depends(get_db),  # noqa: B008
) -> NetworkPathResponse:
    """Explore bounded paths between origin and destination."""

    # 1. Resolve Stations
    stations_q = (
        db.execute(
            select(Station).filter(
                func.lower(Station.code).in_([origin.lower(), destination.lower()])
            )
        )
        .scalars()
        .all()
    )

    origin_station = next((s for s in stations_q if s.code.lower() == origin.lower()), None)
    dest_station = next((s for s in stations_q if s.code.lower() == destination.lower()), None)

    if not origin_station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Origin station '{origin.upper()}' not found.",
        )
    if not dest_station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Destination station '{destination.upper()}' not found.",
        )

    # 2. Get Active Timetable Snapshot
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    # 3. Call the Discovery Service
    try:
        service_results = find_network_paths(
            db=db,
            timetable_snapshot_id=timetable_snapshot_id,
            origin_station_id=origin_station.id,
            destination_station_id=dest_station.id,
            max_hops=max_hops,
            max_paths=max_paths,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e

    # 4. Resolve Station Names safely via API layer
    station_meta: dict[int, tuple[str, str | None]] = {}
    if service_results:
        station_snapshot_id = get_active_station_snapshot_id(db)

        # Collect all unique station IDs in all paths
        unique_station_ids = {sid for path in service_results for sid in path.station_ids}

        observations = db.execute(
            select(Station.id, Station.code, StationObservation.name)
            .outerjoin(
                StationObservation,
                (Station.id == StationObservation.station_id)
                & (StationObservation.snapshot_id == station_snapshot_id),
            )
            .filter(Station.id.in_(unique_station_ids))
        ).all()

        station_meta = {row.id: (row.code, row.name) for row in observations}

    # 5. Map to Response Schema
    items = []
    for path in service_results:
        path_stations = [
            NetworkPathStation(
                station_code=station_meta[sid][0],
                station_name=station_meta[sid][1],
            )
            for sid in path.station_ids
        ]
        items.append(NetworkPathItem(hop_count=path.hop_count, stations=path_stations))

    return NetworkPathResponse(
        origin=origin_station.code,
        destination=dest_station.code,
        timetable_snapshot_id=timetable_snapshot_id,
        max_hops=max_hops,
        max_paths=max_paths,
        total_paths_returned=len(items),
        paths=items,
    )


@router.get(
    "/attribution",
    response_model=NetworkServiceAttributionResponse,
    summary="Get network service attribution",
    description=(
        "Explains which historical service-edge occurrences contributed to a materialized "
        "RailwayNetworkEdge. This does not imply passenger routing viability."
    ),
)
def get_network_service_attribution(
    origin: Annotated[
        str,
        Query(
            description="Canonical origin station code.",
            min_length=1,
            max_length=50,
        ),
    ],
    destination: Annotated[
        str,
        Query(
            description="Canonical destination station code.",
            min_length=1,
            max_length=50,
        ),
    ],
    db: Session = Depends(get_db),  # noqa: B008
) -> NetworkServiceAttributionResponse:
    """Discover network service attribution."""

    # 1. Resolve Stations
    stations_q = (
        db.execute(
            select(Station).filter(
                func.lower(Station.code).in_([origin.lower(), destination.lower()])
            )
        )
        .scalars()
        .all()
    )

    origin_station = next((s for s in stations_q if s.code.lower() == origin.lower()), None)
    dest_station = next((s for s in stations_q if s.code.lower() == destination.lower()), None)

    if not origin_station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Origin station '{origin.upper()}' not found.",
        )
    if not dest_station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Destination station '{destination.upper()}' not found.",
        )

    # 2. Get Active Timetable Snapshot
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    # 3. Call the Discovery Service
    from railgati.services.network import find_network_service_occurrences

    try:
        service_results = find_network_service_occurrences(
            db=db,
            timetable_snapshot_id=timetable_snapshot_id,
            origin_station_id=origin_station.id,
            destination_station_id=dest_station.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e

    # 4. Map to Response Schema
    from railgati.api.v1.schemas import NetworkServiceOccurrenceItem

    items = [
        NetworkServiceOccurrenceItem(
            train_number=res.train_number,
            train_name=res.train_name,
            train_type=res.train_type,
            return_train_number=res.return_train_number,
            from_stop_sequence=res.from_stop_sequence,
            to_stop_sequence=res.to_stop_sequence,
            departure_time=res.departure_time,
            arrival_time=res.arrival_time,
            duration_minutes=res.duration_minutes,
            source_day_offset=res.source_day_offset,
        )
        for res in service_results
    ]

    return NetworkServiceAttributionResponse(
        origin=origin_station.code,
        destination=dest_station.code,
        timetable_snapshot_id=timetable_snapshot_id,
        occurrences_returned=len(items),
        occurrences=items,
    )


@router.get(
    "/path/attribution",
    response_model=NetworkPathAttributionResponse,
    summary="Get network path service attribution",
    description=(
        "Explains which historical service-edge occurrences contributed to an entire "
        "topological path. This does not imply passenger routing viability."
    ),
)
def get_network_path_service_attribution(
    path: Annotated[
        str,
        Query(
            description="Comma-separated canonical station codes.",
            min_length=3,  # At least A,B
        ),
    ],
    db: Session = Depends(get_db),  # noqa: B008
) -> NetworkPathAttributionResponse:
    """Discover network service attribution for a path."""

    station_codes = [c.strip() for c in path.split(",") if c.strip()]
    if len(station_codes) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Path must contain at least 2 stations.",
        )
    if len(station_codes) > 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Path cannot contain more than 10 stations.",
        )

    for i in range(len(station_codes) - 1):
        if station_codes[i].lower() == station_codes[i + 1].lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Path cannot contain consecutive identical stations.",
            )

    # 1. Resolve Stations
    stations_q = (
        db.execute(
            select(Station).filter(func.lower(Station.code).in_([c.lower() for c in station_codes]))
        )
        .scalars()
        .all()
    )

    station_map = {s.code.lower(): s for s in stations_q}

    path_station_ids = []
    for code in station_codes:
        s = station_map.get(code.lower())
        if not s:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Station '{code.upper()}' not found.",
            )
        path_station_ids.append(s.id)

    # 2. Get Active Timetable Snapshot
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    # 3. Call the Discovery Service
    from railgati.services.network import find_network_path_service_occurrences

    try:
        service_results = find_network_path_service_occurrences(
            db=db,
            timetable_snapshot_id=timetable_snapshot_id,
            path_station_ids=path_station_ids,
        )
    except ValueError as e:
        err_msg = str(e)
        if "does not exist in the active network topology" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg,
            ) from e
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=err_msg,
        ) from e

    # 4. Map to Response Schema
    from railgati.api.v1.schemas import NetworkPathAttributionSegment, NetworkServiceOccurrenceItem

    segments = []
    # Create an inverse map for returning original matched station codes
    id_to_code = {s.id: s.code for s in stations_q}

    for seg_data in service_results:
        items = [
            NetworkServiceOccurrenceItem(
                train_number=res.train_number,
                train_name=res.train_name,
                train_type=res.train_type,
                return_train_number=res.return_train_number,
                from_stop_sequence=res.from_stop_sequence,
                to_stop_sequence=res.to_stop_sequence,
                departure_time=res.departure_time,
                arrival_time=res.arrival_time,
                duration_minutes=res.duration_minutes,
                source_day_offset=res.source_day_offset,
            )
            for res in seg_data.occurrences
        ]
        segments.append(
            NetworkPathAttributionSegment(
                from_station=id_to_code[seg_data.from_station_id],
                to_station=id_to_code[seg_data.to_station_id],
                occurrences_returned=len(items),
                occurrences=items,
            )
        )

    # We return the exact uppercase requested canonical codes from db
    canonical_path = [id_to_code[sid] for sid in path_station_ids]

    return NetworkPathAttributionResponse(
        path=canonical_path,
        timetable_snapshot_id=timetable_snapshot_id,
        segments=segments,
    )


@router.get(
    "/path/continuous-services",
    response_model=schemas.NetworkPathContinuousServicesResponse,
    summary="Get continuous historical services for a multi-edge path",
    description="Finds historical train services that seamlessly cover an entire ordered topological path.",
)
def get_network_path_continuous_services(
    path: str = Query(..., description="Comma-separated station codes, e.g. NDLS,AGC,BPL"),
    db: Session = Depends(get_db),
) -> schemas.NetworkPathContinuousServicesResponse:
    from railgati.services.network import find_network_path_continuous_services

    station_codes = [c.strip() for c in path.split(",") if c.strip()]
    if len(station_codes) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Path must contain at least 2 stations.",
        )
    if len(station_codes) > 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Path cannot contain more than 10 stations.",
        )

    for i in range(len(station_codes) - 1):
        if station_codes[i].lower() == station_codes[i + 1].lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Path cannot contain consecutive identical stations.",
            )

    # 1. Resolve Stations
    stations_q = (
        db.execute(
            select(Station).filter(func.lower(Station.code).in_([c.lower() for c in station_codes]))
        )
        .scalars()
        .all()
    )

    station_map = {s.code.lower(): s for s in stations_q}

    path_station_ids = []
    for code in station_codes:
        s = station_map.get(code.lower())
        if not s:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Station '{code.upper()}' not found.",
            )
        path_station_ids.append(s.id)

    snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        services = find_network_path_continuous_services(
            db, timetable_snapshot_id=snapshot_id, path_station_ids=path_station_ids
        )

        return schemas.NetworkPathContinuousServicesResponse(
            path=[station_map[c.lower()].code for c in station_codes],
            timetable_snapshot_id=snapshot_id,
            total_services_returned=len(services),
            services=[s.model_dump() for s in services],
        )
    except ValueError as e:
        import pydantic

        if isinstance(e, pydantic.ValidationError):
            raise
        msg = str(e)
        if "Path must contain" in msg or "consecutive duplicate" in msg:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
        elif "Active graph build unavailable" in msg:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg)
        elif "does not exist in the active network topology" in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.get(
    "/corridors",
    response_model=schemas.CorridorResponse,
    summary="Discover continuous historical corridors between two stations",
    description="Finds structural paths (corridors) traversed by continuous historical train services.",
)
def get_network_corridors(
    origin: str = Query(..., description="Canonical origin station code."),
    destination: str = Query(..., description="Canonical destination station code."),
    db: Session = Depends(get_db),
) -> schemas.CorridorResponse:
    from railgati.services.network import find_network_corridors

    if origin.lower() == destination.lower():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Origin and destination must not be the same.",
        )

    # Resolve Stations
    stations_q = (
        db.execute(
            select(Station).filter(
                func.lower(Station.code).in_([origin.lower(), destination.lower()])
            )
        )
        .scalars()
        .all()
    )

    origin_station = next((s for s in stations_q if s.code.lower() == origin.lower()), None)
    dest_station = next((s for s in stations_q if s.code.lower() == destination.lower()), None)

    if not origin_station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Origin station '{origin.upper()}' not found.",
        )
    if not dest_station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Destination station '{destination.upper()}' not found.",
        )

    snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        corridors = find_network_corridors(
            db,
            timetable_snapshot_id=snapshot_id,
            origin_station_id=origin_station.id,
            destination_station_id=dest_station.id,
        )

        return schemas.CorridorResponse(
            origin=origin_station.code,
            destination=dest_station.code,
            timetable_snapshot_id=snapshot_id,
            corridors=corridors,
        )
    except ValueError as e:
        msg = str(e)
        if "Active graph build unavailable" in msg:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


from enum import Enum


class SortByEnum(str, Enum):
    out_degree = "out_degree"
    in_degree = "in_degree"
    service_volume = "service_volume"


@router.get(
    "/hubs",
    response_model=schemas.HubCentralityResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Timetable snapshot not found"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Active graph build unavailable"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Invalid limit"},
    },
)
def get_network_hubs(
    limit: int = 50,
    sort_by: SortByEnum = SortByEnum.service_volume,
    db: Session = Depends(get_db),
) -> schemas.HubCentralityResponse:
    """Discover structural network hubs by centrality metrics."""
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Limit must be between 1 and 500",
        )

    snapshot_id = get_active_timetable_snapshot_id(db)

    from railgati.services.network import calculate_hub_centrality

    try:
        hubs = calculate_hub_centrality(
            db, timetable_snapshot_id=snapshot_id, limit=limit, sort_by=sort_by.value
        )

        return schemas.HubCentralityResponse(
            timetable_snapshot_id=snapshot_id,
            hubs=[h.model_dump() for h in hubs],
        )
    except ValueError as e:
        msg = str(e)
        if "unavailable" in msg.lower() or "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.get(
    "/edges/volume",
    response_model=schemas.EdgeVolumeResponse,
    summary="Topological Edge Volume Analytics",
)
def get_edge_volume(
    limit: int = Query(50, ge=1, le=500, description="Number of edges to return"),
    db: Session = Depends(get_db),
) -> schemas.EdgeVolumeResponse:
    """Compute topological edge volume (Segment Centrality).

    Returns the historically most frequently traversed direct physical segments
    (adjacent station pairs) in the active network snapshot.
    """
    snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        items = calculate_edge_volume(
            db=db,
            timetable_snapshot_id=snapshot_id,
            limit=limit,
        )
    except ValueError as e:
        if "ACTIVE RailwayGraphBuild" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    return schemas.EdgeVolumeResponse(
        timetable_snapshot_id=snapshot_id,
        edges=items,
    )


@router.get(
    "/termini",
    response_model=TerminusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Network Terminus Analytics",
    description="Retrieve stations ranked by historical terminus occurrence volume.",
)
def get_network_termini(
    limit: Annotated[
        int,
        Query(
            description="Maximum number of stations to return",
            ge=1,
            le=500,
        ),
    ] = 50,
    db: Session = Depends(get_db),  # noqa: B008
) -> TerminusResponse:
    """Discover the historical timetable occurrence boundaries for terminus stations."""
    try:
        timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    from railgati.services.network import calculate_network_termini

    try:
        termini_data = calculate_network_termini(
            db=db,
            timetable_snapshot_id=timetable_snapshot_id,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    return TerminusResponse(
        timetable_snapshot_id=timetable_snapshot_id,
        termini=termini_data,
    )


@router.get(
    "/flows",
    response_model=FlowResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Network O-D Flow Analytics",
    description="Retrieve origin-destination pairs ranked by historical flow volume.",
)
def get_network_flows(
    limit: Annotated[
        int,
        Query(
            description="Maximum number of flows to return",
            ge=1,
            le=500,
        ),
    ] = 50,
    db: Session = Depends(get_db),  # noqa: B008
) -> FlowResponse:
    """Discover the highest-volume historical timetable flow pairs."""
    try:
        timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    from railgati.services.network import calculate_network_flows

    try:
        flows_data = calculate_network_flows(
            db=db,
            timetable_snapshot_id=timetable_snapshot_id,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    return FlowResponse(
        timetable_snapshot_id=timetable_snapshot_id,
        flows=flows_data,
    )


@router.get(
    "/dwells",
    response_model=DwellResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Network Station Dwell Analytics",
    description="Retrieve stations ranked by historical scheduled dwell duration for transit occurrences.",
)
def get_network_dwells(
    limit: Annotated[
        int,
        Query(
            description="Maximum number of stations to return",
            ge=1,
            le=500,
        ),
    ] = 50,
    min_transit_count: Annotated[
        int,
        Query(
            description="Minimum number of transit occurrences required to be included",
            ge=1,
            le=1000,
        ),
    ] = 10,
    db: Session = Depends(get_db),  # noqa: B008
) -> DwellResponse:
    """Discover stations with the longest historical scheduled wait times."""
    try:
        timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    from railgati.services.network import calculate_network_dwells

    try:
        dwell_data = calculate_network_dwells(
            db=db,
            timetable_snapshot_id=timetable_snapshot_id,
            limit=limit,
            min_transit_count=min_transit_count,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    return DwellResponse(
        timetable_snapshot_id=timetable_snapshot_id,
        limit=limit,
        min_transit_count=min_transit_count,
        items=dwell_data,
    )


@router.get("/complexities", response_model=ComplexityResponse)
def get_network_complexities(
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    min_service_count: int = Query(
        10, ge=1, le=1000, description="Minimum transit occurrences to qualify"
    ),
    db: Session = Depends(get_db),
) -> dict:
    """
    Calculate Network Station Route Complexity.

    Returns the average historical scheduled route length (in total stops)
    of all canonical train occurrences visiting a station in the active snapshot.
    """
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    station_snapshot_id = get_active_station_snapshot_id(db)

    complexities = calculate_network_complexities(
        db,
        timetable_snapshot_id,
        station_snapshot_id,
        limit=limit,
        min_service_count=min_service_count,
    )

    return {
        "timetable_snapshot_id": timetable_snapshot_id,
        "limit": limit,
        "min_service_count": min_service_count,
        "items": complexities,
    }


@router.get("/temporal-concentration", response_model=TemporalConcentrationResponse)
def get_network_temporal_concentration(
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    min_service_count: int = Query(
        15, ge=1, le=1000, description="Minimum total occurrences to qualify"
    ),
    db: Session = Depends(get_db),
) -> dict:
    """
    Calculate Network Station Temporal Concentration.

    Returns the scheduled time-of-day concentration (calendar-hour peak)
    for stations within the active timetable snapshot.
    """
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    station_snapshot_id = get_active_station_snapshot_id(db)

    concentrations = calculate_network_temporal_concentration(
        db,
        timetable_snapshot_id,
        station_snapshot_id,
        limit=limit,
        min_service_count=min_service_count,
    )

    return {
        "timetable_snapshot_id": timetable_snapshot_id,
        "limit": limit,
        "min_service_count": min_service_count,
        "items": concentrations,
    }


@router.get("/edge-asymmetry", response_model=EdgeAsymmetryResponse)
def get_network_edge_asymmetry(
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    min_total_volume: int = Query(
        15, ge=0, description="Minimum combined total volume for the edge pair to qualify"
    ),
    db: Session = Depends(get_db),
) -> dict:
    """
    Calculate Network Directional Edge Asymmetry Analytics.

    Identifies track segments scheduled as one-way loops vs symmetrical corridors.
    """
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    station_snapshot_id = get_active_station_snapshot_id(db)

    try:
        items = calculate_network_edge_asymmetry(
            db,
            timetable_snapshot_id,
            station_snapshot_id,
            limit=limit,
            min_total_volume=min_total_volume,
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "timetable_snapshot_id": timetable_snapshot_id,
        "limit": limit,
        "min_total_volume": min_total_volume,
        "items": items,
    }


@router.get(
    "/trains/{train_number}/similar",
    response_model=TrainSimilarityResponse,
)
def get_train_similarity(
    train_number: str,
    db: Session = Depends(get_db),  # noqa: B008
    limit: Annotated[int, Query(ge=1, le=50, description="Max similar trains to return")] = 10,
    min_overlap_stations: Annotated[
        int, Query(ge=1, description="Minimum shared distinct stations")
    ] = 1,
) -> TrainSimilarityResponse:
    """Return historical timetable route-set similarity for a target train."""
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_train_similarity

        target_count, resolved_num, target_name, items = calculate_train_similarity(
            db=db,
            timetable_snapshot_id=timetable_snapshot_id,
            target_train_number=train_number,
            limit=limit,
            min_overlap_stations=min_overlap_stations,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    return TrainSimilarityResponse(
        timetable_snapshot_id=timetable_snapshot_id,
        target_train_number=resolved_num,
        target_train_name=target_name,
        target_station_count=target_count,
        limit=limit,
        min_overlap_stations=min_overlap_stations,
        items=items,
    )


@router.get(
    "/stations/{station_code}/similar",
    response_model=StationSimilarityResponse,
)
def get_station_similarity(
    station_code: str,
    db: Session = Depends(get_db),  # noqa: B008
    limit: Annotated[int, Query(ge=1, le=50, description="Max similar stations to return")] = 10,
    min_overlap_trains: Annotated[
        int, Query(ge=0, description="Minimum shared distinct trains")
    ] = 1,
) -> StationSimilarityResponse:
    """Return historical timetable service-set similarity for a target station."""
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_station_similarity

        target_count, resolved_code, target_name, items = calculate_station_similarity(
            db=db,
            timetable_snapshot_id=timetable_snapshot_id,
            target_station_code=station_code,
            limit=limit,
            min_overlap_trains=min_overlap_trains,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    return StationSimilarityResponse(
        timetable_snapshot_id=timetable_snapshot_id,
        target_station_code=resolved_code,
        target_station_name=target_name,
        target_train_count=target_count,
        limit=limit,
        min_overlap_trains=min_overlap_trains,
        items=items,
    )


@router.get(
    "/stations/{from_station_code}/travel-time/{to_station_code}",
    response_model=TravelTimeResponse,
)
def get_network_travel_time(
    from_station_code: str,
    to_station_code: str,
    db: Session = Depends(get_db),
) -> dict:
    """Calculate Network O-D Travel Time Analytics."""
    if from_station_code.lower() == to_station_code.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Origin and destination stations must be different",
        )

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_network_od_travel_time

        (
            from_code,
            origin_name,
            to_code,
            dest_name,
            qual_count,
            distinct_trains,
            min_dur,
            max_dur,
            avg_dur,
        ) = calculate_network_od_travel_time(
            db, timetable_snapshot_id, from_station_code, to_station_code
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "no qualifying adjacent" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return {
        "timetable_snapshot_id": timetable_snapshot_id,
        "from_station_code": from_code,
        "from_station_name": origin_name,
        "to_station_code": to_code,
        "to_station_name": dest_name,
        "qualifying_occurrence_count": qual_count,
        "distinct_train_count": distinct_trains,
        "min_duration_minutes": min_dur,
        "max_duration_minutes": max_dur,
        "avg_duration_minutes": avg_dur,
    }


from railgati.api.v1.schemas import PairedServiceResponse, PairedSymmetryResponse


@router.get(
    "/stations/{station_code}/paired-services",
    response_model=PairedServiceResponse,
)
def get_network_station_paired_services(
    station_code: str,
    db: Session = Depends(get_db),
) -> dict:
    """Calculate Network Station Paired-Service Analytics."""

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_station_paired_services

        (code, name, count, avg, pairs) = calculate_station_paired_services(
            db, timetable_snapshot_id, station_code
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "no qualifying adjacent" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return {
        "station_code": code,
        "station_name": name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "paired_service_count": count,
        "avg_clock_gap_minutes": avg,
        "paired_services": pairs,
    }


from railgati.api.v1.schemas import ReversalResponse


@router.get(
    "/stations/{station_code}/reversals",
    response_model=ReversalResponse,
)
def get_network_station_reversals(
    station_code: str,
    db: Session = Depends(get_db),
) -> dict:
    """Calculate Network Station Directional Reversal Analytics."""

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_station_reversals

        (code, name, count, trains) = calculate_station_reversals(
            db, timetable_snapshot_id, station_code
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "no qualifying adjacent" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return {
        "station_code": code,
        "station_name": name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "reversal_count": count,
        "reversing_trains": trains,
    }


from railgati.api.v1.schemas import OutboundEdgeTransitResponse


@router.get(
    "/stations/{station_code}/outbound-edges/transit",
    response_model=OutboundEdgeTransitResponse,
)
def get_network_station_outbound_transit(
    station_code: str,
    db: Session = Depends(get_db),
) -> dict:
    """Calculate Network Station Outbound Edge Transit Analytics."""

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_station_outbound_transit

        (code, name, edges) = calculate_station_outbound_transit(
            db, timetable_snapshot_id, station_code
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "no qualifying adjacent" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return {
        "station_code": code,
        "station_name": name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "outbound_edges": edges,
    }


from railgati.api.v1.schemas import TrainRouteProfileResponse


@router.get(
    "/trains/{train_number}/profile",
    response_model=TrainRouteProfileResponse,
)
def get_network_train_profile(
    train_number: str,
    db: Session = Depends(get_db),
) -> dict:
    """Calculate Network Train Route Profile Analytics."""

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_train_profile

        result = calculate_train_profile(db, timetable_snapshot_id, train_number)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "no usable observations" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return result


from railgati.api.v1.schemas import TopologicalLoopResponse


@router.get(
    "/trains/{train_number}/topology-loops",
    response_model=TopologicalLoopResponse,
)
def get_network_train_topology_loops(
    train_number: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    """
    Calculate Network Train Topological Loop Analytics.
    This metric identifies non-consecutive repeated station visits within a historical timetable.
    It is a structural timetable-topology signal and does not establish physical track geometry,
    current operations, passenger movement, or operational continuity.
    """

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_train_topology_loops

        result = calculate_train_topology_loops(db, timetable_snapshot_id, train_number)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "not present in snapshot" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e

    return result


from railgati.api.v1.schemas import ODBridgesResponse


@router.get(
    "/stations/{station_code}/od-bridges",
    response_model=ODBridgesResponse,
)
def get_network_station_od_bridges(
    station_code: str,
    db: Session = Depends(get_db),
) -> dict:
    """Calculate Network Station O-D Bridging Analytics."""

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_station_od_bridges

        result = calculate_station_od_bridges(db, timetable_snapshot_id, station_code)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "no qualifying adjacent" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return result


from railgati.api.v1.schemas import TemporalGapsResponse


@router.get(
    "/stations/{station_code}/temporal-gaps",
    response_model=TemporalGapsResponse,
)
def get_network_station_temporal_gaps(
    station_code: str,
    db: Session = Depends(get_db),
) -> dict:
    """Calculate Network Station Temporal Gap Analytics."""

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_station_temporal_gaps

        result = calculate_station_temporal_gaps(db, timetable_snapshot_id, station_code)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "no qualifying departures" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return result


from railgati.api.v1.schemas import EdgeTemporalBunchingResponse


@router.get(
    "/edges/{origin_code}/{destination_code}/temporal-bunching",
    response_model=EdgeTemporalBunchingResponse,
)
def get_network_edge_temporal_bunching(
    origin_code: str,
    destination_code: str,
    db: Session = Depends(get_db),
) -> dict:
    """Calculate Network Edge Temporal Bunching Analytics."""

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_edge_temporal_bunching

        result = calculate_edge_temporal_bunching(
            db, timetable_snapshot_id, origin_code, destination_code
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "no qualifying adjacent" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return result


@router.get(
    "/trains/{train_number}/paired-symmetry",
    response_model=PairedSymmetryResponse,
)
def get_network_train_paired_symmetry(
    train_number: str,
    db: Session = Depends(get_db),
) -> dict:
    """Calculate Network Train Paired-Service Temporal Symmetry Analytics."""
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_paired_service_symmetry

        result = calculate_paired_service_symmetry(db, timetable_snapshot_id, train_number)
    except ValueError as e:
        msg = str(e)
        if (
            "not found" in msg.lower()
            or "no paired service found" in msg.lower()
            or "not present or incomplete" in msg.lower()
            or "incomplete timing data" in msg.lower()
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return result


@router.get(
    "/trains/{train_number}/structural-halts",
    response_model=StructuralHaltResponse,
)
def get_network_train_structural_halts(
    train_number: str,
    limit: int = Query(10, ge=1, le=50, description="Max stations to return"),
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    """
    Calculate Network Train Structural Halt Analytics.
    This endpoint reports scheduled timetable dwell at strictly intermediate train stops.
    It does not establish the operational reason for a dwell and does not represent live/current railway operations.
    """
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_train_structural_halts

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        return calculate_train_structural_halts(
            db=db,
            timetable_snapshot_id=timetable_snapshot_id,
            train_number=train_number,
            limit=limit,
        )
    except ValueError as e:
        if "not found" in str(e).lower() or "not present" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/trains/{train_number}/relative-edge-slowness",
    response_model=RelativeEdgeSlownessResponse,
)
def get_network_train_relative_edge_slowness(
    train_number: str,
    limit: int = Query(10, ge=1, le=50, description="Max edges to return"),
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    """
    Calculate Network Train Relative Edge Slowness Analytics.
    This metric compares scheduled timetable duration for a train's adjacent edge occurrences
    against the timetable-average scheduled duration for the same adjacent station pair.
    It does not measure physical speed, actual travel time, congestion, capacity,
    passenger demand, or operational causes.
    """
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_train_relative_edge_slowness

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        return calculate_train_relative_edge_slowness(
            db, timetable_snapshot_id, train_number, limit=limit
        )
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail="Train not found")
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/trains/{train_number}/relative-station-dwell",
    response_model=RelativeStationDwellResponse,
)
def get_network_train_relative_station_dwell(
    train_number: str,
    limit: int = Query(10, ge=1, le=50, description="Max stations to return"),
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    """
    Calculate Network Train Relative Station Dwell Analytics.
    This metric compares scheduled timetable dwell for a train's intermediate occurrences
    against the timetable-average scheduled dwell for the identical station.
    It does not measure physical actual wait times, capacity, passenger demand, or operational causes.
    """
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_train_relative_station_dwell

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        return calculate_train_relative_station_dwell(
            db, timetable_snapshot_id, train_number, limit=limit
        )
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail="Train not found")
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/stations/{station_code}/outbound-dominance",
    response_model=StationOutboundDominanceResponse,
)
def get_network_station_outbound_dominance(
    station_code: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    """
    Calculate Network Station Outbound Dominance Analytics.
    This metric determines the concentration of scheduled outbound timetable occurrences from a station.
    It does not measure physical track capacity, passenger demand, or operational routing.
    """
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_station_outbound_dominance

    station_code = station_code.upper()
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        return calculate_station_outbound_dominance(db, timetable_snapshot_id, station_code)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail="Station not found")
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/edges/{from_station}/{to_station}/paired-symmetry",
    response_model=EdgePairedSymmetryResponse,
    summary="Get network edge paired-service route symmetry",
    description=(
        "Calculates the proportion of forward timetable train identities whose dataset-linked "
        "paired service also contains the reciprocal adjacent timetable edge in the same "
        "timetable snapshot. This does not represent physical topology, operational symmetry, "
        "passenger demand, or actual operations."
    ),
)
def get_edge_paired_symmetry(
    from_station: str,
    to_station: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.services.network import calculate_edge_paired_route_symmetry

    from_station = from_station.upper()
    to_station = to_station.upper()

    try:
        return calculate_edge_paired_route_symmetry(db, from_station, to_station)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        if "no active timetable snapshot" in str(e).lower():
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/stations/{station_code}/neighborhood-symmetry",
    response_model=StationNeighborhoodSymmetryResponse,
    summary="Calculate distinct neighborhood directional symmetry",
    description=(
        "Measures the Jaccard similarity between the queried station's distinct "
        "adjacent scheduled outbound destinations and distinct adjacent scheduled inbound origins. "
        "Evaluates pure graph topology; ignores edge volumes, return trains, and operational metrics."
    ),
)
def get_station_neighborhood_symmetry(
    station_code: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.services.network import calculate_station_neighborhood_symmetry

    station_code = station_code.upper()

    try:
        return calculate_station_neighborhood_symmetry(db, station_code)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        if "no active timetable snapshot" in str(e).lower():
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/stations/{station_code}/neighborhood-triadic-closure",
    response_model=StationNeighborhoodTriadicClosureResponse,
    summary="Calculate distinct neighborhood triadic closure",
    description=(
        "Measures the triadic closure ratio among a station's distinct adjacent scheduled "
        "outbound neighbors. Evaluates purely static timetable topology. Returns HTTP 400 "
        "if the outbound degree is less than 2 (ratio undefined)."
    ),
)
def get_station_neighborhood_triadic_closure(
    station_code: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.services.network import calculate_station_neighborhood_triadic_closure

    station_code = station_code.upper()

    try:
        return calculate_station_neighborhood_triadic_closure(db, station_code)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        if "no active timetable snapshot" in str(e).lower():
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/stations/{station_code}/transit-articulation",
    response_model=StationTransitArticulationResponse,
    summary="Calculate network station transit articulation analytics",
    description=(
        "Measures a station's local structural transit-pair dependency in the active timetable graph. "
        "Evaluates whether a station acts as a strict local cut-vertex between its inbound and "
        "outbound neighborhoods. Returns HTTP 400 for mathematically undefined constraints."
    ),
)
def get_station_transit_articulation(
    station_code: str, db: Session = Depends(get_db)
) -> dict[str, typing.Any]:
    from railgati.services.network import calculate_station_transit_articulation

    try:
        return calculate_station_transit_articulation(db, station_code)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        if "No active" in str(e):
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/stations/{station_code}/2-hop-expansion",
    response_model=StationReachabilityExpansionResponse,
    summary="Calculate network station 2-hop reachability expansion analytics",
    description=(
        "Measures the timetable-derived expansion from the target station's immediate outbound frontier "
        "to the new stations reachable one additional adjacent scheduled edge away. "
        "Returns HTTP 400 for mathematically undefined constraints (e.g. n1=0)."
    ),
)
def get_station_reachability_expansion(
    station_code: str, db: Session = Depends(get_db)
) -> dict[str, typing.Any]:
    from railgati.services.network import calculate_station_reachability_expansion

    try:
        return calculate_station_reachability_expansion(
            db, get_active_timetable_snapshot_id(db), station_code
        )
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        if "No active" in str(e):
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/stations/{station_code}/transfer-free-reach",
    response_model=schemas.StationTransferFreeReachResponse,
)
def get_network_station_transfer_free_reach(
    station_code: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    """Calculate Network Station Transfer-Free Reachability Analytics."""

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        from railgati.services.network import calculate_station_transfer_free_reach

        result = calculate_station_transfer_free_reach(db, timetable_snapshot_id, station_code)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "no qualifying adjacent" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return result


@router.get(
    "/trains/{train_number}/structural-subsumption",
    response_model=schemas.TrainStructuralSubsumptionResponse,
    summary="Calculate network train route structural subsumption analytics",
    description="Calculates timetable-derived structural route-sequence containment.",
)
def get_train_structural_subsumption(
    train_number: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_train_structural_subsumption

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        return calculate_train_structural_subsumption(db, timetable_snapshot_id, train_number)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.get(
    "/trains/{train_number}/topological-bypasses",
    response_model=schemas.TrainTopologicalBypassResponse,
    summary="Calculate network train route topological bypass analytics",
    description="Calculates historical timetable-derived structural bypass edges for a train route.",
)
def get_train_topological_bypasses(
    train_number: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_train_topological_bypasses

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        return calculate_train_topological_bypasses(db, timetable_snapshot_id, train_number)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.get(
    "/edges/{from_station_code}/{to_station_code}/traversal-dispersion",
    response_model=schemas.EdgeTraversalDispersionResponse,
    summary="Calculate network edge traversal dispersion analytics",
    description="Calculates historical timetable-derived structural routing dispersion for an edge.",
)
def get_edge_traversal_dispersion(
    from_station_code: str,
    to_station_code: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_edge_traversal_dispersion

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        return calculate_edge_traversal_dispersion(
            db, timetable_snapshot_id, from_station_code, to_station_code
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.get(
    "/edges/{from_station_code}/{to_station_code}/route-terminal-dispersion",
    response_model=schemas.EdgeRouteTerminalDispersionResponse,
    summary="Calculate network edge route terminal dispersion analytics",
    description="Calculates historical timetable-derived structural routing terminal dispersion for an edge.",
)
def get_edge_route_terminal_dispersion(
    from_station_code: str,
    to_station_code: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_edge_route_terminal_dispersion

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        return calculate_edge_route_terminal_dispersion(
            db, timetable_snapshot_id, from_station_code, to_station_code
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.get(
    "/edges/{from_station_code}/{to_station_code}/route-co-traversal-affinity",
    response_model=schemas.EdgeRouteCoTraversalAffinityResponse,
    summary="Calculate network edge route co-traversal affinity analytics",
    description="Calculates historical timetable-derived edge co-traversal affinity.",
)
def get_edge_route_co_traversal_affinity(
    from_station_code: str,
    to_station_code: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_edge_route_co_traversal_affinity

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        return calculate_edge_route_co_traversal_affinity(
            db, timetable_snapshot_id, from_station_code, to_station_code
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.get(
    "/trains/{train_number}/maximum-shared-sub-route",
    response_model=schemas.TrainMaxSharedSubRouteResponse,
    summary="Calculate maximum shared sub-route analytics",
    description="Calculates the maximum contiguous shared structural sub-route for a given train.",
)
def get_train_max_shared_sub_route(
    train_number: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_train_max_shared_sub_route

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    try:
        return calculate_train_max_shared_sub_route(db, timetable_snapshot_id, train_number)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.get(
    "/trains/{train_number}/od-exclusivity",
    response_model=schemas.TrainODExclusivityResponse,
    summary="Calculate Train Route O-D Structural Exclusivity Analytics",
    description="Identifies every ordered Origin-Destination station pair served by the target train that no other distinct train identity serves in the same ordered direction within the active timetable snapshot.",
)
def get_train_od_exclusivity(
    train_number: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.services.network import calculate_train_route_od_exclusivity

    try:
        return calculate_train_route_od_exclusivity(db, train_number)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.get(
    "/stations/{from_station_code}/{to_station_code}/route-diversity",
    response_model=schemas.StationPairRouteDiversityResponse,
    summary="Calculate Station Pair Route Diversity Analytics",
    description="Identifies all distinct structural routes (ordered station sequences) connecting two stations in the timetable.",
)
def get_station_pair_route_diversity(
    from_station_code: str,
    to_station_code: str,
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    from railgati.services.network import calculate_station_pair_route_diversity

    try:
        return calculate_station_pair_route_diversity(db, from_station_code, to_station_code)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.get(
    "/stations/{from_station_code}/{to_station_code}/intermediate-hubs",
    response_model=schemas.StationPairIntermediateHubsResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Station not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Validation error"},
    },
)
def get_network_station_pair_intermediate_hubs(
    from_station_code: str,
    to_station_code: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    """Calculate Station Pair Intermediate Flow Concentration Analytics."""
    from railgati.services.network import calculate_station_pair_intermediate_hubs

    try:
        result = calculate_station_pair_intermediate_hubs(db, from_station_code, to_station_code)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        if "No active" in msg:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e

    return result


@router.get(
    "/stations/{from_station_code}/{to_station_code}/route-boundary-confinement",
    response_model=schemas.StationPairRouteBoundaryConfinementResponse,
    tags=["Network", "Station Pairs", "Phase 47"],
)
def api_get_station_pair_route_boundary_confinement(
    from_station_code: str = Path(..., description="Origin station code"),
    to_station_code: str = Path(..., description="Destination station code"),
    db: Session = Depends(get_db),
) -> typing.Any:
    try:
        return calculate_station_pair_route_boundary_confinement(
            db, from_station_code.upper(), to_station_code.upper()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/trains/{train_number}/terminal-incidence",
    response_model=schemas.TrainRouteTerminalIncidenceResponse,
    tags=["Network", "Trains", "Phase 48"],
)
def api_get_train_route_terminal_incidence(
    train_number: str = Path(..., description="Train number"),
    db: Session = Depends(get_db),
) -> typing.Any:
    """Phase 48: Calculate Network Train Route Terminal Incidence Analytics."""
    from railgati.services.network import calculate_train_route_terminal_incidence

    try:
        return calculate_train_route_terminal_incidence(db, train_number)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        if "no active" in msg.lower():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/station-pairs/{origin_code}/{destination_code}/route-extension",
    response_model=schemas.StationPairRouteExtensionResponse,
    tags=["Network", "Station Pairs", "Phase 49"],
)
def api_get_station_pair_route_extension(
    origin_code: str = Path(..., description="Origin station code"),
    destination_code: str = Path(..., description="Destination station code"),
    db: Session = Depends(get_db),
) -> typing.Any:
    """Phase 49: Calculate Network Station Pair Route Extension Analytics."""
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.services.network import calculate_station_pair_route_extension

    try:
        timetable_snapshot_id = get_active_timetable_snapshot_id(db)
        if not timetable_snapshot_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No active timetable snapshot",
            )

        result = calculate_station_pair_route_extension(
            db, origin_code, destination_code, timetable_snapshot_id
        )
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No direct valid traversal found or stations missing",
            )
        return result
    except ValueError as e:
        msg = str(e)
        if "cannot be identical" in msg.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/station-pairs/{origin_code}/{destination_code}/temporal-order-inversions",
    response_model=schemas.StationPairTemporalOrderInversionsResponse,
    summary="Get Network Station-Pair Temporal Order Inversion Analytics",
)
def get_station_pair_temporal_order_inversions(
    origin_code: str,
    destination_code: str,
    db: Session = Depends(get_db),
):
    """Get temporal order inversion analytics for a given station pair on the active snapshot."""
    origin_code = origin_code.upper()
    destination_code = destination_code.upper()
    if origin_code == destination_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Origin and destination stations cannot be identical.",
        )

    from railgati.services.network import calculate_station_pair_temporal_order_inversions

    try:
        timetable_snapshot_id = get_active_timetable_snapshot_id(db)
        if not timetable_snapshot_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No active timetable snapshot",
            )

        from sqlalchemy import func, select

        from railgati.models.station import Station

        origin_station = db.scalar(
            select(Station).filter(func.lower(Station.code) == origin_code.lower())
        )
        dest_station = db.scalar(
            select(Station).filter(func.lower(Station.code) == destination_code.lower())
        )

        if not origin_station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Origin station '{origin_code}' not found.",
            )
        if not dest_station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination station '{destination_code}' not found.",
            )
        result = calculate_station_pair_temporal_order_inversions(
            db, origin_code, destination_code, timetable_snapshot_id
        )
        return result
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/station-pairs/{origin_code}/{destination_code}/intermediate-halt-stratification",
    response_model=schemas.StationPairIntermediateHaltStratificationResponse,
    status_code=status.HTTP_200_OK,
)
def get_station_pair_intermediate_halt_stratification(
    origin_code: str,
    destination_code: str,
    db: Session = Depends(get_db),
) -> schemas.StationPairIntermediateHaltStratificationResponse:
    try:
        timetable_snapshot_id = get_active_timetable_snapshot_id(db)
        if origin_code.lower() == destination_code.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Origin and destination stations cannot be identical.",
            )

        from sqlalchemy import func, select

        from railgati.models.station import Station

        origin_station = db.scalar(
            select(Station).filter(func.lower(Station.code) == origin_code.lower())
        )
        dest_station = db.scalar(
            select(Station).filter(func.lower(Station.code) == destination_code.lower())
        )

        if not origin_station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Origin station '{origin_code}' not found.",
            )
        if not dest_station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination station '{destination_code}' not found.",
            )

        from railgati.services.network import (
            calculate_station_pair_intermediate_halt_stratification,
        )

        result = calculate_station_pair_intermediate_halt_stratification(
            db, origin_code, destination_code, timetable_snapshot_id
        )
        return result
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/station-pairs/{origin_code}/{destination_code}/return-service-adherence",
    response_model=schemas.StationPairReturnServiceAdherenceResponse,
    status_code=status.HTTP_200_OK,
)
def get_station_pair_return_service_adherence(
    origin_code: str,
    destination_code: str,
    db: Session = Depends(get_db),
) -> Any:
    try:
        timetable_snapshot_id = get_active_timetable_snapshot_id(db)
        if origin_code.lower() == destination_code.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Origin and destination stations cannot be identical.",
            )

        from sqlalchemy import func, select

        from railgati.models.station import Station

        origin_station = db.scalar(
            select(Station).filter(func.lower(Station.code) == origin_code.lower())
        )
        dest_station = db.scalar(
            select(Station).filter(func.lower(Station.code) == destination_code.lower())
        )

        if not origin_station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Origin station '{origin_code}' not found.",
            )
        if not dest_station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination station '{destination_code}' not found.",
            )

        from railgati.services.network import (
            calculate_station_pair_return_service_adherence,
        )

        result = calculate_station_pair_return_service_adherence(
            db, origin_code, destination_code, timetable_snapshot_id
        )
        return result
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/stations/{station_code}/simultaneous-presence",
    response_model=schemas.NetworkStationSimultaneousPresenceResponse,
    summary="Phase 53: Network Station Peak Simultaneous Presence Analytics",
)
def get_station_peak_simultaneous_presence(
    station_code: str = Path(..., description="Station code"),
    db: Session = Depends(get_db),
) -> dict[str, typing.Any]:
    try:
        snapshot_id = get_active_timetable_snapshot_id(db)
        if not snapshot_id:
            raise HTTPException(status_code=503, detail="No active timetable snapshot available.")

        from railgati.services.network import calculate_station_peak_simultaneous_presence

        result = calculate_station_peak_simultaneous_presence(db, snapshot_id, station_code)
        return result
    except ValueError as e:
        if "not found" in str(e).lower() and "station" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/trains/{train_number}/stop-temporal-skew",
    response_model=schemas.TrainStopTemporalSkewResponse,
)
def get_train_stop_temporal_skew(
    train_number: str,
    snapshot_id: int = Query(..., description="Timetable Snapshot ID"),
    db: Session = Depends(get_db),
):
    try:
        from railgati.services.network import calculate_train_stop_temporal_skew

        res = calculate_train_stop_temporal_skew(db, snapshot_id, train_number)
        return schemas.TrainStopTemporalSkewResponse(**res)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/trains/{train_number}/sequence-subgraph-density",
    response_model=schemas.TrainSequenceSubgraphDensityResponse,
)
def get_train_sequence_subgraph_density(
    train_number: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    try:
        snapshot_id = get_active_timetable_snapshot_id(db)
        if not snapshot_id:
            raise HTTPException(status_code=503, detail="No active timetable snapshot available.")

        from railgati.services.network import calculate_train_sequence_subgraph_density

        res = calculate_train_sequence_subgraph_density(db, snapshot_id, train_number)
        return schemas.TrainSequenceSubgraphDensityResponse(**res)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower() and "train" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/trains/{train_number}/topological-transition-continuity",
    response_model=schemas.TrainSequenceTopologicalTransitionContinuityResponse,
)
def get_train_sequence_topological_transition_continuity(
    train_number: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    try:
        snapshot_id = get_active_timetable_snapshot_id(db)
        if not snapshot_id:
            raise HTTPException(status_code=503, detail="No active timetable snapshot available.")

        from railgati.services.network import (
            calculate_train_sequence_topological_transition_continuity,
        )

        res = calculate_train_sequence_topological_transition_continuity(
            db, snapshot_id, train_number
        )
        return schemas.TrainSequenceTopologicalTransitionContinuityResponse(**res)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower() and "train" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/trains/{train_number}/disjoint-subpath-reconvergences",
    response_model=schemas.TrainSequenceDisjointSubpathReconvergencesResponse,
    summary="Calculate Train Sequence Disjoint Sub-Path Reconvergences",
    description=(
        "Identifies split-and-remerge topological redundancy by finding pairs of sequence anchors "
        "in the target train where an alternative train diverges, visits a completely disjoint set "
        "of intermediate stations, and reconverges."
    ),
)
def get_train_sequence_disjoint_subpath_reconvergences(
    train_number: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    try:
        snapshot_id = get_active_timetable_snapshot_id(db)
        if not snapshot_id:
            raise HTTPException(status_code=503, detail="No active timetable snapshot available.")

        from railgati.services.network import (
            calculate_train_sequence_disjoint_subpath_reconvergences,
        )

        res = calculate_train_sequence_disjoint_subpath_reconvergences(
            db, snapshot_id, train_number
        )
        return schemas.TrainSequenceDisjointSubpathReconvergencesResponse(**res)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower() and "train" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/trains/{train_number}/topological-degree-extremes",
    response_model=schemas.TrainSequenceTopologicalDegreeExtremesResponse,
    responses={404: {"description": "Train not found"}},
    summary="Get Train Sequence Topological Degree Extremes",
)
def get_train_sequence_topological_degree_extremes(
    train_number: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    """
    Get Phase 58: Train Sequence Topological Degree Extremes.

    Evaluates the discrete local-extrema of global station degree along the ordered sequence of a train.
    """
    try:
        snapshot_id = get_active_timetable_snapshot_id(db)
        if not snapshot_id:
            raise HTTPException(status_code=503, detail="No active timetable snapshot available.")

        from railgati.services.network import calculate_train_sequence_topological_degree_extremes

        res = calculate_train_sequence_topological_degree_extremes(db, snapshot_id, train_number)
        return schemas.TrainSequenceTopologicalDegreeExtremesResponse(**res)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower() and "train" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/stations/{station_code}/neighborhood-subsumption",
    response_model=schemas.StationNeighborhoodTopologicalSubsumptionResponse,
    summary="Get Station Neighborhood Topological Subsumption",
)
def get_station_neighborhood_subsumption(
    station_code: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    """
    Get Phase 59: Station Neighborhood Topological Subsumption.

    Identifies adjacent stations that topologically dominate the target station.
    """
    try:
        from railgati.services.network import calculate_station_neighborhood_subsumption

        res = calculate_station_neighborhood_subsumption(db, station_code)
        return schemas.StationNeighborhoodTopologicalSubsumptionResponse(**res)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower() and "station" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/stations/{station_code}/strict-local-bridges",
    response_model=schemas.StationStrictLocalBridgesResponse,
    summary="Get Station Neighborhood Strict Local Bridge Pairs",
)
def get_station_strict_local_bridges(
    station_code: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    """
    Get Phase 60: Station Neighborhood Strict Local Bridge Pairs.

    Identifies neighbor pairs for which the target station is the exclusive 2-hop bridge.
    """
    try:
        from railgati.services.network import calculate_station_strict_local_bridges

        res = calculate_station_strict_local_bridges(db, station_code)
        return schemas.StationStrictLocalBridgesResponse(**res)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower() and "station" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/trains/{train_number}/single-station-intersections",
    response_model=schemas.TrainSingleStationIntersectionResponse,
    summary="Get Train Route Single-Station Intersections",
    response_model_exclude_none=True,
)
def get_network_train_single_station_intersections(
    train_number: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    """
    Get Phase 61: Train Route Single-Station Intersection Analytics.

    Identifies other trains that intersect the target train at exactly one station identity.
    """
    try:
        from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
        from railgati.services.network import calculate_train_single_station_intersections

        snapshot_id = get_active_timetable_snapshot_id(db)
        res = calculate_train_single_station_intersections(db, snapshot_id, train_number)
        return schemas.TrainSingleStationIntersectionResponse(**res)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower() and "train" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/trains/{train_number}/structural-shortest-path-divergence",
    response_model=schemas.TrainStructuralShortestPathDivergence,
    summary="Train Route Structural Shortest-Path Divergence",
)
def get_network_train_structural_shortest_path_divergence(
    train_number: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    """
    Get Phase 62: Train Route Structural Shortest-Path Divergence.

    Compares the actual number of consecutive timetable network edges traversed
    against the minimum unweighted structural network hops between start and end.
    """
    try:
        from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
        from railgati.services.network import calculate_train_structural_shortest_path_divergence

        snapshot_id = get_active_timetable_snapshot_id(db)
        res = calculate_train_structural_shortest_path_divergence(db, snapshot_id, train_number)
        return schemas.TrainStructuralShortestPathDivergence(**res)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower() and "train" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/stations/{station_code}/junction-through-service",
    response_model=schemas.StationJunctionThroughServiceResponse,
    summary="Station Junction Through-Service Connectivity",
)
def get_network_station_junction_through_service(
    station_code: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    """
    Get Phase 63: Station Junction Through-Service Connectivity.

    Evaluates a station that acts as a structural junction to determine
    the proportion of its topological branch pairings that are explicitly
    traversed by a continuous through-service sequence.
    """
    try:
        from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
        from railgati.services.network import calculate_station_junction_through_service

        snapshot_id = get_active_timetable_snapshot_id(db)
        res = calculate_station_junction_through_service(db, snapshot_id, station_code)
        return schemas.StationJunctionThroughServiceResponse(**res)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower() and "station" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/trains/{train_number}/topological-perimeter-expansion",
    response_model=schemas.TrainTopologicalPerimeterExpansionResponse,
    summary="Train Route Topological Perimeter Expansion",
)
def get_network_train_topological_perimeter_expansion(
    train_number: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    """
    Get Phase 64: Train Route Topological Perimeter Expansion.

    Evaluates the structural 1-hop boundary of an entire train route,
    excluding stations visited by the train itself.
    """
    try:
        from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
        from railgati.services.network import calculate_train_topological_perimeter_expansion

        snapshot_id = get_active_timetable_snapshot_id(db)
        if not snapshot_id:
            raise HTTPException(status_code=503, detail="No active timetable snapshot available.")

        res = calculate_train_topological_perimeter_expansion(db, snapshot_id, train_number)
        return schemas.TrainTopologicalPerimeterExpansionResponse(**res)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower() and "train" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/edges/{from_station_code}/{to_station_code}/topological-resilience-detour",
    response_model=schemas.NetworkEdgeTopologicalResilienceDetourResponse,
)
def get_edge_resilience_detour(
    from_station_code: str,
    to_station_code: str,
    db: Session = Depends(get_db),
):
    """
    Get the exact minimum unweighted alternative path length strictly in G-e.
    """
    if from_station_code.upper() == to_station_code.upper():
        raise HTTPException(
            status_code=400,
            detail="Self-loops are not valid network edges.",
        )

    try:
        from railgati.services.network import get_edge_resilience_detour as get_resilience

        res = get_resilience(db, from_station_code.upper(), to_station_code.upper())
    except ValueError as e:
        if "unavailable" in str(e).lower():
            raise HTTPException(
                status_code=503,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    if res is None:
        raise HTTPException(
            status_code=404,
            detail=f"Edge {from_station_code.upper()} -> {to_station_code.upper()} not found in the active topological graph",
        )

    return res


@router.get(
    "/stations/{station_code}/topological-coreness",
    response_model=schemas.StationTopologicalCorenessResponse,
    summary="Get Station Topological Coreness",
    description="Returns the structural k-core number for the station in the active graph.",
)
def get_station_coreness_endpoint(
    station_code: str = Path(..., description="Station Code (e.g., NDLS)"),
    db: Session = Depends(get_db),
) -> typing.Any:
    try:
        from railgati.services.network import get_station_topological_coreness

        res = get_station_topological_coreness(db, station_code)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(
            status_code=503,
            detail=msg,
        )

    if res is None:
        raise HTTPException(
            status_code=404,
            detail=f"Station {station_code.upper()} has no topological coreness in the active graph",
        )

    return res


@router.get(
    "/edges/{from_station_code}/{to_station_code}/topological-trussness",
    response_model=schemas.NetworkEdgeTopologicalTrussnessResponse,
)
def get_network_edge_topological_trussness_endpoint(
    from_station_code: str,
    to_station_code: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    """
    Get the exact k-truss decomposition topological trussness for the canonical undirected edge.
    """
    if from_station_code.upper() == to_station_code.upper():
        raise HTTPException(
            status_code=400,
            detail="Invalid target: self-loops are not structural network edges.",
        )

    try:
        from railgati.services.network import get_edge_topological_trussness

        res = get_edge_topological_trussness(db, from_station_code.upper(), to_station_code.upper())
    except ValueError as e:
        if "unavailable" in str(e).lower() or "no active" in str(e).lower():
            raise HTTPException(
                status_code=503,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    if res is None:
        raise HTTPException(
            status_code=404,
            detail=f"Edge {from_station_code.upper()} -> {to_station_code.upper()} not found in the active topological graph",
        )

    return res


@router.get(
    "/edges/{from_station_code}/{to_station_code}/topological-quadrangle-support",
    response_model=schemas.NetworkEdgeTopologicalQuadrangleSupportResponse,
)
def get_network_edge_topological_quadrangle_support_endpoint(
    from_station_code: str,
    to_station_code: str,
    db: Session = Depends(get_db),
) -> typing.Any:
    """
    Get the Phase 68 Edge Topological Quadrangle Support for the canonical undirected edge.
    """
    if from_station_code.upper() == to_station_code.upper():
        raise HTTPException(
            status_code=400,
            detail="Invalid target: self-loops are not structural network edges.",
        )

    try:
        from railgati.services.network import get_edge_topological_quadrangle_support

        res = get_edge_topological_quadrangle_support(
            db, from_station_code.upper(), to_station_code.upper()
        )
    except ValueError as e:
        if "unavailable" in str(e).lower() or "no active" in str(e).lower():
            raise HTTPException(
                status_code=503,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    if res is None:
        raise HTTPException(
            status_code=404,
            detail=f"Edge {from_station_code.upper()} -> {to_station_code.upper()} not found in the active topological graph",
        )

    return res
