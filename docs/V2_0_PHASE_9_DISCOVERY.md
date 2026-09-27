# v2.0 Phase 9 Discovery: Network Terminus Analytics

**STATUS:** DISCOVERY ONLY.
**IMPLEMENTATION:** DEFERRED.

## 1. Problem Statement
RailGati currently possesses macroscopic network graph capabilities including Corridor Analytics (Phase 6), Node Hub Centrality (Phase 7), and Segment Edge Volume (Phase 8). Phase 7 Hub Centrality successfully identifies the busiest transit hubs by summing *all* adjacent service occurrences (both passing through and stopping). However, this fails to distinguish between heavy intermediate transit hubs and true structural **termini**—stations where historical train occurrences absolutely originate (source) or terminate (sink). Analytical systems need to identify the network's structural endpoints without conflating them with mere high-throughput intermediate nodes.

## 2. User / Product Purpose
To expose the historical stations that act as the primary structural sources and sinks of the active railway network. This provides intelligence on network generation and consumption points, isolating actual journey boundaries from simple transit topology.

## 3. Explicit Scope
- Create a new endpoint `GET /api/v1/network/termini` to return stations ranked by their historical terminus occurrence volume.
- Compute the absolute starting and ending stops for all continuous train occurrences in the active snapshot.
- Restrict logic strictly to the active `DatasetSnapshot`.
- Ensure strict ₹0 compatibility using pure PostgreSQL execution.

## 4. Explicit Non-Goals
- **Passenger Demand:** Terminus occurrences do not equate to passenger boarding or alighting volume.
- **Physical Capacity:** Does not infer the number of physical platforms, yard lines, or track capacity.
- **Live Operations:** Does not track current train cancellations, delays, or dynamic platform assignments.
- **Distinct Trains:** The metric tracks historical *occurrences*, not unique physical train sets.

## 5. Existing Models Reused
- `TrainStopObservation`
- `Station`
- `StationObservation`
- `RailwayGraphBuild` (used as a proxy for validating the network is fully active)
- `DatasetSnapshot`

## 6. Exact Metric Definitions
- **Originating Count (`originating_count`)**: The sum of continuous historical train occurrences where the station acts as the absolute minimum `stop_sequence` for that `train_id`.
- **Terminating Count (`terminating_count`)**: The sum of continuous historical train occurrences where the station acts as the absolute maximum `stop_sequence` for that `train_id`.
- **Total Terminus Volume (`total_terminus_volume`)**: `originating_count + terminating_count`.

## 7. Semantics and Provenance
- **Occurrence Semantics:** Each valid historical train occurrence defined in `train_stop_observations` contributes exactly +1 to its originating station and +1 to its terminating station.
- **Snapshot/Provenance:** Resolves strictly against the active timetable snapshot. Metadata resolves against the active station snapshot.
- **Graph-Build Dependency:** A successfully completed `ACTIVE` `RailwayGraphBuild` must exist for the timetable snapshot to ensure topological completeness.
- **Timing:** None. Entirely topological.
- **Missing Data:** Trains with fewer than 2 stops are structurally invalid and excluded.
- **Directionality:** A station can be both an origin and a destination for different services. They are counted independently and summed.

## 8. API Proposal
**Endpoint:** `GET /api/v1/network/termini`
**Method:** GET

**Query Parameters:**
- `limit` (integer, default 50, min 1, max 500)

**Sort Semantics (Deterministic):**
- `total_terminus_volume DESC`
- `originating_count DESC`
- `station_code ASC`

**Response Structure:**
```json
{
  "timetable_snapshot_id": 2,
  "termini": [
    {
      "station_code": "HWH",
      "station_name": "Howrah Junction",
      "originating_count": 136,
      "terminating_count": 127,
      "total_terminus_volume": 263
    }
  ]
}
```

## 9. Database / Query Strategy
The required aggregation must be pushed to PostgreSQL.
**Conceptual Query:**
1. Define a CTE `train_bounds` that groups `train_stop_observations` by `train_id` to find `MIN(stop_sequence)` and `MAX(stop_sequence)`.
2. Define a CTE `termini` that joins `train_bounds` back to `train_stop_observations` filtering only rows where the stop sequence equals the min or max bound.
3. Aggregate the results by `station_id` to compute `originating_count` and `terminating_count`.
4. Join to `stations` and active `station_observations` for canonical metadata.
5. Apply `ORDER BY` and `LIMIT`.

## 10. Performance Methodology
Performance MUST be measured via `EXPLAIN ANALYZE` during eventual implementation.
- The query will scan `train_stop_observations` twice (once for bounds, once for join).
- Expected bounds are ~100k-200k stop observations per snapshot.
- The planner should utilize HashAggregates and HashJoins.
- Limit must be resolved efficiently.
- If planning or execution time exceeds 250ms, a materialized view or `RailwayGraphBuild` pipeline modification may be required (deferred consideration).
- No unsupported "infinite scalability" claims should be made; performance is validated against the actual historical dataset size.

## 11. Test Strategy
- **Service Tests:** 
  - Validate metrics with manual dummy train observations (e.g. Train 1: A->B->C, Train 2: C->B).
  - Assert C gets 1 originating and 1 terminating. B gets 0 (it is purely intermediate).
  - Validate snapshot isolation (inactive snapshot trains are ignored).
  - Validate deterministic ordering constraints.
- **API Tests:**
  - Standard FastAPI request bounds (limit rules).
  - 503 response if no active graph build is present.
  - 200 empty response if network contains no trains.
- **Real-Data Validation:** Cross-reference the top 5 termini returned by the API directly against raw `train_stop_observations` in PostgreSQL.

## 12. Candidate Directions Evaluated
1. **Network Service Trajectory Analytics (Longest Trains):** Analyzes the continuous occurrences traveling the most topological nodes. While valuable, it is highly train-centric rather than station-centric.
2. **Network Terminus Analytics (Source/Sink Centrality):** Analyzes true endpoints of the network. Selected because it perfectly complements Phase 7 (Hub transit centrality) by establishing Hub Terminus centrality, relying entirely on existing stop sequence bounds without expensive recursive logic.
3. **Regional Network Component Analytics (Connected Subgraphs):** Attempts to find isolated rail networks (e.g., disconnected narrow gauge clusters). Rejected due to high implementation complexity (recursive CTEs) and significant performance risk for minimal ₹0 budget constraints.

## 13. Limitations & Future Extensions
- **Limitations:** Only measures static, historical timetable schedules. Terminus volume does not correlate with live operational frequency or depot maintenance capabilities.
- **Future Extensions:** Time-bounded terminus analytics (e.g., busiest termini during morning rush hours).

*(End of Discovery)*
