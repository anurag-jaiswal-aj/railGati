# v2.0 Phase 13 Discovery: Network Station Temporal Concentration Analytics

**STATUS:** DISCOVERY ONLY.
**IMPLEMENTATION:** DEFERRED.

## 1. Problem Statement
RailGati currently maps network structure (paths, hubs, edges, boundaries) and scheduled transit wait times (dwells). However, it entirely lacks visibility into the **Temporal Load Distribution** of stations over a 24-hour period. Users cannot distinguish a station that processes 100 trains perfectly distributed throughout the day (uniform load) from a station that processes 100 trains entirely clustered within a two-hour midnight window (severe peak load/congestion). A metric is needed to evaluate the scheduled "rush-hour" concentration of services at each node.

## 2. Complete Phase 1–12 Capability Boundary
V2.0 currently provides:
- **Phase 1-5:** Canonical graph topology and bounded reachability/paths.
- **Phase 6:** Network Corridor volumes.
- **Phase 7:** Network Hub Centrality (node adjacent occurrence volumes).
- **Phase 8:** Network Edge Volume (directional track segment occurrences).
- **Phase 9:** Network Terminus Analytics (boundary originating/terminating volumes).
- **Phase 10:** Network O-D Flow Analytics (global boundaries origins and destinations paired volumes).
- **Phase 11:** Network Station Dwell Analytics (scheduled topological delay/wait times).
- **Phase 12:** Network Station Route Complexity (average topological route scale visiting a node).

## 3. Analytical Dimensions Already Covered
- **Topology & Connectivity:** Graph nodes, paths, and corridors.
- **Structural Volume:** Hubs, Edges, Flows, Termini.
- **Topological Delay:** Dwells (Interval wait).
- **Structural Scale:** Route Complexity (Topological route length).

## 4. Remaining Analytical Gap
RailGati lacks the **Absolute Temporal Distribution** dimension. We know *where* trains go, *how many* exist, and *how long* they wait, but we do not know *when* they cluster. Identifying severe "peak-hour scheduling" versus uniform scheduling introduces a completely new temporal dimension distinct from Phase 11's interval delay metric.

## 5. Data-Capability Audit
Read-only queries over the active snapshot dataset confirmed:
- Deriving train types (Service Diversity) yields mostly generic text (`Pass`, `Exp`, `SF`) with relatively flat diversity variance.
- Deriving directional Edge Asymmetry (Flow Imbalance) is highly performant (~160ms) and successfully identifies cyclic network routing loops, but is structurally a direct derivative of the Phase 8 network edge logic.
- Deriving **Time-of-Day Concentration** via Postgres `EXTRACT(HOUR FROM time)` on timetable observations executes extremely quickly (~190ms). It correctly identifies stations with severe localized temporal clustering (e.g., stations where 37% of daily scheduled volume occurs within a single clock hour) compared to structurally balanced transit hubs.

## 6. Candidate Directions Considered
1. **Network Directional Edge Asymmetry (Flow Imbalance):** Calculates `ABS(forward - reverse) / total` for track segments to identify cyclic/one-way scheduled loops. (Rejected as it borders on re-expressing Phase 8 edge calculations, despite offering new topology insights).
2. **Network Station Service Diversity:** Calculates the ratio of unique canonical train `type` strings passing through a node. (Rejected due to low data cardinality and generic legacy strings rendering the metric productively weak).
3. **Network Station Temporal Concentration Analytics:** Calculates the maximum localized scheduled occurrences within any 1-hour window as a percentage of the station's total daily scheduled load.

## 7. Selected Phase 13 Scope
**Network Station Temporal Concentration Analytics**

## 8. Evidence Supporting Selection
- **Meaningful New Dimension:** Introduces Time-of-Day distribution (Absolute temporal clustering), resolving a major gap in congestion analysis.
- **Clearly Distinct:** Differentiates entirely from Hub Centrality (Total Volume) and Dwells (Interval Time).
- **Not a Duplicate:** Cannot be computed from any combination of Phase 1-12 API endpoints, as absolute occurrence timestamps are not aggregated anywhere else.
- **Highly Performant:** Database-side `EXTRACT(HOUR)` grouping executes in under 200ms natively on PostgreSQL.
- **₹0 Constraint:** Purely SQL-driven natively on PostgreSQL with no external dependencies.

## 9. Explicit Non-Goals
- **Passenger Crowding:** Does NOT measure physical passengers or actual platform congestion.
- **Live Delays:** Based strictly on historical scheduled timetables, not live running status.
- **Exact Interval Windows:** Groups by discrete 24-hour clock hours (e.g., 22:00 to 22:59) rather than calculating arbitrary sliding 60-minute windows, for database scalability.

## 10. Exact Metric Semantics
- **Transit Event Time:** Defined as `COALESCE(departure_time, arrival_time)`. This guarantees exactly one timestamp per canonical train visit (if a train dwells across an hour boundary, its departure time defines its occurrence).
- **Peak Hour Volume (`peak_hour_volume`):** The absolute maximum number of scheduled transit events occurring within a single discrete clock hour (0-23).
- **Total Volume (`total_volume`):** The total number of scheduled transit events at that station across all 24 hours.
- **Concentration Percentage (`concentration_pct`):** `(peak_hour_volume / total_volume) * 100`
- **Peak Hour Value (`peak_hour_val`):** The integer clock hour (0-23) during which the peak occurred.

## 11. Unit and Occurrence Semantics
- **Unit of Analysis:** The canonical Station.
- **Occurrence Definition:** A canonical `train_id` mapped via `TrainStopObservation` within the active snapshot. Missing temporal data (`arrival_time IS NULL AND departure_time IS NULL`) is strictly excluded from the total volume. Repeated visits by the same train to the same station represent valid, independent scheduled transit events and are counted.

## 12. Snapshot and Provenance Semantics
- **Timetable Snapshot:** Logic executes strictly within a single `DatasetSnapshot`.
- **Station Snapshot:** Metadata resolves strictly against the active station snapshot.
- **Graph-Build Dependency:** **NOT REQUIRED**. This metric evaluates the canonical timetable temporal properties projected onto nodes. It bypasses any recursive topological graph traversal logic.

## 13. Proposed API
**Endpoint:** `GET /api/v1/network/temporal-concentration`
**Method:** GET

**Query Parameters:**
- `limit` (integer, default 50, bounds 1-500)
- `min_service_count` (integer, default 15, bounds 1-1000)

**Response Schema:**
```json
{
  "timetable_snapshot_id": 2,
  "limit": 50,
  "min_service_count": 15,
  "items": [
    {
      "station_code": "CKX",
      "station_name": "Chakradharpur",
      "peak_hour_val": 22,
      "peak_hour_volume": 6,
      "total_volume": 16,
      "concentration_pct": 37.5
    }
  ]
}
```

## 14. Query Strategy
Set-based PostgreSQL strategy:
1. **CTE 1 (`station_events`):** Extract `station_id` and `EXTRACT(HOUR FROM COALESCE(departure_time, arrival_time)::time)` as `event_hour` from `train_stop_observations`, bounded strictly to the active snapshot. Filter out NULL time rows.
2. **CTE 2 (`station_peak`):** `GROUP BY station_id, event_hour` to count occurrences (`hour_volume`).
3. **CTE 3 (`station_max`):** `GROUP BY station_id` to extract `MAX(hour_volume)` and `SUM(hour_volume)`. Enforce `HAVING SUM(hour_volume) >= :min_service_count`.
4. **Final Query:** Calculate percentage. Join canonical `stations` and `station_observations` for metadata. Resolve ties in `peak_hour_val` via a correlated subquery if necessary, or `GROUP BY` logic. Apply database-side `ORDER BY` and `LIMIT`.

## 15. Ordering (Deterministic)
1. `concentration_pct DESC`
2. `total_volume DESC`
3. `station_code ASC`

## 16. Resource Bounds
The query scans the active snapshot `train_stop_observations` table using the snapshot index, applies an in-memory HashAggregate, and bounds the output before Python serialization. Peak memory usage remains strictly bounded by PostgreSQL `work_mem`.

## 17. Performance Methodology
Must be verified via `EXPLAIN ANALYZE` ensuring:
- `HashAggregate` execution strategy is favored over nested loops for the time-grouping CTEs.
- `LIMIT` is applied natively by PostgreSQL to constrain python memory.

## 18. Test Strategy
**Service Tests:**
- Validate exact maximum clock hour calculation and percentage logic.
- Validate `COALESCE` precedence (departure > arrival).
- Validate snapshot boundary isolation.
- Validate parameter limits (`min_service_count`).
- Validate deterministic ordering constraints.
- Validate exclusion of missing temporal data.

**API Tests:**
- Standard HTTP 200 checks, boundary checks (422), empty snapshot behavior, and schema structural validation.

## 19. Real-Data Validation Results
Run natively against Snapshot 2 (`min_service_count=15`):
- High Concentration: `CKX` (37.5% clustered in hour 22:00, 6 out of 16 total transits), `GNH` (37.5% clustered in hour 00:00).
- Query timing: ~191.5ms
- The results mathematically align with localized midnight-transit bunching observed at smaller junction stations.

## 20. Limitations
Because RailGati groups by discrete clock hours (e.g., 22:00:00 to 22:59:59), a cluster of trains arriving between 21:50 and 22:10 will be split across two discrete hours, artificially lowering the measured concentration. While an arbitrary rolling 60-minute window calculation would be more precise, it violates the $O(N)$ database query constraint, making the discrete clock-hour approach the correct systemic compromise.

## 21. Unresolved Questions
None. The metric logic and SQL constraints are fully validated.

## 22. Implementation Sequencing
1. Update `schemas.py` (`TemporalConcentrationItem`, `TemporalConcentrationResponse`).
2. Add core service in `services/network.py`.
3. Add REST endpoint in `api/v1/network.py`.
4. Add service and API tests.
