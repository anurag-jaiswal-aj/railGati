"""Service for materializing the railway network graph."""

from datetime import UTC, datetime

from collections import defaultdict, deque
import sys

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from railgati.models.graph import (
    RailwayGraphBuild,
    RailwayNetworkEdge,
    RailwayServiceEdge,
    RailwayNetworkEdgeResilience
)
from railgati.models.train import TrainStopObservation
from railgati.services.journey import _parse_time_to_minutes


def build_graph_for_timetable_snapshot(
    db: Session, timetable_snapshot_id: int
) -> RailwayGraphBuild:
    """Materializes ServiceEdges and NetworkEdges for a given timetable snapshot.

    This is an idempotent, deterministic operation that deletes existing edges for the snapshot
    and rebuilds them from TrainStopObservation.
    """

    # 1. Fetch or create the build record
    build_record = db.scalar(
        select(RailwayGraphBuild).filter(
            RailwayGraphBuild.timetable_snapshot_id == timetable_snapshot_id
        )
    )
    is_new = False
    if not build_record:
        is_new = True
        build_record = RailwayGraphBuild(
            timetable_snapshot_id=timetable_snapshot_id,
            status="PENDING",
        )
        db.add(build_record)
        db.commit()
        db.refresh(build_record)

    old_status = build_record.status

    try:
        # Mark as PENDING in the transaction so it rolls back if we fail
        build_record.status = "PENDING"
        build_record.error_message = None
        build_record.completed_at = None

        # 2. Delete existing edges for idempotency
        db.execute(
            delete(RailwayNetworkEdge).where(
                RailwayNetworkEdge.timetable_snapshot_id == timetable_snapshot_id
            )
        )
        db.execute(
            delete(RailwayServiceEdge).where(
                RailwayServiceEdge.timetable_snapshot_id == timetable_snapshot_id
            )
        )
        db.flush()

        db.execute(
            delete(RailwayNetworkEdgeResilience).where(
                RailwayNetworkEdgeResilience.timetable_snapshot_id == timetable_snapshot_id
            )
        )
        db.flush()

        import time
        t_start = time.time()

        # 3. Generate ServiceEdges
        # Fetch all stops for the snapshot, ordered by train and sequence
        query = (
            select(
                TrainStopObservation.train_id,
                TrainStopObservation.stop_sequence,
                TrainStopObservation.station_id,
                TrainStopObservation.departure_time,
                TrainStopObservation.arrival_time,
                TrainStopObservation.source_day,
            )
            .filter(TrainStopObservation.snapshot_id == timetable_snapshot_id)
            .order_by(TrainStopObservation.train_id, TrainStopObservation.stop_sequence)
        )
        stops = db.execute(query).all()

        service_edges = []
        for i in range(len(stops) - 1):
            curr = stops[i]
            nxt = stops[i + 1]

            # Ensure consecutive stops of the same train
            if curr.train_id == nxt.train_id and curr.stop_sequence + 1 == nxt.stop_sequence:
                orig_mins = _parse_time_to_minutes(curr.departure_time, curr.source_day)
                dest_mins = _parse_time_to_minutes(nxt.arrival_time, nxt.source_day)

                duration = None
                if orig_mins is not None and dest_mins is not None:
                    # Guard against negative durations across days if missing source day increment
                    # (Fallback safety, though source_day should cover this)
                    calc_duration = dest_mins - orig_mins
                    if calc_duration >= 0:
                        duration = calc_duration

                service_edges.append(
                    {
                        "timetable_snapshot_id": timetable_snapshot_id,
                        "train_id": curr.train_id,
                        "from_station_id": curr.station_id,
                        "from_stop_sequence": curr.stop_sequence,
                        "to_station_id": nxt.station_id,
                        "to_stop_sequence": nxt.stop_sequence,
                        "departure_time": curr.departure_time,
                        "arrival_time": nxt.arrival_time,
                        "source_day_offset": curr.source_day,
                        "duration_minutes": duration,
                    }
                )

        # Bulk insert ServiceEdges in chunks to avoid memory spikes
        if service_edges:
            db.execute(insert(RailwayServiceEdge), service_edges)
            db.flush()

        # 4. Generate NetworkEdges
        # Aggregate from newly created ServiceEdges
        agg_query = (
            select(
                RailwayServiceEdge.from_station_id,
                RailwayServiceEdge.to_station_id,
                func.count(RailwayServiceEdge.train_id).label("train_count"),
                func.min(RailwayServiceEdge.duration_minutes).label("min_duration_minutes"),
            )
            .filter(RailwayServiceEdge.timetable_snapshot_id == timetable_snapshot_id)
            .group_by(RailwayServiceEdge.from_station_id, RailwayServiceEdge.to_station_id)
        )

        agg_results = db.execute(agg_query).all()

        network_edges = [
            {
                "timetable_snapshot_id": timetable_snapshot_id,
                "from_station_id": row.from_station_id,
                "to_station_id": row.to_station_id,
                "train_count": row.train_count,
                "min_duration_minutes": row.min_duration_minutes,
            }
            for row in agg_results
        ]

        if network_edges:
            db.execute(insert(RailwayNetworkEdge), network_edges)
            db.flush()

        t_graph_extraction = time.time()
        print(f"Graph extraction (Service/Network edges) took {t_graph_extraction - t_start:.2f}s")

        # 4.5 Precompute Phase 65 Edge Resilience
        sys.setrecursionlimit(20000)

        # Build adjacency
        adj = defaultdict(set)
        vertices = set()
        edges = set()
        for ne in network_edges:
            u, v = ne["from_station_id"], ne["to_station_id"]
            if u != v:
                adj[u].add(v)
                adj[v].add(u)
                vertices.add(u)
                vertices.add(v)
                if u < v:
                    edges.add((u, v))
                else:
                    edges.add((v, u))

        # Tarjan's Bridge Finding
        timer = 0
        tin = {}
        low = {}
        visited = set()
        bridges = set()

        def dfs(v, p=-1):
            nonlocal timer
            visited.add(v)
            tin[v] = low[v] = timer
            timer += 1
            for to in adj[v]:
                if to == p:
                    continue
                if to in visited:
                    low[v] = min(low[v], tin[to])
                else:
                    dfs(to, v)
                    low[v] = min(low[v], low[to])
                    if low[to] > tin[v]:
                        if v < to:
                            bridges.add((v, to))
                        else:
                            bridges.add((to, v))

        for v in vertices:
            if v not in visited:
                dfs(v)

        non_bridge_edges = edges - bridges

        # 2-Edge-Connected Component mapping
        ecc_adj = defaultdict(set)
        for u, v in non_bridge_edges:
            ecc_adj[u].add(v)
            ecc_adj[v].add(u)

        resilience_rows = []

        # Generate bridge rows
        for u, v in bridges:
            resilience_rows.append({
                "timetable_snapshot_id": timetable_snapshot_id,
                "graph_build_id": build_record.id,
                "station_a_id": u,
                "station_b_id": v,
                "detour_distance": None,
                "detour_exists": False,
                "is_structural_bridge": True
            })

        # Run BFS for non-bridges strictly inside the 2-ECC
        for u, v in non_bridge_edges:
            q = deque([(u, 0)])
            visited_bfs = {u}
            found_dist = None

            while q:
                curr, dist = q.popleft()
                for neighbor in ecc_adj[curr]:
                    if (curr == u and neighbor == v) or (curr == v and neighbor == u):
                        continue
                    if neighbor == v:
                        found_dist = dist + 1
                        break
                    if neighbor not in visited_bfs:
                        visited_bfs.add(neighbor)
                        q.append((neighbor, dist + 1))
                if found_dist is not None:
                    break

            resilience_rows.append({
                "timetable_snapshot_id": timetable_snapshot_id,
                "graph_build_id": build_record.id,
                "station_a_id": u,
                "station_b_id": v,
                "detour_distance": found_dist,
                "detour_exists": True,
                "is_structural_bridge": False
            })

        if resilience_rows:
            db.execute(insert(RailwayNetworkEdgeResilience), resilience_rows)
            db.flush()

        # 5. Finalize
        build_record.status = "ACTIVE"
        build_record.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(build_record)
        return build_record

    except Exception as e:
        db.rollback()
        if is_new or old_status != "ACTIVE":
            build_record.status = "FAILED"
        else:
            build_record.status = "ACTIVE"

        build_record.error_message = str(e)
        db.commit()
        db.refresh(build_record)

        # Raise the exception so it is surfaced to the caller
        raise e
