# RailGati v2.0 — Railway Network Graph Discovery

## 1. Objective
Design and validate the architecture for a Railway Network Graph foundation (v2.0) that enables multi-transfer routing, path exploration, and network analysis, strictly adhering to the project's historical/static data semantics and ₹0 budget constraint.

## 2. Current State and Findings
- **Data Model**: RailGati successfully operates a relational PostgreSQL schema encompassing canonical `Station`s, `Train`s, and snapshot-isolated `TrainStopObservation`s (~417k historical records).
- **Existing Search**: v1.x provides high-performance direct and bounded 1-transfer discovery by relying on `B-tree` indexes and set-based relational algebra, intentionally deferring open-ended graph searches to prevent Cartesian explosion.
- **Provenance**: Data isolation is rigorously enforced through `DatasetSnapshot`.

## 3. Problem Statement
The current relational design easily models point-to-point schedule queries but struggles with open-ended multi-hop network traversals. Evaluating arbitrary routes (e.g., "Find all paths from A to D with up to 3 transfers") requires navigating an interconnected topology of train segments. A robust, reproducible, and historical-snapshot-bound graph representation is required to support this natively.

## 4. Graph Concepts
The railway graph must decouple physical connectivity from service-level connectivity while maintaining strict traceability to the active timetable snapshot.

## 5. Node Semantics
- **Candidate**: Canonical `Station` identity (`station_id`).
- **Rationale**: A node represents a physical location in the network. Station metadata (names, geo-coordinates) lives in `StationObservation` and is resolved at the presentation layer. The graph topology structurally relies only on the stable `Station.id`.

## 6. Edge Semantics
- **Candidate**: A directed link between consecutive `TrainStopObservation` records (`stop_sequence` $N \rightarrow N+1$) within a specific timetable snapshot.
- **Dual-Layer Approach**:
  1. **`NetworkEdge` (Aggregated Topology)**: `from_station` $\rightarrow$ `to_station`. Represents physical connectivity. Useful for high-level neighbor discovery ("Can I physically travel from A to B directly?").
  2. **`ServiceEdge` (Train-Specific Segment)**: `from_station` $\rightarrow$ `to_station` via a specific `train_id` at a specific `stop_sequence`. Essential for actual routing and transfer calculations.

## 7. Historical Snapshot Semantics
- Graph data must NOT mix timetable snapshots. 
- **Strategy**: Every materialized edge must carry a `timetable_snapshot_id`. The graph is effectively partitioned by snapshot, ensuring complete historical isolation. A query for "reachable stations" always filters by `snapshot_id`.

## 8. Multiple-Visit Handling
- Trains may visit a station multiple times (looping routes).
- **Strategy**: The `ServiceEdge` must explicitly store `from_stop_sequence` and `to_stop_sequence`. An edge from Station A $\rightarrow$ B is uniquely identified by `(snapshot_id, train_id, from_stop_sequence)`. This guarantees traversal algorithms respect linear time and direction, preventing infinite loops on circular train routes.

## 9. Transfer Semantics
- An edge `A -> B` connecting to `B -> C` (different trains) does not imply a valid transfer.
- **Strategy**: Transfer edges should **NOT** be eagerly materialized in the database. Generating every possible `A -> B -> C` transfer permutation per station would cause an N² explosion. Instead, transfers must be dynamically evaluated during path traversal (checking arrival buffer vs departure) using the timing constraints natively embedded in the `ServiceEdge`.

## 10. Timing Semantics
- The `ServiceEdge` should contain `duration_minutes`, `source_day_offset`, `departure_time`, and `arrival_time`.
- Aggregated `NetworkEdge` records can store `min_duration_minutes` (fastest historical segment) to optimize heuristics (e.g., A* search).

## 11. Candidate Data Model
PostgreSQL can seamlessly store graph adjacency lists:

```sql
-- Represents a single physical movement of a specific train between two consecutive stops
CREATE TABLE railway_service_edges (
    timetable_snapshot_id INT NOT NULL,
    train_id INT NOT NULL,
    from_station_id INT NOT NULL,
    from_stop_sequence INT NOT NULL,
    to_station_id INT NOT NULL,
    to_stop_sequence INT NOT NULL,
    departure_time VARCHAR(20),
    arrival_time VARCHAR(20),
    duration_minutes INT,
    
    PRIMARY KEY (timetable_snapshot_id, train_id, from_stop_sequence)
);

-- Represents aggregated physical network connectivity
CREATE TABLE railway_network_edges (
    timetable_snapshot_id INT NOT NULL,
    from_station_id INT NOT NULL,
    to_station_id INT NOT NULL,
    train_count INT NOT NULL,
    min_duration_minutes INT,
    
    PRIMARY KEY (timetable_snapshot_id, from_station_id, to_station_id)
);
```

## 12. PostgreSQL vs Graph Database Assessment
- **PostgreSQL**: Highly capable of recursive CTEs (`WITH RECURSIVE`) for pathfinding. With ~417k train stop observations, the materialized edge tables will also be ~400k rows—trivially small for PostgreSQL (fitting entirely in RAM). It preserves ACID compliance, shares existing infrastructure, ensures zero operational drift, and costs ₹0.
- **Graph DB (Neo4j, RedisGraph)**: Offers optimized traversal syntax (Cypher) and superior deep-hop performance, but requires deploying and maintaining a secondary data store, writing complex synchronization pipelines, and managing snapshot semantics manually. Usually violates the ₹0 hosting budget.
- **Verdict**: PostgreSQL is objectively the correct foundation for v2.0. If multi-hop algorithms eventually exceed CTE performance limits, an in-memory application-layer graph (e.g., NetworkX loaded dynamically per request) or a dedicated graph DB can be adopted later without changing the relational source of truth.

## 13. Provenance Design
Graph structures are derivative. The `timetable_snapshot_id` serves as the absolute provenance anchor. A separate `RailwayGraphBuild` log table may track materialization status (Pending, Success, Failed) per timetable snapshot, ensuring transparent rebuilds.

## 14. Build Pipeline
Materialization is a batch process that occurs immediately after a new timetable snapshot reaches `ACTIVE` status.
1. Query `TrainStopObservation` using `LEAD()` window functions to extract consecutive $N \rightarrow N+1$ stop pairs.
2. Bulk insert into `railway_service_edges`.
3. Aggregate and bulk insert into `railway_network_edges`.
4. Log completion.

## 15. Failure & Idempotency Strategy
- **Failure**: Handled via standard PostgreSQL transactions. If graph generation fails, the transaction rolls back, leaving no orphaned edges. The underlying timetable snapshot remains untouched and active for direct queries.
- **Idempotency**: Graph build operations `DELETE FROM railway_service_edges WHERE timetable_snapshot_id = X` before generating to prevent duplicate edges if retried.

## 16. Validation Strategy
Integrity checks applied during/after build:
- `from_stop_sequence` must strictly be `< to_stop_sequence`.
- Edge count must conceptually align with `(total_stops - total_trains)`.
- No self-loops (`from_station_id != to_station_id`).
- All foreign keys bind to the exact same `snapshot_id`.

## 17. Index Strategy
Targeted B-tree indexes for fast adjacency lookups:
- `ix_network_edges_from_station` (`snapshot_id`, `from_station_id`) -> Fast topological neighbor lookups.
- `ix_service_edges_from_station` (`snapshot_id`, `from_station_id`) -> Fast departure routing.
- `ix_service_edges_to_station` (`snapshot_id`, `to_station_id`) -> Fast arrival routing.

## 18. Initial Graph Queries (v2.0 Scope)
1. **Station Neighbors**: Fetch immediate adjacent connected stations.
2. **Aggregated Direct Connectivity**: Discover all direct edges leaving a station.

## 19. Deferred Functionality (Future Work)
- Multi-transfer / Multi-hop route discovery APIs.
- Dedicated graph database deployment.
- ML/Centrality analytics.
- Live data routing.

## 20. Performance Considerations
A `LEAD()` query over 417k observations partitioned by `train_id` will execute in seconds. Querying the resulting adjacency tables using standard B-tree indices takes sub-millisecond time.

## 21. ₹0 Compliance
Relying entirely on PostgreSQL completely satisfies the absolute ₹0 deployment budget.

## 22. Open Questions
- Should `ServiceEdge` be a materialized table, or merely a materialized view dynamically computed from `TrainStopObservation`? Given the static historical nature, a concrete table allows aggressive indexing.
- Should transfer wait-time heuristics be pre-computed at the `NetworkEdge` level to speed up heuristic searches? (e.g. average layover time at Station X).

## 23. Readiness
The graph architecture is fully specified. The next logical increment is to implement the relational models, migrations, and pipeline logic to materialize `railway_service_edges` and `railway_network_edges`.

*(End of Discovery)*
