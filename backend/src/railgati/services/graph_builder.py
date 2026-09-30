"""Service for materializing the railway network graph."""

import sys
from collections import defaultdict, deque
from datetime import UTC, datetime

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from railgati.models.graph import (
    RailwayGraphBuild,
    RailwayNetworkEdge,
    RailwayNetworkEdgeResilience,
    RailwayServiceEdge,
    RailwayStationTopologicalCoreness,
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

        from railgati.models.graph import (
            RailwayNetworkEdgeTopologicalQuadrangleSupport,
            RailwayNetworkEdgeTopologicalTrussness,
            RailwayNetworkEdgeTopologicalBiconnectedComponent,
        )

        db.execute(
            delete(RailwayNetworkEdgeTopologicalTrussness).where(
                RailwayNetworkEdgeTopologicalTrussness.timetable_snapshot_id
                == timetable_snapshot_id
            )
        )
        db.execute(
            delete(RailwayNetworkEdgeTopologicalQuadrangleSupport).where(
                RailwayNetworkEdgeTopologicalQuadrangleSupport.timetable_snapshot_id
                == timetable_snapshot_id
            )
        )
        db.execute(
            delete(RailwayNetworkEdgeTopologicalBiconnectedComponent).where(
                RailwayNetworkEdgeTopologicalBiconnectedComponent.timetable_snapshot_id
                == timetable_snapshot_id
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
            resilience_rows.append(
                {
                    "timetable_snapshot_id": timetable_snapshot_id,
                    "graph_build_id": build_record.id,
                    "station_a_id": u,
                    "station_b_id": v,
                    "detour_distance": None,
                    "detour_exists": False,
                    "is_structural_bridge": True,
                }
            )

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

            resilience_rows.append(
                {
                    "timetable_snapshot_id": timetable_snapshot_id,
                    "graph_build_id": build_record.id,
                    "station_a_id": u,
                    "station_b_id": v,
                    "detour_distance": found_dist,
                    "detour_exists": True,
                    "is_structural_bridge": False,
                }
            )

        if resilience_rows:
            db.execute(insert(RailwayNetworkEdgeResilience), resilience_rows)
            db.flush()

        # 4.6 Precompute Phase 66 Station Topological Coreness
        db.execute(
            delete(RailwayStationTopologicalCoreness).where(
                RailwayStationTopologicalCoreness.timetable_snapshot_id == timetable_snapshot_id
            )
        )
        db.flush()

        deg = {v: len(adj[v]) for v in vertices}
        max_deg = max(deg.values()) if deg else 0
        bins = [0] * (max_deg + 1)
        for v in vertices:
            bins[deg[v]] += 1

        start = 0
        for d in range(max_deg + 1):
            num = bins[d]
            bins[d] = start
            start += num

        pos = {}
        vert = [0] * len(vertices)
        for v in vertices:
            pos[v] = bins[deg[v]]
            vert[pos[v]] = v
            bins[deg[v]] += 1

        for d in range(max_deg, 0, -1):
            bins[d] = bins[d - 1]
        bins[0] = 0

        coreness_dict = {}
        original_deg = dict(deg)

        for i in range(len(vertices)):
            v = vert[i]
            coreness_dict[v] = deg[v]
            for u in adj[v]:
                if deg[u] > deg[v]:
                    du = deg[u]
                    pu = pos[u]
                    pw = bins[du]
                    w = vert[pw]

                    if u != w:
                        pos[u] = pw
                        vert[pu] = w
                        pos[w] = pu
                        vert[pw] = u

                    bins[du] += 1
                    deg[u] -= 1

        coreness_rows = []
        for v in vertices:
            coreness_rows.append(
                {
                    "timetable_snapshot_id": timetable_snapshot_id,
                    "graph_build_id": build_record.id,
                    "station_id": v,
                    "coreness": coreness_dict[v],
                    "degree": original_deg[v],
                }
            )

        if coreness_rows:
            db.execute(insert(RailwayStationTopologicalCoreness), coreness_rows)
            db.flush()

        # 4.7 Precompute Phase 67 Edge Topological Trussness
        db.execute(
            delete(RailwayNetworkEdgeTopologicalTrussness).where(
                RailwayNetworkEdgeTopologicalTrussness.timetable_snapshot_id
                == timetable_snapshot_id
            )
        )
        db.flush()

        # Find initial triangle support for all canonical edges
        support = {}
        original_support = {}
        for u, v in edges:
            support[(u, v)] = 0

        for u, v in edges:
            common = adj[u] & adj[v]
            support[(u, v)] = len(common)
            original_support[(u, v)] = len(common)

        max_sup = max(support.values()) if support else 0
        buckets: list[set[tuple[int, int]]] = [set() for _ in range(max_sup + 1)]
        for e, sup in support.items():
            buckets[sup].add(e)

        trussness = {}
        k = 2

        remaining = set(support.keys())

        while remaining:
            min_sup = min(support[e] for e in remaining)
            k = max(k, min_sup + 2)

            to_remove = deque([e for e in remaining if support[e] <= k - 2])
            in_queue = set(to_remove)

            while to_remove:
                e = to_remove.popleft()
                in_queue.remove(e)
                if e not in remaining:
                    continue

                remaining.remove(e)
                trussness[e] = k

                u, v = e
                common = adj[u] & adj[v]
                for w in common:
                    e1 = (u, w) if u < w else (w, u)
                    e2 = (v, w) if v < w else (w, v)

                    if e1 in remaining and e2 in remaining:
                        support[e1] -= 1
                        support[e2] -= 1
                        if support[e1] <= k - 2 and e1 not in in_queue:
                            to_remove.append(e1)
                            in_queue.add(e1)
                        if support[e2] <= k - 2 and e2 not in in_queue:
                            to_remove.append(e2)
                            in_queue.add(e2)

                adj[u].remove(v)
                adj[v].remove(u)

        trussness_rows = []
        for u, v in edges:
            trussness_rows.append(
                {
                    "timetable_snapshot_id": timetable_snapshot_id,
                    "graph_build_id": build_record.id,
                    "station_a_id": u,
                    "station_b_id": v,
                    "trussness": trussness[(u, v)],
                    "triangle_support": original_support[(u, v)],
                }
            )

        if trussness_rows:
            db.execute(insert(RailwayNetworkEdgeTopologicalTrussness), trussness_rows)
            db.flush()

        # 5. Phase 68: Edge Topological Quadrangle Support
        adj_full: defaultdict[int, set[int]] = defaultdict(set)
        for u, v in edges:
            adj_full[u].add(v)
            adj_full[v].add(u)

        quad_support_rows = []
        for u, v in edges:
            n_u = adj_full[u] - adj_full[v] - {v}
            n_v = adj_full[v] - adj_full[u] - {u}

            c4_count = 0
            if len(n_u) <= len(n_v):
                for x in n_u:
                    c4_count += len(adj_full[x] & n_v)
            else:
                for y in n_v:
                    c4_count += len(adj_full[y] & n_u)

            quad_support_rows.append(
                {
                    "timetable_snapshot_id": timetable_snapshot_id,
                    "graph_build_id": build_record.id,
                    "station_a_id": u,
                    "station_b_id": v,
                    "quadrangle_support": c4_count,
                }
            )

        if quad_support_rows:
            from railgati.models.graph import RailwayNetworkEdgeTopologicalQuadrangleSupport

            db.execute(insert(RailwayNetworkEdgeTopologicalQuadrangleSupport), quad_support_rows)
            db.flush()

        # 6. Phase 69: Edge Topological Biconnected Component (Block) Size
        discovery = {}
        low = {}
        time_count = 0
        stack = []
        blocks = []

        for start_node in adj_full:
            if start_node in discovery:
                continue

            dfs_stack = [(start_node, None, iter(adj_full[start_node]))]
            time_count += 1
            discovery[start_node] = low[start_node] = time_count

            while dfs_stack:
                u, parent, n_iter = dfs_stack[-1]
                try:
                    v = next(n_iter)
                    if v == parent:
                        continue
                    if v in discovery:
                        low[u] = min(low[u], discovery[v])
                        if discovery[v] < discovery[u]:
                            stack.append((u, v))
                    else:
                        time_count += 1
                        discovery[v] = low[v] = time_count
                        stack.append((u, v))
                        dfs_stack.append((v, u, iter(adj_full[v])))
                except StopIteration:
                    dfs_stack.pop()
                    if dfs_stack:
                        p, _, _ = dfs_stack[-1]
                        low[p] = min(low[p], low[u])
                        if low[u] >= discovery[p]:
                            component = []
                            while stack:
                                edge = stack.pop()
                                component.append(edge)
                                if (edge[0] == p and edge[1] == u) or (edge[0] == u and edge[1] == p):
                                    break
                            blocks.append(component)
            if stack:
                blocks.append(list(stack))
                stack.clear()

        edge_to_block_size = {}
        for block in blocks:
            canonical_edges_in_block = {
                (min(u, v), max(u, v)) for u, v in block
            }
            size = len(canonical_edges_in_block)
            for ce in canonical_edges_in_block:
                edge_to_block_size[ce] = size

        biconnected_rows = []
        for u, v in edges:
            size = edge_to_block_size.get((u, v))
            if size is None:
                raise ValueError(f"Edge ({u}, {v}) did not receive a block assignment.")
            biconnected_rows.append(
                {
                    "timetable_snapshot_id": timetable_snapshot_id,
                    "graph_build_id": build_record.id,
                    "station_a_id": u,
                    "station_b_id": v,
                    "block_edge_count": size,
                }
            )

        if biconnected_rows:
            from railgati.models.graph import RailwayNetworkEdgeTopologicalBiconnectedComponent
            db.execute(insert(RailwayNetworkEdgeTopologicalBiconnectedComponent), biconnected_rows)
            db.flush()

        # 7. Finalize
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
