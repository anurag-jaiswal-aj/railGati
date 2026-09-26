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
