# v2.0 Phase 6 Discovery: Network Corridor Analytics

## 1. Phase 6 Title
**Network Corridor Analytics (Continuous Service Route Discovery)**

## 2. Problem Statement
Phase 2C provides the shortest topological path between two stations via a Breadth-First Search on `RailwayNetworkEdge`. Phase 5 validates whether a *specific, provided* path is traversed by continuous historical services. However, users and analytical systems currently cannot ask the graph: *"What are the actual, utilized physical corridors (paths) between Station A and Station D, and which corridor carries the most continuous trains?"* Attempting to answer this by exhaustively traversing the `RailwayNetworkEdge` graph for all possible paths and testing each via Phase 5 would require evaluating many paths that no single train actually traverses.

## 3. Why It Follows Phase 5
Phase 5 established the rigid domain semantics for continuous single-train traversals across topological segments. Phase 6 inverts this constraint: rather than checking a user-supplied path for continuous services, it aggregates the exact contiguous sequences of utilized train stops to *discover* the distinct topological paths (corridors) operating in the historical dataset. It builds upon Phase 5's conceptual foundation of structural continuity while solving the unbounded graph-traversal problem using deterministic relational algebra.

## 4. Existing Capabilities Reused
- `TrainStopObservation` boundary checking (used in v1.x direct journeys).
- Phase 5 missing-data timing semantics (`_parse_time_to_minutes`).
- `DatasetSnapshot` isolation and `RailwayGraphBuild` dependencies.
- Canonical station resolution and API validation patterns.

## 5. Candidate Directions Considered
- **Historical Timetable Journey Search (Passenger Transfer Routing):** *REJECTED.* Modeling 1-hop or 2-hop transfers between different trains requires explicit calendar operating days (e.g., "Runs on M,T,W"). The current Datameet-derived timetable provides `source_day_offset` (relative days) but lacks absolute calendar alignments. Joining Train 1 and Train 2 based purely on time-of-day offsets creates theoretically unsafe, passenger-invalid journeys.
- **Historical Service Journey Comparison:** *REJECTED.* v1.2 already provides direct journey comparison. Phase 6 must advance the v2.0 network graph architecture.
- **Connection-Risk Foundations:** *REJECTED.* Requires valid transfer semantics, which are rejected above due to data limitations.
- **Network Corridor Analytics (Selected):** *SELECTED.* Safely utilizes explicit, single-train continuous services to discover macroscopic network topology without theoretical transfer risks.

## 6. Architectural Trade-offs
To discover topological paths between A and D:
- **Option A (Recursive CTE on NetworkEdge):** Blindly generating possible physical topologies via Cartesian graph traversal and checking if trains run on them. Evaluates paths that no single train actually drives, leading to unnecessary database work.
- **Option B (Array Aggregation on TrainStops):** Identifying explicitly observed continuous train occurrences between A and D, extracting their exact sequential stops using `array_agg(station_id ORDER BY stop_sequence)`, and grouping identical routes into distinct corridors.
**Selection:** *Option B*. This avoids recursive traversal over topological paths because candidates originate from observed train-stop sequences. Actual performance and intermediate cardinality must be established with EXPLAIN ANALYZE.

## 7. Selected Scope
**Network Corridor Analytics.** Discovering and ranking the distinct topological routes (corridors) formed by continuous historical services between an origin and destination.

## 8. Explicit Scope
- Given an origin and destination station, return all unique topological station-paths (corridors) traversed by at least one continuous historical train occurrence.
- Aggregate the total number of continuous service occurrences operating on each corridor.
- Calculate the fastest observed historical duration across all occurrences in each corridor.
- Maintain strict snapshot isolation.
- Require an `ACTIVE` `RailwayGraphBuild`.

## 9. Explicit Non-Scope
- **Passenger Routing / Transfers:** Will not combine different trains to form a corridor.
- **Calendar Validity:** Will not claim the corridor operates on a specific real-world date.
- **Live Operations:** No live delays, fares, seat availability, or operational status.
- **ML / LLM / Intelligent Agents:** No predictive capabilities or conversational agents.

## 10. Historical-Data Semantics
Corridors represent aggregated historical structural connectivity. A returned corridor proves that in the specified snapshot, train occurrence(s) physically drove that exact sequence of stations. It does not guarantee current passenger availability.

## 11. Domain Semantics
- A **Corridor** is defined as a unique, ordered array of canonical station codes connecting an Origin to a Destination, historically generated by the contiguous stop sequences of one or more continuous train occurrences.
- **Service Count Semantics:** The metric exposed will be `occurrence_count`, explicitly counting structural O-D occurrences (COUNT(*)). If a single train loop visits the origin and destination multiple times producing multiple valid sequence pairs, each valid continuous pair constitutes a distinct structural occurrence before aggregation.

## 12. Timing Semantics
- Uses the Phase 5 timing strategy at the **occurrence level**.
- Duration must be calculated for each individual O-D occurrence BEFORE grouping corridors.
- For each occurrence: `destination arrival + destination source_day` minus `origin departure + origin source_day`.
- Missing or inconsistent timing gracefully evaluates to `null` for that occurrence.
- The corridor aggregation then calculates `MIN(duration)` across all associated valid occurrence durations.

## 13. Transfer Semantics
Explicitly N/A. The feature strictly utilizes continuous, single-seat historical services to avoid calendar-day fallacies.

## 14. Data / Query Model
**Tables:**
- `train_stop_observations` (for bounding O-D and extracting path sequences)
- `stations` (for resolving codes)

**Three Conceptual Stages:**
1. **bounds:** Identify every valid O-D occurrence pair. Identity is strictly defined by `(train_id, start_stop_sequence, end_stop_sequence)`.
2. **occurrence_paths:** Extract exactly one ordered station sequence (path array) and calculate the individual occurrence duration per occurrence identity.
3. **corridor_aggregation:** Group by the identical station sequences (`path_array`), aggregating `COUNT(*)` as `occurrence_count` and `MIN(duration)` as `fastest_duration_minutes`.

## 15. Snapshot & Graph-Build Semantics
- All `TrainStopObservation` rows must strictly belong to the single requested `timetable_snapshot_id`.
- Canonical station resolution uses the active station snapshot.
- No cross-snapshot joins are permitted.
- **Graph-Build Dependency:** To ensure the returned topological corridors structurally align with the network topology available in Phase 2C/4/5, an `ACTIVE` `RailwayGraphBuild` corresponding to the exact same `timetable_snapshot_id` is explicitly REQUIRED. Without it, the endpoint must abort.

## 16. Service-Layer Responsibilities
- Validate input (Origin != Destination).
- Resolve canonical station IDs.
- Verify `ACTIVE` `RailwayGraphBuild`.
- Execute the array-aggregation SQL query maintaining occurrence identity.
- Map returned arrays back to canonical station codes.
- Format the response and enforce deterministic ordering.

## 17. Proposed API
**Endpoint:** `GET /api/v1/network/corridors`
**Method:** GET

## 18. Request Parameters
| Name | Type | Location | Required | Default | Description |
|---|---|---|---|---|---|
| `origin` | `string` | Query | Yes | - | Canonical origin station code (e.g., `NDLS`) |
| `destination` | `string` | Query | Yes | - | Canonical destination station code (e.g., `BPL`) |

## 19. Response Shape
```json
{
  "origin": "NDLS",
  "destination": "BPL",
  "timetable_snapshot_id": 2,
  "corridors": [
    {
      "path": ["NDLS", "AGC", "GWL", "VGLJ", "BPL"],
      "occurrence_count": 45,
      "fastest_duration_minutes": 420
    },
    {
      "path": ["NDLS", "MTJ", "AGC", "GWL", "VGLJ", "BPL"],
      "occurrence_count": 12,
      "fastest_duration_minutes": 480
    }
  ]
}
```

## 20. Validation Rules
- `origin` and `destination` must be provided and valid canonical codes.
- `origin` must not equal `destination` (case-insensitive).

## 21. Error Semantics
- **422 Unprocessable Entity:** Origin equals destination.
- **404 Not Found:** Origin or destination station unknown.
- **503 Service Unavailable:** Active snapshot or active `RailwayGraphBuild` unavailable.

## 22. Deterministic Ordering
The final aggregated output must enforce deterministic ordering:
1. `occurrence_count` DESC
2. `fastest_duration_minutes` ASC NULLS LAST
3. Array length (`json_array_length(path)` equivalent) ASC
4. Canonical station-code sequence string comparison ASC

## 23. Resource Limits
Result cardinality depends on the number of distinct observed O-D trajectories. Intermediate occurrence count and array aggregation memory must be evaluated. While an output `LIMIT` (e.g., top 100) bounds network payload size, it does not strictly bound intermediate database work. Actual resource consumption will be established via benchmark testing.

## 24. Performance Considerations
Actual performance and join/aggregation strategy must be established with `EXPLAIN ANALYZE` on the dataset. The query avoids CTE graph recursion, but the aggregation costs associated with `array_agg` over the bounds must be explicitly measured.

## 25. Query Strategy
```sql
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
         array_agg(tso.station_id ORDER BY tso.stop_sequence) as path_array,
         -- occurrence duration calculated here using b timing fields
         (b.arrival_time, b.end_day, b.departure_time, b.start_day) as duration
  FROM bounds b
  JOIN train_stop_observations tso
    ON tso.train_id = b.train_id
   AND tso.snapshot_id = :snapshot
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
SELECT * FROM corridor_aggregation
ORDER BY occurrence_count DESC, fastest_duration_minutes ASC;
```

## 26. Index Strategy
The query leverages the existing composite index `ix_train_stops_snapshot_station` on `(snapshot_id, station_id)`. The specific execution path will depend on the query planner and must be validated.

## 27. Benchmark Methodology
- **A. Normal case:** Dense intercity corridor (e.g., Delhi to Kanpur).
- **B. Sparse case:** Cross-country corridor with few direct trains (e.g., Jammu to Kanyakumari).
- **C. High-Density Multi-Route case:** Stations connected by multiple differing physical paths (e.g., Delhi to Mumbai).
- For each, record: `EXPLAIN ANALYZE` (Planning, Execution, Scans, Join Strategy, Array Aggregate memory) and application-level execution time.

## 28. Test Strategy
At a minimum, the following mandatory scenarios must be tested:
1. One train, one O-D occurrence.
2. One train, multiple origin occurrences.
3. One train, multiple destination occurrences.
4. One train, multiple valid O-D occurrence pairs.
5. Two trains with identical corridor.
6. Two trains with different corridors.
7. Same corridor with different timing.
8. Missing timing in one occurrence.
9. Missing timing in all occurrences.
10. Reverse direction.
11. Origin after destination.
12. Same station (422 validation).
13. Unknown station (404 validation).
14. Snapshot isolation (different snapshots do not mix).
15. ACTIVE Graph Build isolation (endpoint aborts if build is missing).
16. Deterministic ordering when all primary ordering fields tie.

## 29. Security Considerations
ORM and parameterized text queries prevent SQL injection.

## 30. ₹0 Validation
Relies strictly on native PostgreSQL array aggregation and relational grouping.

## 31. Future Extension Points
The discovered corridor arrays can be fed into a UI mapping layer to visualize the actual trunk routes of the Indian Railway network.

## 32. Risks
- **Memory Consumption in Array Aggregation:** Extremely long trains aggregated in memory across many occurrences could consume higher `work_mem`. Intermediate row counts and array memory footprints must be observed.

## 33. Unresolved Questions
None. The dependency on an `ACTIVE` `RailwayGraphBuild` has been explicitly affirmed for structural network consistency.

## 34. Implementation Sequencing
1. Implement occurrence-level duration extraction Python logic / SQL macro.
2. Build the explicit 3-stage SQLAlchemy CTE inside `services/network.py`.
3. Create schemas and the `GET /api/v1/network/corridors` endpoint.
4. Validate with `EXPLAIN ANALYZE` on the dataset.
