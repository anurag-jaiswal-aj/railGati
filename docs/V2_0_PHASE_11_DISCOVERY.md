# v2.0 Phase 11 Discovery: Network Station Dwell Analytics

**STATUS:** DISCOVERY ONLY.
**IMPLEMENTATION:** DEFERRED.

## 1. Problem Statement
RailGati provides extensive topological intelligence (hubs, edges, termini, corridors, flows) based on historical occurrence volumes and spatial boundaries. However, it currently lacks any analytics derived from the temporal (timing) characteristics of the network. There is no macroscopic visibility into where scheduled train services historically spend the most time waiting. A capability is needed to identify stations with the longest historical scheduled transit delays/congestion (average scheduled dwell time), introducing a new time-based analytical axis to the network intelligence platform.

## 2. Complete Current Capability Boundary
V2.0 currently provides:
- **Phase 1-5:** Graph construction, bounded reachability, bounded path discovery, service/path attribution, continuous historical service tracking, railway search, timetable discovery, and destination discovery.
- **Phase 6 (Corridors):** Explicit spatial paths between a queried O-D pair.
- **Phase 7 (Hub Centrality):** Node occurrence volume (topological in/out degree).
- **Phase 8 (Edge Volume):** Directed physical track segment occurrence volume.
- **Phase 9 (Termini):** Absolute starting/ending node occurrence bounds.
- **Phase 10 (O-D Flows):** Global structural bounds linking Origins to Destinations.

**Remaining Gap:** All previous analytics are purely *spatial* and *topological* count metrics. The temporal domain (scheduled wait time) remains completely unanalyzed.

## 3. Data-Capability Audit
An audit of the real dataset (`TrainStopObservation`) revealed:
- `arrival_time` and `departure_time` exist as strings.
- 121 cases of `departure_time` preceding `arrival_time` exist (representing classic midnight-crossing schedules).
- Dwell time can be cleanly derived using Postgres `EXTRACT(EPOCH FROM time::time)`.
- Global aggregation over 417,000+ stop observations completes in ~100ms.

## 4. Candidate Directions Evaluated
1. **Network Route Diversity Analytics:** Station pairs connected by the most diverse physical graph paths.
2. **Network Station Reachability Footprint:** Ranking stations by the distinct number of destinations reachable directly from them without a transfer.
3. **Network Station Dwell Analytics:** Ranking stations by their average scheduled historical wait (dwell) time across all passing transit occurrences.

## 5. Candidate Analysis & Selection
**Selected Scope: Network Station Dwell Analytics**
- **Meaningful New Capability:** Introduces temporal network analytics, distinct from all spatial count metrics.
- **Clearly Distinct:** Answers *how long* rather than *how many*.
- **Strong Data Support:** Utilizes `arrival_time` and `departure_time` directly from `TrainStopObservation`.
- **Reasonable Implementation:** Benchmark queries show Postgres natively parses and averages epochs across the entire network in < 100ms.
- **₹0 Constraint:** Purely SQL-driven; requires no caching, LLMs, or paid processing.

## 6. Explicit Non-Goals
- **Live Delays:** Does NOT measure current train delays, active congestion, or real-time waiting logic.
- **Passenger Wait Time:** Does NOT measure how long passengers wait for tickets or trains.
- **Physical Capacity:** Does NOT claim a station lacks physical platform capacity.
- **Absolute Termini:** Dwell time at an absolute origin or destination is semantically meaningless (0 or infinite) and is explicitly excluded from this transit metric.

## 7. Exact Metric Semantics
- **Average Dwell Minutes (`avg_dwell_minutes`):** The historical scheduled difference between `departure_time` and `arrival_time` for transit stops, averaged across all valid occurrences at a station in the active snapshot.
- **Transit Count (`transit_count`):** The number of valid transit observations contributing to the average.
- **Midnight Crossings:** If a scheduled departure time precedes the arrival time, a 24-hour (86400s) adjustment is automatically applied.

## 8. Snapshot and Provenance Semantics
- **Timetable Snapshot:** Timings are resolved strictly from observations bound to the single active `DatasetSnapshot`.
- **Station Snapshot:** Metadata resolves strictly against the active station snapshot.
- **Graph-Build Dependency:** **NOT REQUIRED**. Dwell analytics are timetable-derived from node-specific timing fields. `RailwayGraphBuild` is entirely unnecessary.
- **Cross-Snapshot Contamination:** Explicitly prevented by `WHERE snapshot_id = :timetable_snapshot_id`.

## 9. Proposed API
**Endpoint:** `GET /api/v1/network/dwells`
**Method:** GET

**Query Parameters:**
- `limit` (int, default 50, bounds 1-500)
- `min_transit_count` (int, default 10, bounds 1-1000) -> Ensures statistical relevance (e.g. ignoring a station with 1 extremely long wait).

**Response Schema:**
```json
{
  "timetable_snapshot_id": 2,
  "dwells": [
    {
      "station_code": "NDLS",
      "station_name": "New Delhi",
      "avg_dwell_minutes": 28.1,
      "transit_count": 69
    }
  ]
}
```

## 10. Query Strategy
Set-based PostgreSQL strategy:
1. `SELECT` from `train_stop_observations` bound to the active timetable snapshot.
2. Filter for non-null, non-'None' arrival and departure times where arrival != departure.
3. Compute dwell using `EXTRACT(EPOCH)` and a `CASE` statement for midnight crossings (+86400).
4. `GROUP BY station_id`.
5. Apply `HAVING COUNT(train_id) >= :min_transit_count`.
6. `INNER JOIN` against active station observations for metadata.
7. DB-side `ORDER BY` and `LIMIT`.

## 11. Ordering (Deterministic)
1. `avg_dwell_minutes DESC`
2. `transit_count DESC`
3. `station_code ASC`

## 12. Resource Bounds
The query executes entirely on the database side, returning only the requested `limit` to Python memory. No intermediate materialization or N+1 queries are required.

## 13. Performance Methodology
Must be verified using `EXPLAIN ANALYZE`. Record:
- Total execution time.
- Join strategy (e.g., Hash Join).
- Aggregate strategy (HashAggregate).
- `TrainStopObservation` filtering speed.

## 14. Test Strategy
**Service Tests:**
- Validate correct epoch math (e.g., 10:00 to 10:15 yields 15.0).
- Validate midnight crossing (e.g., 23:50 to 00:10 yields 20.0).
- Validate snapshot isolation.
- Validate `min_transit_count` filtering.
- Validate deterministic ordering.

**API Tests:**
- Validate limits (default, explicit, 422 for invalid).
- Validate empty timetable behavior (empty response, not 503).
- Validate graph-build absence tolerance.

## 15. Limitations
This metric only accounts for scheduled dwell time. Stations with extremely high un-scheduled congestion (live delays) will not be reflected in this static/historical metric.

## 16. Unresolved Questions
None block implementation. The discovery effectively isolated the temporal parsing logic required.

## 17. Implementation Sequencing
1. Update `schemas.py` (`DwellItem`, `DwellResponse`).
2. Add service logic in `services/network.py`.
3. Expose via `api/v1/network.py`.
4. Implement API and Service tests.
