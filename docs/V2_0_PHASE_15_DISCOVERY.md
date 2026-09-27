# V2.0 PHASE 15 DISCOVERY: Train Route Similarity Analytics

**DISCOVERY ONLY — NO PRODUCTION IMPLEMENTATION.**

## 1. Problem Statement
The V2.0 Network Analytics suite has thoroughly modeled graph topology, network flows, and station characteristics. However, it lacks a mechanism to structurally compare historical train services against each other. When a user asks, "Which historical services provide identical or highly overlapping topological coverage to this specific train?", existing capabilities can only answer fragmentarily (e.g., querying paths or checking corridors). We need a definitive mathematical metric of structural topological overlap between scheduled train occurrences.

## 2. Phase 1–14 Capability Boundary
Current V2.0 phases cover:
- **Phase 1**: Graph construction
- **Phase 2-3**: Reachability and bounded paths
- **Phase 4-5**: Service attribution and continuity
- **Phase 6**: Corridors (shared consecutive sequences)
- **Phase 7**: Hub Centrality (station degree)
- **Phase 8**: Edge Volume (train count density)
- **Phase 9**: Network Termini
- **Phase 10**: Origin-Destination Flows
- **Phase 11**: Station Scheduled Dwell Analytics
- **Phase 12**: Station Route Complexity
- **Phase 13**: Station Temporal Concentration
- **Phase 14**: Directional Edge Asymmetry

## 3. Analytical Coverage Audit
- **Topology**: Well-covered (reachability, paths, hubs).
- **Volume**: Well-covered (edges, nodes, O-D flows).
- **Temporal**: Partially covered (dwell, concentration).
- **Directionality**: Covered (asymmetry).
- **Service Structure Comparison**: **Absent**. No feature computes holistic similarity or redundancy between distinct scheduled train occurrences.

## 4. Remaining Product/Analytical Gap
There is no direct analytical way to discover topological overlap at a macro-service level. Users cannot automatically identify pairs of structurally twin trains without manually comparing their stop lists.

## 5. Data-Capability Audit
The database accurately maps canonical `Train` entities to `Station` entities via `TrainStopObservation` bounded by `TrainObservation` within specific snapshots.
This data cleanly supports topological intersection operations. A standard Jaccard Similarity index (Intersection over Union) between the station sets of two trains natively evaluates structural overlap.

## 6. Candidate Directions
1. **Scheduled Service Gaps**: Maximum interval (in minutes) between consecutive trains at a station.
2. **Edge Transit Duration**: Average scheduled transit time between adjacent stations.
3. **Station Outward Reach**: Distinct terminal destinations accessible directly from a station.
4. **Train Route Similarity**: Structural overlap of scheduled station visits between services (Jaccard Index).

## 7. Candidate Comparison

| Dimension | Scheduled Service Gaps | Edge Transit Duration | Train Route Similarity |
| :--- | :--- | :--- | :--- |
| **Product Question** | Which stations experience the longest breaks in service? | Which segments are historically the slowest? | Which services share historical timetable route-set similarity? |
| **Data Required** | `TrainStopObservation.departure_time` | `TrainStopObservation` arrival/departure | `TrainStopObservation.station_id` |
| **Data Compatibility** | Poor (times stored as `String`) | Poor (times stored as `String`) | **Excellent** (pure relational foreign keys) |
| **Graph Dependency** | None | Edges | None |
| **Distinction** | Temporal addition | Temporal addition | Structural comparison addition |
| **₹0 Feasibility** | Complex string parsing | Complex string parsing | **High** (Native PostgreSQL set operations) |

## 8. Rejected Candidates
- **Scheduled Service Gaps & Edge Transit Duration**: Both were rejected because `arrival_time` and `departure_time` are stored as `String(20)` rather than native PostgreSQL `TIME` types. Performing complex gap calculations across midnight boundaries on strings using SQLite/PostgreSQL compliant queries would require heavy database-side casting, regex, and condition handling that harms performance and violates elegant set-based query principles.
- **Station Outward Reach**: Largely redundant with Phase 6 Corridors and Phase 7 Hubs.

## 9. Selected Phase 15 Scope
**Train Route Similarity (Jaccard Index Analytics)**

Provide a network endpoint that, given a target railway train number, calculates the historical timetable route-set similarity (Jaccard Index) against all other scheduled trains in the active timetable snapshot.

## 10. Evidence Supporting Selection
Read-only exploration against the current dataset measured execution at approximately 32ms. It efficiently identifies trains with historically similar station-set topologies, such as reverse-direction services or physically overlapping route segments, using standard set-theoretic operations.

## 11. Exact Metric Semantics
The metric computes the topological station-set overlap between a target train $T$ and a compared train $O$:
$$ Jaccard = \frac{| Stations(T) \cap Stations(O) |}{| Stations(T) \cup Stations(O) |} \times 100 $$
Expressed strictly as a percentage rounded to one decimal place.

**CRITICAL SEMANTIC BOUNDARIES**:
This is strictly a TOPOLOGICAL STATION-SET similarity metric. It intentionally ignores:
- Stop sequence / order
- Travel direction
- Arrival and departure times
- Calendar dates
- Service timing or operational interchangeability

As a mathematical property of this metric, routes `A -> B -> C` and `C -> B -> A` produce identical station sets and yield identical Jaccard similarity (100% if sets match perfectly). High similarity scores merely identify mathematically overlapping sets, they do NOT imply equivalent, replacement, alternative, or parallel operational services.

## 12. Unit of Analysis and Identifier Semantics
- **Target Identifier**: The public API will use the railway `train_number` (e.g., `GET /api/v1/network/trains/{train_number}/similar`). This perfectly aligns with existing V1 endpoints (e.g., `GET /api/v1/trains/{train_number}`). Internal `train_id` integers are explicitly shielded from the API path.
- **Missing Train Behavior**: If the `train_number` does not exist in the active timetable snapshot, the API must return an HTTP 404 Not Found, matching existing conventions.
- **Entity**: The comparison occurs between canonical `Train` entities, strictly mapped through `TrainObservation` records resolving to the active timetable snapshot.

## 13. Occurrence Semantics
- The presence of a `TrainStopObservation` binds a train to a station within the snapshot.
- **Repeated Station Visits**: If a train visits the same station multiple times (e.g., a looping journey), these visits must mathematically collapse into a single distinct station ID. Jaccard similarity measures the distinct set of stations. Raw stop-row counts are NOT used for Jaccard counting.

## 14. Jaccard Edge Cases and Self-Match Behavior
- **Self-Match**: Excluded. The target train must NOT be compared against itself (`target_train_id != compared_train_id`).
- **Zero Overlap**: A compared train with zero shared stations evaluates to 0.0%. However, these are excluded by the default `min_overlap_stations` filter.
- **Empty Station Set**: If a train theoretically lacks `TrainStopObservation` records, its station set is zero. Division by zero in the Jaccard formula must be safely caught and mapped to 0.0%.
- **Reverse Station Sequence**: Evaluates identically to the forward sequence if the distinct station sets are identical.
- **Duplicate TrainObservations**: Structurally prevented by `(snapshot_id, train_id)` primary keys.

## 15. Return-Train / Metadata Semantics
The `TrainObservation.return_train_number` field provides metadata about associated return journeys.
- **Weighting**: The similarity calculation completely IGNORES `return_train_number`. No artificial weighting is applied. High similarity for reverse routes emerges naturally from the pure mathematical Jaccard overlap.
- **Exposure**: The field will be exposed in the response payload for informational purposes, maintaining parity with existing search schemas.

## 16. Snapshot/Provenance Semantics
- **Timetable Bound**: The query strictly resolves and enforces the active timetable snapshot ID exactly once.
- **Metadata**: Target train, compared trains, and stop observations must universally belong to this identical snapshot.
- **Graph-Build Dependency**: **None.** This metric evaluates set overlap directly via `TrainStopObservation`. It does not evaluate sequential graph connectivity. Therefore, it does not require an active `RailwayGraphBuild` or `RailwayNetworkEdge` records.

## 17. Proposed API
**GET /api/v1/network/trains/{train_number}/similar**

**Parameters:**
- `limit` (int): minimum 1, maximum 50, default 10.
- `min_overlap_stations` (int): minimum 1, default 1. (Candidates with 0 overlap are entirely excluded).

**Response Envelope:**
```json
{
  "timetable_snapshot_id": 2,
  "target_train_number": "12345",
  "target_train_name": "Example Express",
  "target_station_count": 185,
  "limit": 10,
  "min_overlap_stations": 1,
  "items": [
    {
      "train_number": "04727",
      "train_name": "Example Return",
      "train_type": "EXP",
      "return_train_number": "12345",
      "overlap_station_count": 184,
      "compared_station_count": 185,
      "union_station_count": 186,
      "similarity_pct": 98.9
    }
  ]
}
```

## 18. Query Strategy
Set-based PostgreSQL CTE approach avoiding Cartesian many-to-many joins:
1. `target_stations`: Select `DISTINCT station_id` for the target train ID.
2. `other_trains`: Select `train_id`, `COUNT(DISTINCT station_id)` for all other trains in the snapshot.
3. `intersection`: Join `train_stop_observations` against `target_stations` and aggregate `COUNT(DISTINCT tso.station_id)` as `intersection_count`.
4. `computation`: Derive `union_count` mathematically: `(target_station_count + compared_station_count - intersection_count)`.
5. Calculate `similarity_pct`: `ROUND(CAST(intersection_count AS FLOAT) / CAST(union_count AS FLOAT) * 100.0, 1)`.
6. Join to `Train` and `TrainObservation` to attach public `train_number` and metadata.

## 19. Ordering
Strictly deterministic sorting enforced on the database side:
1. `similarity_pct DESC`
2. `overlap_station_count DESC`
3. `union_station_count ASC`
4. `train_number ASC`

## 20. Performance Methodology
- Verify query execution using `EXPLAIN (ANALYZE, BUFFERS)` on the local dataset.
- Exploratory execution on the current local dataset measured approximately 32ms.
- Ensure Planner utilizes `HashAggregate` and avoids N+1 Python loops.
- Confirm that database-side `LIMIT` safely bounds the resulting top-N sort.

## 21. Limitations and Non-Goals
- **Non-Directional**: Identifies station sets independent of order. `A->B->C` is 100% similar to `C->B->A`.
- **Non-Temporal**: Evaluates static timetable topology; a 100% overlapping train might operate at entirely different times of day.
- **No Operational Substitutability**: We are NOT claiming passenger tickets can be transferred, that trains act as operational replacements, or that they run concurrently.
- **No Live Assertions**: We do NOT model live track sharing, physical congestion, or passenger demand.

## 22. Unresolved Questions
None remaining. The API identifier, set-based Jaccard logic, snapshot isolation, and deterministic ordering have been firmly established.

## 23. Implementation Sequencing
1. Implement `TrainSimilarityItem` and `TrainSimilarityResponse` schemas in `schemas.py`.
2. Implement `calculate_train_similarity` in `services/network.py`.
3. Implement `GET /api/v1/network/trains/{train_number}/similar` in `api/v1/network.py`.
4. Add service tests verifying distinct sets, self-exclusion, and sorting rules.
5. Add API tests verifying parameter bounds (422) and missing train states (404/503).
6. Validate via `EXPLAIN ANALYZE`.
