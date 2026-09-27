# v2.0 Phase 10 Discovery: Network O-D Flow Analytics

**STATUS:** DISCOVERY ONLY.
**IMPLEMENTATION:** DEFERRED.

## 1. Problem Statement
RailGati currently provides detailed local graph attributes (Hub Centrality, Edge Volumes, Termini) and explicitly bounded paths (Corridors between a known origin and destination). However, the platform lacks a macroscopic view of the strongest origin-destination linkages across the entire network. Without specifying an exact pair to search, there is no way to discover which pairs of stations historically generate the highest volume of end-to-end train occurrences (Origin-Destination Flow Density). A global analytics capability is needed to expose the heaviest structural structural flows linking the network's extremities.

## 2. Existing Capability Boundary
- **Phase 6 (Network Corridors):** Finds distinct spatial paths between a *user-specified* origin and destination. It does not globally rank all O-D pairs.
- **Phase 7 (Hub Centrality):** Ranks individual nodes by total adjacent occurrence volume, blending transit and terminus traffic.
- **Phase 8 (Edge Volumes):** Ranks physical track segments (adjacent node pairs), not end-to-end journey bounds.
- **Phase 9 (Terminus Analytics):** Ranks individual nodes by their absolute origination or termination boundary counts, but does not pair them together.

Phase 10 bridges the gap by globally ranking pairs of absolute termini (Origin to Destination).

## 3. Candidate Directions Evaluated
1. **Network Route Diversity Analytics (Multipath Centrality):** Ranking station pairs by the sheer number of unique physical corridors connecting them. *Rejected:* Computationally expensive to resolve all simple paths globally without a strict depth limit.
2. **Historical Train Topology Analytics (Longest Trains):** Ranking individual trains by their topological stop counts or duration. *Rejected:* Train-centric rather than spatial network-centric, deviating from the macroscopic structural intelligence theme.
3. **Network O-D Flow Analytics (Flow Density):** Grouping historical train occurrences by their absolute start station and absolute end station, creating a global ranking of Origin-Destination linkage volumes. *Selected.*

## 4. Candidate Analysis & Selection
**Selected Scope: Network O-D Flow Analytics**
- **Meaningful New Capability:** Provides a global map of the strongest end-to-end service corridors.
- **Strong Data Support:** Utilizes `TrainStopObservation` sequence boundaries directly.
- **Minimal Assumptions:** No passenger, capacity, or live traffic assumptions required.
- **Limited Overlap:** Unifies the boundary concepts of Phase 9 with the directional pairing concepts of Phase 6 without duplicating either.
- **Reasonable Implementation:** Benchmark queries demonstrate PostgreSQL can resolve global bounds across 417,000+ stop observations using Parallel HashAggregates in <100ms.
- **₹0 Constraint:** Purely SQL-driven; requires no external services, graph databases, or memory-heavy Python processing.

## 5. Explicit Non-Goals
- **Live Flow:** Does not track current train positions, active routes, or live schedules.
- **Passenger Flow:** Does not represent passenger travel demand, ticketing origins/destinations, or crowds.
- **Transfers:** Does not account for journeys requiring transfers; this measures direct occurrence boundaries.
- **Route Tracking:** Does not specify *which* physical path (corridor) the flow takes, only the absolute endpoints.

## 6. Exact Metric Semantics
- **Origin-Destination Flow Volume (`flow_volume`):** The total number of historical train occurrences within a single active timetable snapshot that share the exact same originating station (minimum `stop_sequence`) and terminating station (maximum `stop_sequence`).
- A train occurrence contributes exactly +1 to its specific `(origin_station, destination_station)` pair.

## 7. Snapshot and Provenance Semantics
- **Timetable Snapshot:** Calculations are strictly bounded to the single active `DatasetSnapshot` resolving `TrainObservation` records.
- **Station Snapshot:** Station metadata resolves strictly against the active station snapshot.
- **Graph-Build Dependency:** **NOT REQUIRED**. O-D Flow Analytics is purely timetable-derived from sequence boundaries. It does not traverse `RailwayNetworkEdge` topology. The endpoint will operate successfully even if `RailwayGraphBuild` is inactive or missing.
- **Cross-Snapshot Leakage:** The derivation query must explicitly enforce `WHERE snapshot_id = :active_timetable_snapshot_id` during the `MIN/MAX` boundary calculation to prevent canonical `Train` entities from blending multi-snapshot observations.

## 8. Proposed API
**Endpoint:** `GET /api/v1/network/flows`
**Method:** GET

**Query Parameters:**
- `limit` (integer, default 50, min 1, max 500). (Output bound only).

**Sort Semantics (Deterministic):**
1. `flow_volume DESC`
2. `origin_station_code ASC`
3. `destination_station_code ASC`

**Response Structure:**
```json
{
  "timetable_snapshot_id": 2,
  "flows": [
    {
      "origin_station_code": "MSB",
      "origin_station_name": "Chennai Beach",
      "destination_station_code": "VLCY",
      "destination_station_name": "Velachery",
      "flow_volume": 70
    }
  ]
}
```

## 9. Query Strategy
The database strategy ensures efficient set-based execution:
1. Resolve the active timetable and station snapshot IDs.
2. Define a CTE (`train_bounds`) computing `MIN(stop_sequence)` and `MAX(stop_sequence)` per `train_id`, bounded strictly by the active timetable snapshot.
3. Define a CTE (`od_pairs`) joining `train_bounds` back to `train_stop_observations` twice (once for the origin stop, once for the destination stop) to resolve station IDs.
4. Aggregate `COUNT(train_id)` grouped by `(origin_id, destination_id)`.
5. `INNER JOIN` to canonical stations and active station observations for metadata.
6. Apply `ORDER BY` and `LIMIT` natively in PostgreSQL.

*Note: No Python-side aggregation or N+1 queries are permitted.*

## 10. Performance Methodology
The implementation must be validated using `EXPLAIN ANALYZE` on the active dataset.
Required captures:
- Planning and Execution time.
- Node joins (Merge/Hash).
- Sort strategy (Top-N heapsort).
- `TrainStopObservation` scan behavior.
Performance assertions must remain limited to the observed historical dataset size. No infinite scalability claims.

## 11. Test Strategy
**Service Tests:**
- Validate correct topological O-D pairing (Train A->B->C yields A->C flow +1).
- Validate empty timetable (returns empty list).
- Validate snapshot isolation (inactive snapshot data cannot bleed).
- Validate repeated loops (Train A->B->A yields A->A flow +1).
- Validate deterministic ordering and tie-breakers.

**API Tests:**
- Limit parameter bounds (default, valid explicit, 422 for invalid).
- Empty result correctly returns HTTP 200 with empty array.
- Missing active station metadata safely excludes the pair via INNER JOIN.
- Strict isolation of graph-build dependencies (must succeed without a graph).

## 12. Limitations & Future Extensions
- **Limitations:** Identifies absolute bounds only; does not expose the intermediate corridors traversed by the flow.
- **Future Extensions:** Time-bounded flows (e.g., O-D flows departing strictly in morning hours).

*(End of Discovery)*
