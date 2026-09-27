"""Network reachability API endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from railgati.api.v1 import schemas
from railgati.api.v1.schemas import (
    NetworkPathAttributionResponse,
    NetworkPathItem,
    NetworkPathResponse,
    NetworkPathStation,
    NetworkReachabilityItem,
    NetworkReachabilityResponse,
    NetworkServiceAttributionResponse,
)
from railgati.api.v1.snapshots import (
    get_active_station_snapshot_id,
    get_active_timetable_snapshot_id,
)
from railgati.db import get_db
from railgati.models.station import Station, StationObservation
from railgati.services.network import (
    calculate_edge_volume,
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


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
