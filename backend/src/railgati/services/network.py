"""Service for graph-based network traversal queries."""

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from railgati.api.v1.schemas import (
    ComplexityItem,
    DwellItem,
    EdgeAsymmetryItem,
    EdgeVolumeItem,
    FlowItem,
    HubCentralityItem,
    TemporalConcentrationItem,
    TerminusItem,
)
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
    from sqlalchemy import and_, or_

    conditions = [
        and_(RailwayNetworkEdge.from_station_id == s[0], RailwayNetworkEdge.to_station_id == s[1])
        for s in segments
    ]
    matched_edges = db.execute(
        select(RailwayNetworkEdge.from_station_id, RailwayNetworkEdge.to_station_id).filter(
            RailwayNetworkEdge.timetable_snapshot_id == timetable_snapshot_id, or_(*conditions)
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

    from sqlalchemy import tuple_
    from sqlalchemy.orm import aliased

    from railgati.models.graph import RailwayNetworkEdge, RailwayServiceEdge
    from railgati.models.train import Train, TrainObservation
    from railgati.services.journey import _parse_time_to_minutes

    segments = [
        (path_station_ids[i], path_station_ids[i + 1]) for i in range(len(path_station_ids) - 1)
    ]
    segment_tuples = [tuple_(s[0], s[1]) for s in segments]

    # Verify that all segments exist in the network graph
    from sqlalchemy import and_, or_

    conditions = [
        and_(RailwayNetworkEdge.from_station_id == s[0], RailwayNetworkEdge.to_station_id == s[1])
        for s in segments
    ]
    matched_edges = db.execute(
        select(RailwayNetworkEdge.from_station_id, RailwayNetworkEdge.to_station_id).filter(
            RailwayNetworkEdge.timetable_snapshot_id == timetable_snapshot_id, or_(*conditions)
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
        results = db.execute(
            query,
            {
                "snapshot": timetable_snapshot_id,
                "origin": origin_station_id,
                "dest": destination_station_id,
            },
        ).all()

        # SQLite processing in Python
        from collections import defaultdict

        corridors = defaultdict(lambda: {"count": 0, "durations": []})
        for row in results:
            path = row[0].split(",") if row[0] else []
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
            corridors[tuple(path)]["count"] += count
            if dur is not None:
                corridors[tuple(path)]["durations"].append(dur)

        items = []
        for p, data in corridors.items():
            fastest = min(data["durations"]) if data["durations"] else None
            items.append(
                CorridorItem(
                    path=list(p), occurrence_count=data["count"], fastest_duration_minutes=fastest
                )
            )

        items.sort(
            key=lambda x: (
                -x.occurrence_count,
                x.fastest_duration_minutes
                if x.fastest_duration_minutes is not None
                else float("inf"),
                len(x.path),
                ",".join(x.path),
            )
        )
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


def calculate_hub_centrality(
    db: Session, timetable_snapshot_id: int, limit: int = 50, sort_by: str = "service_volume"
) -> list[HubCentralityItem]:
    """Compute network hub centrality analytics for a given snapshot."""

    from railgati.api.v1.snapshots import get_active_station_snapshot_id
    from railgati.models.graph import RailwayGraphBuild
    from railgati.models.provenance import DatasetSnapshot

    # 1. Active Timetable Snapshot check
    snapshot = db.scalar(
        select(DatasetSnapshot).filter(
            DatasetSnapshot.id == timetable_snapshot_id, DatasetSnapshot.status == "ACTIVE"
        )
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    # 2. Active Graph Build check
    build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id
        )
    )
    if not build or build.status != "ACTIVE":
        raise ValueError("Active graph build unavailable for this snapshot")

    # 3. Active Station Snapshot
    station_snapshot_id = get_active_station_snapshot_id(db)
    if not station_snapshot_id:
        raise ValueError("Active station snapshot not found")

    # The query calculates the out-degree and outbound volume, and in-degree and inbound volume,
    # then full outer joins them, then inner joins to stations for canonical metadata.
    # Note: the full outer join on station_id is needed if a station has only incoming or only outgoing edges.

    query = text("""
        WITH out_stats AS (
            SELECT from_station_id as station_id,
                   COUNT(*) as out_degree,
                   SUM(train_count) as outbound_vol
            FROM railway_network_edges
            WHERE timetable_snapshot_id = :snapshot_id
            GROUP BY from_station_id
        ),
        in_stats AS (
            SELECT to_station_id as station_id,
                   COUNT(*) as in_degree,
                   SUM(train_count) as inbound_vol
            FROM railway_network_edges
            WHERE timetable_snapshot_id = :snapshot_id
            GROUP BY to_station_id
        ),
        merged_stats AS (
            SELECT
                COALESCE(o.station_id, i.station_id) as station_id,
                COALESCE(o.out_degree, 0) as out_degree,
                COALESCE(i.in_degree, 0) as in_degree,
                COALESCE(o.outbound_vol, 0) as outbound_vol,
                COALESCE(i.inbound_vol, 0) as inbound_vol
            FROM out_stats o
            FULL OUTER JOIN in_stats i ON o.station_id = i.station_id
        )
        SELECT
            s.code,
            so.name,
            m.out_degree,
            m.in_degree,
            (m.out_degree + m.in_degree) as total_degree,
            CAST(m.outbound_vol AS INTEGER) as outbound_vol,
            CAST(m.inbound_vol AS INTEGER) as inbound_vol,
            CAST((m.outbound_vol + m.inbound_vol) AS INTEGER) as total_vol
        FROM merged_stats m
        JOIN stations s ON m.station_id = s.id
        JOIN station_observations so ON so.station_id = s.id
        WHERE so.snapshot_id = :station_snapshot_id
    """)

    results = db.execute(
        query, {"snapshot_id": timetable_snapshot_id, "station_snapshot_id": station_snapshot_id}
    ).all()

    items = []
    for row in results:
        items.append(
            HubCentralityItem(
                station_code=row.code,
                station_name=row.name,
                out_degree=row.out_degree,
                in_degree=row.in_degree,
                total_topological_degree=row.total_degree,
                outbound_service_occurrence_volume=row.outbound_vol,
                inbound_service_occurrence_volume=row.inbound_vol,
                combined_occurrence_volume=row.total_vol,
            )
        )

    # In-memory sorting as requested to apply deterministic sort rules
    if sort_by == "out_degree":
        items.sort(
            key=lambda x: (
                -x.out_degree,
                -x.total_topological_degree,
                -x.combined_occurrence_volume,
                x.station_code,
            )
        )
    elif sort_by == "in_degree":
        items.sort(
            key=lambda x: (
                -x.in_degree,
                -x.total_topological_degree,
                -x.combined_occurrence_volume,
                x.station_code,
            )
        )
    elif sort_by == "service_volume":
        items.sort(
            key=lambda x: (
                -x.combined_occurrence_volume,
                -x.total_topological_degree,
                x.station_code,
            )
        )
    else:
        raise ValueError(f"Invalid sort_by value: {sort_by}")

    return items[:limit]


def calculate_edge_volume(
    db: Session, timetable_snapshot_id: int, limit: int = 50
) -> list[EdgeVolumeItem]:
    """Calculate edge volume directly from historical RailwayNetworkEdge occurrences.

    Args:
        db: Database session.
        timetable_snapshot_id: Active timetable snapshot ID.
        limit: Number of edges to return.

    Returns:
        List of EdgeVolumeItem.

    Raises:
        ValueError: If graph build is not ACTIVE or snapshot is invalid.
    """
    build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id,
            RailwayGraphBuild.status == "ACTIVE",
        )
    )
    if not build:
        raise ValueError(
            f"No ACTIVE RailwayGraphBuild found for timetable snapshot {timetable_snapshot_id}"
        )

    station_snapshot_id = db.scalar(
        select(DatasetSnapshot.id)
        .filter(DatasetSnapshot.status == "ACTIVE")
        .filter(
            DatasetSnapshot.id.in_(
                select(text("station_observations.snapshot_id FROM station_observations"))
            )
        )
        .order_by(DatasetSnapshot.retrieved_at.desc())
        .limit(1)
    )
    if not station_snapshot_id:
        # Fallback if the subquery text strategy fails in dialect:
        res = db.execute(text("SELECT snapshot_id FROM station_observations LIMIT 1")).scalar()
        if res:
            station_snapshot_id = res

    query = text("""
        SELECT
            fs.code as from_station_code,
            fso.name as from_station_name,
            ts.code as to_station_code,
            tso.name as to_station_name,
            CAST(e.train_count AS INTEGER) as service_occurrence_volume
        FROM railway_network_edges e
        JOIN stations fs ON e.from_station_id = fs.id
        JOIN stations ts ON e.to_station_id = ts.id
        JOIN station_observations fso ON fso.station_id = fs.id
        JOIN station_observations tso ON tso.station_id = ts.id
        WHERE e.timetable_snapshot_id = :timetable_snapshot_id
          AND fso.snapshot_id = :station_snapshot_id
          AND tso.snapshot_id = :station_snapshot_id
        ORDER BY e.train_count DESC, fs.code ASC, ts.code ASC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {
            "timetable_snapshot_id": timetable_snapshot_id,
            "station_snapshot_id": station_snapshot_id,
            "limit": limit,
        },
    ).fetchall()

    return [
        EdgeVolumeItem(
            from_station_code=row.from_station_code,
            from_station_name=row.from_station_name,
            to_station_code=row.to_station_code,
            to_station_name=row.to_station_name,
            service_occurrence_volume=row.service_occurrence_volume,
        )
        for row in results
    ]


def calculate_network_termini(
    db: Session, timetable_snapshot_id: int, limit: int = 50
) -> list[TerminusItem]:
    """
    Computes historical timetable occurrence boundaries (originating/terminating counts)
    for all stations in the specified active timetable snapshot.

    A train occurrence's absolute first stop contributes +1 to originating_count.
    A train occurrence's absolute last stop contributes +1 to terminating_count.

    Args:
        db: SQLAlchemy session.
        timetable_snapshot_id: The ID of the active timetable snapshot.
        limit: Max number of stations to return (default 50).

    Returns:
        List of TerminusItem.

    Raises:
        ValueError: If snapshot is invalid or active station snapshot missing.
    """
    station_snapshot_id = db.scalar(
        select(DatasetSnapshot.id)
        .filter(DatasetSnapshot.status == "ACTIVE")
        .filter(
            DatasetSnapshot.id.in_(
                select(text("station_observations.snapshot_id FROM station_observations"))
            )
        )
        .order_by(DatasetSnapshot.retrieved_at.desc())
        .limit(1)
    )
    if not station_snapshot_id:
        res = db.execute(text("SELECT snapshot_id FROM station_observations LIMIT 1")).scalar()
        if res:
            station_snapshot_id = res

    query = text("""
        WITH train_bounds AS (
            SELECT
                train_id,
                MIN(stop_sequence) as start_seq,
                MAX(stop_sequence) as end_seq
            FROM train_stop_observations
            WHERE snapshot_id = :timetable_snapshot_id
            GROUP BY train_id
        ),
        termini AS (
            SELECT
                tso.station_id,
                SUM(CASE WHEN tso.stop_sequence = tb.start_seq THEN 1 ELSE 0 END) as originating_count,
                SUM(CASE WHEN tso.stop_sequence = tb.end_seq THEN 1 ELSE 0 END) as terminating_count
            FROM train_stop_observations tso
            JOIN train_bounds tb ON tso.train_id = tb.train_id
            WHERE tso.snapshot_id = :timetable_snapshot_id
              AND (tso.stop_sequence = tb.start_seq OR tso.stop_sequence = tb.end_seq)
            GROUP BY tso.station_id
        )
        SELECT
            s.code as station_code,
            so.name as station_name,
            CAST(t.originating_count AS INTEGER) as originating_count,
            CAST(t.terminating_count AS INTEGER) as terminating_count,
            CAST(t.originating_count + t.terminating_count AS INTEGER) as total_terminus_volume
        FROM termini t
        JOIN stations s ON t.station_id = s.id
        JOIN station_observations so ON so.station_id = s.id
        WHERE so.snapshot_id = :station_snapshot_id
        ORDER BY
            (t.originating_count + t.terminating_count) DESC,
            t.originating_count DESC,
            t.terminating_count DESC,
            s.code ASC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {
            "timetable_snapshot_id": timetable_snapshot_id,
            "station_snapshot_id": station_snapshot_id,
            "limit": limit,
        },
    ).fetchall()

    return [
        TerminusItem(
            station_code=row.station_code,
            station_name=row.station_name,
            originating_count=row.originating_count,
            terminating_count=row.terminating_count,
            total_terminus_volume=row.total_terminus_volume,
        )
        for row in results
    ]


def calculate_network_flows(
    db: Session, timetable_snapshot_id: int, limit: int = 50
) -> list[FlowItem]:
    """
    Computes global Origin-Destination flow density.
    Identifies the strongest structural flows between absolute timetable occurrence boundaries.

    Args:
        db: SQLAlchemy session.
        timetable_snapshot_id: The ID of the active timetable snapshot.
        limit: Max number of pairs to return (default 50).

    Returns:
        List of FlowItem.

    Raises:
        ValueError: If snapshot is invalid or active station snapshot missing.
    """
    station_snapshot_id = db.scalar(
        select(DatasetSnapshot.id)
        .filter(DatasetSnapshot.status == "ACTIVE")
        .filter(
            DatasetSnapshot.id.in_(
                select(text("station_observations.snapshot_id FROM station_observations"))
            )
        )
        .order_by(DatasetSnapshot.retrieved_at.desc())
        .limit(1)
    )
    if not station_snapshot_id:
        res = db.execute(text("SELECT snapshot_id FROM station_observations LIMIT 1")).scalar()
        if res:
            station_snapshot_id = res

    query = text("""
        WITH train_bounds AS (
            SELECT
                train_id,
                MIN(stop_sequence) as start_seq,
                MAX(stop_sequence) as end_seq
            FROM train_stop_observations
            WHERE snapshot_id = :timetable_snapshot_id
            GROUP BY train_id
        ),
        od_pairs AS (
            SELECT
                t_start.station_id as origin_id,
                t_end.station_id as dest_id,
                COUNT(tb.train_id) as flow_volume
            FROM train_bounds tb
            JOIN train_stop_observations t_start
              ON tb.train_id = t_start.train_id
             AND tb.start_seq = t_start.stop_sequence
             AND t_start.snapshot_id = :timetable_snapshot_id
            JOIN train_stop_observations t_end
              ON tb.train_id = t_end.train_id
             AND tb.end_seq = t_end.stop_sequence
             AND t_end.snapshot_id = :timetable_snapshot_id
            GROUP BY t_start.station_id, t_end.station_id
        )
        SELECT
            s_org.code as origin_station_code,
            so_org.name as origin_station_name,
            s_dest.code as destination_station_code,
            so_dest.name as destination_station_name,
            CAST(od.flow_volume AS INTEGER) as flow_volume
        FROM od_pairs od
        JOIN stations s_org ON od.origin_id = s_org.id
        JOIN station_observations so_org ON so_org.station_id = s_org.id
        JOIN stations s_dest ON od.dest_id = s_dest.id
        JOIN station_observations so_dest ON so_dest.station_id = s_dest.id
        WHERE so_org.snapshot_id = :station_snapshot_id
          AND so_dest.snapshot_id = :station_snapshot_id
        ORDER BY
            od.flow_volume DESC,
            s_org.code ASC,
            s_dest.code ASC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {
            "timetable_snapshot_id": timetable_snapshot_id,
            "station_snapshot_id": station_snapshot_id,
            "limit": limit,
        },
    ).fetchall()

    return [
        FlowItem(
            origin_station_code=row.origin_station_code,
            origin_station_name=row.origin_station_name,
            destination_station_code=row.destination_station_code,
            destination_station_name=row.destination_station_name,
            flow_volume=row.flow_volume,
        )
        for row in results
    ]


def calculate_network_dwells(
    db: Session, timetable_snapshot_id: int, limit: int = 50, min_transit_count: int = 10
) -> list[DwellItem]:
    """
    Computes global Station Dwell Analytics.
    Identifies stations with the highest average scheduled dwell duration for transit occurrences.

    Args:
        db: SQLAlchemy session.
        timetable_snapshot_id: The ID of the active timetable snapshot.
        limit: Max number of stations to return (default 50).
        min_transit_count: Minimum transit occurrences required to be included.

    Returns:
        List of DwellItem.

    Raises:
        ValueError: If active station snapshot is missing.
    """
    station_snapshot_id = db.scalar(
        select(DatasetSnapshot.id)
        .filter(DatasetSnapshot.status == "ACTIVE")
        .filter(
            DatasetSnapshot.id.in_(
                select(text("station_observations.snapshot_id FROM station_observations"))
            )
        )
        .order_by(DatasetSnapshot.retrieved_at.desc())
        .limit(1)
    )
    if not station_snapshot_id:
        res = db.execute(text("SELECT snapshot_id FROM station_observations LIMIT 1")).scalar()
        if res:
            station_snapshot_id = res

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"

    if is_sqlite:
        time_diff_expr = """
            (strftime("%s", "1970-01-01 " || departure_time) - strftime("%s", "1970-01-01 " || arrival_time)) +
            CASE WHEN strftime("%s", "1970-01-01 " || departure_time) < strftime("%s", "1970-01-01 " || arrival_time)
                 THEN 86400 ELSE 0 END
        """
    else:
        time_diff_expr = """
            (EXTRACT(EPOCH FROM departure_time::time) - EXTRACT(EPOCH FROM arrival_time::time)) +
            CASE WHEN EXTRACT(EPOCH FROM departure_time::time) < EXTRACT(EPOCH FROM arrival_time::time)
                 THEN 86400 ELSE 0 END
        """

    query = text(f"""
        WITH train_bounds AS (
            SELECT
                train_id,
                MIN(stop_sequence) as min_seq,
                MAX(stop_sequence) as max_seq
            FROM train_stop_observations
            WHERE snapshot_id = :timetable_snapshot_id
            GROUP BY train_id
        ),
        transit_stops AS (
            SELECT
                tso.station_id,
                tso.train_id,
                tso.arrival_time,
                tso.departure_time
            FROM train_stop_observations tso
            JOIN train_bounds tb ON tso.train_id = tb.train_id
            WHERE tso.snapshot_id = :timetable_snapshot_id
              AND tso.stop_sequence > tb.min_seq
              AND tso.stop_sequence < tb.max_seq
              AND tso.arrival_time IS NOT NULL
              AND tso.departure_time IS NOT NULL
              AND tso.arrival_time != 'None'
              AND tso.departure_time != 'None'
              AND tso.arrival_time != tso.departure_time
        ),
        dwell_stats AS (
            SELECT
                station_id,
                COUNT(train_id) as transit_count,
                AVG({time_diff_expr}) / 60.0 as avg_dwell_minutes
            FROM transit_stops
            GROUP BY station_id
            HAVING COUNT(train_id) >= :min_transit_count
        )
        SELECT
            s.code as station_code,
            so.name as station_name,
            CAST(ds.avg_dwell_minutes AS FLOAT) as avg_dwell_minutes,
            CAST(ds.transit_count AS INTEGER) as transit_count
        FROM dwell_stats ds
        JOIN stations s ON ds.station_id = s.id
        JOIN station_observations so ON so.station_id = s.id
        WHERE so.snapshot_id = :station_snapshot_id
        ORDER BY
            ds.avg_dwell_minutes DESC,
            ds.transit_count DESC,
            s.code ASC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {
            "timetable_snapshot_id": timetable_snapshot_id,
            "station_snapshot_id": station_snapshot_id,
            "limit": limit,
            "min_transit_count": min_transit_count,
        },
    ).fetchall()

    return [
        DwellItem(
            station_code=row.station_code,
            station_name=row.station_name,
            avg_dwell_minutes=row.avg_dwell_minutes,
            transit_count=row.transit_count,
        )
        for row in results
    ]


def calculate_network_complexities(
    db: Session,
    timetable_snapshot_id: int,
    station_snapshot_id: int,
    limit: int = 50,
    min_service_count: int = 10,
) -> list[ComplexityItem]:
    """
    Calculate the historical station route complexity.

    This derives the average scheduled route length (in total stops)
    for all canonical train occurrences visiting a station in the snapshot.
    """
    query = text("""
        WITH train_lengths AS (
            SELECT
                train_id,
                COUNT(*) as total_stops
            FROM train_stop_observations
            WHERE snapshot_id = :timetable_snapshot_id
            GROUP BY train_id
        ),
        station_avg_length AS (
            SELECT
                tso.station_id,
                COUNT(tso.train_id) as service_count,
                AVG(tl.total_stops) as avg_route_stops
            FROM train_stop_observations tso
            JOIN train_lengths tl ON tso.train_id = tl.train_id
            WHERE tso.snapshot_id = :timetable_snapshot_id
            GROUP BY tso.station_id
            HAVING COUNT(tso.train_id) >= :min_service_count
        )
        SELECT
            s.code as station_code,
            so.name as station_name,
            CAST(s_avg.avg_route_stops AS FLOAT) as avg_route_stops,
            CAST(s_avg.service_count AS INTEGER) as service_count
        FROM station_avg_length s_avg
        JOIN stations s ON s_avg.station_id = s.id
        JOIN station_observations so ON so.station_id = s.id
        WHERE so.snapshot_id = :station_snapshot_id
        ORDER BY
            s_avg.avg_route_stops DESC,
            s_avg.service_count DESC,
            s.code ASC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {
            "timetable_snapshot_id": timetable_snapshot_id,
            "station_snapshot_id": station_snapshot_id,
            "limit": limit,
            "min_service_count": min_service_count,
        },
    ).fetchall()

    return [
        ComplexityItem(
            station_code=row.station_code,
            station_name=row.station_name,
            avg_route_stops=row.avg_route_stops,
            service_count=row.service_count,
        )
        for row in results
    ]


def calculate_network_temporal_concentration(
    db: Session,
    timetable_snapshot_id: int,
    station_snapshot_id: int,
    limit: int = 50,
    min_service_count: int = 15,
) -> list[TemporalConcentrationItem]:
    """
    Calculate the historical station temporal concentration (calendar-hour peak).

    This derives the maximum occurrences in any fixed calendar hour as a percentage
    of total occurrences for stations in the active snapshot.
    """
    is_sqlite = db.bind and db.bind.dialect.name == "sqlite"
    hour_extract = (
        "CAST(strftime('%H', COALESCE(departure_time, arrival_time)) AS INTEGER)"
        if is_sqlite
        else "CAST(EXTRACT(HOUR FROM CAST(COALESCE(departure_time, arrival_time) AS time)) AS INTEGER)"
    )

    query = text(f"""
        WITH station_events AS (
            SELECT
                station_id,
                {hour_extract} as event_hour
            FROM train_stop_observations
            WHERE snapshot_id = :timetable_snapshot_id
              AND (departure_time IS NOT NULL OR arrival_time IS NOT NULL)
        ),
        station_peak AS (
            SELECT
                station_id,
                event_hour,
                COUNT(*) as hour_volume
            FROM station_events
            GROUP BY station_id, event_hour
        ),
        station_max AS (
            SELECT
                station_id,
                MAX(hour_volume) as peak_hour_volume,
                SUM(hour_volume) as total_volume
            FROM station_peak
            GROUP BY station_id
            HAVING SUM(hour_volume) >= :min_service_count
        )
        SELECT
            s.code as station_code,
            so.name as station_name,
            CAST(sm.peak_hour_volume AS INTEGER) as peak_hour_volume,
            CAST(sm.total_volume AS INTEGER) as total_volume,
            CAST(ROUND(sm.peak_hour_volume * 100.0 / sm.total_volume, 1) AS FLOAT) as concentration_pct,
            (
                SELECT sp.event_hour
                FROM station_peak sp
                WHERE sp.station_id = sm.station_id
                  AND sp.hour_volume = sm.peak_hour_volume
                ORDER BY sp.event_hour ASC
                LIMIT 1
            ) as peak_hour_val
        FROM station_max sm
        JOIN stations s ON sm.station_id = s.id
        JOIN station_observations so ON so.station_id = s.id
        WHERE so.snapshot_id = :station_snapshot_id
        ORDER BY
            concentration_pct DESC,
            sm.total_volume DESC,
            s.code ASC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {
            "timetable_snapshot_id": timetable_snapshot_id,
            "station_snapshot_id": station_snapshot_id,
            "limit": limit,
            "min_service_count": min_service_count,
        },
    ).fetchall()

    return [
        TemporalConcentrationItem(
            station_code=row.station_code,
            station_name=row.station_name,
            peak_hour_val=row.peak_hour_val,
            peak_hour_volume=row.peak_hour_volume,
            total_volume=row.total_volume,
            concentration_pct=row.concentration_pct,
        )
        for row in results
    ]


def calculate_network_edge_asymmetry(
    db: Session,
    timetable_snapshot_id: int,
    station_snapshot_id: int,
    limit: int = 50,
    min_total_volume: int = 15,
) -> list[EdgeAsymmetryItem]:
    """
    Calculate Network Directional Edge Asymmetry (Flow Imbalance).

    Identifies track segments scheduled primarily as one-way loops vs symmetrical corridors.
    """
    graph_build = (
        db.query(RailwayGraphBuild)
        .filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id,
            RailwayGraphBuild.status == "ACTIVE",
        )
        .first()
    )

    if not graph_build:
        raise ValueError(f"No ACTIVE graph build found for snapshot {timetable_snapshot_id}")

    is_sqlite = db.bind and db.bind.dialect.name == "sqlite"
    least_func = "MIN" if is_sqlite else "LEAST"
    greatest_func = "MAX" if is_sqlite else "GREATEST"

    query = text(f"""
        WITH paired AS (
            SELECT
                {least_func}(from_station_id, to_station_id) as node_a,
                {greatest_func}(from_station_id, to_station_id) as node_b,
                SUM(CASE WHEN from_station_id = {least_func}(from_station_id, to_station_id) THEN train_count ELSE 0 END) as vol_ab,
                SUM(CASE WHEN from_station_id = {greatest_func}(from_station_id, to_station_id) THEN train_count ELSE 0 END) as vol_ba
            FROM railway_network_edges
            WHERE timetable_snapshot_id = :timetable_snapshot_id
            GROUP BY {least_func}(from_station_id, to_station_id), {greatest_func}(from_station_id, to_station_id)
        ),
        asymmetry AS (
            SELECT
                node_a,
                node_b,
                vol_ab,
                vol_ba,
                (vol_ab + vol_ba) as total_vol,
                CASE
                    WHEN (vol_ab + vol_ba) = 0 THEN 0
                    ELSE ROUND(CAST(ABS(vol_ab - vol_ba) AS FLOAT) / CAST(vol_ab + vol_ba AS FLOAT) * 100.0, 1)
                END as asymmetry_pct
            FROM paired
            WHERE (vol_ab + vol_ba) >= :min_total_volume
        )
        SELECT
            CASE WHEN s1.code < s2.code THEN s1.code ELSE s2.code END as station_a_code,
            CASE WHEN s1.code < s2.code THEN so1.name ELSE so2.name END as station_a_name,
            CASE WHEN s1.code < s2.code THEN s2.code ELSE s1.code END as station_b_code,
            CASE WHEN s1.code < s2.code THEN so2.name ELSE so1.name END as station_b_name,
            CAST(CASE WHEN s1.code < s2.code THEN a.vol_ab ELSE a.vol_ba END AS INTEGER) as forward_volume,
            CAST(CASE WHEN s1.code < s2.code THEN a.vol_ba ELSE a.vol_ab END AS INTEGER) as reverse_volume,
            CAST(a.total_vol AS INTEGER) as total_volume,
            CAST(a.asymmetry_pct AS FLOAT) as asymmetry_pct
        FROM asymmetry a
        JOIN stations s1 ON a.node_a = s1.id
        JOIN stations s2 ON a.node_b = s2.id
        JOIN station_observations so1 ON so1.station_id = s1.id
        JOIN station_observations so2 ON so2.station_id = s2.id
        WHERE so1.snapshot_id = :station_snapshot_id
          AND so2.snapshot_id = :station_snapshot_id
        ORDER BY
            a.asymmetry_pct DESC,
            a.total_vol DESC,
            station_a_code ASC,
            station_b_code ASC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {
            "timetable_snapshot_id": timetable_snapshot_id,
            "station_snapshot_id": station_snapshot_id,
            "min_total_volume": min_total_volume,
            "limit": limit,
        },
    ).fetchall()

    return [
        EdgeAsymmetryItem(
            station_a_code=row.station_a_code,
            station_a_name=row.station_a_name,
            station_b_code=row.station_b_code,
            station_b_name=row.station_b_name,
            forward_volume=row.forward_volume,
            reverse_volume=row.reverse_volume,
            total_volume=row.total_volume,
            asymmetry_pct=row.asymmetry_pct,
        )
        for row in results
    ]


def calculate_train_similarity(
    db: Session,
    timetable_snapshot_id: int,
    target_train_number: str,
    limit: int = 10,
    min_overlap_stations: int = 1,
) -> tuple[int, str, str, list[TrainSimilarityItem]]:
    """Calculate historical timetable route-set similarity for a target train."""
    from sqlalchemy import func

    from railgati.api.v1.schemas import TrainSimilarityItem
    from railgati.models.train import Train, TrainObservation

    # 1. Resolve target train ID and metadata in the active snapshot
    target_train = db.execute(
        select(Train.id, Train.number, TrainObservation.name)
        .join(TrainObservation, TrainObservation.train_id == Train.id)
        .filter(
            TrainObservation.snapshot_id == timetable_snapshot_id,
            func.lower(Train.number) == target_train_number.lower(),
        )
    ).first()

    if not target_train:
        raise ValueError(f"Historical train timetable for '{target_train_number}' not found.")

    target_train_id = target_train.id
    target_train_number_resolved = target_train.number
    target_train_name = target_train.name

    query = text("""
        WITH target_stations AS (
            SELECT DISTINCT station_id
            FROM train_stop_observations
            WHERE snapshot_id = :timetable_snapshot_id
              AND train_id = :target_train_id
        ),
        target_count AS (
            SELECT COUNT(*) AS c FROM target_stations
        ),
        other_trains AS (
            SELECT train_id, COUNT(DISTINCT station_id) as total_stations
            FROM train_stop_observations
            WHERE snapshot_id = :timetable_snapshot_id
              AND train_id != :target_train_id
            GROUP BY train_id
        ),
        intersection AS (
            SELECT tso.train_id, COUNT(DISTINCT tso.station_id) as overlap_count
            FROM train_stop_observations tso
            JOIN target_stations ts ON tso.station_id = ts.station_id
            WHERE tso.snapshot_id = :timetable_snapshot_id
              AND tso.train_id != :target_train_id
            GROUP BY tso.train_id
        )
        SELECT
            t.number AS train_number,
            t_obs.name AS train_name,
            t_obs.type AS train_type,
            t_obs.return_train_number AS return_train_number,
            i.overlap_count AS overlap_station_count,
            ot.total_stations AS compared_station_count,
            (tc.c + ot.total_stations - i.overlap_count) AS union_station_count,
            ROUND(
                (i.overlap_count * 100.0) /
                (tc.c + ot.total_stations - i.overlap_count),
            1) AS similarity_pct,
            tc.c AS target_station_count
        FROM intersection i
        JOIN other_trains ot ON i.train_id = ot.train_id
        JOIN trains t ON t.id = i.train_id
        JOIN train_observations t_obs
          ON t_obs.train_id = t.id
         AND t_obs.snapshot_id = :timetable_snapshot_id
        CROSS JOIN target_count tc
        WHERE i.overlap_count >= :min_overlap_stations
        ORDER BY similarity_pct DESC, i.overlap_count DESC, union_station_count ASC, t.number ASC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {
            "timetable_snapshot_id": timetable_snapshot_id,
            "target_train_id": target_train_id,
            "min_overlap_stations": min_overlap_stations,
            "limit": limit,
        },
    ).fetchall()

    items = []
    target_station_count = 0
    if results:
        target_station_count = results[0].target_station_count

    for row in results:
        items.append(
            TrainSimilarityItem(
                train_number=row.train_number,
                train_name=row.train_name,
                train_type=row.train_type,
                return_train_number=row.return_train_number,
                overlap_station_count=row.overlap_station_count,
                compared_station_count=row.compared_station_count,
                union_station_count=row.union_station_count,
                similarity_pct=row.similarity_pct,
            )
        )

    # If no results, we still need target_station_count
    if not results:
        count = db.execute(
            text("""
                SELECT COUNT(DISTINCT station_id)
                FROM train_stop_observations
                WHERE snapshot_id = :snapshot_id AND train_id = :train_id
            """),
            {"snapshot_id": timetable_snapshot_id, "train_id": target_train_id},
        ).scalar()
        target_station_count = count or 0

    return target_station_count, target_train_number_resolved, target_train_name, items


def calculate_station_similarity(
    db: Session,
    timetable_snapshot_id: int,
    target_station_code: str,
    limit: int = 10,
    min_overlap_trains: int = 1,
) -> tuple[int, str, str | None, list]:
    """Calculate historical timetable service-set similarity for a target station."""
    from sqlalchemy import func

    from railgati.api.v1.schemas import StationSimilarityItem
    from railgati.models.station import Station, StationObservation

    # 1. Resolve target station ID and metadata in the active snapshot
    target_station = db.execute(
        select(Station.id, Station.code, StationObservation.name)
        .outerjoin(
            StationObservation,
            (StationObservation.station_id == Station.id)
            & (StationObservation.snapshot_id == timetable_snapshot_id),
        )
        .filter(func.lower(Station.code) == target_station_code.lower())
    ).first()

    if not target_station:
        raise ValueError(f"Historical timetable station '{target_station_code}' not found.")

    target_station_id = target_station.id
    target_station_code_resolved = target_station.code
    target_station_name = target_station.name

    query = text("""
        WITH target_trains AS (
            SELECT DISTINCT train_id
            FROM train_stop_observations
            WHERE snapshot_id = :timetable_snapshot_id
              AND station_id = :target_station_id
        ),
        target_count AS (
            SELECT COUNT(*) AS c FROM target_trains
        ),
        other_stations AS (
            SELECT station_id, COUNT(DISTINCT train_id) as total_trains
            FROM train_stop_observations
            WHERE snapshot_id = :timetable_snapshot_id
              AND station_id != :target_station_id
            GROUP BY station_id
        ),
        intersection AS (
            SELECT tso.station_id, COUNT(DISTINCT tso.train_id) as overlap_count
            FROM train_stop_observations tso
            JOIN target_trains tt ON tso.train_id = tt.train_id
            WHERE tso.snapshot_id = :timetable_snapshot_id
              AND tso.station_id != :target_station_id
            GROUP BY tso.station_id
        )
        SELECT
            s.code AS station_code,
            s_obs.name AS station_name,
            i.overlap_count AS overlap_train_count,
            os.total_trains AS compared_train_count,
            (tc.c + os.total_trains - i.overlap_count) AS union_train_count,
            ROUND(
                (i.overlap_count * 100.0) /
                (tc.c + os.total_trains - i.overlap_count),
            1) AS similarity_pct,
            tc.c AS target_train_count
        FROM intersection i
        JOIN other_stations os ON i.station_id = os.station_id
        JOIN stations s ON s.id = i.station_id
        LEFT JOIN station_observations s_obs
          ON s_obs.station_id = s.id
         AND s_obs.snapshot_id = :timetable_snapshot_id
        CROSS JOIN target_count tc
        WHERE i.overlap_count >= :min_overlap_trains
        ORDER BY similarity_pct DESC, i.overlap_count DESC, union_train_count ASC, s.code ASC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {
            "timetable_snapshot_id": timetable_snapshot_id,
            "target_station_id": target_station_id,
            "min_overlap_trains": min_overlap_trains,
            "limit": limit,
        },
    ).fetchall()

    items = []
    target_train_count = 0
    if results:
        target_train_count = results[0].target_train_count

    for row in results:
        items.append(
            StationSimilarityItem(
                station_code=row.station_code,
                station_name=row.station_name,
                compared_train_count=row.compared_train_count,
                overlap_train_count=row.overlap_train_count,
                union_train_count=row.union_train_count,
                similarity_pct=row.similarity_pct,
            )
        )

    # If no results, we still need target_train_count
    if not results:
        count = db.execute(
            text("""
                SELECT COUNT(DISTINCT train_id)
                FROM train_stop_observations
                WHERE snapshot_id = :snapshot_id AND station_id = :station_id
            """),
            {"snapshot_id": timetable_snapshot_id, "station_id": target_station_id},
        ).scalar()
        target_train_count = count or 0

    return target_train_count, target_station_code_resolved, target_station_name, items


def calculate_network_od_travel_time(
    db: Session,
    timetable_snapshot_id: int,
    from_station_code: str,
    to_station_code: str,
) -> tuple[str, str | None, str, str | None, int, int, int | None, int | None, float | None]:
    """Calculate Network O-D Travel Time Analytics."""
    from railgati.models.station import Station, StationObservation

    # Find stations
    from_code_upper = from_station_code.strip().upper()
    to_code_upper = to_station_code.strip().upper()

    if from_code_upper == to_code_upper:
        raise ValueError("Origin and destination stations must be different")

    # 1. Resolve Origin Station
    origin_station = db.scalar(select(Station).filter(Station.code == from_code_upper))
    if not origin_station:
        raise ValueError(f"Origin station '{from_code_upper}' not found")

    origin_obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == origin_station.id,
            StationObservation.snapshot_id == timetable_snapshot_id,
        )
    )
    origin_name = origin_obs.name if origin_obs else None

    # 2. Resolve Destination Station
    dest_station = db.scalar(select(Station).filter(Station.code == to_code_upper))
    if not dest_station:
        raise ValueError(f"Destination station '{to_code_upper}' not found")

    dest_obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == dest_station.id,
            StationObservation.snapshot_id == timetable_snapshot_id,
        )
    )
    dest_name = dest_obs.name if dest_obs else None

    # Verify snapshot
    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"

    if is_sqlite:
        query = text("""
            WITH od_trains AS (
                SELECT
                    tso1.train_id,
                    tso1.departure_time as dep_time,
                    tso1.source_day as dep_day,
                    tso2.arrival_time as arr_time,
                    tso2.source_day as arr_day
                FROM train_stop_observations tso1
                JOIN train_stop_observations tso2
                  ON tso1.train_id = tso2.train_id
                 AND tso1.snapshot_id = tso2.snapshot_id
                WHERE tso1.snapshot_id = :snapshot_id
                  AND tso1.station_id = :origin_id
                  AND tso2.station_id = :dest_id
                  AND tso1.stop_sequence < tso2.stop_sequence
                  AND tso1.departure_time IS NOT NULL
                  AND tso2.arrival_time IS NOT NULL
                  AND tso1.source_day IS NOT NULL
                  AND tso2.source_day IS NOT NULL
            )
            SELECT
                train_id, dep_time, dep_day, arr_time, arr_day
            FROM od_trains
        """)
        results = db.execute(
            query,
            {
                "snapshot_id": timetable_snapshot_id,
                "origin_id": origin_station.id,
                "dest_id": dest_station.id,
            },
        ).fetchall()

        qual_count = 0
        trains = set()
        durations = []
        for row in results:
            train_id, dep, dep_day, arr, arr_day = row
            try:
                # Handle SQLite time parsing
                dep_h, dep_m, _ = map(int, str(dep).split(":"))
                arr_h, arr_m, _ = map(int, str(arr).split(":"))
                dep_mins = (int(str(dep_day)) * 1440) + dep_h * 60 + dep_m
                arr_mins = (int(str(arr_day)) * 1440) + arr_h * 60 + arr_m
                dur = arr_mins - dep_mins
                if dur >= 0:
                    durations.append(dur)
                    trains.add(train_id)
                    qual_count += 1
            except Exception:
                pass

        min_dur = min(durations) if durations else None
        max_dur = max(durations) if durations else None
        avg_dur = round(sum(durations) / len(durations), 1) if durations else None

        return (
            from_code_upper,
            origin_name,
            to_code_upper,
            dest_name,
            qual_count,
            len(trains),
            min_dur,
            max_dur,
            avg_dur,
        )

    # Postgres Query
    query = text("""
        WITH od_trains AS (
            SELECT
                tso1.train_id,
                tso1.departure_time as dep_time,
                tso1.source_day as dep_day,
                tso2.arrival_time as arr_time,
                tso2.source_day as arr_day,
                (
                    ((tso2.source_day - tso1.source_day) * 1440) +
                    (EXTRACT(EPOCH FROM tso2.arrival_time::time)/60) -
                    (EXTRACT(EPOCH FROM tso1.departure_time::time)/60)
                ) as duration
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.train_id = tso2.train_id
             AND tso1.snapshot_id = tso2.snapshot_id
            WHERE tso1.snapshot_id = :snapshot_id
              AND tso1.station_id = :origin_id
              AND tso2.station_id = :dest_id
              AND tso1.stop_sequence < tso2.stop_sequence
              AND tso1.departure_time IS NOT NULL
              AND tso2.arrival_time IS NOT NULL
              AND tso1.source_day IS NOT NULL
              AND tso2.source_day IS NOT NULL
        )
        SELECT
            COUNT(train_id) as qualifying_occurrence_count,
            COUNT(DISTINCT train_id) as distinct_train_count,
            CAST(MIN(duration) AS integer) as min_duration_minutes,
            CAST(MAX(duration) AS integer) as max_duration_minutes,
            CAST(ROUND(CAST(AVG(duration) AS numeric), 1) AS double precision) as avg_duration_minutes
        FROM od_trains
        WHERE duration >= 0
    """)

    res = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "origin_id": origin_station.id,
            "dest_id": dest_station.id,
        },
    ).fetchone()

    qualifying_occurrence_count = res[0] if res else 0
    distinct_train_count = res[1] if res else 0
    min_duration = res[2] if res else None
    max_duration = res[3] if res else None
    avg_duration = res[4] if res else None

    # SQLite / Null results returns (0, 0, None, None, None)
    if qualifying_occurrence_count == 0:
        min_duration = None
        max_duration = None
        avg_duration = None

    return (
        from_code_upper,
        origin_name,
        to_code_upper,
        dest_name,
        qualifying_occurrence_count,
        distinct_train_count,
        min_duration,
        max_duration,
        avg_duration,
    )


def calculate_station_paired_services(
    db: Session,
    timetable_snapshot_id: int,
    station_code: str,
) -> tuple[str, str | None, int, float | None, list[dict]]:
    """Calculate Network Station Paired-Service Analytics."""
    from sqlalchemy import text

    from railgati.api.v1.snapshots import get_active_station_snapshot_id
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station, StationObservation

    station_code_upper = station_code.strip().upper()

    # 1. Resolve Station
    station = db.scalar(select(Station).filter(Station.code == station_code_upper))
    if not station:
        raise ValueError(f"Station '{station_code_upper}' not found")

    station_snapshot_id = get_active_station_snapshot_id(db)
    station_obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == station_snapshot_id,
        )
    )
    station_name = station_obs.name if station_obs else None

    # Verify snapshot
    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"

    if is_sqlite:
        query = text("""
            WITH termini AS (
                SELECT
                    snapshot_id, train_id, station_id,
                    MAX(stop_sequence) OVER (PARTITION BY snapshot_id, train_id) as max_seq,
                    MIN(stop_sequence) OVER (PARTITION BY snapshot_id, train_id) as min_seq,
                    stop_sequence, arrival_time, departure_time
                FROM train_stop_observations
                WHERE snapshot_id = :snapshot_id AND station_id = :station_id
            ),
            arrivals AS (
                SELECT t.snapshot_id, t.train_id, t.station_id, t.arrival_time, tr.number as train_number, obs.return_train_number
                FROM termini t
                JOIN train_observations obs ON t.train_id = obs.train_id AND t.snapshot_id = obs.snapshot_id
                JOIN trains tr ON t.train_id = tr.id
                WHERE t.stop_sequence = t.max_seq AND t.arrival_time IS NOT NULL AND obs.return_train_number IS NOT NULL
            ),
            departures AS (
                SELECT t.snapshot_id, t.train_id, t.station_id, t.departure_time, tr.number as train_number
                FROM termini t
                JOIN trains tr ON t.train_id = tr.id
                WHERE t.stop_sequence = t.min_seq AND t.departure_time IS NOT NULL
            )
            SELECT
                a.train_number as arriving_train,
                a.return_train_number as departing_train,
                a.arrival_time,
                d.departure_time
            FROM arrivals a
            JOIN departures d
              ON a.station_id = d.station_id
             AND a.return_train_number = d.train_number
             AND a.snapshot_id = d.snapshot_id
        """)
        results = db.execute(
            query,
            {
                "snapshot_id": timetable_snapshot_id,
                "station_id": station.id,
            },
        ).fetchall()

        paired_services = []
        for row in results:
            arr_train, dep_train, arr_time, dep_time = row
            try:
                arr_h, arr_m, _ = map(int, str(arr_time).split(":"))
                dep_h, dep_m, _ = map(int, str(dep_time).split(":"))

                arr_mins = arr_h * 60 + arr_m
                dep_mins = dep_h * 60 + dep_m

                clock_gap = (dep_mins - arr_mins + 1440) % 1440

                paired_services.append(
                    {
                        "arriving_train_number": str(arr_train),
                        "departing_train_number": str(dep_train),
                        "arrival_time": str(arr_time),
                        "departure_time": str(dep_time),
                        "clock_gap_minutes": clock_gap,
                    }
                )
            except Exception:
                pass

        paired_services.sort(key=lambda x: x["clock_gap_minutes"])

        count = len(paired_services)
        avg = (
            round(sum(p["clock_gap_minutes"] for p in paired_services) / count, 1)
            if count > 0
            else None
        )

        return (station_code_upper, station_name, count, avg, paired_services)

    # Postgres Query
    query = text("""
        WITH termini AS (
            SELECT
                snapshot_id, train_id, station_id,
                MAX(stop_sequence) OVER (PARTITION BY snapshot_id, train_id) as max_seq,
                MIN(stop_sequence) OVER (PARTITION BY snapshot_id, train_id) as min_seq,
                stop_sequence, arrival_time, departure_time
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id AND station_id = :station_id
        ),
        arrivals AS (
            SELECT t.snapshot_id, t.train_id, t.station_id, t.arrival_time, tr.number as train_number, obs.return_train_number
            FROM termini t
            JOIN train_observations obs ON t.train_id = obs.train_id AND t.snapshot_id = obs.snapshot_id
            JOIN trains tr ON t.train_id = tr.id
            WHERE t.stop_sequence = t.max_seq AND t.arrival_time IS NOT NULL AND obs.return_train_number IS NOT NULL
        ),
        departures AS (
            SELECT t.snapshot_id, t.train_id, t.station_id, t.departure_time, tr.number as train_number
            FROM termini t
            JOIN trains tr ON t.train_id = tr.id
            WHERE t.stop_sequence = t.min_seq AND t.departure_time IS NOT NULL
        )
        SELECT
            a.train_number as arriving_train,
            a.return_train_number as departing_train,
            a.arrival_time,
            d.departure_time,
            MOD(CAST((EXTRACT(EPOCH FROM d.departure_time::time)/60 - EXTRACT(EPOCH FROM a.arrival_time::time)/60 + 1440) AS integer), 1440) as clock_gap_mins
        FROM arrivals a
        JOIN departures d
          ON a.station_id = d.station_id
         AND a.return_train_number = d.train_number
         AND a.snapshot_id = d.snapshot_id
        ORDER BY clock_gap_mins ASC
    """)

    res = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "station_id": station.id,
        },
    ).fetchall()

    paired_services = [
        {
            "arriving_train_number": row[0],
            "departing_train_number": row[1],
            "arrival_time": row[2],
            "departure_time": row[3],
            "clock_gap_minutes": row[4],
        }
        for row in res
    ]

    count = len(paired_services)
    avg = (
        round(sum(p["clock_gap_minutes"] for p in paired_services) / count, 1)
        if count > 0
        else None
    )

    return (station_code_upper, station_name, count, avg, paired_services)


def calculate_station_reversals(
    db: Session,
    timetable_snapshot_id: int,
    station_code: str,
) -> tuple[str, str | None, int, list[dict]]:
    """Calculate Network Station Directional Reversal Analytics."""
    from sqlalchemy import text

    from railgati.api.v1.snapshots import get_active_station_snapshot_id
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station, StationObservation

    station_code_upper = station_code.strip().upper()

    # 1. Resolve Station
    station = db.scalar(select(Station).filter(Station.code == station_code_upper))
    if not station:
        raise ValueError(f"Station '{station_code_upper}' not found")

    station_snapshot_id = get_active_station_snapshot_id(db)
    station_obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == station_snapshot_id,
        )
    )
    station_name = station_obs.name if station_obs else None

    # Verify snapshot
    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    query = text("""
        WITH target_trains AS (
            SELECT train_id
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id AND station_id = :station_id
        ),
        stops AS (
            SELECT tso.train_id, tso.stop_sequence, tso.station_id, tso.arrival_time, tso.departure_time,
                   LAG(tso.station_id) OVER (PARTITION BY tso.train_id ORDER BY tso.stop_sequence) as prev_station_id,
                   LEAD(tso.station_id) OVER (PARTITION BY tso.train_id ORDER BY tso.stop_sequence) as next_station_id
            FROM train_stop_observations tso
            JOIN target_trains tt ON tso.train_id = tt.train_id
            WHERE tso.snapshot_id = :snapshot_id
        )
        SELECT tr.number as train_number, s_adj.code as adjoining_station, stops.arrival_time, stops.departure_time
        FROM stops
        JOIN trains tr ON tr.id = stops.train_id
        JOIN stations s_tgt ON s_tgt.id = stops.station_id
        JOIN stations s_adj ON s_adj.id = stops.prev_station_id
        WHERE stops.prev_station_id = stops.next_station_id
          AND s_tgt.id = :station_id
        ORDER BY tr.number
    """)

    results = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "station_id": station.id,
        },
    ).fetchall()

    reversing_trains = [
        {
            "train_number": row[0],
            "adjoining_station_code": row[1],
            "arrival_time": row[2],
            "departure_time": row[3],
        }
        for row in results
    ]

    return (station_code_upper, station_name, len(reversing_trains), reversing_trains)


def calculate_station_outbound_transit(
    db: Session,
    timetable_snapshot_id: int,
    station_code: str,
) -> tuple[str, str | None, list[dict]]:
    """Calculate Network Station Outbound Edge Transit Analytics."""
    from sqlalchemy import text

    from railgati.api.v1.snapshots import get_active_station_snapshot_id
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station, StationObservation

    station_code_upper = station_code.strip().upper()

    # 1. Resolve Station
    station = db.scalar(select(Station).filter(Station.code == station_code_upper))
    if not station:
        raise ValueError(f"Station '{station_code_upper}' not found")

    station_snapshot_id = get_active_station_snapshot_id(db)
    station_obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == station_snapshot_id,
        )
    )
    station_name = station_obs.name if station_obs else None

    # Verify snapshot
    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"
    if is_sqlite:
        duration_calc = "(ns.dst_day - tt.src_day) * 1440 + CAST(strftime('%s', ns.dst_arrival) AS INTEGER) / 60 - CAST(strftime('%s', tt.src_departure) AS INTEGER) / 60"
    else:
        duration_calc = "(ns.dst_day - tt.src_day) * 1440 + EXTRACT(EPOCH FROM ns.dst_arrival::time)/60 - EXTRACT(EPOCH FROM tt.src_departure::time)/60"

    query = text(f"""
        WITH target_trains AS (
            SELECT train_id, stop_sequence as src_seq, departure_time as src_departure, source_day as src_day
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id AND station_id = :station_id
              AND departure_time IS NOT NULL
        ),
        next_stops AS (
            SELECT tso.train_id, tso.station_id as dst_station, tso.arrival_time as dst_arrival, tso.source_day as dst_day
            FROM target_trains tt
            JOIN train_stop_observations tso
              ON tso.train_id = tt.train_id
             AND tso.snapshot_id = :snapshot_id
             AND tso.stop_sequence = tt.src_seq + 1
            WHERE tso.arrival_time IS NOT NULL
        ),
        valid_edges AS (
            SELECT tt.train_id, ns.dst_station,
                   {duration_calc} as duration_mins
            FROM target_trains tt
            JOIN next_stops ns ON tt.train_id = ns.train_id
        )
        SELECT s.code as next_station_code, so.name as next_station_name, COUNT(*) as vol,
               MIN(duration_mins) as min_d, MAX(duration_mins) as max_d, ROUND(AVG(duration_mins), 1) as avg_d
        FROM valid_edges e
        JOIN stations s ON s.id = e.dst_station
        LEFT JOIN station_observations so ON so.station_id = s.id AND so.snapshot_id = :station_snapshot_id
        GROUP BY s.code, so.name
        ORDER BY vol DESC, s.code ASC
    """)

    results = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "station_id": station.id,
            "station_snapshot_id": station_snapshot_id,
        },
    ).fetchall()

    edges = [
        {
            "next_station_code": row[0],
            "next_station_name": row[1],
            "train_volume": row[2],
            "min_duration_minutes": float(row[3]),
            "max_duration_minutes": float(row[4]),
            "avg_duration_minutes": float(row[5]),
        }
        for row in results
    ]

    return (station_code_upper, station_name, edges)


def calculate_train_profile(
    db: Session,
    timetable_snapshot_id: int,
    train_number: str,
) -> dict:
    """Calculate Network Train Route Profile Analytics."""
    from sqlalchemy import text

    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.train import Train

    # Verify snapshot
    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    train = db.scalar(select(Train).filter(Train.number == train_number))
    if not train:
        raise ValueError(f"Train '{train_number}' not found")

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"
    if is_sqlite:
        duration_calc = "(d_day - o_day) * 1440 + CAST(strftime('%s', d_arr) AS INTEGER) / 60 - CAST(strftime('%s', o_dep) AS INTEGER) / 60"
        dwell_calc = "SUM(CAST(strftime('%s', departure_time) AS INTEGER) / 60 - CAST(strftime('%s', arrival_time) AS INTEGER) / 60 + CASE WHEN departure_time < arrival_time THEN 1440 ELSE 0 END)"
    else:
        duration_calc = "(d_day - o_day) * 1440 + EXTRACT(EPOCH FROM d_arr::time)/60 - EXTRACT(EPOCH FROM o_dep::time)/60"
        dwell_calc = "SUM(EXTRACT(EPOCH FROM departure_time::time)/60 - EXTRACT(EPOCH FROM arrival_time::time)/60 + CASE WHEN departure_time < arrival_time THEN 1440 ELSE 0 END)"

    query = text(f"""
        WITH train_stops AS (
            SELECT snapshot_id, train_id, station_id, stop_sequence, departure_time, arrival_time, source_day
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id AND train_id = :train_id
        ),
        termini AS (
            SELECT snapshot_id, train_id,
                   MAX(stop_sequence) as max_seq,
                   MIN(stop_sequence) as min_seq,
                   COUNT(*) as total_stops
            FROM train_stops
            GROUP BY snapshot_id, train_id
        ),
        span_bounds AS (
            SELECT t.train_id, t.total_stops,
                   o.station_id as origin_id, o.departure_time as o_dep, o.source_day as o_day,
                   d.station_id as dest_id, d.arrival_time as d_arr, d.source_day as d_day
            FROM termini t
            JOIN train_stops o ON o.train_id = t.train_id AND o.stop_sequence = t.min_seq
            JOIN train_stops d ON d.train_id = t.train_id AND d.stop_sequence = t.max_seq
        ),
        span_calc AS (
            SELECT train_id, total_stops, origin_id, dest_id,
                   {duration_calc} as total_duration_mins
            FROM span_bounds
        ),
        dwells AS (
            SELECT ts.train_id,
                   {dwell_calc} as total_dwell_mins
            FROM train_stops ts
            JOIN termini t ON t.train_id = ts.train_id
            WHERE ts.stop_sequence > t.min_seq AND ts.stop_sequence < t.max_seq
              AND ts.arrival_time IS NOT NULL AND ts.departure_time IS NOT NULL
            GROUP BY ts.train_id
        )
        SELECT sc.total_stops, sc.total_duration_mins, d.total_dwell_mins,
               ROUND((d.total_dwell_mins * 100.0 / NULLIF(sc.total_duration_mins, 0)), 1) as dwell_percentage,
               o_st.code as origin_station_code, d_st.code as dest_station_code
        FROM span_calc sc
        LEFT JOIN dwells d ON sc.train_id = d.train_id
        JOIN stations o_st ON o_st.id = sc.origin_id
        JOIN stations d_st ON d_st.id = sc.dest_id
    """)

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "train_id": train.id,
        },
    ).fetchone()

    if not result:
        raise ValueError(
            f"No usable observations for train '{train_number}' in snapshot {timetable_snapshot_id}"
        )

    return {
        "train_number": train_number,
        "timetable_snapshot_id": timetable_snapshot_id,
        "origin_station_code": result[4],
        "destination_station_code": result[5],
        "total_stops": result[0],
        "total_duration_minutes": float(result[1]) if result[1] is not None else None,
        "total_dwell_minutes": float(result[2])
        if result[2] is not None
        else (0.0 if result[0] > 0 else None),
        "dwell_percentage": float(result[3])
        if result[3] is not None
        else (0.0 if result[1] is not None and result[2] is None and result[1] > 0 else None),
    }


def calculate_station_od_bridges(
    db: Session,
    timetable_snapshot_id: int,
    station_code: str,
) -> dict:
    """Calculate Network Station O-D Bridging Analytics."""
    from sqlalchemy import text

    from railgati.api.v1.snapshots import get_active_station_snapshot_id
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station, StationObservation

    station_code_upper = station_code.strip().upper()

    # 1. Resolve Station
    station = db.scalar(select(Station).filter(Station.code == station_code_upper))
    if not station:
        raise ValueError(f"Station '{station_code_upper}' not found")

    station_snapshot_id = get_active_station_snapshot_id(db)
    station_obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == station_snapshot_id,
        )
    )
    station_name = station_obs.name if station_obs else None

    # Verify snapshot
    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    query = text("""
        WITH target_trains AS (
            SELECT DISTINCT train_id
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id AND station_id = :station_id
        ),
        train_bounds AS (
            SELECT tt.train_id,
                   (SELECT station_id FROM train_stop_observations WHERE snapshot_id = :snapshot_id AND train_id = tt.train_id ORDER BY stop_sequence ASC LIMIT 1) as origin_id,
                   (SELECT station_id FROM train_stop_observations WHERE snapshot_id = :snapshot_id AND train_id = tt.train_id ORDER BY stop_sequence DESC LIMIT 1) as dest_id
            FROM target_trains tt
        ),
        counts AS (
            SELECT
                COUNT(DISTINCT origin_id) as unique_origins,
                COUNT(DISTINCT dest_id) as unique_destinations,
                COUNT(DISTINCT CAST(origin_id AS TEXT) || '-' || CAST(dest_id AS TEXT)) as unique_od_pairs
            FROM train_bounds
        ),
        top_pairs AS (
            SELECT tb.origin_id, tb.dest_id, COUNT(*) as volume
            FROM train_bounds tb
            GROUP BY tb.origin_id, tb.dest_id
        ),
        top_pairs_detailed AS (
            SELECT o.code as o_code, o_obs.name as o_name,
                   d.code as d_code, d_obs.name as d_name,
                   tp.volume
            FROM top_pairs tp
            JOIN stations o ON tp.origin_id = o.id
            LEFT JOIN station_observations o_obs ON o_obs.station_id = o.id AND o_obs.snapshot_id = :station_snapshot_id
            JOIN stations d ON tp.dest_id = d.id
            LEFT JOIN station_observations d_obs ON d_obs.station_id = d.id AND d_obs.snapshot_id = :station_snapshot_id
            ORDER BY tp.volume DESC, o.code ASC, d.code ASC
            LIMIT 10
        )
        SELECT
            c.unique_origins, c.unique_destinations, c.unique_od_pairs,
            COALESCE(
                (SELECT json_group_array(
                            json_object(
                                'origin_station_code', tpd.o_code,
                                'origin_station_name', tpd.o_name,
                                'destination_station_code', tpd.d_code,
                                'destination_station_name', tpd.d_name,
                                'train_volume', tpd.volume
                            )
                        ) FROM top_pairs_detailed tpd),
                '[]'
            ) as pairs_json
        FROM counts c;
    """)

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"

    if not is_sqlite:
        query = text("""
            WITH target_trains AS (
                SELECT DISTINCT train_id
                FROM train_stop_observations
                WHERE snapshot_id = :snapshot_id AND station_id = :station_id
            ),
            train_bounds AS (
                SELECT tt.train_id,
                       (SELECT station_id FROM train_stop_observations WHERE snapshot_id = :snapshot_id AND train_id = tt.train_id ORDER BY stop_sequence ASC LIMIT 1) as origin_id,
                       (SELECT station_id FROM train_stop_observations WHERE snapshot_id = :snapshot_id AND train_id = tt.train_id ORDER BY stop_sequence DESC LIMIT 1) as dest_id
                FROM target_trains tt
            ),
            counts AS (
                SELECT
                    COUNT(DISTINCT origin_id) as unique_origins,
                    COUNT(DISTINCT dest_id) as unique_destinations,
                    COUNT(DISTINCT origin_id::text || '-' || dest_id::text) as unique_od_pairs
                FROM train_bounds
            ),
            top_pairs AS (
                SELECT tb.origin_id, tb.dest_id, COUNT(*) as volume
                FROM train_bounds tb
                GROUP BY tb.origin_id, tb.dest_id
            ),
            top_pairs_detailed AS (
                SELECT o.code as o_code, o_obs.name as o_name,
                       d.code as d_code, d_obs.name as d_name,
                       tp.volume
                FROM top_pairs tp
                JOIN stations o ON tp.origin_id = o.id
                LEFT JOIN station_observations o_obs ON o_obs.station_id = o.id AND o_obs.snapshot_id = :station_snapshot_id
                JOIN stations d ON tp.dest_id = d.id
                LEFT JOIN station_observations d_obs ON d_obs.station_id = d.id AND d_obs.snapshot_id = :station_snapshot_id
                ORDER BY tp.volume DESC, o.code ASC, d.code ASC
                LIMIT 10
            )
            SELECT
                c.unique_origins, c.unique_destinations, c.unique_od_pairs,
                COALESCE(
                    (SELECT json_agg(
                                json_build_object(
                                    'origin_station_code', tpd.o_code,
                                    'origin_station_name', tpd.o_name,
                                    'destination_station_code', tpd.d_code,
                                    'destination_station_name', tpd.d_name,
                                    'train_volume', tpd.volume
                                )
                            ) FROM top_pairs_detailed tpd),
                    '[]'::json
                ) as pairs_json
            FROM counts c;
        """)

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "station_id": station.id,
            "station_snapshot_id": station_snapshot_id,
        },
    ).fetchone()

    import json

    unique_origins = 0
    unique_dests = 0
    unique_pairs = 0
    pairs = []

    if result:
        unique_origins = result[0]
        unique_dests = result[1]
        unique_pairs = result[2]
        if result[3]:
            if isinstance(result[3], str):
                pairs = json.loads(result[3])
            else:
                pairs = result[3]

    return {
        "station_code": station_code_upper,
        "station_name": station_name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "unique_origins_count": unique_origins,
        "unique_destinations_count": unique_dests,
        "unique_od_pairs_count": unique_pairs,
        "top_od_pairs": pairs,
    }


def calculate_station_temporal_gaps(
    db: Session,
    timetable_snapshot_id: int,
    station_code: str,
) -> dict:
    """Calculate Network Station Temporal Gap Analytics."""
    from sqlalchemy import text

    from railgati.api.v1.snapshots import get_active_station_snapshot_id
    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station, StationObservation

    station_code_upper = station_code.strip().upper()

    station = db.scalar(select(Station).filter(Station.code == station_code_upper))
    if not station:
        raise ValueError(f"Station '{station_code_upper}' not found")

    station_snapshot_id = get_active_station_snapshot_id(db)
    station_obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == station_snapshot_id,
        )
    )
    station_name = station_obs.name if station_obs else None

    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"

    if is_sqlite:
        dep_mins_calc = "CAST(strftime('%s', departure_time) AS INTEGER) / 60"
    else:
        dep_mins_calc = "EXTRACT(EPOCH FROM departure_time::time)/60"

    query = text(f"""
        WITH departures AS (
            SELECT {dep_mins_calc} as dep_mins
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id
              AND station_id = :station_id
              AND departure_time IS NOT NULL
        ),
        sorted_deps AS (
            SELECT dep_mins,
                   LEAD(dep_mins) OVER (ORDER BY dep_mins ASC) as next_dep_mins
            FROM departures
        ),
        gaps AS (
            SELECT next_dep_mins - dep_mins as gap
            FROM sorted_deps
            WHERE next_dep_mins IS NOT NULL
            UNION ALL
            SELECT (MIN(dep_mins) + 1440) - MAX(dep_mins) as gap
            FROM sorted_deps
            WHERE (SELECT COUNT(*) FROM sorted_deps) > 0
        )
        SELECT
            MAX(gap) as max_gap,
            (SELECT COUNT(*) FROM departures) as total_deps,
            ROUND(SUM(gap) / NULLIF(COUNT(gap), 0), 1) as avg_gap
        FROM gaps;
    """)

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "station_id": station.id,
        },
    ).fetchone()

    total_deps = 0
    max_gap = 0.0
    avg_gap = 0.0

    if result and result[1] and result[1] > 0:
        max_gap = float(result[0])
        total_deps = result[1]
        avg_gap = float(result[2])
    else:
        raise ValueError(
            f"No qualifying departures for station '{station_code_upper}' in snapshot {timetable_snapshot_id}"
        )

    return {
        "station_code": station_code_upper,
        "station_name": station_name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "total_departures": total_deps,
        "average_departure_gap_minutes": avg_gap,
        "max_departure_gap_minutes": max_gap,
    }


def calculate_edge_temporal_bunching(
    db: Session,
    timetable_snapshot_id: int,
    origin_code: str,
    destination_code: str,
) -> dict:
    """Calculate Network Edge Temporal Bunching Analytics."""
    from sqlalchemy import text

    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station

    origin_code_upper = origin_code.strip().upper()
    destination_code_upper = destination_code.strip().upper()

    if origin_code_upper == destination_code_upper:
        raise ValueError("Origin and destination cannot be the same station")

    origin = db.scalar(select(Station).filter(Station.code == origin_code_upper))
    if not origin:
        raise ValueError(f"Station '{origin_code_upper}' not found")

    destination = db.scalar(select(Station).filter(Station.code == destination_code_upper))
    if not destination:
        raise ValueError(f"Station '{destination_code_upper}' not found")

    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"

    if is_sqlite:
        dep_mins_calc = "CAST(strftime('%s', tso1.departure_time) AS INTEGER) / 60"
    else:
        dep_mins_calc = "EXTRACT(EPOCH FROM tso1.departure_time::time)/60"

    query = text(f"""
        WITH edge_trains AS (
            SELECT {dep_mins_calc} as dep_mins
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso2.snapshot_id = tso1.snapshot_id
             AND tso2.train_id = tso1.train_id
             AND tso2.stop_sequence = tso1.stop_sequence + 1
            WHERE tso1.snapshot_id = :snapshot_id
              AND tso1.station_id = :origin_id
              AND tso2.station_id = :destination_id
              AND tso1.departure_time IS NOT NULL
        ),
        expanded_trains AS (
            SELECT dep_mins FROM edge_trains
            UNION ALL
            SELECT dep_mins + 1440 FROM edge_trains
        )
        SELECT
            (SELECT COUNT(*) FROM edge_trains) as total_volume,
            MAX(window_count) as peak_60min_trains
        FROM (
            SELECT e1.dep_mins,
                   (SELECT COUNT(*) FROM expanded_trains e2
                    WHERE e2.dep_mins >= e1.dep_mins
                      AND e2.dep_mins < e1.dep_mins + 60) as window_count
            FROM edge_trains e1
        ) w;
    """)

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "origin_id": origin.id,
            "destination_id": destination.id,
        },
    ).fetchone()

    if not result or result[0] == 0:
        raise ValueError("No qualifying adjacent timetable edge found")

    return {
        "origin_station_code": origin_code_upper,
        "destination_station_code": destination_code_upper,
        "timetable_snapshot_id": timetable_snapshot_id,
        "total_edge_volume": result[0],
        "peak_60min_trains": result[1],
    }


def calculate_paired_service_symmetry(
    db: Session,
    timetable_snapshot_id: int,
    train_number: str,
) -> dict:
    """Calculate Network Train Paired-Service Temporal Symmetry Analytics."""
    from sqlalchemy import text

    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.train import Train, TrainObservation

    # Verify snapshot
    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    train = db.scalar(select(Train).filter(Train.number == train_number))
    if not train:
        raise ValueError(f"Train '{train_number}' not found")

    # Get return train
    train_obs = db.scalar(
        select(TrainObservation)
        .filter(TrainObservation.snapshot_id == timetable_snapshot_id)
        .filter(TrainObservation.train_id == train.id)
    )
    if not train_obs or not train_obs.return_train_number:
        raise ValueError(f"No paired service found for train '{train_number}'")

    return_train_number = train_obs.return_train_number

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"
    if is_sqlite:
        duration_calc = "(d.source_day - o.source_day) * 1440 + CAST(strftime('%s', d.arrival_time) AS INTEGER) / 60 - CAST(strftime('%s', o.departure_time) AS INTEGER) / 60"  # noqa: E501
    else:
        duration_calc = "(d.source_day - o.source_day) * 1440 + EXTRACT(EPOCH FROM d.arrival_time::time)/60 - EXTRACT(EPOCH FROM o.departure_time::time)/60"  # noqa: E501

    query = text(f"""
        WITH forward_stops AS (
            SELECT tso.train_id,
                   MIN(tso.stop_sequence) as min_seq,
                   MAX(tso.stop_sequence) as max_seq
            FROM train_stop_observations tso
            WHERE tso.snapshot_id = :snapshot_id AND tso.train_id = :train_id
            GROUP BY tso.train_id
        ),
        forward_duration AS (
            SELECT
                {duration_calc} as f_dur_mins
            FROM forward_stops fs
            JOIN train_stop_observations o ON o.train_id = fs.train_id AND o.stop_sequence = fs.min_seq AND o.snapshot_id = :snapshot_id
            JOIN train_stop_observations d ON d.train_id = fs.train_id AND d.stop_sequence = fs.max_seq AND d.snapshot_id = :snapshot_id
            WHERE o.departure_time IS NOT NULL AND d.arrival_time IS NOT NULL
        ),
        return_train_data AS (
            SELECT t.id as r_train_id
            FROM trains t
            WHERE t.number = :return_train_number
        ),
        return_stops AS (
            SELECT tso.train_id,
                   MIN(tso.stop_sequence) as min_seq,
                   MAX(tso.stop_sequence) as max_seq
            FROM train_stop_observations tso
            JOIN return_train_data rtd ON rtd.r_train_id = tso.train_id
            WHERE tso.snapshot_id = :snapshot_id
            GROUP BY tso.train_id
        ),
        return_duration AS (
            SELECT
                {duration_calc} as r_dur_mins
            FROM return_stops rs
            JOIN train_stop_observations o ON o.train_id = rs.train_id AND o.stop_sequence = rs.min_seq AND o.snapshot_id = :snapshot_id
            JOIN train_stop_observations d ON d.train_id = rs.train_id AND d.stop_sequence = rs.max_seq AND d.snapshot_id = :snapshot_id
            WHERE o.departure_time IS NOT NULL AND d.arrival_time IS NOT NULL
        )
        SELECT f.f_dur_mins, r.r_dur_mins
        FROM forward_duration f
        LEFT JOIN return_duration r ON 1=1;
    """)

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "train_id": train.id,
            "return_train_number": return_train_number,
        },
    ).fetchone()

    if not result:
        raise ValueError(
            f"Incomplete timing data for train '{train_number}' in snapshot {timetable_snapshot_id}"
        )

    f_dur = result[0]
    r_dur = result[1]

    if f_dur is None:
        raise ValueError(
            f"Incomplete timing data for train '{train_number}' in snapshot {timetable_snapshot_id}"
        )
    if r_dur is None:
        raise ValueError(
            f"Paired service '{return_train_number}' not present or incomplete in snapshot {timetable_snapshot_id}"  # noqa: E501
        )

    return {
        "train_number": train_number,
        "return_train_number": return_train_number,
        "timetable_snapshot_id": timetable_snapshot_id,
        "forward_train_duration_minutes": float(f_dur),
        "return_train_duration_minutes": float(r_dur),
        "duration_asymmetry_minutes": float(abs(f_dur - r_dur)),
    }


import typing


def calculate_train_topology_loops(
    db: Session,
    timetable_snapshot_id: int,
    train_number: str,
) -> dict[str, typing.Any]:
    """Calculate Network Train Topological Loop Analytics."""
    from sqlalchemy import text

    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.train import Train

    # Verify snapshot
    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    if snapshot.status == "ARCHIVED":
        raise RuntimeError("Timetable snapshot is archived and cannot be queried")

    # Verify train
    train = db.scalar(select(Train).filter(Train.number == train_number))
    if not train:
        raise ValueError(f"Train '{train_number}' not found")

    query = text("""
        SELECT s.code as station_code,
               COUNT(*) as visit_count,
               MAX(tso.stop_sequence) - MIN(tso.stop_sequence) as max_sequence_span
        FROM train_stop_observations tso
        JOIN stations s ON s.id = tso.station_id
        WHERE tso.snapshot_id = :snapshot_id
          AND tso.train_id = :train_id
        GROUP BY tso.station_id, s.code
        HAVING COUNT(*) > 1
           AND MAX(tso.stop_sequence) - MIN(tso.stop_sequence) > 1
        ORDER BY max_sequence_span DESC, s.code ASC
    """)

    results = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "train_id": train.id,
        },
    ).fetchall()

    # We also need to check if the train exists in the snapshot at all.
    # If no results, verify if train has any observations in this snapshot.
    if not results:
        obs_count = db.execute(
            text(
                "SELECT 1 FROM train_stop_observations "
                "WHERE snapshot_id = :snapshot_id AND train_id = :train_id LIMIT 1"
            ),
            {"snapshot_id": timetable_snapshot_id, "train_id": train.id},
        ).scalar()
        if not obs_count:
            raise ValueError(
                f"Train '{train_number}' not present in snapshot {timetable_snapshot_id}"
            )

    loops = [
        {
            "station_code": row[0],
            "visit_count": row[1],
            "max_sequence_span": row[2],
        }
        for row in results
    ]

    return {
        "train_number": train_number,
        "timetable_snapshot_id": timetable_snapshot_id,
        "has_loops": len(loops) > 0,
        "loop_count": len(loops),
        "loops": loops,
    }


def calculate_train_structural_halts(
    db: Session,
    timetable_snapshot_id: int,
    train_number: str,
    limit: int = 10,
) -> dict[str, typing.Any]:
    """Calculate Network Train Structural Halt Analytics."""
    from sqlalchemy import text

    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.train import Train

    # Verify snapshot
    snapshot = db.scalar(select(DatasetSnapshot).filter_by(id=timetable_snapshot_id))
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    if snapshot.status == "ARCHIVED":
        raise ValueError("Timetable snapshot is archived")

    # Verify train
    train = db.scalar(select(Train).filter_by(number=train_number))
    if not train:
        raise ValueError(f"Train '{train_number}' not found")

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"

    if is_sqlite:
        time_diff_expr = """
            (strftime("%s", "1970-01-01 " || tso.departure_time) - strftime("%s", "1970-01-01 " || tso.arrival_time)) +
            CASE WHEN strftime("%s", "1970-01-01 " || tso.departure_time) < strftime("%s", "1970-01-01 " || tso.arrival_time)
                 THEN 86400 ELSE 0 END
        """
    else:
        time_diff_expr = """
            (EXTRACT(EPOCH FROM tso.departure_time::time) - EXTRACT(EPOCH FROM tso.arrival_time::time)) +
            CASE WHEN EXTRACT(EPOCH FROM tso.departure_time::time) < EXTRACT(EPOCH FROM tso.arrival_time::time)
                 THEN 86400 ELSE 0 END
        """

    query = text(f"""
        WITH train_bounds AS (
            SELECT MIN(stop_sequence) as min_seq, MAX(stop_sequence) as max_seq
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id AND train_id = :train_id
        )
        SELECT s.code as station_code,
               CAST(({time_diff_expr}) / 60.0 AS FLOAT) as dwell_minutes
        FROM train_stop_observations tso
        JOIN stations s ON s.id = tso.station_id
        JOIN train_bounds tb ON 1=1
        WHERE tso.snapshot_id = :snapshot_id
          AND tso.train_id = :train_id
          AND tso.arrival_time IS NOT NULL
          AND tso.departure_time IS NOT NULL
          AND tso.stop_sequence > tb.min_seq
          AND tso.stop_sequence < tb.max_seq
        ORDER BY dwell_minutes DESC, s.code ASC
        LIMIT :limit
    """)

    results = db.execute(
        query,
        {"snapshot_id": timetable_snapshot_id, "train_id": train.id, "limit": limit},
    ).fetchall()

    # We also need to check if the train exists in the snapshot at all.
    if not results:
        obs_count = db.execute(
            text(
                "SELECT 1 FROM train_stop_observations "
                "WHERE snapshot_id = :snapshot_id AND train_id = :train_id LIMIT 1"
            ),
            {"snapshot_id": timetable_snapshot_id, "train_id": train.id},
        ).scalar()
        if not obs_count:
            raise ValueError(
                f"Train '{train_number}' not present in snapshot {timetable_snapshot_id}"
            )

    halts = [{"station_code": r[0], "dwell_minutes": float(r[1])} for r in results]

    return {
        "train_number": train_number,
        "timetable_snapshot_id": timetable_snapshot_id,
        "halts": halts,
    }


def calculate_train_relative_edge_slowness(
    db: Session, snapshot_id: int, train_number: str, limit: int = 10
) -> dict[str, typing.Any]:
    from railgati.models.train import Train

    train = db.query(Train).filter(Train.number == train_number).first()
    if not train:
        raise ValueError(f"Train {train_number} not found")

    bind = db.get_bind()
    is_sqlite = bind.dialect.name == "sqlite" if bind else False

    if is_sqlite:
        time_diff_expr = """
            (strftime("%s", "1970-01-01 " || tso2.arrival_time) - strftime("%s", "1970-01-01 " || tso1.departure_time)) +
            CASE WHEN strftime("%s", "1970-01-01 " || tso2.arrival_time) < strftime("%s", "1970-01-01 " || tso1.departure_time)
                 THEN 86400 ELSE 0 END
        """
    else:
        time_diff_expr = """
            (EXTRACT(EPOCH FROM tso2.arrival_time::time) - EXTRACT(EPOCH FROM tso1.departure_time::time)) +
            CASE WHEN EXTRACT(EPOCH FROM tso2.arrival_time::time) < EXTRACT(EPOCH FROM tso1.departure_time::time)
                 THEN 86400 ELSE 0 END
        """

    query = text(f"""
        WITH target_edges AS (
            SELECT
                tso1.stop_sequence as target_seq,
                tso1.station_id as src_station_id,
                tso2.station_id as dst_station_id,
                s1.code as src,
                s2.code as dst,
                CAST(({time_diff_expr}) / 60.0 AS FLOAT) as target_duration
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.snapshot_id = tso2.snapshot_id
             AND tso1.train_id = tso2.train_id
             AND tso1.stop_sequence + 1 = tso2.stop_sequence
            JOIN stations s1 ON s1.id = tso1.station_id
            JOIN stations s2 ON s2.id = tso2.station_id
            WHERE tso1.snapshot_id = :snapshot_id
              AND tso1.train_id = :train_id
              AND tso1.departure_time IS NOT NULL
              AND tso2.arrival_time IS NOT NULL
        ),
        target_edge_pairs AS (
            SELECT DISTINCT src_station_id, dst_station_id
            FROM target_edges
        ),
        network_edges AS (
            SELECT
                tso1.station_id as src_station_id,
                tso2.station_id as dst_station_id,
                CAST(({time_diff_expr}) / 60.0 AS FLOAT) as duration
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.snapshot_id = tso2.snapshot_id
             AND tso1.train_id = tso2.train_id
             AND tso1.stop_sequence + 1 = tso2.stop_sequence
            JOIN target_edge_pairs tep
              ON tep.src_station_id = tso1.station_id AND tep.dst_station_id = tso2.station_id
            WHERE tso1.snapshot_id = :snapshot_id
              AND tso1.departure_time IS NOT NULL
              AND tso2.arrival_time IS NOT NULL
        ),
        network_stats AS (
            SELECT
                src_station_id,
                dst_station_id,
                AVG(duration) as avg_duration,
                COUNT(*) as occurrence_count
            FROM network_edges
            GROUP BY src_station_id, dst_station_id
        )
        SELECT
            te.target_seq,
            te.src,
            te.dst,
            te.target_duration,
            ns.avg_duration,
            ns.occurrence_count,
            te.target_duration / NULLIF(ns.avg_duration, 0) as slowness_ratio
        FROM target_edges te
        JOIN network_stats ns
          ON te.src_station_id = ns.src_station_id AND te.dst_station_id = ns.dst_station_id
        WHERE (te.target_duration / NULLIF(ns.avg_duration, 0)) > 1.0
        ORDER BY slowness_ratio DESC, te.target_seq ASC
        LIMIT :limit
    """)

    results = db.execute(
        query, {"snapshot_id": snapshot_id, "train_id": train.id, "limit": limit}
    ).fetchall()

    slow_edges = []
    for r in results:
        row = dict(r._mapping)
        slow_edges.append(
            {
                "target_stop_sequence": row["target_seq"],
                "source_station_code": row["src"],
                "destination_station_code": row["dst"],
                "target_duration_minutes": float(row["target_duration"])
                if row["target_duration"] is not None
                else 0.0,
                "network_average_minutes": float(row["avg_duration"])
                if row["avg_duration"] is not None
                else 0.0,
                "network_occurrence_count": row["occurrence_count"],
                "slowness_ratio": float(row["slowness_ratio"])
                if row["slowness_ratio"] is not None
                else 0.0,
            }
        )

    return {
        "train_number": train_number,
        "timetable_snapshot_id": snapshot_id,
        "slow_edges": slow_edges,
    }


def calculate_train_relative_station_dwell(
    db: Session, snapshot_id: int, train_number: str, limit: int = 10
) -> dict[str, typing.Any]:
    from railgati.models.train import Train

    train = db.query(Train).filter(Train.number == train_number).first()
    if not train:
        raise ValueError(f"Train {train_number} not found")

    bind = db.get_bind()
    is_sqlite = bind.dialect.name == "sqlite" if bind else False

    if is_sqlite:
        time_diff_expr = """
            (strftime("%s", "1970-01-01 " || tso.departure_time) - strftime("%s", "1970-01-01 " || tso.arrival_time)) +
            CASE WHEN strftime("%s", "1970-01-01 " || tso.departure_time) < strftime("%s", "1970-01-01 " || tso.arrival_time)
                 THEN 86400 ELSE 0 END
        """
    else:
        time_diff_expr = """
            (EXTRACT(EPOCH FROM tso.departure_time::time) - EXTRACT(EPOCH FROM tso.arrival_time::time)) +
            CASE WHEN EXTRACT(EPOCH FROM tso.departure_time::time) < EXTRACT(EPOCH FROM tso.arrival_time::time)
                 THEN 86400 ELSE 0 END
        """

    query = text(f"""
        WITH target_dwells AS (
            SELECT
                tso.stop_sequence as target_seq,
                tso.station_id as station_id,
                s.code as station_code,
                CAST(({time_diff_expr}) / 60.0 AS FLOAT) as target_dwell
            FROM train_stop_observations tso
            JOIN stations s ON s.id = tso.station_id
            WHERE tso.snapshot_id = :snapshot_id
              AND tso.train_id = :train_id
              AND tso.arrival_time IS NOT NULL
              AND tso.departure_time IS NOT NULL
        ),
        target_station_ids AS (
            SELECT DISTINCT station_id FROM target_dwells
        ),
        network_dwells AS (
            SELECT
                tso.station_id,
                CAST(({time_diff_expr}) / 60.0 AS FLOAT) as dwell
            FROM train_stop_observations tso
            JOIN target_station_ids tid ON tid.station_id = tso.station_id
            WHERE tso.snapshot_id = :snapshot_id
              AND tso.arrival_time IS NOT NULL
              AND tso.departure_time IS NOT NULL
        ),
        network_stats AS (
            SELECT
                station_id,
                AVG(dwell) as avg_dwell,
                COUNT(*) as occurrence_count
            FROM network_dwells
            GROUP BY station_id
        )
        SELECT
            td.target_seq,
            td.station_code,
            td.target_dwell,
            ns.avg_dwell,
            ns.occurrence_count,
            td.target_dwell / NULLIF(ns.avg_dwell, 0) as slowness_ratio
        FROM target_dwells td
        JOIN network_stats ns ON ns.station_id = td.station_id
        WHERE (td.target_dwell / NULLIF(ns.avg_dwell, 0)) > 1.0
        ORDER BY slowness_ratio DESC, td.target_seq ASC
        LIMIT :limit
    """)

    results = db.execute(
        query, {"snapshot_id": snapshot_id, "train_id": train.id, "limit": limit}
    ).fetchall()

    relative_dwells = []
    for r in results:
        row = dict(r._mapping)
        relative_dwells.append(
            {
                "target_stop_sequence": row["target_seq"],
                "station_code": row["station_code"],
                "target_dwell_minutes": float(row["target_dwell"])
                if row["target_dwell"] is not None
                else 0.0,
                "network_average_minutes": float(row["avg_dwell"])
                if row["avg_dwell"] is not None
                else 0.0,
                "network_occurrence_count": row["occurrence_count"],
                "slowness_ratio": float(row["slowness_ratio"])
                if row["slowness_ratio"] is not None
                else 0.0,
            }
        )

    return {
        "train_number": train_number,
        "timetable_snapshot_id": snapshot_id,
        "relative_dwells": relative_dwells,
    }


def calculate_station_outbound_dominance(
    db: Session, timetable_snapshot_id: int, station_code: str
) -> dict[str, typing.Any]:
    from sqlalchemy import select, text

    from railgati.api.v1.snapshots import get_active_station_snapshot_id
    from railgati.models.station import Station, StationObservation

    station = db.scalar(select(Station).filter(Station.code == station_code.upper()))
    if not station:
        raise ValueError(f"Station {station_code} not found")

    station_snapshot_id = get_active_station_snapshot_id(db)
    obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == station_snapshot_id,
        )
    )
    station_name = obs.name if obs else f"{station_code} (Unknown)"

    query = text("""
        WITH target_station AS (
            SELECT :station_id as id
        ),
        outbound_edges AS (
            SELECT
                tso1.station_id as from_id,
                tso2.station_id as to_id,
                COUNT(*) as occurrences
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.train_id = tso2.train_id
              AND tso1.snapshot_id = tso2.snapshot_id
              AND tso1.stop_sequence + 1 = tso2.stop_sequence
            WHERE tso1.snapshot_id = :snapshot_id
              AND tso1.station_id = (SELECT id FROM target_station)
            GROUP BY tso1.station_id, tso2.station_id
        ),
        ranked_destinations AS (
            SELECT
                oe.to_id,
                s.code as dest_code,
                oe.occurrences,
                ROW_NUMBER() OVER (ORDER BY oe.occurrences DESC, s.code ASC) as rnk
            FROM outbound_edges oe
            JOIN stations s ON s.id = oe.to_id
        ),
        station_totals AS (
            SELECT
                from_id,
                SUM(occurrences) as total_outbound,
                MAX(occurrences) as max_outbound
            FROM outbound_edges
            GROUP BY from_id
        )
        SELECT
            st.total_outbound,
            st.max_outbound,
            rd.dest_code as dominant_destination,
            CAST(st.max_outbound AS FLOAT) / NULLIF(st.total_outbound, 0) as dominance_ratio
        FROM station_totals st
        LEFT JOIN ranked_destinations rd ON rd.rnk = 1
    """)

    result = db.execute(
        query, {"snapshot_id": timetable_snapshot_id, "station_id": station.id}
    ).first()

    if not result or not result._mapping.get("total_outbound"):
        raise ValueError(
            f"No qualifying outbound occurrences for station '{station_code.upper()}' in snapshot {timetable_snapshot_id}"
        )

    row = dict(result._mapping)
    return {
        "station_code": station.code,
        "station_name": station_name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "total_outbound_occurrences": int(row["total_outbound"]),
        "max_outbound_occurrences": int(row["max_outbound"]),
        "dominant_destination_station_code": row["dominant_destination"],
        "dominance_ratio": float(row["dominance_ratio"])
        if row["dominance_ratio"] is not None
        else 0.0,
    }


def calculate_edge_paired_route_symmetry(
    db: Session, from_station_code: str, to_station_code: str
) -> dict[str, typing.Any]:
    """
    Calculate paired-service timetable edge reciprocity for an adjacent timetable edge.
    This purely tests whether a dataset-linked paired return service contains the
    reciprocal adjacent timetable edge. It does not measure physical routing, passenger flow,
    actual operations, or operational continuity.
    """
    from sqlalchemy import text

    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.station import Station

    # Resolving only timetable_snapshot_id for edge queries as is standard in Phase 28/30
    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    if not timetable_snapshot_id:
        raise ValueError("No active timetable snapshot available.")

    from_station = db.query(Station).filter(Station.code == from_station_code.upper()).first()
    if not from_station:
        raise ValueError(f"Station {from_station_code.upper()} not found.")

    to_station = db.query(Station).filter(Station.code == to_station_code.upper()).first()
    if not to_station:
        raise ValueError(f"Station {to_station_code.upper()} not found.")

    query = text("""
        WITH forward_trains AS (
            SELECT DISTINCT
                tso1.train_id AS fwd_train_id,
                to_obs.return_train_number
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.train_id = tso2.train_id
              AND tso1.snapshot_id = tso2.snapshot_id
              AND tso1.stop_sequence + 1 = tso2.stop_sequence
            JOIN train_observations to_obs
              ON to_obs.train_id = tso1.train_id
              AND to_obs.snapshot_id = :snapshot_id
            WHERE tso1.snapshot_id = :snapshot_id
              AND tso1.station_id = :from_id
              AND tso2.station_id = :to_id
        ),
        successful_returns AS (
            SELECT DISTINCT
                fwd.fwd_train_id
            FROM forward_trains fwd
            JOIN trains rt ON rt.number = fwd.return_train_number
            JOIN train_stop_observations rtso1 ON rtso1.train_id = rt.id AND rtso1.snapshot_id = :snapshot_id
            JOIN train_stop_observations rtso2 ON rtso2.train_id = rt.id AND rtso2.snapshot_id = :snapshot_id
            WHERE rtso1.station_id = :to_id
              AND rtso2.station_id = :from_id
              AND rtso1.stop_sequence + 1 = rtso2.stop_sequence
        )
        SELECT
            COUNT(*) AS total_forward_trains,
            COUNT(sr.fwd_train_id) AS symmetrical_return_trains
        FROM forward_trains f
        LEFT JOIN successful_returns sr ON sr.fwd_train_id = f.fwd_train_id
    """)

    result = db.execute(
        query,
        {"snapshot_id": timetable_snapshot_id, "from_id": from_station.id, "to_id": to_station.id},
    ).first()

    if not result:
        total_forward = 0
        symmetrical = 0
    else:
        total_forward = int(result[0] or 0)
        symmetrical = int(result[1] or 0)

    if total_forward == 0:
        raise ValueError(
            f"No qualifying forward A -> B timetable train identities for {from_station_code.upper()} -> {to_station_code.upper()}"
        )

    return {
        "from_station_code": from_station.code,
        "to_station_code": to_station.code,
        "timetable_snapshot_id": timetable_snapshot_id,
        "total_forward_trains": total_forward,
        "symmetrical_return_trains": symmetrical,
        "symmetry_ratio": float(symmetrical) / total_forward if total_forward > 0 else 0.0,
    }


def calculate_station_neighborhood_symmetry(
    db: Session, station_code: str
) -> dict[str, typing.Any]:
    from sqlalchemy import select, text

    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.station import Station, StationObservation

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    if not timetable_snapshot_id:
        raise ValueError("No active timetable snapshot available.")

    station = db.scalar(select(Station).filter(Station.code == station_code.upper()))
    if not station:
        raise ValueError(f"Station {station_code.upper()} not found.")

    obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == timetable_snapshot_id,
        )
    )
    station_name = obs.name if obs else f"{station.code} (Unknown)"

    query = text("""
        WITH outbound AS (
            SELECT DISTINCT tso2.station_id
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.train_id = tso2.train_id
              AND tso1.snapshot_id = tso2.snapshot_id
              AND tso1.stop_sequence + 1 = tso2.stop_sequence
            WHERE tso1.snapshot_id = :snapshot_id AND tso1.station_id = :station_id
        ),
        inbound AS (
            SELECT DISTINCT tso1.station_id
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.train_id = tso2.train_id
              AND tso1.snapshot_id = tso2.snapshot_id
              AND tso1.stop_sequence + 1 = tso2.stop_sequence
            WHERE tso2.snapshot_id = :snapshot_id AND tso2.station_id = :station_id
        )
        SELECT
            (SELECT COUNT(*) FROM outbound) AS out_count,
            (SELECT COUNT(*) FROM inbound) AS in_count,
            (SELECT COUNT(*) FROM outbound o JOIN inbound i ON o.station_id = i.station_id) AS intersection_count,
            (SELECT COUNT(DISTINCT station_id) FROM (SELECT station_id FROM outbound UNION SELECT station_id FROM inbound) u) AS union_count
    """)

    result = db.execute(
        query, {"snapshot_id": timetable_snapshot_id, "station_id": station.id}
    ).fetchone()
    if not result:
        # Fallback theoretically impossible due to CTE counts, but to be safe
        raise ValueError(f"No qualifying analytical data for {station_code.upper()}")

    out_count = int(result[0] or 0)
    in_count = int(result[1] or 0)
    intersection_count = int(result[2] or 0)
    union_count = int(result[3] or 0)

    if union_count == 0:
        raise ValueError(
            f"Station {station_code.upper()} has no adjacent scheduled timetable occurrences."
        )

    return {
        "station_code": station.code,
        "station_name": station_name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "outbound_destinations_count": out_count,
        "inbound_origins_count": in_count,
        "symmetric_neighbors_count": intersection_count,
        "total_neighborhood_size": union_count,
        "symmetry_ratio": float(intersection_count) / float(union_count),
    }


def calculate_station_neighborhood_triadic_closure(db: Session, station_code: str) -> dict:
    """Phase 33: Calculates Network Station Neighborhood Triadic Closure Analytics."""
    from railgati.api.v1.snapshots import (
        get_active_station_snapshot_id,
        get_active_timetable_snapshot_id,
    )
    from railgati.models.station import Station, StationObservation

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    if not timetable_snapshot_id:
        raise ValueError("No active timetable snapshot available.")

    station = db.scalar(select(Station).filter(Station.code == station_code.upper()))
    if not station:
        raise ValueError(f"Station {station_code.upper()} not found.")

    station_snapshot_id = get_active_station_snapshot_id(db)
    if not station_snapshot_id:
        raise ValueError("No active station snapshot available.")

    obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == station_snapshot_id,
        )
    )
    if not obs:
        raise ValueError(f"Station {station_code.upper()} not found in active station snapshot.")
    station_name = obs.name

    query = text("""
        WITH outbound_neighbors AS (
            SELECT DISTINCT tso2.station_id
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.train_id = tso2.train_id
              AND tso1.snapshot_id = tso2.snapshot_id
              AND tso1.stop_sequence + 1 = tso2.stop_sequence
            WHERE tso1.snapshot_id = :snapshot_id AND tso1.station_id = :station_id
        ),
        possible_pairs AS (
            SELECT a.station_id AS n1, b.station_id AS n2
            FROM outbound_neighbors a
            JOIN outbound_neighbors b ON a.station_id < b.station_id
        ),
        actual_edges AS (
            SELECT DISTINCT
                CASE WHEN tso1.station_id < tso2.station_id THEN tso1.station_id ELSE tso2.station_id END AS n1,
                CASE WHEN tso1.station_id > tso2.station_id THEN tso1.station_id ELSE tso2.station_id END AS n2
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.train_id = tso2.train_id
              AND tso1.snapshot_id = tso2.snapshot_id
              AND tso1.stop_sequence + 1 = tso2.stop_sequence
            WHERE tso1.snapshot_id = :snapshot_id
              AND tso1.station_id IN (SELECT station_id FROM outbound_neighbors)
              AND tso2.station_id IN (SELECT station_id FROM outbound_neighbors)
              AND tso1.station_id != tso2.station_id
        )
        SELECT
            (SELECT COUNT(*) FROM outbound_neighbors) AS outbound_degree,
            (SELECT COUNT(*) FROM possible_pairs) AS possible_count,
            (SELECT COUNT(*) FROM actual_edges) AS actual_count
    """)

    result = db.execute(
        query, {"snapshot_id": timetable_snapshot_id, "station_id": station.id}
    ).fetchone()

    if not result:
        raise ValueError(f"No qualifying analytical data for {station_code.upper()}")

    out_degree = int(result[0] or 0)
    possible_count = int(result[1] or 0)
    actual_count = int(result[2] or 0)

    if out_degree < 2:
        raise ValueError(
            f"Station {station_code.upper()} has outbound_degree < 2. Triadic closure is mathematically undefined."
        )

    return {
        "station_code": station.code,
        "station_name": station_name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "outbound_degree": out_degree,
        "possible_neighbor_pairs": possible_count,
        "closed_neighbor_pairs": actual_count,
        "triadic_closure_ratio": float(actual_count) / float(possible_count),
    }


def calculate_station_transit_articulation(db: Session, station_code: str) -> dict[str, typing.Any]:
    """Phase 34: Calculates Network Station Transit Articulation Analytics."""
    from sqlalchemy import select, text

    from railgati.api.v1.snapshots import (
        get_active_station_snapshot_id,
        get_active_timetable_snapshot_id,
    )
    from railgati.models.station import Station, StationObservation

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    if not timetable_snapshot_id:
        raise ValueError("No active timetable snapshot available.")

    station = db.scalar(select(Station).filter(Station.code == station_code.upper()))
    if not station:
        raise ValueError(f"Station {station_code.upper()} not found.")

    station_snapshot_id = get_active_station_snapshot_id(db)
    if not station_snapshot_id:
        raise ValueError("No active station snapshot available.")

    obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == station_snapshot_id,
        )
    )
    if not obs:
        raise ValueError(f"Station {station_code.upper()} not found in active station snapshot.")
    station_name = obs.name

    query = text("""
        WITH target AS (
            SELECT :station_id AS id
        ),
        inbound AS (
            SELECT DISTINCT tso1.station_id as o
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.train_id = tso2.train_id
              AND tso1.snapshot_id = tso2.snapshot_id
              AND tso1.stop_sequence + 1 = tso2.stop_sequence
            WHERE tso2.snapshot_id = :snapshot_id AND tso2.station_id = (SELECT id FROM target)
        ),
        outbound AS (
            SELECT DISTINCT tso2.station_id as d
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.train_id = tso2.train_id
              AND tso1.snapshot_id = tso2.snapshot_id
              AND tso1.stop_sequence + 1 = tso2.stop_sequence
            WHERE tso1.snapshot_id = :snapshot_id AND tso1.station_id = (SELECT id FROM target)
        ),
        pairs AS (
            SELECT i.o, o.d
            FROM inbound i
            CROSS JOIN outbound o
            WHERE i.o != o.d
              AND i.o != (SELECT id FROM target)
              AND o.d != (SELECT id FROM target)
        ),
        direct_edges AS (
            SELECT p.o, p.d
            FROM pairs p
            WHERE EXISTS (
                SELECT 1
                FROM train_stop_observations t1
                JOIN train_stop_observations t2
                  ON t1.train_id = t2.train_id
                  AND t1.snapshot_id = t2.snapshot_id
                  AND t1.stop_sequence + 1 = t2.stop_sequence
                WHERE t1.snapshot_id = :snapshot_id
                  AND t1.station_id = p.o
                  AND t2.station_id = p.d
            )
        ),
        alt_paths AS (
            SELECT p.o, p.d
            FROM pairs p
            WHERE EXISTS (
                SELECT 1
                FROM train_stop_observations t1
                JOIN train_stop_observations t2
                  ON t1.train_id = t2.train_id
                  AND t1.snapshot_id = t2.snapshot_id
                  AND t1.stop_sequence + 1 = t2.stop_sequence
                JOIN train_stop_observations t3
                  ON t2.train_id = t3.train_id
                  AND t2.snapshot_id = t3.snapshot_id
                  AND t2.stop_sequence + 1 = t3.stop_sequence
                WHERE t1.snapshot_id = :snapshot_id
                  AND t1.station_id = p.o
                  AND t3.station_id = p.d
                  AND t2.station_id != (SELECT id FROM target)
            )
        ),
        dependent_pairs AS (
            SELECT p.o, p.d
            FROM pairs p
            WHERE NOT EXISTS (SELECT 1 FROM direct_edges d WHERE d.o = p.o AND d.d = p.d)
              AND NOT EXISTS (SELECT 1 FROM alt_paths a WHERE a.o = p.o AND a.d = p.d)
        )
        SELECT
            (SELECT COUNT(*) FROM inbound) as in_deg,
            (SELECT COUNT(*) FROM outbound) as out_deg,
            (SELECT COUNT(*) FROM pairs) as transit_pairs,
            (SELECT COUNT(*) FROM dependent_pairs) as articulation_pairs
    """)

    result = db.execute(
        query, {"snapshot_id": timetable_snapshot_id, "station_id": station.id}
    ).fetchone()

    if not result:
        raise ValueError(f"No qualifying analytical data for {station_code.upper()}")

    in_degree = int(result[0] or 0)
    out_degree = int(result[1] or 0)
    transit_pairs_count = int(result[2] or 0)
    articulation_pairs_count = int(result[3] or 0)

    if transit_pairs_count == 0:
        raise ValueError(
            f"Station {station_code.upper()} has transit_pairs_count == 0. Transit articulation is mathematically undefined."
        )

    return {
        "station_code": station.code,
        "station_name": station_name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "inbound_degree": in_degree,
        "outbound_degree": out_degree,
        "transit_pairs_count": transit_pairs_count,
        "articulation_pairs_count": articulation_pairs_count,
        "articulation_ratio": float(articulation_pairs_count) / float(transit_pairs_count),
    }


def calculate_station_reachability_expansion(
    db: Session, timetable_snapshot_id: int, station_code: str
) -> dict[str, typing.Any]:
    """Calculate Network Station 2-Hop Reachability Expansion Analytics."""
    from sqlalchemy import select, text

    from railgati.api.v1.snapshots import get_active_station_snapshot_id
    from railgati.models.station import Station, StationObservation

    station_snapshot_id = get_active_station_snapshot_id(db)

    station = db.scalar(select(Station).filter(Station.code == station_code.upper()))
    if not station:
        raise ValueError(f"Station '{station_code}' not found")

    obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == station_snapshot_id,
        )
    )
    station_name = obs.name if obs else station.code

    query = text("""
        WITH target AS (
            SELECT :station_id as id
        ),
        n1 AS (
            SELECT DISTINCT t2.station_id as id
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id
              AND t1.snapshot_id = t2.snapshot_id
              AND t1.stop_sequence + 1 = t2.stop_sequence
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = (SELECT id FROM target)
        ),
        n2 AS (
            SELECT DISTINCT t3.station_id as id
            FROM train_stop_observations t2
            JOIN train_stop_observations t3
              ON t2.train_id = t3.train_id
              AND t2.snapshot_id = t3.snapshot_id
              AND t2.stop_sequence + 1 = t3.stop_sequence
            WHERE t2.snapshot_id = :snapshot_id
              AND t2.station_id IN (SELECT id FROM n1)
              AND t3.station_id != (SELECT id FROM target)
              AND t3.station_id NOT IN (SELECT id FROM n1)
        )
        SELECT
            (SELECT COUNT(*) FROM n1) as n1_count,
            (SELECT COUNT(*) FROM n2) as n2_count
    """)

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "station_id": station.id,
        },
    ).fetchone()

    n1_count = int(result[0] or 0)
    n2_count = int(result[1] or 0)

    if n1_count == 0:
        raise ValueError(
            f"Station {station_code.upper()} has n1_count == 0. Reachability expansion is mathematically undefined."
        )

    return {
        "station_code": station.code,
        "station_name": station_name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "n1_count": n1_count,
        "n2_count": n2_count,
        "expansion_ratio": float(n2_count) / float(n1_count),
    }


def calculate_station_transfer_free_reach(
    db: Session, timetable_snapshot_id: int, station_code: str
) -> dict[str, typing.Any]:
    """Calculate Network Station Transfer-Free Reachability (TFR) Analytics."""
    from sqlalchemy import select, text

    from railgati.api.v1.snapshots import get_active_station_snapshot_id
    from railgati.models.station import Station, StationObservation

    station_snapshot_id = get_active_station_snapshot_id(db)

    station = db.scalar(select(Station).filter(Station.code == station_code.upper()))
    if not station:
        raise ValueError(f"Station '{station_code}' not found")

    obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == station_snapshot_id,
        )
    )
    station_name = obs.name if obs else station.code

    query = text("""
        WITH target AS (
            SELECT :station_id as id
        ),
        n1 AS (
            SELECT DISTINCT t2.station_id
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id
             AND t1.snapshot_id = t2.snapshot_id
             AND t1.stop_sequence + 1 = t2.stop_sequence
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = (SELECT id FROM target)
        ),
        tfor AS (
            SELECT DISTINCT t2.station_id
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id
             AND t1.snapshot_id = t2.snapshot_id
             AND t1.stop_sequence < t2.stop_sequence
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = (SELECT id FROM target)
              AND t2.station_id != (SELECT id FROM target)
        )
        SELECT
            (SELECT COUNT(*) FROM n1) as n1_count,
            (SELECT COUNT(*) FROM tfor) as tfor_count
    """)

    res = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "station_id": station.id,
        },
    ).fetchone()

    if res is None:
        raise ValueError("Unexpected query failure")

    row = typing.cast("tuple[int, int]", res)
    n1_count = row[0] or 0
    tfor_count = row[1] or 0

    if n1_count == 0:
        raise ValueError(
            f"Station {station_code.upper()} has n1_count == 0. Transfer-free reachability ratio is undefined."
        )

    expansion_ratio = tfor_count / n1_count

    return {
        "station_code": station.code,
        "station_name": station_name,
        "topological_outbound_degree": n1_count,
        "transfer_free_outbound_reach": tfor_count,
        "reachability_span_ratio": round(expansion_ratio, 2),
    }


def calculate_train_structural_subsumption(
    db: Session, timetable_snapshot_id: int, train_number: str
) -> dict[str, typing.Any]:
    """Calculate Network Train Route Structural Subsumption Analytics."""
    from sqlalchemy import select, text

    from railgati.models.train import Train

    train = db.scalar(select(Train).filter(Train.number == train_number))
    if not train:
        raise ValueError(f"Train '{train_number}' not found")

    query = text("""
        WITH target_stops AS (
            SELECT station_id,
                   ROW_NUMBER() OVER (ORDER BY stop_sequence) as target_rnk
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id
              AND train_id = :train_id
        ),
        target_count AS (
            SELECT COUNT(*) as k FROM target_stops
        ),
        candidate_trains AS (
            SELECT DISTINCT tso1.train_id
            FROM train_stop_observations tso1
            JOIN train_stop_observations tso2
              ON tso1.train_id = tso2.train_id
             AND tso1.snapshot_id = tso2.snapshot_id
             AND tso1.stop_sequence < tso2.stop_sequence
            WHERE tso1.snapshot_id = :snapshot_id
              AND tso1.station_id = (SELECT station_id FROM target_stops ORDER BY target_rnk ASC LIMIT 1)
              AND tso2.station_id = (SELECT station_id FROM target_stops ORDER BY target_rnk DESC LIMIT 1)
              AND tso1.train_id != :train_id
        ),
        candidate_stops AS (
            SELECT tso.train_id,
                   tso.station_id,
                   ROW_NUMBER() OVER (PARTITION BY tso.train_id ORDER BY tso.stop_sequence) as cand_rnk
            FROM train_stop_observations tso
            JOIN candidate_trains ct ON tso.train_id = ct.train_id
            WHERE tso.snapshot_id = :snapshot_id
        ),
        matches AS (
            SELECT cs.train_id,
                   (cs.cand_rnk - ts.target_rnk) as offset_val,
                   COUNT(*) as matched_stops
            FROM candidate_stops cs
            JOIN target_stops ts ON cs.station_id = ts.station_id
            GROUP BY cs.train_id, (cs.cand_rnk - ts.target_rnk)
            HAVING COUNT(*) = (SELECT k FROM target_count)
        )
        SELECT COUNT(DISTINCT train_id) FROM matches
    """)

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "train_id": train.id,
        },
    ).fetchone()

    subsuming_count = int(result[0]) if result and result[0] is not None else 0

    return {
        "train_number": train.number,
        "subsuming_train_count": subsuming_count,
        "is_structurally_subsumed": subsuming_count > 0,
    }


def calculate_train_topological_bypasses(
    db: Session, timetable_snapshot_id: int, train_number: str
) -> dict[str, object]:
    """Calculate the topological bypass analytics for a target train route."""
    from railgati.models.train import Train

    train = db.query(Train).filter(Train.number == train_number).first()
    if not train:
        raise ValueError(f"Train {train_number} not found in database.")

    query = text(
        """
        WITH target_seq AS (
            SELECT station_id,
                   ROW_NUMBER() OVER (ORDER BY stop_sequence) as rnk
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id
              AND train_id = :train_id
        ),
        target_pairs AS (
            SELECT ts1.station_id as o, ts2.station_id as d, ts1.rnk as rnk_o, ts2.rnk as rnk_d
            FROM target_seq ts1
            JOIN target_seq ts2 ON ts2.rnk > ts1.rnk + 1
        ),
        bypasses AS (
            SELECT DISTINCT tp.o, tp.d
            FROM target_pairs tp
            JOIN train_stop_observations t1 ON t1.station_id = tp.o AND t1.snapshot_id = :snapshot_id
            JOIN train_stop_observations t2 ON t2.station_id = tp.d AND t2.snapshot_id = :snapshot_id
              AND t1.train_id = t2.train_id
              AND t1.stop_sequence + 1 = t2.stop_sequence
        )
        SELECT
            (SELECT COUNT(*) FROM target_seq) as route_length,
            (SELECT COUNT(*) FROM bypasses) as bypass_count
        """
    )

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "train_id": train.id,
        },
    ).fetchone()

    route_length = int(result[0]) if result and result[0] is not None else 0
    bypass_count = int(result[1]) if result and result[1] is not None else 0

    return {
        "train_number": train.number,
        "timetable_snapshot_id": timetable_snapshot_id,
        "route_length": route_length,
        "bypass_edge_count": bypass_count,
        "has_topological_bypasses": bypass_count > 0,
    }


def calculate_edge_traversal_dispersion(
    db: Session, timetable_snapshot_id: int, from_station_code: str, to_station_code: str
) -> dict[str, object]:
    """Calculate structural traversal dispersion analytics for a target network edge."""
    from railgati.models.station import Station

    st_from = db.query(Station).filter(Station.code == from_station_code).first()
    if not st_from:
        raise ValueError(f"Station {from_station_code} not found")

    st_to = db.query(Station).filter(Station.code == to_station_code).first()
    if not st_to:
        raise ValueError(f"Station {to_station_code} not found")

    query = text(
        """
        WITH edge_traversals AS (
            SELECT
                t1.train_id,
                t1.station_id as o,
                t2.station_id as d,
                t1.stop_sequence as seq_o,
                t2.stop_sequence as seq_d
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id
             AND t1.snapshot_id = t2.snapshot_id
             AND t1.stop_sequence + 1 = t2.stop_sequence
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = :from_id
              AND t2.station_id = :to_id
        )
        SELECT
            (SELECT COUNT(*) FROM edge_traversals) as edge_volume,
            (SELECT COUNT(DISTINCT t_prev.station_id)
             FROM edge_traversals et
             JOIN train_stop_observations t_prev
               ON t_prev.train_id = et.train_id
              AND t_prev.snapshot_id = :snapshot_id
              AND t_prev.stop_sequence = et.seq_o - 1) as convergence_count,
            (SELECT COUNT(*)
             FROM edge_traversals et
             WHERE NOT EXISTS (
                 SELECT 1 FROM train_stop_observations t_prev
                 WHERE t_prev.train_id = et.train_id
                   AND t_prev.snapshot_id = :snapshot_id
                   AND t_prev.stop_sequence = et.seq_o - 1
             )) as edge_originating_train_count,
            (SELECT COUNT(DISTINCT t_next.station_id)
             FROM edge_traversals et
             JOIN train_stop_observations t_next
               ON t_next.train_id = et.train_id
              AND t_next.snapshot_id = :snapshot_id
              AND t_next.stop_sequence = et.seq_d + 1) as bifurcation_count,
            (SELECT COUNT(*)
             FROM edge_traversals et
             WHERE NOT EXISTS (
                 SELECT 1 FROM train_stop_observations t_next
                 WHERE t_next.train_id = et.train_id
                   AND t_next.snapshot_id = :snapshot_id
                   AND t_next.stop_sequence = et.seq_d + 1
             )) as edge_terminating_train_count
        """
    )

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "from_id": st_from.id,
            "to_id": st_to.id,
        },
    ).fetchone()

    if not result or result[0] == 0:
        raise ValueError(
            f"No qualifying adjacent timetable edge found for {from_station_code} to {to_station_code}"
        )

    edge_volume = int(result[0])
    convergence_count = int(result[1])
    originating_count = int(result[2])
    bifurcation_count = int(result[3])
    terminating_count = int(result[4])

    return {
        "from_station_code": from_station_code,
        "to_station_code": to_station_code,
        "timetable_snapshot_id": timetable_snapshot_id,
        "edge_volume": edge_volume,
        "convergence_count": convergence_count,
        "originating_count": originating_count,
        "bifurcation_count": bifurcation_count,
        "terminating_count": terminating_count,
    }


def calculate_train_route_edge_exclusivity(
    db: Session, timetable_snapshot_id: int, train_number: str
) -> dict[str, object]:
    """Calculate historical timetable-derived structural route edge exclusivity analytics."""
    from railgati.models.train import Train, TrainObservation

    train = (
        db.query(Train)
        .join(TrainObservation, TrainObservation.train_id == Train.id)
        .filter(
            Train.number == train_number,
            TrainObservation.snapshot_id == timetable_snapshot_id,
        )
        .first()
    )
    if not train:
        raise ValueError(f"Train {train_number} not found in active snapshot")

    query = text(
        """
        WITH target_train AS (
            SELECT :train_id AS id
        ),
        target_len AS (
            SELECT COUNT(*) as clen
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id
              AND train_id = (SELECT id FROM target_train)
        ),
        target_edges AS (
            SELECT
                t1.station_id as o,
                t2.station_id as d,
                t1.stop_sequence
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id
             AND t1.snapshot_id = t2.snapshot_id
             AND t1.stop_sequence + 1 = t2.stop_sequence
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.train_id = (SELECT id FROM target_train)
        ),
        edge_exclusivity AS (
            SELECT
                te.stop_sequence,
                te.o,
                te.d,
                NOT EXISTS (
                    SELECT 1
                    FROM train_stop_observations tso1
                    JOIN train_stop_observations tso2
                      ON tso2.train_id = tso1.train_id
                     AND tso2.station_id = te.d
                     AND tso2.snapshot_id = :snapshot_id
                     AND tso2.stop_sequence = tso1.stop_sequence + 1
                    WHERE tso1.station_id = te.o
                      AND tso1.snapshot_id = :snapshot_id
                      AND (
                          (SELECT COUNT(*) FROM train_stop_observations WHERE snapshot_id = :snapshot_id AND train_id = tso1.train_id) != (SELECT clen FROM target_len)
                          OR EXISTS (
                              SELECT 1
                              FROM train_stop_observations targ
                              JOIN train_stop_observations cand
                                ON targ.stop_sequence = cand.stop_sequence
                               AND cand.train_id = tso1.train_id
                               AND cand.snapshot_id = :snapshot_id
                              WHERE targ.train_id = (SELECT id FROM target_train)
                                AND targ.snapshot_id = :snapshot_id
                                AND targ.station_id != cand.station_id
                          )
                      )
                ) as is_exclusive
            FROM target_edges te
        )
        SELECT
            (SELECT COUNT(*) FROM target_edges) as route_edge_count,
            COUNT(CASE WHEN is_exclusive THEN 1 END) as exclusive_edge_count
        FROM edge_exclusivity
        """
    )

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "train_id": train.id,
        },
    ).fetchone()

    route_edge_count = int(result[0]) if result and result[0] is not None else 0
    exclusive_edge_count = int(result[1]) if result and result[1] is not None else 0
    route_length = route_edge_count + 1 if route_edge_count > 0 else 0
    # Wait, if route_edge_count == 0, the train could have 1 stop. Let's just query the stop count if needed,
    # but route_edge_count + 1 is accurate for connected sequences. If a train has 1 stop, route_edge_count is 0.
    # Let's get the exact stop count.

    # Actually, we can get stop count properly to be safe:
    stop_count_query = text(
        "SELECT COUNT(*) FROM train_stop_observations WHERE snapshot_id = :snapshot_id AND train_id = :train_id"
    )
    stop_count = int(
        db.execute(
            stop_count_query, {"snapshot_id": timetable_snapshot_id, "train_id": train.id}
        ).scalar()
        or 0
    )

    shared_edge_count = route_edge_count - exclusive_edge_count

    exclusivity_ratio = None
    if route_edge_count > 0:
        exclusivity_ratio = exclusive_edge_count / route_edge_count

    return {
        "train_number": train.number,
        "timetable_snapshot_id": timetable_snapshot_id,
        "route_length": stop_count,
        "route_edge_count": route_edge_count,
        "exclusive_edge_count": exclusive_edge_count,
        "shared_edge_count": shared_edge_count,
        "exclusivity_ratio": exclusivity_ratio,
    }


def calculate_edge_route_terminal_dispersion(
    db: Session,
    timetable_snapshot_id: int,
    from_station_code: str,
    to_station_code: str,
) -> dict[str, typing.Any]:
    """Calculate historical timetable-derived structural routing terminal dispersion for an edge."""

    from sqlalchemy import select, text

    from railgati.models.station import Station

    # 1. Verify Origin Station
    from_station = db.scalar(select(Station).filter(Station.code == from_station_code.upper()))
    if not from_station:
        raise ValueError(f"Station not found: {from_station_code}")

    # 2. Verify Destination Station
    to_station = db.scalar(select(Station).filter(Station.code == to_station_code.upper()))
    if not to_station:
        raise ValueError(f"Station not found: {to_station_code}")

    query = text("""
        WITH edge_trains AS (
            SELECT DISTINCT
                t1.train_id
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id
             AND t1.snapshot_id = t2.snapshot_id
             AND t2.stop_sequence = t1.stop_sequence + 1
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = :from_id
              AND t2.station_id = :to_id
        ),
        train_bounds AS (
            SELECT
                tso.train_id,
                MIN(tso.stop_sequence) as min_seq,
                MAX(tso.stop_sequence) as max_seq
            FROM train_stop_observations tso
            JOIN edge_trains et ON tso.train_id = et.train_id
            WHERE tso.snapshot_id = :snapshot_id
            GROUP BY tso.train_id
        ),
        train_terminals AS (
            SELECT
                tb.train_id,
                orig_tso.station_id as origin_id,
                dest_tso.station_id as dest_id
            FROM train_bounds tb
            JOIN train_stop_observations orig_tso
              ON orig_tso.train_id = tb.train_id
             AND orig_tso.stop_sequence = tb.min_seq
             AND orig_tso.snapshot_id = :snapshot_id
            JOIN train_stop_observations dest_tso
              ON dest_tso.train_id = tb.train_id
             AND dest_tso.stop_sequence = tb.max_seq
             AND dest_tso.snapshot_id = :snapshot_id
        )
        SELECT
            COUNT(train_id) as traversing_train_count,
            COUNT(DISTINCT origin_id) as distinct_origin_count,
            COUNT(DISTINCT dest_id) as distinct_destination_count
        FROM train_terminals;
    """)

    result = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "from_id": from_station.id,
            "to_id": to_station.id,
        },
    ).fetchone()

    traversing_train_count = result.traversing_train_count if result else 0
    distinct_origin_count = result.distinct_origin_count if result else 0
    distinct_destination_count = result.distinct_destination_count if result else 0

    if traversing_train_count == 0:
        raise ValueError(
            f"Edge not found: {from_station_code} -> {to_station_code} "
            f"in snapshot {timetable_snapshot_id}"
        )

    return {
        "from_station_code": from_station_code,
        "to_station_code": to_station_code,
        "timetable_snapshot_id": timetable_snapshot_id,
        "traversing_train_count": traversing_train_count,
        "distinct_origin_count": distinct_origin_count,
        "distinct_destination_count": distinct_destination_count,
    }


def calculate_edge_route_co_traversal_affinity(
    db: Session,
    timetable_snapshot_id: int,
    from_station_code: str,
    to_station_code: str,
) -> dict[str, typing.Any]:
    """Calculate historical timetable-derived edge co-traversal affinity."""

    from sqlalchemy import select, text

    from railgati.models.station import Station

    from_station = db.scalar(select(Station).filter(Station.code == from_station_code.upper()))
    if not from_station:
        raise ValueError(f"Station not found: {from_station_code}")

    to_station = db.scalar(select(Station).filter(Station.code == to_station_code.upper()))
    if not to_station:
        raise ValueError(f"Station not found: {to_station_code}")

    query = text("""
        WITH target_trains AS (
            SELECT DISTINCT t1.train_id
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id AND t1.snapshot_id = t2.snapshot_id
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = :from_id
              AND t2.station_id = :to_id
              AND t2.stop_sequence = t1.stop_sequence + 1
        ),
        target_train_count AS (
            SELECT COUNT(*) as c FROM target_trains
        ),
        other_edges AS (
            SELECT
                t1.station_id as o,
                t2.station_id as d,
                COUNT(DISTINCT t1.train_id) as shared_trains
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id AND t1.snapshot_id = t2.snapshot_id
            JOIN target_trains tt ON tt.train_id = t1.train_id
            WHERE t1.snapshot_id = :snapshot_id
              AND t2.stop_sequence = t1.stop_sequence + 1
              AND NOT (t1.station_id = :from_id AND t2.station_id = :to_id)
            GROUP BY t1.station_id, t2.station_id
        )
        SELECT
            (SELECT c FROM target_train_count) as traversing_train_count,
            s1.code as o_code,
            s2.code as d_code,
            oe.shared_trains
        FROM other_edges oe
        JOIN stations s1 ON s1.id = oe.o
        JOIN stations s2 ON s2.id = oe.d
        ORDER BY oe.shared_trains DESC, s1.code ASC, s2.code ASC;
    """)

    rows = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "from_id": from_station.id,
            "to_id": to_station.id,
        },
    ).fetchall()

    traversing_train_count = 0
    if not rows:
        # We need to manually check if target edge exists to handle "0 trains" vs "just no co-traversals"
        edge_check_q = text("""
            SELECT COUNT(DISTINCT t1.train_id)
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id AND t1.snapshot_id = t2.snapshot_id
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = :from_id
              AND t2.station_id = :to_id
              AND t2.stop_sequence = t1.stop_sequence + 1
        """)
        traversing_train_count = (
            db.scalar(
                edge_check_q,
                {
                    "snapshot_id": timetable_snapshot_id,
                    "from_id": from_station.id,
                    "to_id": to_station.id,
                },
            )
            or 0
        )
        if traversing_train_count == 0:
            raise ValueError(
                f"Directed edge not found: {from_station_code}->{to_station_code} (no active timetable trains)."
            )
    else:
        traversing_train_count = rows[0][0]

    return {
        "from_station_code": from_station_code.upper(),
        "to_station_code": to_station_code.upper(),
        "timetable_snapshot_id": timetable_snapshot_id,
        "traversing_train_count": traversing_train_count,
        "shared_edges": [
            {
                "from_station_code": r[1],
                "to_station_code": r[2],
                "shared_train_count": r[3],
            }
            for r in rows
            if r[1] is not None
        ],
    }


def calculate_train_max_shared_sub_route(
    db: Session,
    timetable_snapshot_id: int,
    train_number: str,
) -> dict[str, typing.Any]:
    """Calculate maximum shared contiguous sub-route analytics."""

    from sqlalchemy import select, text

    from railgati.models.train import Train

    train = db.scalar(select(Train).filter(Train.number == train_number.upper()))
    if not train:
        raise ValueError(f"Train not found: {train_number}")

    # Must also verify the train actually exists in the snapshot observation table to respect isolation
    target_check = db.execute(
        text("""
        SELECT 1 FROM train_stop_observations
        WHERE train_id = :train_id AND snapshot_id = :snapshot_id
        LIMIT 1
    """),
        {"train_id": train.id, "snapshot_id": timetable_snapshot_id},
    ).scalar()

    if not target_check:
        raise ValueError(f"Train not found: {train_number} in snapshot {timetable_snapshot_id}")

    query = text("""
        WITH target_stops AS (
            SELECT
                t1.station_id,
                t1.stop_sequence,
                s.code as station_code
            FROM train_stop_observations t1
            JOIN stations s ON s.id = t1.station_id
            WHERE t1.train_id = :target_id
              AND t1.snapshot_id = :snapshot_id
        ),
        shared_segments AS (
            SELECT
                tr2.number as other_train,
                COUNT(*) as shared_len,
                MIN(ts.stop_sequence) as start_seq,
                MAX(ts.stop_sequence) as end_seq
            FROM train_stop_observations t2
            JOIN target_stops ts ON ts.station_id = t2.station_id
            JOIN trains tr2 ON tr2.id = t2.train_id
            WHERE t2.snapshot_id = :snapshot_id
              AND tr2.id != :target_id
            GROUP BY t2.train_id, tr2.number, (ts.stop_sequence - t2.stop_sequence)
        ),
        ranked_segments AS (
            SELECT
                ss.other_train,
                ss.shared_len,
                (SELECT station_code FROM target_stops WHERE stop_sequence = ss.start_seq) as start_code,
                (SELECT station_code FROM target_stops WHERE stop_sequence = ss.end_seq) as end_code,
                RANK() OVER (ORDER BY ss.shared_len DESC) as rnk
            FROM shared_segments ss
        )
        SELECT DISTINCT
            other_train,
            shared_len,
            start_code,
            end_code
        FROM ranked_segments
        WHERE rnk = 1
        ORDER BY other_train ASC, start_code ASC;
    """)

    rows = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "target_id": train.id,
        },
    ).fetchall()

    return {
        "target_train_number": train_number.upper(),
        "timetable_snapshot_id": timetable_snapshot_id,
        "top_shared_sub_routes": [
            {
                "other_train_number": r[0],
                "shared_station_count": r[1],
                "start_station_code": r[2],
                "end_station_code": r[3],
            }
            for r in rows
        ],
    }


def calculate_train_route_od_exclusivity(db: Session, train_number: str) -> dict[str, typing.Any]:
    """Phase 44: Calculates Train Route O-D Structural Exclusivity Analytics."""
    from sqlalchemy import select, text

    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.train import Train, TrainObservation

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    if not timetable_snapshot_id:
        raise ValueError("No active timetable snapshot available.")

    train = db.scalar(select(Train).filter(Train.number == train_number.upper()))
    if not train:
        raise ValueError(f"Train {train_number.upper()} not found.")

    obs = db.scalar(
        select(TrainObservation).filter(
            TrainObservation.train_id == train.id,
            TrainObservation.snapshot_id == timetable_snapshot_id,
        )
    )
    if not obs:
        raise ValueError(f"Train {train_number.upper()} not found in active timetable snapshot.")

    query = text("""
        WITH target_stops AS (
            SELECT station_id, stop_sequence,
                (SELECT code FROM stations WHERE id = station_id) as code
            FROM train_stop_observations
            WHERE train_id = :target_id
              AND snapshot_id = :snapshot_id
        ),
        target_pairs AS (
            SELECT DISTINCT
                t1.station_id as o_id, t1.code as o_code,
                t2.station_id as d_id, t2.code as d_code
            FROM target_stops t1
            JOIN target_stops t2 ON t1.stop_sequence < t2.stop_sequence
        ),
        shared_pairs AS (
            SELECT DISTINCT tp.o_id, tp.d_id
            FROM target_pairs tp
            JOIN train_stop_observations ts1
              ON ts1.station_id = tp.o_id AND ts1.snapshot_id = :snapshot_id
            JOIN train_stop_observations ts2
              ON ts2.station_id = tp.d_id AND ts2.snapshot_id = :snapshot_id
             AND ts1.train_id = ts2.train_id
             AND ts1.stop_sequence < ts2.stop_sequence
            WHERE ts1.train_id != :target_id
        ),
        exclusive_pairs AS (
            SELECT tp.o_code, tp.d_code
            FROM target_pairs tp
            LEFT JOIN shared_pairs sp ON tp.o_id = sp.o_id AND tp.d_id = sp.d_id
            WHERE sp.o_id IS NULL
        )
        SELECT o_code, d_code
        FROM exclusive_pairs
        ORDER BY o_code ASC, d_code ASC;
    """)

    rows = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "target_id": train.id,
        },
    ).fetchall()

    return {
        "target_train_number": train_number.upper(),
        "timetable_snapshot_id": timetable_snapshot_id,
        "exclusive_od_pair_count": len(rows),
        "exclusive_od_pairs": [
            {
                "origin_station_code": r[0],
                "destination_station_code": r[1],
            }
            for r in rows
        ],
    }


def calculate_station_pair_route_diversity(
    db, from_station_code: str, to_station_code: str
) -> dict[str, typing.Any]:
    from sqlalchemy import text

    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.station import Station

    from_station_code = from_station_code.upper()
    to_station_code = to_station_code.upper()

    from_st = db.query(Station).filter(Station.code == from_station_code).first()
    if not from_st:
        raise ValueError(f"Station not found: {from_station_code}")
    to_st = db.query(Station).filter(Station.code == to_station_code).first()
    if not to_st:
        raise ValueError(f"Station not found: {to_station_code}")

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    if not timetable_snapshot_id:
        raise ValueError("No active timetable snapshot available.")

    query = text("""
        WITH target_trains AS (
            SELECT t1.train_id, t1.stop_sequence as o_seq, t2.stop_sequence as d_seq
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id AND t1.snapshot_id = t2.snapshot_id
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = :from_id
              AND t2.station_id = :to_id
              AND t1.stop_sequence < t2.stop_sequence
        )
        SELECT
            tt.train_id,
            tt.o_seq,
            tt.d_seq,
            s.code
        FROM target_trains tt
        JOIN train_stop_observations ts
          ON ts.train_id = tt.train_id
         AND ts.snapshot_id = :snapshot_id
         AND ts.stop_sequence >= tt.o_seq
         AND ts.stop_sequence <= tt.d_seq
        JOIN stations s ON s.id = ts.station_id
        ORDER BY tt.train_id, tt.o_seq, tt.d_seq, ts.stop_sequence ASC
    """)

    rows = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "from_id": from_st.id,
            "to_id": to_st.id,
        },
    ).fetchall()

    import itertools

    paths_map = {}

    for _, group in itertools.groupby(rows, key=lambda x: (x[0], x[1], x[2])):
        seq = tuple(row[3] for row in group)
        paths_map[seq] = paths_map.get(seq, 0) + 1

    paths = []
    for seq, count in paths_map.items():
        paths.append(
            {"station_sequence": list(seq), "path_length": len(seq), "traversal_count": count}
        )

    paths.sort(key=lambda x: (-x["traversal_count"], -x["path_length"], x["station_sequence"]))

    return {
        "from_station_code": from_station_code,
        "to_station_code": to_station_code,
        "timetable_snapshot_id": timetable_snapshot_id,
        "distinct_path_count": len(paths),
        "paths": paths,
    }


from typing import Any

from sqlalchemy.orm import Session


def calculate_station_pair_intermediate_hubs(
    db: Session, from_station_code: str, to_station_code: str
) -> dict[str, Any]:
    from sqlalchemy import select

    from railgati.api.v1.snapshots import (
        get_active_station_snapshot_id,
        get_active_timetable_snapshot_id,
    )
    from railgati.models.station import Station, StationObservation

    from_station_code = from_station_code.upper()
    to_station_code = to_station_code.upper()

    from_st = db.scalar(select(Station).filter(Station.code == from_station_code))
    if not from_st:
        raise ValueError(f"Station not found: {from_station_code}")

    to_st = db.scalar(select(Station).filter(Station.code == to_station_code))
    if not to_st:
        raise ValueError(f"Station not found: {to_station_code}")

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    if not timetable_snapshot_id:
        raise ValueError("No active timetable snapshot available.")

    station_snapshot_id = get_active_station_snapshot_id(db)

    # First get total traversal instance count
    total_query = text("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT t1.train_id, t1.stop_sequence as o_seq, t2.stop_sequence as d_seq
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id AND t1.snapshot_id = t2.snapshot_id
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = :from_id
              AND t2.station_id = :to_id
              AND t1.stop_sequence < t2.stop_sequence
        ) q
    """)
    total_instances = (
        db.scalar(
            total_query,
            {"snapshot_id": timetable_snapshot_id, "from_id": from_st.id, "to_id": to_st.id},
        )
        or 0
    )

    if total_instances == 0:
        return {
            "from_station_code": from_station_code,
            "to_station_code": to_station_code,
            "timetable_snapshot_id": timetable_snapshot_id,
            "total_traversal_instances": 0,
            "intermediate_hubs": [],
        }

    query = text("""
        WITH target_trains AS (
            SELECT t1.train_id, t1.stop_sequence as o_seq, t2.stop_sequence as d_seq
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id AND t1.snapshot_id = t2.snapshot_id
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = :from_id
              AND t2.station_id = :to_id
              AND t1.stop_sequence < t2.stop_sequence
        ),
        hub_occurrences AS (
            SELECT
                s.id as station_id,
                s.code as station_code,
                ts.train_id,
                tt.o_seq,
                tt.d_seq
            FROM target_trains tt
            JOIN train_stop_observations ts
              ON ts.train_id = tt.train_id
             AND ts.snapshot_id = :snapshot_id
             AND ts.stop_sequence > tt.o_seq
             AND ts.stop_sequence < tt.d_seq
            JOIN stations s ON s.id = ts.station_id
        )
        SELECT
            station_code as code,
            MAX(station_id) as station_id,
            COUNT(train_id) as occurrence_count,
            (
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT train_id, o_seq, d_seq
                    FROM hub_occurrences h2
                    WHERE h2.station_code = h1.station_code
                ) q
            ) as traversal_instance_count
        FROM hub_occurrences h1
        GROUP BY station_code
        ORDER BY traversal_instance_count DESC, occurrence_count DESC, station_code ASC
    """)

    res = db.execute(
        query, {"snapshot_id": timetable_snapshot_id, "from_id": from_st.id, "to_id": to_st.id}
    ).fetchall()

    # Preload active station names
    station_ids = [r.station_id for r in res]
    station_names = {}
    if station_ids:
        obs = db.scalars(
            select(StationObservation)
            .filter(StationObservation.snapshot_id == station_snapshot_id)
            .filter(StationObservation.station_id.in_(station_ids))
        ).all()
        station_names = {o.station_id: o.name for o in obs}

    hubs = []
    for r in res:
        hubs.append(
            {
                "station_code": r.code,
                "station_name": station_names.get(r.station_id),
                "traversal_instance_count": r.traversal_instance_count,
                "occurrence_count": r.occurrence_count,
            }
        )

    return {
        "from_station_code": from_station_code,
        "to_station_code": to_station_code,
        "timetable_snapshot_id": timetable_snapshot_id,
        "total_traversal_instances": total_instances,
        "intermediate_hubs": hubs,
    }


def calculate_station_pair_route_boundary_confinement(
    db: Session, from_station_code: str, to_station_code: str
) -> dict[str, typing.Any]:
    from fastapi import HTTPException, status
    from sqlalchemy import select

    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.station import Station

    from_st = db.scalar(select(Station).filter(Station.code == from_station_code.upper()))
    if not from_st:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Station not found: {from_station_code}"
        )

    to_st = db.scalar(select(Station).filter(Station.code == to_station_code.upper()))
    if not to_st:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Station not found: {to_station_code}"
        )

    timetable_snap_id = get_active_timetable_snapshot_id(db)

    q = text("""
        WITH target_traversals AS (
            SELECT DISTINCT
                t1.train_id,
                t1.stop_sequence as o_seq,
                t2.stop_sequence as d_seq
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id AND t1.snapshot_id = t2.snapshot_id
            WHERE t1.snapshot_id = :snap_id
              AND t1.station_id = :from_id
              AND t2.station_id = :to_id
              AND t1.stop_sequence < t2.stop_sequence
        ),
        train_boundaries AS (
            SELECT
                t.train_id,
                MIN(t.stop_sequence) as t_min,
                MAX(t.stop_sequence) as t_max
            FROM target_traversals tt
            JOIN train_stop_observations t
              ON t.train_id = tt.train_id AND t.snapshot_id = :snap_id
            GROUP BY t.train_id
        ),
        classified_traversals AS (
            SELECT
                tt.train_id,
                tt.o_seq,
                tt.d_seq,
                tb.t_min,
                tb.t_max,
                CASE
                    WHEN tt.o_seq = tb.t_min AND tt.d_seq = tb.t_max THEN 'STRICTLY_BOUNDED'
                    WHEN tt.o_seq = tb.t_min AND tt.d_seq < tb.t_max THEN 'ORIGIN_BOUNDED'
                    WHEN tt.o_seq > tb.t_min AND tt.d_seq = tb.t_max THEN 'DESTINATION_BOUNDED'
                    ELSE 'UNBOUNDED_EMBEDDED'
                END as boundary_state
            FROM target_traversals tt
            JOIN train_boundaries tb ON tt.train_id = tb.train_id
        )
        SELECT
            boundary_state,
            COUNT(*) as traversal_count
        FROM classified_traversals
        GROUP BY boundary_state
    """)

    rows = db.execute(
        q,
        {
            "snap_id": timetable_snap_id,
            "from_id": from_st.id,
            "to_id": to_st.id,
        },
    ).fetchall()

    strictly_bounded_count = 0
    origin_bounded_count = 0
    destination_bounded_count = 0
    unbounded_embedded_count = 0
    total_traversal_count = 0

    for row in rows:
        state = row[0]
        count = row[1]
        total_traversal_count += count
        if state == "STRICTLY_BOUNDED":
            strictly_bounded_count += count
        elif state == "ORIGIN_BOUNDED":
            origin_bounded_count += count
        elif state == "DESTINATION_BOUNDED":
            destination_bounded_count += count
        elif state == "UNBOUNDED_EMBEDDED":
            unbounded_embedded_count += count

    return {
        "from_station_code": from_station_code,
        "to_station_code": to_station_code,
        "timetable_snapshot_id": timetable_snap_id,
        "total_traversal_count": total_traversal_count,
        "strictly_bounded_count": strictly_bounded_count,
        "origin_bounded_count": origin_bounded_count,
        "destination_bounded_count": destination_bounded_count,
        "unbounded_embedded_count": unbounded_embedded_count,
    }


def calculate_train_route_terminal_incidence(
    db: Session, train_number: str
) -> dict[str, typing.Any]:
    """Phase 48: Network Train Route Terminal Incidence Analytics."""
    from sqlalchemy import select, text

    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.train import Train, TrainObservation

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    if not timetable_snapshot_id:
        raise ValueError("No active timetable snapshot available.")

    train_num_upper = train_number.upper()
    train_obs = db.scalar(
        select(TrainObservation)
        .join(Train, Train.id == TrainObservation.train_id)
        .filter(
            Train.number == train_num_upper, TrainObservation.snapshot_id == timetable_snapshot_id
        )
    )

    if not train_obs:
        raise ValueError(f"Train {train_num_upper} not found in the active timetable snapshot.")

    target_train_id = train_obs.train_id

    # The query calculates the network terminals from the active snapshot,
    # then probes them with the target train's occurrences.
    query = text("""
        WITH train_bounds AS (
            SELECT train_id, MIN(stop_sequence) as t_min, MAX(stop_sequence) as t_max
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id
            GROUP BY train_id
        ),
        global_terminals AS (
            SELECT DISTINCT ts.station_id
            FROM train_stop_observations ts
            JOIN train_bounds tb ON ts.train_id = tb.train_id
            WHERE ts.snapshot_id = :snapshot_id
              AND (ts.stop_sequence = tb.t_min OR ts.stop_sequence = tb.t_max)
        ),
        target_stops AS (
            SELECT station_id, stop_sequence
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id
              AND train_id = :target_train_id
        )
        SELECT
            (SELECT COUNT(*) FROM target_stops) as route_stop_occurrence_count,
            (SELECT COUNT(DISTINCT station_id) FROM target_stops) as distinct_route_station_count,
            (SELECT COUNT(*) FROM target_stops WHERE station_id IN (SELECT station_id FROM global_terminals)) as terminal_occurrence_count,
            (SELECT COUNT(DISTINCT station_id) FROM target_stops WHERE station_id IN (SELECT station_id FROM global_terminals)) as distinct_terminal_station_count
    """)

    res = db.execute(
        query, {"snapshot_id": timetable_snapshot_id, "target_train_id": target_train_id}
    ).fetchone()

    if not res:
        raise ValueError("Failed to calculate train route terminal incidence.")

    route_stop_occurrence_count = res[0] or 0
    distinct_route_station_count = res[1] or 0
    terminal_occurrence_count = res[2] or 0
    distinct_terminal_station_count = res[3] or 0

    incidence_ratio = 0.0
    if route_stop_occurrence_count > 0:
        incidence_ratio = float(terminal_occurrence_count) / float(route_stop_occurrence_count)

    return {
        "train_number": train_num_upper,
        "route_stop_occurrence_count": route_stop_occurrence_count,
        "distinct_route_station_count": distinct_route_station_count,
        "terminal_occurrence_count": terminal_occurrence_count,
        "distinct_terminal_station_count": distinct_terminal_station_count,
        "incidence_ratio": round(incidence_ratio, 3),
    }


def calculate_station_pair_route_extension(
    db: Session, origin_code: str, destination_code: str, timetable_snapshot_id: int
) -> dict[str, object]:
    """
    Calculate the Phase 49 Network Station Pair Route Extension Analytics metric.
    Extracts the timetable-derived station extension structures lying outside the O->D pair.
    """
    origin_code = origin_code.strip().upper()
    destination_code = destination_code.strip().upper()

    if origin_code == destination_code:
        raise ValueError("Origin and destination cannot be identical.")

    from sqlalchemy import select

    from railgati.models.station import Station

    # Validate stations
    orig_st = db.scalar(select(Station).filter_by(code=origin_code))
    dest_st = db.scalar(select(Station).filter_by(code=destination_code))
    if not orig_st or not dest_st:
        return {}  # Signal 404

    query = text("""
        WITH valid_traversals AS (
            SELECT
                t1.train_id,
                t1.stop_sequence as s_o,
                t2.stop_sequence as s_d
            FROM train_stop_observations t1
            JOIN train_stop_observations t2
              ON t1.train_id = t2.train_id
             AND t1.snapshot_id = t2.snapshot_id
            WHERE t1.snapshot_id = :snapshot_id
              AND t1.station_id = :orig_id
              AND t2.station_id = :dest_id
              AND t1.stop_sequence < t2.stop_sequence
        ),
        pre_origin_stops AS (
            SELECT DISTINCT ts.station_id
            FROM train_stop_observations ts
            JOIN valid_traversals vt ON ts.train_id = vt.train_id
            WHERE ts.snapshot_id = :snapshot_id
              AND ts.stop_sequence < vt.s_o
        ),
        post_dest_stops AS (
            SELECT DISTINCT ts.station_id
            FROM train_stop_observations ts
            JOIN valid_traversals vt ON ts.train_id = vt.train_id
            WHERE ts.snapshot_id = :snapshot_id
              AND ts.stop_sequence > vt.s_d
        ),
        combined_extension AS (
            SELECT station_id FROM pre_origin_stops
            UNION
            SELECT station_id FROM post_dest_stops
        )
        SELECT
            (SELECT COUNT(*) FROM valid_traversals) as traversal_occurrence_count,
            (SELECT COUNT(*) FROM pre_origin_stops) as pre_origin_station_count,
            (SELECT COUNT(*) FROM post_dest_stops) as post_destination_station_count,
            (SELECT COUNT(*) FROM combined_extension) as total_extension_station_count
    """)

    res = db.execute(
        query, {"snapshot_id": timetable_snapshot_id, "orig_id": orig_st.id, "dest_id": dest_st.id}
    ).fetchone()

    # If no valid traversals were found, it means the O->D direct path does not exist.
    # Return empty to signal 404 per API convention.
    if not res or res[0] == 0:
        return {}

    return {
        "origin_station": origin_code,
        "destination_station": destination_code,
        "traversal_occurrence_count": res[0],
        "pre_origin_station_count": res[1],
        "post_destination_station_count": res[2],
        "total_extension_station_count": res[3],
    }


def calculate_station_pair_temporal_order_inversions(
    db: Session, origin_code: str, destination_code: str, snapshot_id: int
) -> dict[str, Any]:
    """
    Calculate network station-pair temporal order inversion analytics.
    Finds how often scheduled traversals on a shared origin-destination structural corridor
    invert their temporal order (i.e. one departs strictly later but arrives strictly earlier).
    """
    if origin_code == destination_code:
        raise ValueError("Origin and destination stations cannot be identical.")

    is_sqlite = db.bind and db.bind.dialect.name == "sqlite"

    if is_sqlite:
        dep_mins_expr = "CAST(strftime('%H', t1.departure_time) AS INTEGER) * 60 + CAST(strftime('%M', t1.departure_time) AS INTEGER)"
        arr_mins_expr = "CAST(strftime('%H', t2.arrival_time) AS INTEGER) * 60 + CAST(strftime('%M', t2.arrival_time) AS INTEGER)"
    else:
        dep_mins_expr = "EXTRACT(HOUR FROM CAST(t1.departure_time AS time)) * 60 + EXTRACT(MINUTE FROM CAST(t1.departure_time AS time))"
        arr_mins_expr = "EXTRACT(HOUR FROM CAST(t2.arrival_time AS time)) * 60 + EXTRACT(MINUTE FROM CAST(t2.arrival_time AS time))"

    query = text(f"""
    WITH valid_traversals AS (
        SELECT
            t1.train_id,
            t1.stop_sequence as s_o,
            t2.stop_sequence as s_d,
            t1.departure_time,
            t1.source_day as day_o,
            t2.arrival_time,
            t2.source_day as day_d,
            (t1.source_day - 1) * 24 * 60 + {dep_mins_expr} as abs_dep_mins,

            (t2.source_day - 1) * 24 * 60 + {arr_mins_expr} as abs_arr_mins

        FROM train_stop_observations t1
        JOIN train_stop_observations t2
          ON t1.train_id = t2.train_id
         AND t1.snapshot_id = t2.snapshot_id
        WHERE t1.snapshot_id = :snapshot_id
          AND t1.station_id = (SELECT id FROM stations WHERE code = :o_code)
          AND t2.station_id = (SELECT id FROM stations WHERE code = :d_code)
          AND t1.stop_sequence < t2.stop_sequence
          AND t1.departure_time IS NOT NULL
          AND t2.arrival_time IS NOT NULL
          AND t1.source_day IS NOT NULL
          AND t2.source_day IS NOT NULL
    ),
    inversions AS (
        SELECT
            v1.train_id as train_a,
            v1.s_o as s_o_a,
            v1.s_d as s_d_a,
            v2.train_id as train_b,
            v2.s_o as s_o_b,
            v2.s_d as s_d_b
        FROM valid_traversals v1
        JOIN valid_traversals v2
          ON (v1.train_id != v2.train_id OR v1.s_o != v2.s_o OR v1.s_d != v2.s_d)
        WHERE v1.abs_dep_mins < v2.abs_dep_mins
          AND v1.abs_arr_mins > v2.abs_arr_mins
    )
    SELECT
        (SELECT COUNT(*) FROM valid_traversals) as total_valid_traversal_count,
        COUNT(*) as inversion_pair_count,
        (
            SELECT COUNT(DISTINCT train_id)
            FROM (
                SELECT train_a as train_id FROM inversions
                UNION
                SELECT train_b as train_id FROM inversions
            ) as distinct_inverted
        ) as distinct_inverted_train_count
    FROM inversions
    """)

    res = db.execute(
        query, {"snapshot_id": snapshot_id, "o_code": origin_code, "d_code": destination_code}
    ).fetchone()
    if not res:
        return {
            "origin_station_code": origin_code,
            "destination_station_code": destination_code,
            "timetable_snapshot_id": snapshot_id,
            "total_valid_traversal_count": 0,
            "inversion_pair_count": 0,
            "distinct_inverted_train_count": 0,
        }

    mapping = dict(res._mapping)
    total_valid = mapping["total_valid_traversal_count"] or 0
    inv_count = mapping["inversion_pair_count"] or 0
    dist_trains = mapping["distinct_inverted_train_count"] or 0

    return {
        "origin_station_code": origin_code,
        "destination_station_code": destination_code,
        "timetable_snapshot_id": snapshot_id,
        "total_valid_traversal_count": total_valid,
        "inversion_pair_count": inv_count,
        "distinct_inverted_train_count": dist_trains,
    }


def calculate_station_pair_intermediate_halt_stratification(
    db: Session, origin_code: str, destination_code: str, snapshot_id: int
) -> dict[str, Any]:
    """
    Calculate the stratification of intermediate halt counts for
    trains traveling between two stations.
    """
    if origin_code == destination_code:
        raise ValueError("Origin and destination stations cannot be identical.")

    query = text("""
    WITH traversals AS (
        SELECT
            t1.train_id,
            (t2.stop_sequence - t1.stop_sequence - 1) as halt_count
        FROM train_stop_observations t1
        JOIN train_stop_observations t2
          ON t1.train_id = t2.train_id
         AND t1.snapshot_id = t2.snapshot_id
        WHERE t1.snapshot_id = :snapshot_id
          AND t1.station_id = (SELECT id FROM stations WHERE code = :o_code)
          AND t2.station_id = (SELECT id FROM stations WHERE code = :d_code)
          AND t1.stop_sequence < t2.stop_sequence
    )
    SELECT
        COUNT(*) as total_traversal_count,
        MIN(halt_count) as min_halts,
        MAX(halt_count) as max_halts,
        COUNT(DISTINCT halt_count) as distinct_halt_strata_count
    FROM traversals
    """)

    res = db.execute(
        query, {"snapshot_id": snapshot_id, "o_code": origin_code, "d_code": destination_code}
    ).fetchone()

    if not res:
        total_traversals = 0
        min_halts = None
        max_halts = None
        strata_count = 0
    else:
        mapping = dict(res._mapping)
        total_traversals = mapping["total_traversal_count"] or 0
        min_halts = mapping["min_halts"]
        max_halts = mapping["max_halts"]
        strata_count = mapping["distinct_halt_strata_count"] or 0

        if total_traversals == 0:
            min_halts = None
            max_halts = None

    is_homogeneous = False
    if total_traversals > 0 and min_halts is not None and max_halts is not None:
        is_homogeneous = min_halts == max_halts

    return {
        "origin_station_code": origin_code,
        "destination_station_code": destination_code,
        "timetable_snapshot_id": snapshot_id,
        "total_traversal_count": total_traversals,
        "min_halts": min_halts,
        "max_halts": max_halts,
        "distinct_halt_strata_count": strata_count,
        "is_perfectly_homogeneous": is_homogeneous,
    }


def calculate_station_pair_return_service_adherence(
    db: Session, origin_code: str, destination_code: str, snapshot_id: int
) -> dict[str, Any]:
    """
    Calculate the structural adherence of published return services
    for trains traveling between two stations.
    """
    if origin_code == destination_code:
        raise ValueError("Origin and destination stations cannot be identical.")

    query = text("""
    WITH forward_traversals AS (
        SELECT
            t1.train_id,
            t1.snapshot_id,
            tr_obs.return_train_number,
            t1.stop_sequence as o_seq,
            t2.stop_sequence as d_seq
        FROM train_stop_observations t1
        JOIN train_stop_observations t2
          ON t1.train_id = t2.train_id
         AND t1.snapshot_id = t2.snapshot_id
        JOIN train_observations tr_obs
          ON t1.train_id = tr_obs.train_id
         AND t1.snapshot_id = tr_obs.snapshot_id
        WHERE t1.snapshot_id = :snapshot_id
          AND t1.station_id = (SELECT id FROM stations WHERE code = :o_code)
          AND t2.station_id = (SELECT id FROM stations WHERE code = :d_code)
          AND t1.stop_sequence < t2.stop_sequence
    ),
    return_validation AS (
        SELECT
            f.train_id,
            f.o_seq,
            f.d_seq,
            CASE
                WHEN f.return_train_number IS NULL OR f.return_train_number = '' THEN 'unpaired'
                WHEN r_t.id IS NULL THEN 'non_adherent'
                WHEN EXISTS (
                    SELECT 1
                    FROM train_stop_observations r_t1
                    JOIN train_stop_observations r_t2
                      ON r_t1.train_id = r_t2.train_id
                     AND r_t1.snapshot_id = r_t2.snapshot_id
                    WHERE r_t1.train_id = r_t.id
                      AND r_t1.snapshot_id = f.snapshot_id
                      AND r_t1.station_id = (SELECT id FROM stations WHERE code = :d_code)
                      AND r_t2.station_id = (SELECT id FROM stations WHERE code = :o_code)
                      AND r_t1.stop_sequence < r_t2.stop_sequence
                ) THEN 'adherent'
                ELSE 'non_adherent'
            END as adherence_status
        FROM forward_traversals f
        LEFT JOIN trains r_t
          ON r_t.number = f.return_train_number
    )
    SELECT
        COUNT(*) as total_forward_traversals,
        COUNT(CASE WHEN adherence_status = 'unpaired' THEN 1 END) as unpaired_traversals,
        COUNT(CASE WHEN adherence_status = 'adherent' THEN 1 END) as adherent_traversals,
        COUNT(CASE WHEN adherence_status = 'non_adherent' THEN 1 END) as non_adherent_traversals
    FROM return_validation;
    """)

    res = db.execute(
        query, {"snapshot_id": snapshot_id, "o_code": origin_code, "d_code": destination_code}
    ).fetchone()

    total_forward = 0
    unpaired = 0
    adherent = 0
    non_adherent = 0

    if res:
        mapping = dict(res._mapping)
        total_forward = mapping["total_forward_traversals"] or 0
        unpaired = mapping["unpaired_traversals"] or 0
        adherent = mapping["adherent_traversals"] or 0
        non_adherent = mapping["non_adherent_traversals"] or 0

    adherence_ratio = None
    unpaired_ratio = None
    non_adherent_ratio = None

    if total_forward > 0:
        adherence_ratio = adherent / total_forward
        unpaired_ratio = unpaired / total_forward
        non_adherent_ratio = non_adherent / total_forward

    return {
        "origin_station_code": origin_code,
        "destination_station_code": destination_code,
        "timetable_snapshot_id": snapshot_id,
        "total_forward_traversal_count": total_forward,
        "unpaired_traversal_count": unpaired,
        "adherent_return_traversal_count": adherent,
        "non_adherent_return_traversal_count": non_adherent,
        "adherence_ratio": adherence_ratio,
        "unpaired_ratio": unpaired_ratio,
        "non_adherent_ratio": non_adherent_ratio,
    }


def calculate_station_peak_simultaneous_presence(
    db: Session,
    timetable_snapshot_id: int,
    station_code: str,
) -> dict[str, typing.Any]:
    """Phase 53: Network Station Peak Simultaneous Presence Analytics."""
    from sqlalchemy import select, text

    from railgati.models.provenance import DatasetSnapshot
    from railgati.models.station import Station, StationObservation

    snapshot = db.scalar(
        select(DatasetSnapshot).filter(DatasetSnapshot.id == timetable_snapshot_id)
    )
    if not snapshot:
        raise ValueError("Timetable snapshot not found")

    station_code_upper = station_code.strip().upper()
    station = db.scalar(select(Station).filter(Station.code == station_code_upper))
    if not station:
        raise ValueError(f"Station '{station_code_upper}' not found")

    station_obs = db.scalar(
        select(StationObservation).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == timetable_snapshot_id,
        )
    )
    station_name = station_obs.name if station_obs else None

    is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"
    if is_sqlite:
        arr_calc = "CAST(strftime('%s', arrival_time) AS INTEGER) / 60"
        dep_calc = "CAST(strftime('%s', departure_time) AS INTEGER) / 60"
        time_logic = "departure_time < arrival_time"
    else:
        arr_calc = "EXTRACT(EPOCH FROM arrival_time::time)/60"
        dep_calc = "EXTRACT(EPOCH FROM departure_time::time)/60"
        time_logic = "departure_time < arrival_time"

    query = text(f"""
        WITH raw_events AS (
            SELECT
                (CAST(train_id AS TEXT) || '-' || CAST(stop_sequence AS TEXT)) as occurrence_id,
                (source_day * 1440 + {arr_calc}) as arr_mins,
                (source_day * 1440 + {dep_calc} +
                 CASE WHEN {time_logic} THEN 1440 ELSE 0 END) as dep_mins
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id
              AND station_id = :station_id
              AND arrival_time IS NOT NULL
              AND departure_time IS NOT NULL
              AND source_day IS NOT NULL
        ),
        events AS (
            SELECT arr_mins as event_time, 1 as change, occurrence_id FROM raw_events
            UNION ALL
            SELECT dep_mins as event_time, -1 as change, occurrence_id FROM raw_events
        ),
        running AS (
            SELECT
                event_time,
                change,
                occurrence_id,
                SUM(change) OVER (ORDER BY event_time ASC, change DESC, occurrence_id ASC) as concurrent_trains
            FROM events
        )
        SELECT
            COUNT(DISTINCT occurrence_id) as total_occurrences,
            MAX(concurrent_trains) as peak_concurrent
        FROM running;
    """)

    res = db.execute(
        query,
        {
            "snapshot_id": timetable_snapshot_id,
            "station_id": station.id,
        },
    ).fetchone()

    qualifying_occurrence_count = res[0] if res and res[0] is not None else 0
    peak_concurrent = int(res[1]) if res and res[1] is not None else None

    if qualifying_occurrence_count == 0:
        peak_concurrent = None

    return {
        "station_code": station_code_upper,
        "station_name": station_name,
        "timetable_snapshot_id": timetable_snapshot_id,
        "qualifying_occurrence_count": qualifying_occurrence_count,
        "peak_simultaneous_presence": peak_concurrent,
    }


def calculate_train_stop_temporal_skew(
    session: Session, snapshot_id: int, train_number: str
) -> dict[str, typing.Any]:

    from railgati.models.train import Train, TrainStopObservation

    train = session.query(Train).filter_by(number=train_number).first()
    if not train:
        raise ValueError(f"Train with number {train_number} not found")

    stops = (
        session.query(TrainStopObservation)
        .filter_by(snapshot_id=snapshot_id, train_id=train.id)
        .order_by(TrainStopObservation.stop_sequence.asc())
        .all()
    )

    if not stops or len(stops) < 2:
        return {
            "train_number": train_number,
            "timetable_snapshot_id": snapshot_id,
            "intermediate_stop_occurrence_count": 0,
            "valid_intermediate_timing_occurrence_count": 0,
            "mean_fraction": None,
            "temporal_skew": None,
            "journey_duration_minutes": None,
            "classification": None,
        }

    origin = stops[0]
    dest = stops[-1]

    if (
        not origin.departure_time
        or not dest.arrival_time
        or origin.source_day is None
        or dest.source_day is None
    ):
        return {
            "train_number": train_number,
            "timetable_snapshot_id": snapshot_id,
            "intermediate_stop_occurrence_count": max(0, len(stops) - 2),
            "valid_intermediate_timing_occurrence_count": 0,
            "mean_fraction": None,
            "temporal_skew": None,
            "journey_duration_minutes": None,
            "classification": None,
        }

    def time_to_mins(t_str: str) -> float:
        parts = t_str.split(":")
        return int(parts[0]) * 60.0 + int(parts[1])

    start_mins = origin.source_day * 1440.0 + time_to_mins(origin.departure_time)
    end_mins = dest.source_day * 1440.0 + time_to_mins(dest.arrival_time)

    if dest.arrival_time < origin.departure_time and dest.source_day == origin.source_day:
        end_mins += 1440.0

    duration = end_mins - start_mins
    if duration <= 0:
        return {
            "train_number": train_number,
            "timetable_snapshot_id": snapshot_id,
            "intermediate_stop_occurrence_count": max(0, len(stops) - 2),
            "valid_intermediate_timing_occurrence_count": 0,
            "mean_fraction": None,
            "temporal_skew": None,
            "journey_duration_minutes": None,
            "classification": None,
        }

    fractions = []
    intermediates = stops[1:-1]

    for o in intermediates:
        if o.source_day is None:
            continue

        arr_t = o.arrival_time
        dep_t = o.departure_time
        if not arr_t and not dep_t:
            continue

        m_list = []
        if arr_t:
            a_mins = o.source_day * 1440.0 + time_to_mins(arr_t)
            if arr_t < origin.departure_time and o.source_day == origin.source_day:
                a_mins += 1440.0
            m_list.append(a_mins)
        if dep_t:
            d_mins = o.source_day * 1440.0 + time_to_mins(dep_t)
            if dep_t < origin.departure_time and o.source_day == origin.source_day:
                d_mins += 1440.0
            m_list.append(d_mins)

        inter_mins = sum(m_list) / len(m_list)
        fractions.append((inter_mins - start_mins) / duration)

    mean_fraction = sum(fractions) / len(fractions) if fractions else None
    temporal_skew = mean_fraction - 0.5 if mean_fraction is not None else None

    classification = None
    if temporal_skew is not None:
        if temporal_skew < 0:
            classification = "FRONT_LOADED"
        elif temporal_skew == 0:
            classification = "BALANCED"
        else:
            classification = "BACK_LOADED"

    return {
        "train_number": train_number,
        "timetable_snapshot_id": snapshot_id,
        "intermediate_stop_occurrence_count": len(intermediates),
        "valid_intermediate_timing_occurrence_count": len(fractions),
        "mean_fraction": mean_fraction,
        "temporal_skew": temporal_skew,
        "journey_duration_minutes": duration,
        "classification": classification,
    }


def calculate_train_sequence_subgraph_density(
    db: Session, snapshot_id: int, train_number: str
) -> dict[str, Any]:
    """Calculate the sequence-induced subgraph density for a target train (Phase 55)."""
    from sqlalchemy import func, select, text

    from railgati.models.train import Train

    train = db.scalar(select(Train).filter(func.upper(Train.number) == train_number.upper()))
    if not train:
        raise ValueError(f"Train '{train_number}' not found.")

    query = text("""
    WITH target_seq AS (
        SELECT station_id, stop_sequence as seq
        FROM train_stop_observations
        WHERE train_id = :train_id AND snapshot_id = :snap_id
    ),
    global_edges AS (
        SELECT DISTINCT s1.station_id as o, s2.station_id as d
        FROM train_stop_observations s1
        JOIN train_stop_observations s2
          ON s1.train_id = s2.train_id AND s2.stop_sequence = s1.stop_sequence + 1
        WHERE s1.snapshot_id = :snap_id
    )
    SELECT
        (SELECT COUNT(*) FROM target_seq) as n,
        COUNT(CASE WHEN ts2.seq > ts1.seq + 1 AND ge.o IS NOT NULL THEN 1 END) as fwd_actual,
        COUNT(CASE WHEN ts2.seq < ts1.seq AND ge.o IS NOT NULL THEN 1 END) as bwd_actual
    FROM target_seq ts1
    JOIN target_seq ts2 ON ts1.seq != ts2.seq
    LEFT JOIN global_edges ge ON ge.o = ts1.station_id AND ge.d = ts2.station_id;
    """)
    result = db.execute(query, {"train_id": train.id, "snap_id": snapshot_id}).fetchone()

    n = result[0] if result and result[0] else 0
    fwd_actual = result[1] if result and result[1] else 0
    bwd_actual = result[2] if result and result[2] else 0

    d_fwd_max = ((n - 1) * (n - 2)) // 2 if n >= 3 else 0
    d_bwd_max = (n * (n - 1)) // 2 if n >= 2 else 0

    forward_density = float(fwd_actual) / d_fwd_max if d_fwd_max > 0 else 0.0
    backward_density = float(bwd_actual) / d_bwd_max if d_bwd_max > 0 else 0.0

    return {
        "train_number": train.number,
        "timetable_snapshot_id": snapshot_id,
        "total_sequence_occurrences": n,
        "forward_max_possible_chords": d_fwd_max,
        "backward_max_possible_chords": d_bwd_max,
        "forward_actual_chords": fwd_actual,
        "backward_actual_chords": bwd_actual,
        "forward_density": forward_density,
        "backward_density": backward_density,
    }


def calculate_train_sequence_topological_transition_continuity(
    db: Session, snapshot_id: int, train_number: str
) -> dict[str, Any]:
    """Calculate the sequence topological transition continuity (Phase 56)."""
    from sqlalchemy import func, select, text

    from railgati.models.train import Train

    train = db.scalar(select(Train).filter(func.upper(Train.number) == train_number.upper()))
    if not train:
        raise ValueError(f"Train '{train_number}' not found.")

    query = text("""
    WITH target_stops AS (
        SELECT station_id, stop_sequence as seq
        FROM train_stop_observations
        WHERE train_id = :train_id AND snapshot_id = :snap_id
    ),
    target_triplets AS (
        SELECT
            s1.station_id as st1, s1.seq as seq1,
            s2.station_id as st2, s2.seq as seq2,
            s3.station_id as st3, s3.seq as seq3
        FROM target_stops s1
        JOIN target_stops s2 ON s2.seq = s1.seq + 1
        JOIN target_stops s3 ON s3.seq = s2.seq + 1
    )
    SELECT
        tt.seq1, tt.seq2, tt.seq3,
        st1.code as code1, st2.code as code2, st3.code as code3,
        (SELECT COUNT(*)
         FROM train_stop_observations o1
         JOIN train_stop_observations o2
           ON o1.train_id = o2.train_id AND o1.snapshot_id = o2.snapshot_id AND o2.stop_sequence = o1.stop_sequence + 1
         WHERE o1.snapshot_id = :snap_id AND o1.station_id = tt.st1 AND o2.station_id = tt.st2
        ) as first_edge_occurrence_count,
        (SELECT COUNT(*)
         FROM train_stop_observations o1
         JOIN train_stop_observations o2
           ON o1.train_id = o2.train_id AND o1.snapshot_id = o2.snapshot_id AND o2.stop_sequence = o1.stop_sequence + 1
         JOIN train_stop_observations o3
           ON o2.train_id = o3.train_id AND o2.snapshot_id = o3.snapshot_id AND o3.stop_sequence = o2.stop_sequence + 1
         WHERE o1.snapshot_id = :snap_id AND o1.station_id = tt.st1 AND o2.station_id = tt.st2 AND o3.station_id = tt.st3
        ) as transition_occurrence_count
    FROM target_triplets tt
    JOIN stations st1 ON st1.id = tt.st1
    JOIN stations st2 ON st2.id = tt.st2
    JOIN stations st3 ON st3.id = tt.st3
    ORDER BY tt.seq1 ASC;
    """)

    results = db.execute(query, {"train_id": train.id, "snap_id": snapshot_id}).fetchall()

    if not results:
        return {
            "train_number": train.number,
            "timetable_snapshot_id": snapshot_id,
            "total_transition_count": 0,
            "average_continuity_ratio": None,
            "minimum_continuity_ratio": None,
            "maximum_continuity_ratio": None,
            "transitions": [],
        }

    transitions = []
    ratios = []

    for r in results:
        n_in = r.first_edge_occurrence_count
        n_path = r.transition_occurrence_count
        if n_in == 0:
            ratio = 0.0
        else:
            ratio = float(n_path) / float(n_in)

        ratios.append(ratio)
        transitions.append(
            {
                "from_station_code": r.code1,
                "via_station_code": r.code2,
                "to_station_code": r.code3,
                "from_sequence": r.seq1,
                "via_sequence": r.seq2,
                "to_sequence": r.seq3,
                "first_edge_occurrence_count": n_in,
                "transition_occurrence_count": n_path,
                "continuity_ratio": ratio,
            }
        )

    return {
        "train_number": train.number,
        "timetable_snapshot_id": snapshot_id,
        "total_transition_count": len(transitions),
        "average_continuity_ratio": sum(ratios) / len(ratios),
        "minimum_continuity_ratio": min(ratios),
        "maximum_continuity_ratio": max(ratios),
        "transitions": transitions,
    }


def calculate_train_sequence_disjoint_subpath_reconvergences(
    db: Session, snapshot_id: int, train_number: str
) -> dict[str, typing.Any]:
    """Calculate Train Sequence Disjoint Sub-Path Reconvergences."""
    from sqlalchemy import func, select, text

    from railgati.models.train import Train

    train = db.scalar(select(Train).filter(func.upper(Train.number) == train_number.upper()))
    if not train:
        raise ValueError(f"Train '{train_number}' not found.")

    query = text("""
    WITH target_stops AS (
        SELECT station_id, stop_sequence as seq
        FROM train_stop_observations
        WHERE train_id = :train_id AND snapshot_id = :snap_id
    ),
    target_anchors AS (
        SELECT
            t1.station_id as st_A, t1.seq as seq_A,
            t2.station_id as st_B, t2.seq as seq_B
        FROM target_stops t1
        JOIN target_stops t2 ON t2.seq > t1.seq + 1
    ),
    candidate_trains AS (
        SELECT
            c1.train_id,
            a.st_A, a.st_B, a.seq_A as t_seq_A, a.seq_B as t_seq_B,
            c1.stop_sequence as c_seq_A, c2.stop_sequence as c_seq_B
        FROM target_anchors a
        JOIN train_stop_observations c1
          ON c1.station_id = a.st_A AND c1.snapshot_id = :snap_id
        JOIN train_stop_observations c2
          ON c2.station_id = a.st_B AND c2.snapshot_id = :snap_id
         AND c2.train_id = c1.train_id
         AND c2.stop_sequence > c1.stop_sequence + 1
        WHERE c1.train_id != :train_id
    ),
    disjoint_candidates AS (
        SELECT c.*
        FROM candidate_trains c
        WHERE NOT EXISTS (
            SELECT 1
            FROM train_stop_observations c_int
            WHERE c_int.train_id = c.train_id AND c_int.snapshot_id = :snap_id
              AND c_int.stop_sequence > c.c_seq_A AND c_int.stop_sequence < c.c_seq_B
              AND EXISTS (
                  SELECT 1
                  FROM target_stops t_int
                  WHERE t_int.seq > c.t_seq_A AND t_int.seq < c.t_seq_B
                    AND t_int.station_id = c_int.station_id
              )
        )
    )
    SELECT
        d.t_seq_A as t_seq_a, d.t_seq_B as t_seq_b,
        s_A.code as anchor_from_code, s_B.code as anchor_to_code,
        tr.number as candidate_number,
        d.train_id as c_id,
        d.c_seq_A as c_seq_a, d.c_seq_B as c_seq_b
    FROM disjoint_candidates d
    JOIN stations s_A ON s_A.id = d.st_A
    JOIN stations s_B ON s_B.id = d.st_B
    JOIN trains tr ON tr.id = d.train_id
    ORDER BY d.t_seq_A, d.t_seq_B, tr.number, d.c_seq_A, d.c_seq_B
    """)

    if db.bind.dialect.name == "postgresql":
        pg_query = text("""
        WITH target_stops AS (
            SELECT station_id, stop_sequence as seq
            FROM train_stop_observations
            WHERE train_id = :train_id AND snapshot_id = :snap_id
        ),
        target_anchors AS (
            SELECT
                t1.station_id as st_A, t1.seq as seq_A,
                t2.station_id as st_B, t2.seq as seq_B
            FROM target_stops t1
            JOIN target_stops t2 ON t2.seq > t1.seq + 1
        ),
        candidate_trains AS (
            SELECT
                c1.train_id,
                a.st_A, a.st_B, a.seq_A as t_seq_A, a.seq_B as t_seq_B,
                c1.stop_sequence as c_seq_A, c2.stop_sequence as c_seq_B
            FROM target_anchors a
            JOIN train_stop_observations c1
              ON c1.station_id = a.st_A AND c1.snapshot_id = :snap_id
            JOIN train_stop_observations c2
              ON c2.station_id = a.st_B AND c2.snapshot_id = :snap_id
             AND c2.train_id = c1.train_id
             AND c2.stop_sequence > c1.stop_sequence + 1
            WHERE c1.train_id != :train_id
        ),
        disjoint_candidates AS (
            SELECT c.*
            FROM candidate_trains c
            WHERE NOT EXISTS (
                SELECT 1
                FROM train_stop_observations c_int
                WHERE c_int.train_id = c.train_id AND c_int.snapshot_id = :snap_id
                  AND c_int.stop_sequence > c.c_seq_A AND c_int.stop_sequence < c.c_seq_B
                  AND EXISTS (
                      SELECT 1
                      FROM target_stops t_int
                      WHERE t_int.seq > c.t_seq_A AND t_int.seq < c.t_seq_B
                        AND t_int.station_id = c_int.station_id
                  )
            )
        )
        SELECT
            d.t_seq_A as t_seq_a, d.t_seq_B as t_seq_b,
            s_A.code as anchor_from_code, s_B.code as anchor_to_code,
            tr.number as candidate_number,
            d.train_id as c_id,
            d.c_seq_A as c_seq_a, d.c_seq_B as c_seq_b,
            (
                SELECT COALESCE(array_agg(s.code ORDER BY t_int.seq), '{}')
                FROM target_stops t_int
                JOIN stations s ON s.id = t_int.station_id
                WHERE t_int.seq > d.t_seq_A AND t_int.seq < d.t_seq_B
            ) as target_interior_codes,
            (
                SELECT COALESCE(array_agg(s.code ORDER BY c_int.stop_sequence), '{}')
                FROM train_stop_observations c_int
                JOIN stations s ON s.id = c_int.station_id
                WHERE c_int.train_id = d.train_id AND c_int.snapshot_id = :snap_id
                  AND c_int.stop_sequence > d.c_seq_A AND c_int.stop_sequence < d.c_seq_B
            ) as candidate_interior_codes
        FROM disjoint_candidates d
        JOIN stations s_A ON s_A.id = d.st_A
        JOIN stations s_B ON s_B.id = d.st_B
        JOIN trains tr ON tr.id = d.train_id
        ORDER BY d.t_seq_A, d.t_seq_B, tr.number, d.c_seq_A, d.c_seq_B
        """)
        rows = db.execute(pg_query, {"train_id": train.id, "snap_id": snapshot_id}).fetchall()

        reconvergences = []
        for row in rows:
            target_interior = list(row.target_interior_codes)
            candidate_interior = list(row.candidate_interior_codes)
            reconvergences.append(
                {
                    "anchor_from_station_code": row.anchor_from_code,
                    "anchor_to_station_code": row.anchor_to_code,
                    "target_from_sequence": row.t_seq_a,
                    "target_to_sequence": row.t_seq_b,
                    "candidate_train_number": row.candidate_number,
                    "candidate_from_sequence": row.c_seq_a,
                    "candidate_to_sequence": row.c_seq_b,
                    "target_interior_station_count": len(target_interior),
                    "candidate_interior_station_count": len(candidate_interior),
                    "shared_interior_station_count": 0,
                    "target_interior_station_codes": target_interior,
                    "candidate_interior_station_codes": candidate_interior,
                }
            )
    else:
        rows = db.execute(query, {"train_id": train.id, "snap_id": snapshot_id}).fetchall()

        reconvergences = []

        target_codes_query = text("""
            SELECT s.code
            FROM train_stop_observations t_int
            JOIN stations s ON s.id = t_int.station_id
            WHERE t_int.train_id = :t_id AND t_int.snapshot_id = :snap_id
              AND t_int.stop_sequence > :t_seq_A AND t_int.stop_sequence < :t_seq_B
            ORDER BY t_int.stop_sequence
        """)

        candidate_codes_query = text("""
            SELECT s.code
            FROM train_stop_observations c_int
            JOIN stations s ON s.id = c_int.station_id
            WHERE c_int.train_id = :c_id AND c_int.snapshot_id = :snap_id
              AND c_int.stop_sequence > :c_seq_A AND c_int.stop_sequence < :c_seq_B
            ORDER BY c_int.stop_sequence
        """)

        for row in rows:
            t_res = db.execute(
                target_codes_query,
                {
                    "t_id": train.id,
                    "snap_id": snapshot_id,
                    "t_seq_A": row.t_seq_a,
                    "t_seq_B": row.t_seq_b,
                },
            ).fetchall()
            target_interior = [r[0] for r in t_res]

            c_res = db.execute(
                candidate_codes_query,
                {
                    "c_id": row.c_id,
                    "snap_id": snapshot_id,
                    "c_seq_A": row.c_seq_a,
                    "c_seq_B": row.c_seq_b,
                },
            ).fetchall()
            candidate_interior = [r[0] for r in c_res]

            reconvergences.append(
                {
                    "anchor_from_station_code": row.anchor_from_code,
                    "anchor_to_station_code": row.anchor_to_code,
                    "target_from_sequence": row.t_seq_a,
                    "target_to_sequence": row.t_seq_b,
                    "candidate_train_number": row.candidate_number,
                    "candidate_from_sequence": row.c_seq_a,
                    "candidate_to_sequence": row.c_seq_b,
                    "target_interior_station_count": len(target_interior),
                    "candidate_interior_station_count": len(candidate_interior),
                    "shared_interior_station_count": 0,
                    "target_interior_station_codes": target_interior,
                    "candidate_interior_station_codes": candidate_interior,
                }
            )

    return {
        "train_number": train.number,
        "timetable_snapshot_id": snapshot_id,
        "total_reconvergence_count": len(reconvergences),
        "reconvergences": reconvergences,
    }


def calculate_train_sequence_topological_degree_extremes(
    db: Session, snapshot_id: int, train_number: str
) -> dict[str, typing.Any]:
    """Calculate Train Sequence Topological Degree Extremes."""
    from sqlalchemy import func, select, text

    from railgati.models.train import Train

    train = db.scalar(select(Train).filter(func.upper(Train.number) == train_number.upper()))
    if not train:
        raise ValueError(f"Train '{train_number}' not found.")

    query = text("""
    WITH edge_pairs AS (
        SELECT o1.station_id as s1, o2.station_id as s2
        FROM train_stop_observations o1
        JOIN train_stop_observations o2
          ON o1.train_id = o2.train_id
         AND o1.snapshot_id = o2.snapshot_id
         AND o2.stop_sequence = o1.stop_sequence + 1
        WHERE o1.snapshot_id = :snap_id
    ),
    undirected_edges AS (
        SELECT s1 as u, s2 as v FROM edge_pairs
        UNION
        SELECT s2 as u, s1 as v FROM edge_pairs
    ),
    station_degrees AS (
        SELECT u as station_id, count(distinct v) as global_degree
        FROM undirected_edges
        GROUP BY u
    ),
    target_seq AS (
        SELECT
            o.stop_sequence,
            s.code as station_code,
            COALESCE(sd.global_degree, 0) as global_degree,
            LAG(COALESCE(sd.global_degree, 0)) OVER (ORDER BY o.stop_sequence) as prev_deg,
            LEAD(COALESCE(sd.global_degree, 0)) OVER (ORDER BY o.stop_sequence) as next_deg,
            ROW_NUMBER() OVER (ORDER BY o.stop_sequence) as rnum,
            COUNT(*) OVER () as total_count
        FROM train_stop_observations o
        JOIN stations s ON s.id = o.station_id
        LEFT JOIN station_degrees sd ON sd.station_id = o.station_id
        WHERE o.train_id = :train_id AND o.snapshot_id = :snap_id
    )
    SELECT
        stop_sequence,
        station_code,
        global_degree,
        CASE
            WHEN rnum = 1 OR rnum = total_count THEN 'TERMINAL'
            WHEN global_degree > prev_deg AND global_degree > next_deg THEN 'LOCAL_MAXIMUM'
            WHEN global_degree < prev_deg AND global_degree < next_deg THEN 'LOCAL_MINIMUM'
            ELSE 'TRANSIT'
        END as classification_type
    FROM target_seq
    ORDER BY stop_sequence
    """)

    rows = db.execute(query, {"train_id": train.id, "snap_id": snapshot_id}).fetchall()

    local_maxima_count = 0
    local_minima_count = 0
    transit_count = 0
    sequence_classification = []

    for row in rows:
        classification = row.classification_type
        if classification == "LOCAL_MAXIMUM":
            local_maxima_count += 1
        elif classification == "LOCAL_MINIMUM":
            local_minima_count += 1
        elif classification == "TRANSIT":
            transit_count += 1

        sequence_classification.append(
            {
                "stop_sequence": row.stop_sequence,
                "station_code": row.station_code,
                "global_degree": row.global_degree,
                "classification_type": classification,
            }
        )

    return {
        "train_number": train.number,
        "timetable_snapshot_id": snapshot_id,
        "total_stops": len(rows),
        "local_maxima_count": local_maxima_count,
        "local_minima_count": local_minima_count,
        "transit_count": transit_count,
        "sequence_classification": sequence_classification,
    }


def calculate_station_neighborhood_subsumption(
    db: Session, station_code: str
) -> dict[str, typing.Any]:
    """Calculate Station Neighborhood Topological Subsumption."""
    from fastapi import HTTPException
    from sqlalchemy import func, select, text

    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.station import Station

    snapshot_id = get_active_timetable_snapshot_id(db)
    target = db.scalar(select(Station).filter(func.lower(Station.code) == station_code.lower()))
    if not target:
        raise HTTPException(status_code=404, detail="Station not found")

    query = text("""
    WITH target_neighbors AS (
        SELECT o2.station_id as v
        FROM train_stop_observations o1
        JOIN train_stop_observations o2
          ON o1.train_id = o2.train_id
         AND o1.snapshot_id = o2.snapshot_id
         AND o2.stop_sequence = o1.stop_sequence + 1
        WHERE o1.snapshot_id = :snap_id AND o1.station_id = :target_id
        UNION
        SELECT o1.station_id as v
        FROM train_stop_observations o1
        JOIN train_stop_observations o2
          ON o1.train_id = o2.train_id
         AND o1.snapshot_id = o2.snapshot_id
         AND o2.stop_sequence = o1.stop_sequence + 1
        WHERE o1.snapshot_id = :snap_id AND o2.station_id = :target_id
    ),
    target_neighbors_clean AS (
        SELECT v FROM target_neighbors WHERE v != :target_id
    ),
    candidate_edges AS (
        SELECT o1.station_id as u, o2.station_id as v
        FROM target_neighbors_clean tn
        JOIN train_stop_observations o1 ON o1.station_id = tn.v AND o1.snapshot_id = :snap_id
        JOIN train_stop_observations o2
          ON o1.train_id = o2.train_id
         AND o1.snapshot_id = o2.snapshot_id
         AND o2.stop_sequence = o1.stop_sequence + 1
        UNION
        SELECT o1.station_id as u, o2.station_id as v
        FROM target_neighbors_clean tn
        JOIN train_stop_observations o2 ON o2.station_id = tn.v AND o2.snapshot_id = :snap_id
        JOIN train_stop_observations o1
          ON o2.train_id = o1.train_id
         AND o2.snapshot_id = o1.snapshot_id
         AND o1.stop_sequence = o2.stop_sequence - 1
    ),
    candidate_neighbors AS (
        SELECT u, v FROM candidate_edges WHERE u != v
        UNION
        SELECT v as u, u as v FROM candidate_edges WHERE u != v
    ),
    candidate_neighbors_clean AS (
        SELECT u, v FROM candidate_neighbors
        WHERE u IN (SELECT v FROM target_neighbors_clean)
    ),
    neighbor_degrees AS (
        SELECT u, COUNT(*) as deg FROM candidate_neighbors_clean GROUP BY u
    )
    SELECT
        s.code as neighbor_code,
        nd.deg as neighbor_degree
    FROM target_neighbors_clean t
    JOIN stations s ON s.id = t.v
    JOIN neighbor_degrees nd ON nd.u = t.v
    WHERE
        NOT EXISTS (
            SELECT 1 FROM target_neighbors_clean t2
            WHERE t2.v != t.v
            AND NOT EXISTS (
                SELECT 1 FROM candidate_neighbors_clean c
                WHERE c.u = t.v AND c.v = t2.v
            )
        )
        AND EXISTS (
            SELECT 1 FROM candidate_neighbors_clean c
            WHERE c.u = t.v
            AND c.v != :target_id
            AND NOT EXISTS (
                SELECT 1 FROM target_neighbors_clean t3 WHERE t3.v = c.v
            )
        )
    ORDER BY s.code
    """)

    rows = db.execute(query, {"target_id": target.id, "snap_id": snapshot_id}).fetchall()

    total_neighbors = (
        db.scalar(
            text("""
        WITH edge_pairs AS (
            SELECT o1.station_id as u, o2.station_id as v
            FROM train_stop_observations o1
            JOIN train_stop_observations o2
              ON o1.train_id = o2.train_id
             AND o1.snapshot_id = o2.snapshot_id
             AND o2.stop_sequence = o1.stop_sequence + 1
            WHERE o1.snapshot_id = :snap_id
        ),
        undirected_edges AS (
            SELECT u, v FROM edge_pairs WHERE u != v
            UNION
            SELECT v as u, u as v FROM edge_pairs WHERE u != v
        )
        SELECT COUNT(*) FROM undirected_edges WHERE u = :target_id
    """),
            {"target_id": target.id, "snap_id": snapshot_id},
        )
        or 0
    )

    subsuming_neighbors = []
    for row in rows:
        subsuming_neighbors.append(
            {"station_code": row.neighbor_code, "neighbor_degree": row.neighbor_degree}
        )

    return {
        "station_code": target.code,
        "timetable_snapshot_id": snapshot_id,
        "total_neighbors": total_neighbors,
        "subsuming_neighbors": subsuming_neighbors,
    }


def calculate_station_strict_local_bridges(db: Session, station_code: str) -> dict[str, typing.Any]:
    """Calculate Station Neighborhood Strict Local Bridge Pairs."""
    from fastapi import HTTPException
    from sqlalchemy import func, select, text

    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.station import Station

    snapshot_id = get_active_timetable_snapshot_id(db)
    target = db.scalar(select(Station).filter(func.lower(Station.code) == station_code.lower()))
    if not target:
        raise HTTPException(status_code=404, detail="Station not found")

    query = text("""
    WITH target_neighbors AS (
        SELECT DISTINCT o2.station_id as v
        FROM train_stop_observations o1
        JOIN train_stop_observations o2
          ON o1.train_id = o2.train_id
         AND o1.snapshot_id = o2.snapshot_id
         AND (o2.stop_sequence = o1.stop_sequence + 1 OR o2.stop_sequence = o1.stop_sequence - 1)
        WHERE o1.snapshot_id = :snap_id
          AND o1.station_id = :target_id
    ),
    extended_edges AS (
        SELECT DISTINCT oa.station_id as u, ob.station_id as v
        FROM target_neighbors tn
        JOIN train_stop_observations oa ON oa.station_id = tn.v AND oa.snapshot_id = :snap_id
        JOIN train_stop_observations ob
          ON oa.train_id = ob.train_id
         AND oa.snapshot_id = ob.snapshot_id
         AND (ob.stop_sequence = oa.stop_sequence + 1 OR ob.stop_sequence = oa.stop_sequence - 1)
    ),
    undirected_extended AS (
        SELECT u, v FROM extended_edges
        UNION
        SELECT v as u, u as v FROM extended_edges
    ),
    neighbor_pairs AS (
        SELECT a.v as a_id, b.v as b_id
        FROM target_neighbors a
        JOIN target_neighbors b ON a.v < b.v
    ),
    pair_evals AS (
        SELECT
            np.a_id,
            np.b_id,
            EXISTS(
                SELECT 1 FROM undirected_extended e WHERE e.u = np.a_id AND e.v = np.b_id
            ) as has_direct,
            (
                SELECT COUNT(DISTINCT x.v)
                FROM undirected_extended x
                JOIN undirected_extended y ON y.u = x.v AND y.v = np.b_id
                WHERE x.u = np.a_id
                  AND x.v != :target_id
                  AND x.v != np.a_id
                  AND x.v != np.b_id
            ) as alt_count
        FROM neighbor_pairs np
    )
    SELECT
        sa.code as neighbor_a,
        sb.code as neighbor_b,
        pe.has_direct,
        pe.alt_count
    FROM pair_evals pe
    JOIN stations sa ON sa.id = pe.a_id
    JOIN stations sb ON sb.id = pe.b_id
    ORDER BY sa.code, sb.code
    """)

    rows = db.execute(query, {"target_id": target.id, "snap_id": snapshot_id}).fetchall()

    evaluated_pairs = []
    for row in rows:
        has_direct = bool(row.has_direct)
        alt_count = int(row.alt_count)
        is_strict = (not has_direct) and (alt_count == 0)

        evaluated_pairs.append(
            {
                "neighbor_a": row.neighbor_a,
                "neighbor_b": row.neighbor_b,
                "has_direct_adjacency": has_direct,
                "alternative_bridge_count": alt_count,
                "is_strict_local_bridge": is_strict,
            }
        )

    return {
        "station_code": target.code,
        "timetable_snapshot_id": snapshot_id,
        "total_neighbor_pairs": len(evaluated_pairs),
        "evaluated_pairs": evaluated_pairs,
    }


def calculate_train_single_station_intersections(
    db: Session, snapshot_id: int, target_train_number: str
) -> dict:
    from sqlalchemy import func, select, text

    from railgati.models.train import Train, TrainObservation

    target = db.execute(
        select(Train.id, Train.number)
        .join(TrainObservation, TrainObservation.train_id == Train.id)
        .filter(
            TrainObservation.snapshot_id == snapshot_id,
            func.lower(Train.number) == target_train_number.lower(),
        )
    ).first()

    if not target:
        raise ValueError(f"Train {target_train_number} not found in snapshot {snapshot_id}")

    target_train_id = target.id
    target_train_number_resolved = target.number

    query = text("""
        WITH target_stations AS (
            SELECT DISTINCT station_id
            FROM train_stop_observations
            WHERE snapshot_id = :snapshot_id
              AND train_id = :target_train_id
        ),
        intersecting_trains AS (
            SELECT tso.train_id, tso.station_id
            FROM train_stop_observations tso
            JOIN target_stations ts ON tso.station_id = ts.station_id
            WHERE tso.snapshot_id = :snapshot_id
              AND tso.train_id != :target_train_id
        ),
        qualifying_trains AS (
            SELECT train_id, MIN(station_id) as shared_station_id
            FROM intersecting_trains
            GROUP BY train_id
            HAVING COUNT(DISTINCT station_id) = 1
        )
        SELECT
            t.number AS other_train_number,
            t_obs.name AS other_train_name,
            s.code AS shared_station_code,
            s_obs.name AS shared_station_name
        FROM qualifying_trains qt
        JOIN trains t ON t.id = qt.train_id
        JOIN train_observations t_obs ON t_obs.train_id = t.id AND t_obs.snapshot_id = :snapshot_id
        JOIN stations s ON s.id = qt.shared_station_id
        LEFT JOIN station_observations s_obs ON s_obs.station_id = s.id AND s_obs.snapshot_id = :snapshot_id
        ORDER BY t.number ASC
    """)

    rows = db.execute(
        query, {"snapshot_id": snapshot_id, "target_train_id": target_train_id}
    ).fetchall()

    items = []
    for row in rows:
        items.append(
            {
                "other_train_number": row.other_train_number,
                "other_train_name": row.other_train_name,
                "shared_station_code": row.shared_station_code,
                "shared_station_name": row.shared_station_name,
            }
        )

    return {
        "target_train_number": target_train_number_resolved,
        "timetable_snapshot_id": snapshot_id,
        "total_intersecting_trains": len(items),
        "items": items,
    }


def calculate_train_structural_shortest_path_divergence(
    db: Session, timetable_snapshot_id: int, train_number: str
) -> dict[str, typing.Any]:
    """Calculate Train Route Structural Shortest-Path Divergence."""
    from sqlalchemy import select

    from railgati.models.graph import RailwayGraphBuild
    from railgati.models.station import Station
    from railgati.models.train import Train, TrainStopObservation

    build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id
        )
    )
    if not build or build.status != "ACTIVE":
        raise ValueError("Active graph build unavailable for this snapshot")

    train = db.scalar(select(Train).filter(Train.number == train_number.upper()))
    if not train:
        raise ValueError(f"Train '{train_number}' not found")

    stops = (
        db.execute(
            select(TrainStopObservation.station_id)
            .filter(
                TrainStopObservation.snapshot_id == timetable_snapshot_id,
                TrainStopObservation.train_id == train.id,
            )
            .order_by(TrainStopObservation.stop_sequence)
        )
        .scalars()
        .all()
    )

    if not stops:
        raise ValueError(f"Train '{train_number}' has no scheduled stops in this snapshot")

    start_id = stops[0]
    end_id = stops[-1]
    actual_edges = len(stops) - 1

    shortest_edges: int | None = None

    if start_id == end_id:
        shortest_edges = 0
    else:
        query = text("""
            WITH RECURSIVE search_graph(station_id, depth) AS (
                SELECT :start_id, 0
                UNION
                SELECT
                    CASE WHEN e.from_station_id = sg.station_id THEN e.to_station_id ELSE e.from_station_id END,
                    sg.depth + 1
                FROM search_graph sg
                JOIN railway_network_edges e ON
                    (e.from_station_id = sg.station_id OR e.to_station_id = sg.station_id)
                    AND e.timetable_snapshot_id = :snapshot_id
                WHERE sg.depth < :max_edges
            )
            SELECT depth FROM search_graph WHERE station_id = :end_id ORDER BY depth LIMIT 1;
        """)

        res = db.execute(
            query,
            {
                "start_id": start_id,
                "end_id": end_id,
                "snapshot_id": timetable_snapshot_id,
                "max_edges": actual_edges,
            },
        ).scalar()

        if res is not None:
            shortest_edges = int(res)

    start_st = db.scalar(select(Station.code).filter(Station.id == start_id))
    end_st = db.scalar(select(Station.code).filter(Station.id == end_id))

    div_abs: int | None = None
    div_ratio: float | None = None

    if shortest_edges is not None:
        div_abs = actual_edges - shortest_edges
        if shortest_edges > 0:
            div_ratio = round(actual_edges / shortest_edges, 4)

    return {
        "train_number": train.number,
        "timetable_snapshot_id": timetable_snapshot_id,
        "start_station_code": start_st,
        "end_station_code": end_st,
        "actual_structural_edges": actual_edges,
        "shortest_structural_edges": shortest_edges,
        "divergence_absolute": div_abs,
        "divergence_ratio": div_ratio,
    }


def calculate_station_junction_through_service(
    db: Session, timetable_snapshot_id: int, station_code: str
) -> dict[str, typing.Any]:
    from railgati.models.station import Station, StationObservation

    station = db.scalar(select(Station).filter(Station.code == station_code))
    if not station:
        raise ValueError(f"Station not found: '{station_code}'")

    obs = db.scalar(
        select(StationObservation.name).filter(
            StationObservation.station_id == station.id,
            StationObservation.snapshot_id == timetable_snapshot_id,
        )
    )
    station_name = obs if obs else station_code

    # Step 1: Find topological neighbors in active snapshot
    neighbors_query = text("""
        SELECT DISTINCT CASE WHEN from_station_id = :st_id THEN to_station_id ELSE from_station_id END
        FROM railway_network_edges
        WHERE timetable_snapshot_id = :snap_id AND (from_station_id = :st_id OR to_station_id = :st_id)
    """)
    neighbor_ids = [
        row[0]
        for row in db.execute(
            neighbors_query, {"st_id": station.id, "snap_id": timetable_snapshot_id}
        ).fetchall()
    ]
    k = len(neighbor_ids)

    if k < 2:
        raise ValueError(
            f"Station '{station_code}' is not a structural junction (degree = {k}) in this snapshot"
        )

    possible_pairs = k * (k - 1) // 2

    # Step 2: Extract sequences for trains passing through S
    bridged_query = text("""
        WITH target_trains AS (
            SELECT DISTINCT train_id
            FROM train_stop_observations
            WHERE snapshot_id = :snap_id AND station_id = :st_id
        ),
        sequence_visits AS (
            SELECT
                train_id,
                LAG(station_id) OVER (PARTITION BY train_id ORDER BY stop_sequence) as prev_stn,
                station_id,
                LEAD(station_id) OVER (PARTITION BY train_id ORDER BY stop_sequence) as next_stn
            FROM train_stop_observations
            WHERE snapshot_id = :snap_id AND train_id IN (SELECT train_id FROM target_trains)
        )
        SELECT prev_stn, next_stn, train_id
        FROM sequence_visits
        WHERE station_id = :st_id AND prev_stn IS NOT NULL AND next_stn IS NOT NULL AND prev_stn != next_stn
    """)
    visits = db.execute(
        bridged_query, {"snap_id": timetable_snapshot_id, "st_id": station.id}
    ).fetchall()

    neighbor_set = set(neighbor_ids)
    served_pairs_map: dict[tuple[int, int], set[int]] = {}

    for prev_stn, next_stn, train_id in visits:
        if prev_stn in neighbor_set and next_stn in neighbor_set:
            # Canonicalize unordered pair (A,B) and deduplicate train identities
            pair = tuple(sorted([prev_stn, next_stn]))
            if pair not in served_pairs_map:
                served_pairs_map[pair] = set()
            served_pairs_map[pair].add(train_id)

    relevant_ids = set()
    for a, b in served_pairs_map:
        relevant_ids.add(a)
        relevant_ids.add(b)

    st_codes = {}
    if relevant_ids:
        rows = db.execute(
            select(Station.id, Station.code).where(Station.id.in_(relevant_ids))
        ).fetchall()
        st_codes = {r[0]: r[1] for r in rows}

    served_pairs_out = []
    for (a, b), train_ids in served_pairs_map.items():
        # Enforce canonical string sorting for neighbor_a and neighbor_b
        code_a = st_codes[a]
        code_b = st_codes[b]
        if code_a > code_b:
            code_a, code_b = code_b, code_a

        served_pairs_out.append(
            {"neighbor_a": code_a, "neighbor_b": code_b, "qualifying_train_count": len(train_ids)}
        )

    served_pairs_out.sort(key=lambda x: (x["neighbor_a"], x["neighbor_b"]))

    served_count = len(served_pairs_out)
    ratio = round(served_count / possible_pairs, 4)

    return {
        "station_code": station.code,
        "station_name": station_name,
        "neighbor_count": k,
        "possible_neighbor_pairs": possible_pairs,
        "served_neighbor_pairs": served_count,
        "through_service_pair_ratio": ratio,
        "served_pairs": served_pairs_out,
    }


def calculate_train_topological_perimeter_expansion(
    db: Session, timetable_snapshot_id: int, train_number: str
) -> dict[str, typing.Any]:
    from sqlalchemy import select, text

    from railgati.models.train import Train

    train = db.scalar(select(Train).filter(Train.number == train_number))
    if not train:
        raise ValueError(f"Train not found: '{train_number}'")

    # Verify train exists in snapshot
    route_count = db.scalar(
        text(
            "SELECT COUNT(DISTINCT station_id) FROM train_stop_observations WHERE train_id = :tr_id AND snapshot_id = :snap_id"
        ),
        {"tr_id": train.id, "snap_id": timetable_snapshot_id},
    )

    if not route_count or route_count == 0:
        raise ValueError(f"Train not found: '{train_number}'")

    query = text("""
        WITH route_stations AS (
            SELECT DISTINCT station_id
            FROM train_stop_observations
            WHERE train_id = :tr_id AND snapshot_id = :snap_id
        ),
        adjacent_stations AS (
            SELECT to_station_id AS st_id
            FROM railway_network_edges
            WHERE timetable_snapshot_id = :snap_id
              AND from_station_id IN (SELECT station_id FROM route_stations)
            UNION
            SELECT from_station_id AS st_id
            FROM railway_network_edges
            WHERE timetable_snapshot_id = :snap_id
              AND to_station_id IN (SELECT station_id FROM route_stations)
        ),
        perimeter_stations AS (
            SELECT st_id
            FROM adjacent_stations
            EXCEPT
            SELECT station_id FROM route_stations
        )
        SELECT
            p.st_id,
            s.code,
            so.name
        FROM perimeter_stations p
        JOIN stations s ON s.id = p.st_id
        LEFT JOIN station_observations so ON so.station_id = p.st_id AND so.snapshot_id = :snap_id
        ORDER BY s.code
    """)

    results = (
        db.execute(query, {"tr_id": train.id, "snap_id": timetable_snapshot_id}).mappings().all()
    )

    perimeter_count = len(results)
    ratio = perimeter_count / route_count

    perimeter_items = [
        {"station_code": row["code"], "station_name": row["name"] or row["code"]} for row in results
    ]

    return {
        "target_train_number": train.number,
        "route_station_count": route_count,
        "perimeter_station_count": perimeter_count,
        "perimeter_expansion_ratio": float(ratio),
        "perimeter_stations": perimeter_items,
    }


def get_edge_resilience_detour(db: Session, from_station_code: str, to_station_code: str) -> dict:
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.graph import (
        RailwayGraphBuild,
        RailwayNetworkEdgeResilience,
    )
    from railgati.models.station import Station

    if from_station_code == to_station_code:
        raise ValueError("Invalid target: self-loops are not structural network edges.")

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)

    # Resolve stations
    stations = db.scalars(
        select(Station).filter(Station.code.in_([from_station_code, to_station_code]))
    ).all()

    if len(stations) != 2:
        return None

    st_dict = {s.code: s for s in stations}
    from_station = st_dict.get(from_station_code)
    to_station = st_dict.get(to_station_code)

    canonical_a = min(from_station.id, to_station.id)
    canonical_b = max(from_station.id, to_station.id)

    # Resolve active Graph Build
    graph_build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id,
            RailwayGraphBuild.status == "ACTIVE",
        )
    )
    if not graph_build:
        raise ValueError(
            f"No ACTIVE RailwayGraphBuild found for timetable snapshot {timetable_snapshot_id}"
        )

    resilience_record = db.scalar(
        select(RailwayNetworkEdgeResilience).filter(
            RailwayNetworkEdgeResilience.graph_build_id == graph_build.id,
            RailwayNetworkEdgeResilience.station_a_id == canonical_a,
            RailwayNetworkEdgeResilience.station_b_id == canonical_b,
        )
    )

    if not resilience_record:
        return None

    return {
        "from_station_code": from_station_code,
        "to_station_code": to_station_code,
        "detour_distance": resilience_record.detour_distance,
        "is_structural_bridge": resilience_record.is_structural_bridge,
    }


def get_station_topological_coreness(
    db: Session, station_code: str
) -> dict[str, typing.Any] | None:

    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.graph import RailwayGraphBuild, RailwayStationTopologicalCoreness
    from railgati.models.station import Station

    station_code = station_code.upper()
    snap_id = get_active_timetable_snapshot_id(db)
    if not snap_id:
        raise ValueError("No active timetable snapshot found")

    station = db.query(Station).filter(Station.code == station_code).first()
    if not station:
        raise ValueError(f"Station {station_code} not found")

    build = (
        db.query(RailwayGraphBuild)
        .filter(
            RailwayGraphBuild.timetable_snapshot_id == snap_id,
            RailwayGraphBuild.status == "ACTIVE",
        )
        .first()
    )

    if not build:
        raise ValueError("No active completed graph build found for current snapshot")

    core_record = (
        db.query(RailwayStationTopologicalCoreness)
        .filter(
            RailwayStationTopologicalCoreness.graph_build_id == build.id,
            RailwayStationTopologicalCoreness.station_id == station.id,
        )
        .first()
    )

    if not core_record:
        return None

    return {
        "station_code": station_code,
        "coreness": core_record.coreness,
        "degree": core_record.degree,
    }


def get_edge_topological_trussness(
    db: Session, from_station_code: str, to_station_code: str
) -> dict[str, typing.Any] | None:
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.graph import RailwayGraphBuild, RailwayNetworkEdgeTopologicalTrussness
    from railgati.models.station import Station

    if from_station_code == to_station_code:
        raise ValueError("Invalid target: self-loops are not structural network edges.")

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    if not timetable_snapshot_id:
        raise ValueError("No active timetable snapshot found")

    stations = db.scalars(
        select(Station).filter(Station.code.in_([from_station_code, to_station_code]))
    ).all()

    if len(stations) != 2:
        return None

    st_dict = {s.code: s for s in stations}
    from_station = st_dict.get(from_station_code)
    to_station = st_dict.get(to_station_code)

    if not from_station or not to_station:
        return None

    canonical_a = min(from_station.id, to_station.id)
    canonical_b = max(from_station.id, to_station.id)

    graph_build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id,
            RailwayGraphBuild.status == "ACTIVE",
        )
    )
    if not graph_build:
        raise ValueError(
            f"No ACTIVE RailwayGraphBuild found for timetable snapshot {timetable_snapshot_id}"
        )

    trussness_record = db.scalar(
        select(RailwayNetworkEdgeTopologicalTrussness).filter(
            RailwayNetworkEdgeTopologicalTrussness.graph_build_id == graph_build.id,
            RailwayNetworkEdgeTopologicalTrussness.station_a_id == canonical_a,
            RailwayNetworkEdgeTopologicalTrussness.station_b_id == canonical_b,
        )
    )

    if not trussness_record:
        return None

    return {
        "from_station_code": from_station_code,
        "to_station_code": to_station_code,
        "trussness": trussness_record.trussness,
        "triangle_support": trussness_record.triangle_support,
    }


def get_edge_topological_quadrangle_support(
    db: Session, from_station_code: str, to_station_code: str
) -> dict[str, typing.Any] | None:
    """Retrieve Phase 68 Edge Topological Quadrangle Support."""
    from railgati.api.v1.snapshots import get_active_timetable_snapshot_id
    from railgati.models.graph import (
        RailwayGraphBuild,
        RailwayNetworkEdgeTopologicalQuadrangleSupport,
    )
    from railgati.models.station import Station

    if from_station_code == to_station_code:
        raise ValueError("Invalid target: self-loops are not structural network edges.")

    timetable_snapshot_id = get_active_timetable_snapshot_id(db)
    if not timetable_snapshot_id:
        raise ValueError("No active timetable snapshot found")

    stations = db.scalars(
        select(Station).filter(Station.code.in_([from_station_code, to_station_code]))
    ).all()

    if len(stations) != 2:
        return None

    st_dict = {s.code: s for s in stations}
    from_station = st_dict.get(from_station_code)
    to_station = st_dict.get(to_station_code)

    if not from_station or not to_station:
        return None

    canonical_a = min(from_station.id, to_station.id)
    canonical_b = max(from_station.id, to_station.id)

    graph_build = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id,
            RailwayGraphBuild.status == "ACTIVE",
        )
    )
    if not graph_build:
        raise ValueError(
            f"No ACTIVE RailwayGraphBuild found for timetable snapshot {timetable_snapshot_id}"
        )

    quad_record = db.scalar(
        select(RailwayNetworkEdgeTopologicalQuadrangleSupport).filter(
            RailwayNetworkEdgeTopologicalQuadrangleSupport.graph_build_id == graph_build.id,
            RailwayNetworkEdgeTopologicalQuadrangleSupport.station_a_id == canonical_a,
            RailwayNetworkEdgeTopologicalQuadrangleSupport.station_b_id == canonical_b,
        )
    )

    if not quad_record:
        return None

    return {
        "from_station_code": from_station_code,
        "to_station_code": to_station_code,
        "quadrangle_support": quad_record.quadrangle_support,
    }
