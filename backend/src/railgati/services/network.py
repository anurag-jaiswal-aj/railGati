"""Service for graph-based network traversal queries."""

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from railgati.models.graph import RailwayGraphBuild
from railgati.models.provenance import DatasetSnapshot


class StationReachability(BaseModel):
    """Result model for a topologically reachable station."""

    station_id: int
    min_hops: int


class NetworkPath(BaseModel):
    """Result model for a topologically discovered path."""

    hop_count: int
    station_ids: list[int]


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
