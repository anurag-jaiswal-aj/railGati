# v2.0 Phase 12 Discovery: Network Station Route Complexity Analytics

**STATUS:** DISCOVERY ONLY.
**IMPLEMENTATION:** DEFERRED.

## 1. Problem Statement
RailGati provides deep insights into the structural volumes (hubs, edges, flows, termini) and scheduled delays (dwells) across the railway network. However, it completely lacks visibility into the *topological nature* of the services operating through those nodes. Users cannot differentiate a station that serves 100 localized 5-stop commuter shuttles from a station that serves 100 trans-continental 150-stop express trains. A metric is required to evaluate the average structural complexity (route length) of the network services that visit each station.

## 2. Complete Phase 1–11 Capability Boundary
V2.0 currently provides:
- **Phase 1-5:** Canonical graph/path logic.
- **Phase 6:** Network Corridor Analytics (path occurrence volumes).
- **Phase 7:** Network Hub Centrality (node adjacent occurrence volumes).
- **Phase 8:** Network Edge Volume (adjacent node-to-node track segment occurrence volumes).
- **Phase 9:** Network Terminus Analytics (absolute starting/ending occurrence volumes).
- **Phase 10:** Network O-D Flow Analytics (global ranking of historical origin-destination boundary volumes).
- **Phase 11:** Network Station Dwell Analytics (historical scheduled transit wait times).

## 3. Current Analytical Dimensions Covered
- **Topology:** Static graph layout (Phases 1, 2)
- **Path Structure:** Continuous path identification (Phases 3, 4, 5, 6)
- **Occurrence Volume:** Nodes (7, 9), Edges (8), and O-D Bounds (10).
- **Temporal:** Scheduled delay/wait density (11).

## 4. Remaining Analytical Gap
RailGati lacks the ability to analyze **Service Complexity/Coverage Asymmetry**. We know *how many* trains visit a station and *how long* they wait, but we do not know the *scale* of those trains (are they local shuttles or structural network backbones?).

## 5. Data-Capability Audit
Read-only queries over the active snapshot dataset confirmed:
- Computing the global out-degree reachability footprint of stations takes ~6–11 seconds (too computationally heavy for a rapid REST API without materialization).
- Deriving train velocity is impossible as `distance_km` is not universally populated or present in the current schema.
- **Breakthrough:** Deriving the canonical route length (total scheduled stops) for every train, and projecting that average onto every visited station executes in **< 100ms** using PostgreSQL set-based Hash Aggregation.
- The results clearly differentiate commuter-centric nodes (e.g., Darjeeling [DJ] with ~4.9 avg route stops) from massive structural hubs (e.g., Guntakal [GUL] with ~475 avg route stops).

## 6. Candidate Directions Considered
1. **Network Station Reachability Footprint:** (How many unique destinations can a station reach directly). Rejected due to high $O(N^2)$ execution latency (~6-11s).
2. **Network Route Duration Span:** (Top trains by total scheduled duration hours). Rejected as purely train-centric rather than network-centric.
3. **Network Station Route Complexity Analytics:** (Average length of routes traversing a given node).

## 7. Selected Phase 12 Scope
**Network Station Route Complexity Analytics**

## 8. Evidence Supporting Selection
- **Meaningful New Dimension:** Moves beyond "volume" and "time" to measure the topological *weight/scale* of a station's connections.
- **Clearly Distinct:** Differentiates from Hub Centrality. A hub may have high volume but low route complexity (a major suburban metro hub), while a minor rural station may have low volume but high route complexity (only visited by a daily trans-continental train).
- **Highly Performant:** Database-side grouping executes in ~90ms.
- **₹0 Constraint:** Purely SQL-driven natively on PostgreSQL.

## 9. Explicit Non-Goals
- **Passenger Journey Length:** Does NOT measure how far passengers actually travel.
- **Physical Distance:** Measures topological stops, NOT physical kilometers/miles.
- **Live Train Routes:** Based entirely on historical scheduled timetable boundaries, not live detours or diversions.

## 10. Exact Metric Semantics
- **Average Route Stops (`avg_route_stops`):** The average scheduled topological length (total count of stops) of all canonical train occurrences that visit this station within the active snapshot.
- **Service Count (`service_count`):** The number of unique train occurrences passing through the station (contextualizes the average).

## 11. Unit and Occurrence Semantics
- **Unit of Analysis:** The canonical Station.
- **Occurrence Definition:** A canonical `train_id`'s total route stops (from `MIN(stop_sequence)` to `MAX(stop_sequence)`) is mapped to every station it visits.

## 12. Snapshot and Provenance Semantics
- **Timetable Snapshot:** Logic executes strictly within a single `DatasetSnapshot`.
- **Station Snapshot:** Metadata resolves strictly against the active station snapshot.
- **Graph-Build Dependency:** **NOT REQUIRED**. This metric evaluates the canonical timetable structure projected onto nodes. It bypasses any recursive graph traversal logic.

## 13. Proposed API
**Endpoint:** `GET /api/v1/network/complexities`
**Method:** GET

**Query Parameters:**
- `limit` (integer, default 50, bounds 1-500)
- `min_service_count` (integer, default 10, bounds 1-1000)

**Response Schema:**
```json
{
  "timetable_snapshot_id": 2,
  "limit": 50,
  "min_service_count": 10,
  "items": [
    {
      "station_code": "DJ",
      "station_name": "Darjeeling",
      "avg_route_stops": 4.9,
      "service_count": 13
    }
  ]
}
```

## 14. Query Strategy
Set-based PostgreSQL strategy:
1. **CTE 1 (`train_lengths`):** Group `train_stop_observations` by `train_id` (filtered by snapshot) to `COUNT(*)` as `total_stops`.
2. **CTE 2 (`station_avg`):** Join `train_stop_observations` to `train_lengths` on `train_id`. `GROUP BY station_id`. Compute `AVG(total_stops)` and `COUNT(train_id)`. Filter via `HAVING COUNT(train_id) >= :min_service_count`.
3. **Final Query:** Join canonical `stations` and `station_observations`. Apply database-side `ORDER BY` and `LIMIT`.

## 15. Ordering (Deterministic)
1. `avg_route_stops DESC`
2. `service_count DESC`
3. `station_code ASC`

## 16. Resource Bounds
The query requires reading the timetable snapshot entirely into a hash table in Postgres memory (typically < 3MB). Sorting and aggregation occur prior to LIMIT, meaning only the requested subset is serialized across the network to Python.

## 17. Performance Methodology
Must be verified via `EXPLAIN ANALYZE` ensuring:
- `HashAggregate` is favored over nested loops for the initial `train_lengths` CTE.
- Memory thresholds remain within `work_mem` bounds.

## 18. Test Strategy
**Service Tests:**
- Validate exact mathematical average (e.g., Station X visited by a 10-stop train and 20-stop train yields 15.0).
- Validate snapshot boundary isolation.
- Validate parameter limits (`min_service_count`).
- Validate deterministic ordering constraints.

**API Tests:**
- Standard HTTP 200 checks, boundary checks (422), empty snapshot behavior, and schema structural validation.

## 19. Real-Data Validation Results
Run natively against Snapshot 2 (`min_service_count=10`):
- High Complexity: `WAT` (499.2 avg stops, 15 services), `GUL` (475.0 avg stops, 32 services)
- Low Complexity (Local Shuttles): `RJL` (2.3 avg stops, 11 services), `DJ` (Darjeeling, 4.9 avg stops, 13 services)
- Query timing: ~90.7ms
- The results mathematically align with known localized railway networks (e.g., Darjeeling Himalayan Railway).

## 20. Limitations
Because RailGati normalizes loops and return-services, trains with cyclical return numbers may exhibit inflated stop counts (e.g., if Train 15905 represents a merged round-trip, its stop count incorporates both legs). However, this reflects the canonical timetable presentation accurately.

## 21. Unresolved Questions
None. The metric logic and SQL constraints are fully validated.

## 22. Implementation Sequencing
1. Update `schemas.py` (`ComplexityItem`, `ComplexityResponse`).
2. Add core service in `services/network.py`.
3. Add REST endpoint in `api/v1/network.py`.
4. Add service and API tests.
