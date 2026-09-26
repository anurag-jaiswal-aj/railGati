# v2.0 Phase 4 Discovery: Network Path Service Attribution

## 1. Phase 4 Title
**Network Path Service Attribution** (Topology + Service Attribution Composition)

## 2. Problem Statement
v2.0 Phase 2C established bounded topological path discovery (e.g., Station A → Station B → Station C). v2.0 Phase 3 established historical service attribution for a single directed edge (Station A → Station B). However, there is no capability to explain the underlying historical services for a full multi-hop topological path atomically. Clients must currently make $N-1$ separate API calls to the Phase 3 endpoint for a path of length $N$. This is inefficient, lacks atomicity, and forces the client to manage snapshot coordination across multiple network requests.

## 3. Why This Phase Follows Phase 3
This phase is the strongest logical next step because it composes the primitives exactly as they were built in Phase 2C and Phase 3. Phase 3 successfully isolated service-edge occurrences and established a rigid boundary between topological explanation and passenger routing. Phase 4 simply composes Phase 3's attribution over the multi-edge outputs of Phase 2C, completing the core historical graph intelligence suite before any future domain shifts (such as live data, dynamic calendars, or pricing).

## 4. Existing Capabilities Reused
- `RailwayNetworkEdge` (for path validation)
- `RailwayServiceEdge` (for physical occurrences)
- `Train` and `TrainObservation` (for canonical train identity)
- Snapshot isolation helpers
- The 500-result API limit established in Phase 3

## 5. Explicit Scope
- Given an ordered sequence of canonical station codes representing a topological path, return the service attribution for each contiguous segment in the path.
- Validate that the path exists in the active `RailwayNetworkEdge` topology.
- Apply a deterministic limit (e.g., 500) per segment to bound response size.
- Maintain strict snapshot isolation.

## 6. Explicit Non-Scope
- **Passenger Routing**: This is NOT passenger routing. It does not validate transfer buffers, time progression between segments, or calendar operating days.
- **Path Discovery**: It does not find paths (Phase 2C does that). It only attributes a provided path.
- **Live Tracking / Fares / Seats**: Excluded entirely.
- **Graph Database Migration**: Remains 100% PostgreSQL.

## 7. Domain Model Impact
No new domain entities are required. The existing canonical `Station`, `Train`, `TrainObservation`, `RailwayServiceEdge`, and `RailwayNetworkEdge` entities are fully sufficient. Creating a new entity for a "Path Segment" would violate normalization and snapshot provenance, as a segment is merely a query-time aggregation of existing edges.

## 8. Data / Query Model
For a provided path (e.g., A → B → C → D), there are 3 segments: (A,B), (B,C), (C,D).
The query must fetch occurrences for these segments and apply a `LIMIT 500` *per segment*.

**Query Strategy:**
A single PostgreSQL query using a window function (`ROW_NUMBER() OVER (PARTITION BY from_station_id, to_station_id)`) to enforce the top-N limit per segment.

**Tables & Joins:**
- `railway_service_edges` (e)
- `trains` (t) ON `e.train_id = t.id`
- `train_observations` (to) ON `to.train_id = t.id AND to.snapshot_id = :snapshot_id`

**Expected Cardinality & Worst-Case:**
Maximum path length from Phase 2C is 10 hops (9 segments).
At 500 occurrences per segment, the maximum possible result size is $9 \times 500 = 4,500$ rows. PostgreSQL handles sorting and filtering 4,500 rows in milliseconds. This is absolutely safe and bounded.

## 9. Snapshot / Provenance Semantics
The entire query must be strictly filtered by the currently `ACTIVE` timetable snapshot. Both `RailwayServiceEdge.timetable_snapshot_id` and `TrainObservation.snapshot_id` must match the active snapshot. The graph build must be `ACTIVE`.

## 10. Proposed Service-Layer Responsibilities
- Validate the maximum path length (e.g., max 10 stations).
- Resolve canonical station codes to IDs using the active station snapshot.
- Verify that every contiguous segment in the provided path exists in `RailwayNetworkEdge`.
- Execute the window-function query to fetch service occurrences.
- Assemble the response into a structured list of segments.

## 11. Proposed API Surface
**Endpoint:** `GET /api/v1/network/path/attribution`
**HTTP Method:** GET

## 12. Request Parameters
| Name | Type | Location | Required | Default | Description |
|---|---|---|---|---|---|
| `path` | `string` | Query | Yes | - | Comma-separated canonical station codes (e.g., `NDLS,AGC,BPL`). Min 2 stations, Max 10 stations. |

## 13. Response Shape
```json
{
  "path": ["NDLS", "AGC", "BPL"],
  "timetable_snapshot_id": 2,
  "segments": [
    {
      "from_station": "NDLS",
      "to_station": "AGC",
      "occurrences_returned": 143,
      "occurrences": [
        {
          "train_number": "12137",
          "train_name": "PUNJAB MAIL",
          "train_type": "SF",
          "from_stop_sequence": 5,
          "to_stop_sequence": 6,
          "departure_time": "05:15",
          "arrival_time": "08:10",
          "duration_minutes": 175
        }
      ]
    },
    {
      "from_station": "AGC",
      "to_station": "BPL",
      "occurrences_returned": 85,
      "occurrences": [ ... ]
    }
  ]
}
```

## 14. Validation Rules
- `path` must contain at least 2 and at most 10 station codes.
- `path` cannot contain consecutive identical stations (A → A is invalid).

## 15. Error Semantics
- **422 Unprocessable Entity**: Invalid path format, path too long, or consecutive duplicates.
- **404 Not Found**: One or more station codes in the path do not exist.
- **400 Bad Request**: A segment in the requested path does not exist in the active network topology (invalid topological path).
- **503 Service Unavailable**: Active graph build is missing, `PENDING`, or `FAILED`.

## 16. Deterministic Ordering Rules
Occurrences within each segment must be strictly ordered identically to Phase 3:
1. `Train.number` ASC (lexicographical)
2. `RailwayServiceEdge.from_stop_sequence` ASC

## 17. Resource & Performance Considerations
The query executes entirely on PostgreSQL. No multi-query N+1 loops are permitted. The memory footprint in Python for 4,500 rows is trivial (< 10 MB). 

## 18. Query Strategy Detail
```sql
WITH RankedEdges AS (
  SELECT 
    e.from_station_id, e.to_station_id,
    t.number AS train_number,
    to.name AS train_name,
    e.from_stop_sequence, e.to_stop_sequence,
    e.departure_time, e.arrival_time, e.duration_minutes,
    ROW_NUMBER() OVER(
      PARTITION BY e.from_station_id, e.to_station_id 
      ORDER BY t.number ASC, e.from_stop_sequence ASC
    ) as rn
  FROM railway_service_edges e
  JOIN trains t ON e.train_id = t.id
  JOIN train_observations to ON to.train_id = t.id AND to.snapshot_id = :snapshot_id
  WHERE e.timetable_snapshot_id = :snapshot_id
    AND (e.from_station_id, e.to_station_id) IN ( (1, 2), (2, 3) )
)
SELECT * FROM RankedEdges WHERE rn <= 500;
```
This is fully capable of execution by PostgreSQL in a single pass.

## 19. Index Strategy
The query will heavily utilize the existing composite index established in Phase 1: `ix_service_edges_to_station("timetable_snapshot_id", "to_station_id")`. Because the tuples are explicitly provided, PostgreSQL will likely perform an Index Scan or Bitmap Heap Scan. No new index is justified without empirical `EXPLAIN ANALYZE` proof showing slow execution on the production dataset.

## 20. Benchmark Methodology
During implementation, Antigravity must measure:
1. **Normal Case**: A 3-hop path (e.g., NDLS → AGC → BPL).
2. **Worst Case**: A 9-hop path traversing the heaviest known edges.
3. Execute `EXPLAIN ANALYZE` on the worst-case window function query.
4. Measure end-to-end Python application execution time.

## 21. Test Strategy
Focused pytest cases must include:
- **Normal behavior**: Valid 3-station path returning correct segments.
- **Empty/Invalid Topology**: Querying a path where a segment does not exist (returns 400).
- **Unknown Stations**: Querying a path with a fake station code (returns 404).
- **Snapshot Isolation**: Ensure TrainObservations from old snapshots do not leak in.
- **Graph Build Isolation**: Returns 503 if graph build is not ACTIVE.
- **Repeated Train Occurrences**: Validate that if a train visits a segment twice, both occurrences appear (inherited from Phase 3 behavior).
- **Deterministic Ordering**: Verify the window function correctly sorts before limiting.
- **Resource Limits**: Ensure segments with >500 occurrences are strictly truncated at 500.

## 22. Security Considerations
- Parameterized SQL via SQLAlchemy is mandatory to prevent SQL injection in the `IN` clause.
- FastAPI strictly validates the maximum path length, preventing denial-of-service through massive window-function partitions.

## 23. ₹0 Constraint Validation
The solution is purely relational and scales securely within the existing PostgreSQL boundaries. There is no external cost.

## 24. Future Extension Points
This API enables frontends to immediately render full route service combinations. Future Machine Learning modules can call this internally to extract feature sets for corridor reliability analysis without re-writing SQL joins.

## 25. Historical Semantics Reminder
This capability provides historical/static graph attribution. It does not prove current railway operations, guarantee passenger transfers, or assert future operating days.

## 26. Risks and Unresolved Questions
- **Client Cacheability**: Given the deterministic historical nature of the data, the API response is highly cacheable. Implementing `Cache-Control` headers is deferred to a future performance pass.
- **Window Function Performance**: While expected to be fast, the window function must be empirically profiled on the heaviest multi-edge path to confirm sub-10ms performance.

## 27. Implementation Sequencing
1. Implement service logic leveraging SQLAlchemy `func.row_number()`.
2. Implement robust path topological validation against `RailwayNetworkEdge`.
3. Build the `/api/v1/network/path/attribution` router.
4. Execute benchmark suite and report.
