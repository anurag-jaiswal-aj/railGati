"""Service for graph-based network traversal queries."""

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild
from railgati.models.provenance import DatasetSnapshot


class CorridorItem(BaseModel):
    path: list[str]
    occurrence_count: int
    fastest_duration_minutes: int | None


class StationReachability(BaseModel):
    """Result model for a topologically reachable station."""

    station_id: int
    min_hops: int


class NetworkPath(BaseModel):
    """Result model for a topologically discovered path."""

    hop_count: int
    station_ids: list[int]


class NetworkPathContinuousServiceItem(BaseModel):
    train_number: str
    train_name: str
    train_type: str | None
    start_sequence: int
    end_sequence: int
    departure_time: str | None
    arrival_time: str | None
    start_day_offset: int
    end_day_offset: int
    total_duration_minutes: int | None


def find_reachable_stations(
    db: Session,
    origin_station_id: int,
    max_hops: int,
    timetable_snapshot_id: int,
) -> list[StationReachability]:
    """Find canonical stations reachable from the origin within max_hops using NetworkEdges."""

    if max_hops < 1 or max_hops > 10:
        raise ValueError("max_hops must be between 1 and 10")

    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id
        )
    )
    if not build or build.status != "ACTIVE":
        raise ValueError("Active graph build unavailable for this snapshot")

    # Using raw SQL parameterization for the recursive CTE.
    # It ensures type safety and optimal execution.
    query = text("""
        WITH RECURSIVE reachable AS (
            -- Base case: neighbors of origin
            SELECT
                to_station_id,
                1 AS depth,
                ARRAY[from_station_id, to_station_id] AS visited_ids
            FROM railway_network_edges
            WHERE timetable_snapshot_id = :snapshot_id
              AND from_station_id = :origin_id
              AND to_station_id != :origin_id

            UNION ALL

            -- Recursive case
            SELECT
                e.to_station_id,
                r.depth + 1,
                r.visited_ids || e.to_station_id
            FROM railway_network_edges e
            JOIN reachable r ON e.from_station_id = r.to_station_id
            WHERE e.timetable_snapshot_id = :snapshot_id
              AND r.depth < :max_hops
              AND NOT (e.to_station_id = ANY(r.visited_ids))
        )
        SELECT r.to_station_id, MIN(r.depth) AS min_hops
        FROM reachable r
        JOIN stations s ON r.to_station_id = s.id
        GROUP BY r.to_station_id, s.code
        ORDER BY min_hops ASC, s.code ASC
    """)

    results = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "origin_id": origin_station_id,
            "max_hops": max_hops,
        },
    ).all()

    # If raw query returns records, they will be formatted as tuples
    return [StationReachability(station_id=row[0], min_hops=row[1]) for row in results]


def find_network_paths(
    db: Session,
    timetable_snapshot_id: int,
    origin_station_id: int,
    destination_station_id: int,
    max_hops: int,
    max_paths: int,
) -> list[NetworkPath]:
    """Find simple bounded topology paths from origin to destination."""

    if max_hops < 1 or max_hops > 10:
        raise ValueError("max_hops must be between 1 and 10")
    if max_paths < 1 or max_paths > 50:
        raise ValueError("max_paths must be between 1 and 50")

    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id
        )
    )
    if not build or build.status != "ACTIVE":
        raise ValueError("Active graph build unavailable for this snapshot")

    # If origin is destination, handle explicitly without CTE
    if origin_station_id == destination_station_id:
        return [NetworkPath(hop_count=0, station_ids=[origin_station_id])]

    query = text("""
        WITH RECURSIVE paths AS (
            -- Base case: neighbors of origin
            SELECT
                to_station_id,
                1 AS depth,
                ARRAY[from_station_id, to_station_id] AS visited_ids,
                ARRAY[(SELECT code FROM stations WHERE id = from_station_id), (SELECT code FROM stations WHERE id = to_station_id)]::varchar[] AS path_codes
            FROM railway_network_edges
            WHERE timetable_snapshot_id = :snapshot_id
              AND from_station_id = :origin_id
              AND to_station_id != :origin_id

            UNION ALL

            -- Recursive case
            SELECT
                e.to_station_id,
                p.depth + 1,
                p.visited_ids || e.to_station_id,
                p.path_codes || (SELECT code FROM stations WHERE id = e.to_station_id)
            FROM railway_network_edges e
            JOIN paths p ON e.from_station_id = p.to_station_id
            WHERE e.timetable_snapshot_id = :snapshot_id
              AND p.depth < :max_hops
              AND NOT (e.to_station_id = ANY(p.visited_ids))
        )
        SELECT depth, visited_ids, path_codes
        FROM paths
        WHERE to_station_id = :destination_id
        ORDER BY depth ASC, path_codes ASC
        LIMIT :max_paths
    """)

    results = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "origin_id": origin_station_id,
            "destination_id": destination_station_id,
            "max_hops": max_hops,
            "max_paths": max_paths,
        },
    ).all()

    return [NetworkPath(hop_count=row[0], station_ids=row[1]) for row in results]


class NetworkServiceOccurrence(BaseModel):
    """Internal model for a service-edge occurrence."""

    train_number: str
    train_name: str
    train_type: str | None
    return_train_number: str | None
    from_stop_sequence: int
    to_stop_sequence: int
    departure_time: str | None
    arrival_time: str | None
    duration_minutes: int | None
    source_day_offset: int | None


def find_network_service_occurrences(
    db: Session,
    timetable_snapshot_id: int,
    origin_station_id: int,
    destination_station_id: int,
    limit: int = 500,
) -> list[NetworkServiceOccurrence]:
    """Find historical service-edge occurrences for a given network edge."""

    # Require an ACTIVE timetable snapshot and graph build
    snapshot = db.scalar(
        select(DatasetSnapshot).filter(
            DatasetSnapshot.id == timetable_snapshot_id, DatasetSnapshot.status == "ACTIVE"
        )
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id
        )
    )
    if not build or build.status != "ACTIVE":
        raise ValueError("Active graph build unavailable for this snapshot")

    from railgati.models.graph import RailwayServiceEdge
    from railgati.models.train import Train, TrainObservation

    query = (
        select(
            Train.number.label("train_number"),
            TrainObservation.name.label("train_name"),
            TrainObservation.type.label("train_type"),
            TrainObservation.return_train_number.label("return_train_number"),
            RailwayServiceEdge.from_stop_sequence,
            RailwayServiceEdge.to_stop_sequence,
            RailwayServiceEdge.departure_time,
            RailwayServiceEdge.arrival_time,
            RailwayServiceEdge.duration_minutes,
            RailwayServiceEdge.source_day_offset,
        )
        .select_from(RailwayServiceEdge)
        .join(Train, RailwayServiceEdge.train_id == Train.id)
        .join(
            TrainObservation,
            (RailwayServiceEdge.train_id == TrainObservation.train_id)
            & (TrainObservation.snapshot_id == timetable_snapshot_id),
        )
        .filter(
            RailwayServiceEdge.timetable_snapshot_id == timetable_snapshot_id,
            RailwayServiceEdge.from_station_id == origin_station_id,
            RailwayServiceEdge.to_station_id == destination_station_id,
        )
        .order_by(Train.number.asc(), RailwayServiceEdge.from_stop_sequence.asc())
        .limit(limit)
    )

    results = db.execute(query).all()

    return [
        NetworkServiceOccurrence(
            train_number=row.train_number,
            train_name=row.train_name,
            train_type=row.train_type,
            return_train_number=row.return_train_number,
            from_stop_sequence=row.from_stop_sequence,
            to_stop_sequence=row.to_stop_sequence,
            departure_time=row.departure_time,
            arrival_time=row.arrival_time,
            duration_minutes=row.duration_minutes,
            source_day_offset=row.source_day_offset,
        )
        for row in results
    ]


class NetworkPathAttributionSegmentData(BaseModel):
    """Internal model for a segment of a topological path."""

    from_station_id: int
    to_station_id: int
    occurrences: list[NetworkServiceOccurrence]


def find_network_path_service_occurrences(
    db: Session,
    timetable_snapshot_id: int,
    path_station_ids: list[int],
    limit: int = 500,
) -> list[NetworkPathAttributionSegmentData]:
    """Find historical service-edge occurrences for an entire topological path."""
    if len(path_station_ids) < 2:
        raise ValueError("Path must contain at least 2 stations")
    if len(path_station_ids) > 10:
        raise ValueError("Path cannot contain more than 10 stations")

    for i in range(len(path_station_ids) - 1):
        if path_station_ids[i] == path_station_ids[i + 1]:
            raise ValueError("Path cannot contain consecutive identical stations")

    # Require an ACTIVE timetable snapshot and graph build
    from railgati.models.graph import RailwayGraphBuild
    from railgati.models.provenance import DatasetSnapshot

    snapshot = db.scalar(
        select(DatasetSnapshot).filter(
            DatasetSnapshot.id == timetable_snapshot_id, DatasetSnapshot.status == "ACTIVE"
        )
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id
        )
    )
    if not build or build.status != "ACTIVE":
        raise ValueError("Active graph build unavailable for this snapshot")

    from sqlalchemy import func, tuple_

    from railgati.models.graph import RailwayNetworkEdge, RailwayServiceEdge
    from railgati.models.train import Train, TrainObservation

    segments = [
        (path_station_ids[i], path_station_ids[i + 1]) for i in range(len(path_station_ids) - 1)
    ]
    segment_tuples = [tuple_(s[0], s[1]) for s in segments]

    # Verify that all segments exist in the network graph
    from sqlalchemy import or_, and_
    conditions = [
        and_(RailwayNetworkEdge.from_station_id == s[0], RailwayNetworkEdge.to_station_id == s[1])
        for s in segments
    ]
    matched_edges = db.execute(
        select(RailwayNetworkEdge.from_station_id, RailwayNetworkEdge.to_station_id).filter(
            RailwayNetworkEdge.timetable_snapshot_id == timetable_snapshot_id,
            or_(*conditions)
        )
    ).all()

    matched_set = {(r[0], r[1]) for r in matched_edges}
    for seg in segments:
        if seg not in matched_set:
            raise ValueError(f"Path segment {seg} does not exist in the active network topology")

    # Execute the window function query
    partition_window = func.row_number().over(
        partition_by=[RailwayServiceEdge.from_station_id, RailwayServiceEdge.to_station_id],
        order_by=[Train.number.asc(), RailwayServiceEdge.from_stop_sequence.asc()],
    )

    inner_query = (
        select(
            RailwayServiceEdge.from_station_id,
            RailwayServiceEdge.to_station_id,
            Train.number.label("train_number"),
            TrainObservation.name.label("train_name"),
            TrainObservation.type.label("train_type"),
            TrainObservation.return_train_number.label("return_train_number"),
            RailwayServiceEdge.from_stop_sequence,
            RailwayServiceEdge.to_stop_sequence,
            RailwayServiceEdge.departure_time,
            RailwayServiceEdge.arrival_time,
            RailwayServiceEdge.duration_minutes,
            RailwayServiceEdge.source_day_offset,
            partition_window.label("rn"),
        )
        .select_from(RailwayServiceEdge)
        .join(Train, RailwayServiceEdge.train_id == Train.id)
        .join(
            TrainObservation,
            (RailwayServiceEdge.train_id == TrainObservation.train_id)
            & (TrainObservation.snapshot_id == timetable_snapshot_id),
        )
        .filter(
            RailwayServiceEdge.timetable_snapshot_id == timetable_snapshot_id,
            tuple_(RailwayServiceEdge.from_station_id, RailwayServiceEdge.to_station_id).in_(
                segment_tuples
            ),
        )
    ).subquery()

    query = (
        select(inner_query)
        .filter(inner_query.c.rn <= limit)
        .order_by(
            inner_query.c.from_station_id,
            inner_query.c.to_station_id,
            inner_query.c.train_number.asc(),
            inner_query.c.from_stop_sequence.asc(),
        )
    )

    results = db.execute(query).all()

    # Group by segment
    segment_map: dict[tuple[int, int], list[NetworkServiceOccurrence]] = {
        seg: [] for seg in segments
    }

    for row in results:
        seg = (row.from_station_id, row.to_station_id)
        if seg in segment_map:
            segment_map[seg].append(
                NetworkServiceOccurrence(
                    train_number=row.train_number,
                    train_name=row.train_name,
                    train_type=row.train_type,
                    return_train_number=row.return_train_number,
                    from_stop_sequence=row.from_stop_sequence,
                    to_stop_sequence=row.to_stop_sequence,
                    departure_time=row.departure_time,
                    arrival_time=row.arrival_time,
                    duration_minutes=row.duration_minutes,
                    source_day_offset=row.source_day_offset,
                )
            )

    return [
        NetworkPathAttributionSegmentData(
            from_station_id=seg[0], to_station_id=seg[1], occurrences=segment_map[seg]
        )
        for seg in segments
    ]


def find_network_path_continuous_services(
    db: Session,
    timetable_snapshot_id: int,
    path_station_ids: list[int],
    limit: int = 500,
) -> list[NetworkPathContinuousServiceItem]:
    """Find continuous train services that traverse an entire path."""
    if len(path_station_ids) < 2 or len(path_station_ids) > 10:
        raise ValueError("Path must contain between 2 and 10 stations")

    for i in range(len(path_station_ids) - 1):
        if path_station_ids[i] == path_station_ids[i + 1]:
            raise ValueError("Path cannot contain consecutive duplicate stations")

    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.graph import RailwayGraphBuild

    snapshot = db.scalar(
        select(DatasetSnapshot).filter(
            DatasetSnapshot.id == timetable_snapshot_id, DatasetSnapshot.status == "ACTIVE"
        )
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id
        )
    )
    if not build or build.status != "ACTIVE":
        raise ValueError("Active graph build unavailable for this snapshot")

    from sqlalchemy import func, tuple_, text
    from sqlalchemy.orm import aliased
    from railgati.models.graph import RailwayNetworkEdge, RailwayServiceEdge
    from railgati.models.train import Train, TrainObservation
    from railgati.services.journey import _parse_time_to_minutes

    segments = [
        (path_station_ids[i], path_station_ids[i + 1]) for i in range(len(path_station_ids) - 1)
    ]
    segment_tuples = [tuple_(s[0], s[1]) for s in segments]

    # Verify that all segments exist in the network graph
    from sqlalchemy import or_, and_
    conditions = [
        and_(RailwayNetworkEdge.from_station_id == s[0], RailwayNetworkEdge.to_station_id == s[1])
        for s in segments
    ]
    matched_edges = db.execute(
        select(RailwayNetworkEdge.from_station_id, RailwayNetworkEdge.to_station_id).filter(
            RailwayNetworkEdge.timetable_snapshot_id == timetable_snapshot_id,
            or_(*conditions)
        )
    ).all()

    matched_set = {(r[0], r[1]) for r in matched_edges}
    for seg in segments:
        if seg not in matched_set:
            raise ValueError(f"Path segment {seg} does not exist in the active network topology")

    aliases = [aliased(RailwayServiceEdge) for _ in segments]

    first_alias = aliases[0]
    last_alias = aliases[-1]

    query = (
        select(
            Train.number.label("train_number"),
            TrainObservation.name.label("train_name"),
            TrainObservation.type.label("train_type"),
            first_alias.from_stop_sequence.label("start_sequence"),
            last_alias.to_stop_sequence.label("end_sequence"),
            first_alias.departure_time.label("departure_time"),
            last_alias.arrival_time.label("arrival_time"),
            first_alias.source_day_offset.label("start_day_offset"),
            last_alias.source_day_offset.label("end_day_offset"),
        )
        .select_from(first_alias)
        .join(Train, first_alias.train_id == Train.id)
        .join(
            TrainObservation,
            (TrainObservation.train_id == Train.id)
            & (TrainObservation.snapshot_id == timetable_snapshot_id),
        )
    )

    query = query.filter(
        first_alias.timetable_snapshot_id == timetable_snapshot_id,
        first_alias.from_station_id == segments[0][0],
        first_alias.to_station_id == segments[0][1],
    )

    for i in range(1, len(aliases)):
        prev_alias = aliases[i - 1]
        curr_alias = aliases[i]

        query = query.join(
            curr_alias,
            (curr_alias.train_id == prev_alias.train_id)
            & (curr_alias.timetable_snapshot_id == prev_alias.timetable_snapshot_id)
            & (curr_alias.from_stop_sequence == prev_alias.to_stop_sequence),
        )

        query = query.filter(
            curr_alias.from_station_id == segments[i][0],
            curr_alias.to_station_id == segments[i][1],
        )

    # Apply limits and ordering at the outer query
    query = query.order_by(
        first_alias.departure_time.asc().nulls_last(),
        Train.number.asc(),
        first_alias.from_stop_sequence.asc(),
    ).limit(limit)

    results = db.execute(query).all()

    items = []
    for row in results:
        duration = None
        orig_mins = _parse_time_to_minutes(row.departure_time, row.start_day_offset)
        dest_mins = _parse_time_to_minutes(row.arrival_time, row.end_day_offset)
        if orig_mins is not None and dest_mins is not None:
            calc_dur = dest_mins - orig_mins
            if calc_dur >= 0:
                duration = calc_dur

        items.append(
            NetworkPathContinuousServiceItem(
                train_number=row.train_number,
                train_name=row.train_name,
                train_type=row.train_type,
                start_sequence=row.start_sequence,
                end_sequence=row.end_sequence,
                departure_time=row.departure_time,
                arrival_time=row.arrival_time,
                start_day_offset=row.start_day_offset,
                end_day_offset=row.end_day_offset,
                total_duration_minutes=duration,
            )
        )

    return items


def find_network_corridors(
    db: Session,
    timetable_snapshot_id: int,
    origin_station_id: int,
    destination_station_id: int,
) -> list[CorridorItem]:
    """Discover distinct historical railway corridors between two stations."""
    
    if origin_station_id == destination_station_id:
        raise ValueError("Origin and destination must not be the same")

    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.graph import RailwayGraphBuild

    snapshot = db.scalar(
        select(DatasetSnapshot).filter(
            DatasetSnapshot.id == timetable_snapshot_id, DatasetSnapshot.status == "ACTIVE"
        )
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id
        )
    )
    if not build or build.status != "ACTIVE":
        raise ValueError("Active graph build unavailable for this snapshot")

    is_sqlite = db.bind.dialect.name == "sqlite"

    if is_sqlite:
        query = text("""
            WITH bounds AS (
                SELECT o.train_id, 
                       o.stop_sequence as start_seq, 
                       d.stop_sequence as end_seq,
                       o.departure_time, o.source_day as start_day,
                       d.arrival_time, d.source_day as end_day
                FROM train_stop_observations o
                JOIN train_stop_observations d 
                  ON o.train_id = d.train_id 
                 AND o.snapshot_id = d.snapshot_id
                WHERE o.station_id = :origin 
                  AND d.station_id = :dest 
                  AND o.stop_sequence < d.stop_sequence
                  AND o.snapshot_id = :snapshot
            ),
            occurrence_paths AS (
                SELECT b.train_id,
                       b.start_seq,
                       b.end_seq,
                       group_concat(s.code) as path_array,
                       -- occurrence duration calculated in python for sqlite
                       b.arrival_time, b.end_day, b.departure_time, b.start_day
                FROM bounds b
                JOIN train_stop_observations tso 
                  ON tso.train_id = b.train_id 
                 AND tso.snapshot_id = :snapshot
                JOIN stations s ON tso.station_id = s.id
                WHERE tso.stop_sequence >= b.start_seq 
                  AND tso.stop_sequence <= b.end_seq
                GROUP BY b.train_id, b.start_seq, b.end_seq, b.departure_time, b.start_day, b.arrival_time, b.end_day
                ORDER BY tso.stop_sequence ASC
            )
            SELECT path_array, 
                   COUNT(*) as occurrence_count, 
                   arrival_time, end_day, departure_time, start_day
            FROM occurrence_paths
            GROUP BY path_array, arrival_time, end_day, departure_time, start_day
        """)
        results = db.execute(query, {"snapshot": timetable_snapshot_id, "origin": origin_station_id, "dest": destination_station_id}).all()
        
        # SQLite processing in Python
        from collections import defaultdict
        corridors = defaultdict(lambda: {'count': 0, 'durations': []})
        for row in results:
            path = row[0].split(',') if row[0] else []
            count = row[1]
            arr, end_day, dep, start_day = row[2], row[3], row[4], row[5]
            dur = None
            if arr and end_day and dep and start_day:
                from railgati.services.journey import _parse_time_to_minutes
                orig_mins = _parse_time_to_minutes(dep, start_day)
                dest_mins = _parse_time_to_minutes(arr, end_day)
                if orig_mins is not None and dest_mins is not None:
                    calc = dest_mins - orig_mins
                    if calc >= 0:
                        dur = calc
            corridors[tuple(path)]['count'] += count
            if dur is not None:
                corridors[tuple(path)]['durations'].append(dur)
        
        items = []
        for p, data in corridors.items():
            fastest = min(data['durations']) if data['durations'] else None
            items.append(CorridorItem(path=list(p), occurrence_count=data['count'], fastest_duration_minutes=fastest))
            
        items.sort(key=lambda x: (
            -x.occurrence_count,
            x.fastest_duration_minutes if x.fastest_duration_minutes is not None else float('inf'),
            len(x.path),
            ",".join(x.path)
        ))
        return items

    # Postgres Query
    query = text("""
        WITH bounds AS (
            SELECT o.train_id, 
                   o.stop_sequence as start_seq, 
                   d.stop_sequence as end_seq,
                   o.departure_time, o.source_day as start_day,
                   d.arrival_time, d.source_day as end_day
            FROM train_stop_observations o
            JOIN train_stop_observations d 
              ON o.train_id = d.train_id 
             AND o.snapshot_id = d.snapshot_id
            WHERE o.station_id = :origin 
              AND d.station_id = :dest 
              AND o.stop_sequence < d.stop_sequence
              AND o.snapshot_id = :snapshot
        ),
        occurrence_paths AS (
            SELECT b.train_id,
                   b.start_seq,
                   b.end_seq,
                   array_agg(s.code ORDER BY tso.stop_sequence) as path_array,
                   CASE 
                       WHEN b.arrival_time IS NOT NULL AND b.end_day IS NOT NULL 
                            AND b.departure_time IS NOT NULL AND b.start_day IS NOT NULL
                       THEN 
                           ( (b.end_day - 1) * 1440 + CAST(split_part(b.arrival_time, ':', 1) AS integer) * 60 + CAST(split_part(b.arrival_time, ':', 2) AS integer) ) -
                           ( (b.start_day - 1) * 1440 + CAST(split_part(b.departure_time, ':', 1) AS integer) * 60 + CAST(split_part(b.departure_time, ':', 2) AS integer) )
                       ELSE NULL
                   END as duration
            FROM bounds b
            JOIN train_stop_observations tso 
              ON tso.train_id = b.train_id 
             AND tso.snapshot_id = :snapshot
            JOIN stations s ON tso.station_id = s.id
            WHERE tso.stop_sequence >= b.start_seq 
              AND tso.stop_sequence <= b.end_seq
            GROUP BY b.train_id, b.start_seq, b.end_seq, b.departure_time, b.start_day, b.arrival_time, b.end_day
        ),
        corridor_aggregation AS (
            SELECT path_array, 
                   COUNT(*) as occurrence_count, 
                   MIN(duration) as fastest_duration_minutes
            FROM occurrence_paths
            GROUP BY path_array
        )
        SELECT path_array, occurrence_count, fastest_duration_minutes
        FROM corridor_aggregation
        ORDER BY occurrence_count DESC, 
                 fastest_duration_minutes ASC NULLS LAST, 
                 array_length(path_array, 1) ASC, 
                 array_to_string(path_array, ',') ASC
    """)

    results = db.execute(
        query,
        {
            "snapshot": timetable_snapshot_id,
            "origin": origin_station_id,
            "dest": destination_station_id,
        },
    ).all()

    items = []
    for row in results:
        dur = row[2]
        if dur is not None and dur < 0:
            dur = None
        items.append(
            CorridorItem(
                path=row[0],
                occurrence_count=row[1],
                fastest_duration_minutes=dur,
            )
        )
    return items
