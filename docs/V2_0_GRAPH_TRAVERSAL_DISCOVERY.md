# RailGati v2.0 Phase 2 — Railway Graph Traversal & Network Query Discovery

## 1. Objective
Design the first usable graph traversal query layer on top of the established `RailwayNetworkEdge` foundation. This defines the architecture for a bounded, deterministic network traversal capability to answer topological connectivity queries without conflating them with passenger routing.

## 2. Current Graph Foundation
The v2.0 Phase 1 foundation successfully materialized a PostgreSQL-native graph bound to historical snapshots.
- **`RailwayGraphBuild`**: Tracks build status (ACTIVE, PENDING, FAILED) per snapshot.
- **`RailwayServiceEdge`**: Train-specific consecutive segments (~411k edges).
- **`RailwayNetworkEdge`**: Aggregated station-to-station physical connectivity (~20k edges).
- **Materialization**: Idempotent, deterministic, and transactionally safe (takes ~48s for ~417k observations).

## 3. Network Topology vs Passenger Routing
It is critical to distinguish these two domains:
- **Network Topology**: Answers *"Can the timetable-derived network reach Station C from Station A?"* It uses `RailwayNetworkEdge` to traverse physical station adjacency.
- **Passenger Routing**: Answers *"Can a passenger feasibly travel from A to C given transfer wait times and train schedules?"* It requires `RailwayServiceEdge` and timing checks.

Phase 2 focuses exclusively on **Network Topology**.

## 4. Traversal Candidates
- **Direct neighbors**: 1-hop reachability.
- **Bounded reachability**: Stations reachable within $N$ network hops.
- **Shortest-hop path**: The specific sequence of stations to reach a destination.
- **Service-aware / Time-aware passenger path**: Full routing.

## 5. Selected Phase 2 Primitive
**Bounded Reachability (`Reachable stations within N hops`)** is the selected first traversal primitive. It exercises the core recursive logic necessary for graph queries, handles cycles, and provides the baseline for both immediate neighbors (when $N=1$) and deep network connectivity, without requiring complex path-reconstruction or timing logic.

## 6. NetworkEdge vs ServiceEdge Choice
**`RailwayNetworkEdge`** must be used for Phase 2 topology traversal. 
- It is 20x smaller than `ServiceEdge` (~20,000 vs ~411,000 rows).
- It explicitly abstracts away train identity, making it perfect for answering topological adjacency questions. 
- Attempting to traverse `ServiceEdge` without transfer constraints would incorrectly imply arbitrary train-hopping is always valid.

## 7. Recursive CTE vs BFS Analysis
- **Application BFS**: Pulling all edges into Python memory and manually tracking visited sets.
- **PostgreSQL Recursive CTE**: Utilizing `WITH RECURSIVE` directly on the database.
- **Decision**: **Recursive CTE**. The graph fits effortlessly in memory. Read-only benchmarking on the actual graph shows a 10-hop cycle-free recursive CTE executes in ~12 milliseconds, traversing 6,000+ paths seamlessly via `Index Only Scans`. This completely eliminates the network I/O penalty of pulling the graph into Python.

## 8. Cycle Handling
The graph contains bidirectional routes and potential cycles (e.g., A $\rightarrow$ B $\rightarrow$ A).
- **Strategy**: The CTE tracks visited stations using string concatenation (e.g., `',' || from_station_id || ',' || to_station_id || ','`). The recursive join strictly enforces `r.visited NOT LIKE '%,' || e.to_station_id || ',%'`. This natively prevents infinite loops and terminates cyclic paths immediately while maintaining universal compatibility (PostgreSQL/SQLite).

## 9. Maximum Depth
To protect database resources, traversal must have a hard upper bound.
- **Limit**: `max_hops <= 10`. 
- **Rationale**: 10 hops represent an extreme upper bound for any reasonable physical train network traversal. A 10-hop traversal benchmark completed in 12ms, well within safe operational parameters.

## 10. Snapshot Semantics
Traversal queries must strictly filter by `timetable_snapshot_id = X` in both the CTE base query and the recursive JOIN clause. Graph data from different snapshots will never intersect.

## 11. Graph Build Status Behavior
Before traversing, the application must verify `RailwayGraphBuild.status == 'ACTIVE'` for the requested snapshot. If the build is `PENDING`, `FAILED`, or absent, the service must abort and return a clear error (e.g., HTTP `404 Not Found` mapping to "Active graph unavailable for this snapshot") to prevent traversing a partial or corrupted layer.

## 12. Result Semantics
The primitive will aggregate the CTE output to return a set of distinct reachable stations and their minimum network depth.
- **Output**: `[{ "station": <StationSchema>, "min_hops": 2 }]`
- **Ordering**: Deterministically ordered by `min_hops ASC`, then `station.code ASC`.

## 13. Path Identity
For reachability, individual paths (e.g., A $\rightarrow$ B $\rightarrow$ C vs A $\rightarrow$ D $\rightarrow$ C) are deduplicated in the final aggregation (`SELECT station_id, MIN(depth)`). Explicit path sequence reconstruction is deferred to shortest-path discovery.

## 14. Self-Loop Handling
The dataset contains a valid self-loop. The CTE string constraint natively handles this. If a path is at Station A, traversing A $\rightarrow$ A is immediately rejected because A is already in the visited string. Additionally, the base case explicitly filters `to_station_id != origin_id`. Self-loops safely evaporate during traversal.

## 15. Timing Semantics
Timing is **strictly ignored**. `NetworkEdge.min_duration_minutes` is unused.
*Phase 2 topology traversal answers network reachability, not passenger journey feasibility.*

## 16. Transfer Semantics
Passenger transfer buffers are **strictly ignored**. Validating a transfer belongs to passenger routing (`ServiceEdge`), not network topology.

## 17. Proposed Service Boundary
```python
def find_reachable_stations(
    db: Session, 
    origin_station_id: int, 
    max_hops: int, 
    timetable_snapshot_id: int
) -> list[StationReachability]:
    # 1. Verify ACTIVE RailwayGraphBuild
    # 2. Execute CTE with max_hops and cycle prevention
    # 3. Join Station observations for metadata
    # 4. Return deduplicated list
```

## 18. Future API Boundary
`GET /api/v1/network/reachable?origin=NDLS&max_hops=3`
- Leverages existing snapshot-selection dependency.

## 19. Safety Limits
- `max_hops` is capped at 10 via Pydantic validation.
- Traversal strictly requires an origin station.
- Database query execution inherits global `statement_timeout` safeguards.

## 20. Performance Analysis
Empirical, read-only EXPLAIN ANALYZE benchmarks on `timetable_snapshot=2` (19,866 edges):
- 3-hop cycle-free traversal: **~0.39ms** (18 paths evaluated)
- 10-hop cycle-free traversal: **~12.1ms** (6,586 paths evaluated)
The performance is profoundly efficient due to the optimal `ix_network_edges_from_station` B-tree index.

## 21. PostgreSQL Suitability
PostgreSQL is definitively the correct technology. It natively handles cycle-free recursive queries in sub-20 milliseconds. There is absolutely no justification for introducing a secondary Graph Database (Neo4j/RedisGraph) at this scale.

## 22. Future Multi-Transfer Compatibility
This CTE architectural pattern establishes a conceptual paradigm for future graph exploration, but **topology traversal is only a foundation**. Multi-transfer passenger routing CANNOT be implemented merely by swapping `NetworkEdge` for `ServiceEdge`. Passenger routing requires significantly more state, including:
- Train identity and stop occurrence
- Arrival and departure timing
- Minimum transfer buffers
- Source-day progression
- Potentially additional journey constraints

## 23. Deferred Scope
- Shortest-path sequential route reconstruction.
- Passenger routing (transfers, wait times, `ServiceEdge` traversal).
- Live data routing.

## 24. Open Questions
- Should `max_hops=1` be extracted into a dedicated `/api/v1/network/neighbors` convenience endpoint, or is `/reachable` sufficient?

## 25. Implementation Sequence
1. ~~Implement `find_reachable_stations` service logic with CTE.~~ *(IMPLEMENTED)*
2. ~~Add service-level unit tests for varying `max_hops`, cycle prevention, and snapshot status validation.~~ *(IMPLEMENTED)*
3. Expose `GET /api/v1/network/reachable` endpoint.
4. Add API integration tests.

*(End of Discovery)*
