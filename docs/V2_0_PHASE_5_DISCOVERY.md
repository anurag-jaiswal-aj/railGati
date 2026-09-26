# v2.0 Phase 5 Discovery: Continuous Path Service Discovery

## 1. Phase 5 Title
**Continuous Path Service Discovery** (Through-Service Attribution)

## 2. Problem Statement
v2.0 Phase 4 successfully enabled service attribution for a multi-edge topological path, allowing clients to see which historical trains operated on *each individual segment* of a route. However, it does not distinguish between a disjointed set of segment services and a single, continuous "through-service" that traverses the entire path sequentially. Currently, a client must download all segment occurrences and manually intersect `train_id` and contiguous `stop_sequence` values. This is computationally expensive, requires excessive data transfer, and leaks relational-join logic into the client application.

## 3. Why It Follows Phase 4
Phase 4 proved that multi-segment graph properties can be queried safely while maintaining strict snapshot isolation. Phase 5 takes the exact same input (a bounded topological path) and applies a stricter structural constraint: identifying only the subset of historical trains that formed an uninterrupted, sequential chain of `RailwayServiceEdge` records covering the entire path. This completes the static network-path analysis suite by answering "Which single trains cover this entire route historically?"—proving historical structural continuity in the timetable/service-edge dataset.

## 4. Existing Capabilities Reused
- `RailwayNetworkEdge` (for path validation)
- `RailwayServiceEdge` (for continuous sequence validation)
- `Train` and `TrainObservation` (for canonical identity)
- Snapshot isolation helpers
- The Phase 2C/4 path validation constraints (max 10 stations)

## 5. Candidate Directions Considered
- **Network Corridor Service Analytics:** Calculating aggregate train volumes, fastest historical traversals, and bottleneck segments across a corridor. *Trade-off:* While analytically useful, it skips the more fundamental requirement of identifying continuous individual train traversals, which is a prerequisite for accurate corridor metrics.
- **Historical Network Connectivity Analytics:** Node degree centrality and graph-wide heaviest edges. *Trade-off:* Detached from the core path-exploration user journey. RailGati's primary trajectory is enabling path and service discovery before macro-analytics.
- **Passenger Itinerary Transfer Routing:** Modeling layovers between different trains. *Trade-off:* Explicitly forbidden by the current domain boundary. Transfer routing introduces time, calendar, and operational feasibility logic that requires a massive domain shift.

## 6. Architectural Trade-offs
To achieve continuous service discovery, the architecture must ensure contiguous `stop_sequence` values for a single `train_id` across $K-1$ segments.
- *Option A: Client-side intersection.* (Current state). High data transfer, pushes database logic to the frontend.
- *Option B: PostgreSQL Array Aggregation.* Grouping by `train_id` and using `array_agg(station_id)`. Vulnerable to sequence gaps or out-of-order arrays if not strictly controlled.
- *Option C: Dynamic N-way SQL JOINs.* Dynamically generating a query that self-joins `RailwayServiceEdge` $K-1$ times using its exact Primary Key `(timetable_snapshot_id, train_id, from_stop_sequence)`.
**Selection:** *Option C* is selected. Because the maximum path length is strictly bounded (max 10 stations / 9 segments), a 9-way self-join on primary keys is bounded by the maximum path length limit. The maximum path length is bounded to 10 stations. The query contains at most 9 service-edge aliases. Primary-key access is available for the relevant service-edge identity. PostgreSQL's optimizer chooses the actual execution plan. Execution behavior must be validated with EXPLAIN ANALYZE for representative and long paths.

## 7. Selected Scope
**Continuous Path Service Discovery.** Identifying single historical trains that traversed an entire provided topological path contiguously.

## 8. Explicit Scope
- Given an ordered sequence of canonical station codes (min 2, max 10), return the specific historical train services that have contiguous `RailwayServiceEdge` records covering the path.
- Compute the aggregate start/end timings and source-day offsets for the entire continuous journey.
- Validate topological path existence against `RailwayNetworkEdge`.
- Apply strict `timetable_snapshot_id` isolation.

## 9. Explicit Non-Scope
- **Passenger Routing / Transfers:** This does not find paths requiring a transfer between two different trains.
- **Calendar Validity:** It does not prove the train runs on a specific real-world calendar date.
- **Live Operations:** No live delays, fares, or seat availability.
- **Pathfinding:** It does not find the topological path; the client must provide it.

## 10. Domain Semantics
- A **Continuous Service** is structurally defined as a single `train_id` possessing $N$ `RailwayServiceEdge` records corresponding to the $N$ requested network edges.
- For consecutive requested segments $S_i \rightarrow S_{i+1}$ and $S_{i+1} \rightarrow S_{i+2}$, the same train must have:
  - `edge_i.to_station_id = edge_(i+1).from_station_id` (station identity matters because trains may visit the same station multiple times; `stop_sequence` alone is insufficient)
  - `edge_i.to_stop_sequence = edge_(i+1).from_stop_sequence` (contiguous sequence)
  - `edge_i.timetable_snapshot_id = edge_(i+1).timetable_snapshot_id` (snapshot isolation)
  - `edge_i.train_id = edge_(i+1).train_id` (same train identity)
- Each edge corresponds to the exact requested directed station pair.
- This remains a historical graph intelligence feature. This is historical dataset structure only. It does not prove actual historical operation, current operation, passenger-valid travel, ticketability, or a guaranteed through journey.

## 11. Data / Query Model
**Exact Tables & Joins:**
- $N$ instances of `railway_service_edges` (e.g., `e1`, `e2`, ... `eN`)
- `trains` (t)
- `train_observations` (to_obs)

**Join Logic:**
```sql
FROM railway_service_edges e1
JOIN railway_service_edges e2 
  ON e1.train_id = e2.train_id AND e1.to_stop_sequence = e2.from_stop_sequence AND e1.timetable_snapshot_id = e2.timetable_snapshot_id
...
JOIN trains t ON e1.train_id = t.id
JOIN train_observations to_obs ON to_obs.train_id = t.id AND to_obs.snapshot_id = e1.timetable_snapshot_id
```

**Expected Cardinality:**
The bounded maximum path length limits the number of self-join aliases. However, intermediate cardinality and execution strategy remain data- and planner-dependent and must be measured against the active dataset. A `LIMIT 500` is applied at the outer query for API output safety, which bounds the response payload but does not inherently bound intermediate database materialization memory.

## 12. Snapshot / Provenance Semantics
The query is strictly bound to the active timetable snapshot.
Every alias of `railway_service_edges` in the dynamic join must explicitly filter `timetable_snapshot_id = :snapshot_id`.
If the feature relies on the materialized `RailwayNetworkEdge` graph for internal path validation (following Phase 4 conventions), the corresponding `RailwayGraphBuild` must be explicitly required to be `ACTIVE`. The service does not independently select different graph/timetable snapshots for different segments; every alias in the query is scoped to the exact same `timetable_snapshot_id`.

## 13. Service-Layer Responsibilities
- Validate path parameters (length, duplicate consecutive stations).
- Resolve canonical stations.
- Verify path topology against `RailwayNetworkEdge`.
- Dynamically generate the SQLAlchemy N-way self-join query.
- Execute and map the result to the response schema, calculating total `duration_minutes` natively or via Python datetime parsing using start/end times and day offsets.

## 14. Proposed API Surface
**Endpoint:** `GET /api/v1/network/path/continuous-services`
**HTTP Method:** GET

## 15. Request Parameters
| Name | Type | Location | Required | Default | Description |
|---|---|---|---|---|---|
| `path` | `string` | Query | Yes | - | Comma-separated canonical station codes (e.g., `NDLS,AGC,BPL`). Min 2, Max 10 stations. |

## 16. Response Shape
```json
{
  "path": ["NDLS", "AGC", "BPL"],
  "timetable_snapshot_id": 2,
  "total_services_returned": 1,
  "services": [
    {
      "train_number": "12137",
      "train_name": "PUNJAB MAIL",
      "train_type": "SF",
      "start_sequence": 5,
      "end_sequence": 7,
      "departure_time": "05:15",
      "arrival_time": "12:30",
      "start_day_offset": 0,
      "end_day_offset": 0,
      "total_duration_minutes": 435
    }
  ]
}
```

## 17. Validation Rules
- `path` must contain 2 to 10 valid station codes.
- Consecutive stations cannot be identical.

## 18. Error Semantics
- **422 Unprocessable Entity**: Invalid path format or length.
- **404 Not Found**: Unknown station code.
- **400 Bad Request**: Path segment does not exist in the active network topology.
- **503 Service Unavailable**: Active graph build unavailable.

## 19. Deterministic Ordering
Results must be deterministically ordered by:
1. `departure_time` ASC
2. `train_number` ASC

## 20. Resource Limits
- Maximum 10 stations per path.
- API response output bound: 500 continuous services maximum per request. Note that this limits the output payload, but does not guarantee strictly bounded intermediate memory consumption in PostgreSQL.

## 21. Performance Considerations
The dynamic self-join is selected based on the strict continuity semantics and bounded path length (max 10 stations). Primary-key access paths are available for the service-edge identity. However, intermediate result growth, join order, and execution strategy are planner-dependent and must be validated with `EXPLAIN ANALYZE`.

## 22. Query Strategy
Instead of a window function (which would pull all segments into memory before filtering), the dynamic INNER JOIN forces PostgreSQL to perform exact Primary Key lookups for continuity. 
```sql
SELECT 
  t.number, to_obs.name, 
  e1.from_stop_sequence, eN.to_stop_sequence,
  e1.departure_time, eN.arrival_time,
  e1.source_day_offset, eN.source_day_offset
FROM railway_service_edges e1
JOIN railway_service_edges e2 ON e1.train_id = e2.train_id AND e1.to_stop_sequence = e2.from_stop_sequence
...
```

## 23. Index Strategy
The existing indexes provide access paths for the relevant station/snapshot predicates; actual index usage must be verified with `EXPLAIN ANALYZE`. The schema supports primary key lookups, but we do not claim a particular index will be used until the implementation query is empirically benchmarked.

## 24. Benchmark Methodology
Replace assumptions with empirical measurement on the active dataset:
- **A. Normal case**: 3-station / 2-segment path.
- **B. Medium case**: Approximately 5-station path if real data contains one.
- **C. Long case**: Maximum valid 10-station / 9-segment path, if available.
- **D. Dense case**: Path containing a high-density service edge.

For each, record:
- `EXPLAIN ANALYZE` output
- Planning time and execution time
- Scan types, index usage, and join strategy
- Rows at important stages
- Sort/window/materialization behavior if present
- Application-level SQLAlchemy execution time

## 25. Test Strategy
Expand testing to comprehensively cover:
1. Two-station path.
2. Three-station continuous service.
3. Longer continuous path.
4. Same train with contiguous stop sequences.
5. Same train with a stop-sequence gap (must be excluded).
6. Same train with station mismatch (must be excluded).
7. Different trains across segments (must be excluded).
8. Repeated station occurrence.
9. Multiple valid continuous occurrences of the same train if data permits.
10. Reverse direction.
11. Timetable snapshot isolation.
12. TrainObservation snapshot isolation.
13. ACTIVE graph requirement.
14. Unknown station.
15. Invalid path parameter.
16. Broken topology.
17. Missing timing data handling.
18. Cross-day timing.
19. Deterministic ordering.
20. 500-result API bound limit enforcement.
21. Phase 3 regression.
22. Phase 4 regression.

## 26. Security Considerations
Dynamic query generation using SQLAlchemy must use parameterized binding or ORM joins to prevent SQL injection. Raw string concatenation of SQL is strictly prohibited.

## 27. ₹0 Validation
Relies entirely on PostgreSQL nested loop performance. No external dependencies.

## 28. Future Extension Points
This capability provides the exact underlying data structure needed for a future "Direct Journey Search" or "One-Seat Ride" query. However, Phase 5 itself does NOT establish calendar validity, passenger eligibility, operating-date validity, current operation, or ticketability. A continuous historical service is a structural dataset result only.

## 29. Risks
- **SQLAlchemy Dynamic Joins**: Constructing N-way self-joins dynamically in SQLAlchemy Core/ORM can be syntactically dense. The implementation must carefully alias the `RailwayServiceEdge` table (`aliased(RailwayServiceEdge)`) in a loop.

## 30. Unresolved Questions
- **Time/Duration Calculation**: Following established Phase 3 missing-data semantics, if required start departure or final arrival timing is missing or inconsistent, the total duration must evaluate to `null` without fabricating calendar dates.

## 31. Implementation Sequencing
1. Write SQLAlchemy dynamic self-join logic using `aliased`.
2. Implement service layer with robust null-handling for duration calculations.
3. Build the `/api/v1/network/path/continuous-services` endpoint.
4. Execute full benchmark suite and record EXPLAIN ANALYZE proof.
