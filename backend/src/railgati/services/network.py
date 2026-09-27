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
