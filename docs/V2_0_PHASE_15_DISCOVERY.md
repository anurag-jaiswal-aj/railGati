# V2.0 PHASE 15 DISCOVERY: Train Route Similarity Analytics

**DISCOVERY ONLY — NO PRODUCTION IMPLEMENTATION.**

## 1. Problem Statement
The V2.0 Network Analytics suite has thoroughly modeled graph topology, network flows, and station characteristics. However, it lacks a mechanism to structurally compare historical train services against each other. When a user asks, "Which historical services provide identical or highly parallel topological coverage to this specific train?", existing capabilities can only answer fragmentarily (e.g., querying paths or checking corridors). We need a definitive mathematical metric of structural topological overlap between scheduled train occurrences.

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
There is no direct analytical way to discover topological redundancy or operational alternatives at a macro-service level. Users cannot automatically identify pairs of structurally twin trains (e.g., return journeys or parallel services run by different operators) without manually comparing their stop lists.

## 5. Data-Capability Audit
The database accurately maps `Train` to `Station` occurrences via `TrainStopObservation`.
This data cleanly supports topological intersection operations. A standard Jaccard Similarity index (Intersection over Union) between the station sets of two trains can natively describe structural overlap without requiring time-parsing or assumptions about passenger behavior.

## 6. Candidate Directions
1. **Scheduled Service Gaps**: Maximum interval (in minutes) between consecutive trains at a station.
2. **Edge Transit Duration**: Average scheduled transit time between adjacent stations.
3. **Station Outward Reach**: Distinct terminal destinations accessible directly from a station.
4. **Train Route Similarity**: Structural overlap of scheduled station visits between services (Jaccard Index).

## 7. Candidate Comparison

| Dimension | Scheduled Service Gaps | Edge Transit Duration | Train Route Similarity |
| :--- | :--- | :--- | :--- |
| **Product Question** | Which stations experience the longest breaks in service? | Which segments are historically the slowest? | Which services are structurally parallel? |
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

Provide a network endpoint that, given a target `train_id`, calculates the topological structural overlap (Jaccard Similarity) against all other scheduled trains in the active timetable snapshot.

## 10. Evidence Supporting Selection
Real-data exploration proved this metric is highly performant (~32ms execution time) and yields profoundly useful railway intelligence. It flawlessly identified exact return journeys (98.9% overlap) and structurally parallel trains (89% overlap) without requiring complex graph traversal or recursive pathfinding.

## 11. Exact Metric Semantics
The metric evaluates the topological station-set overlap between a target train $T$ and another train $O$:
$$ Jaccard = \frac{| stations(T) \cap stations(O) |}{| stations(T) \cup stations(O) |} \times 100 $$
Expressed strictly as a percentage from 0.0 to 100.0.

## 12. Unit of Analysis
The unit of analysis is the historical scheduled `Train` occurrence within an active snapshot.

## 13. Occurrence Semantics
- **Train-Stop Occurrence**: The presence of a `TrainStopObservation` binds a train to a station.
- **Set Semantics**: A station visited multiple times by the same train in a single journey (e.g., a loop) is counted natively as part of the union/intersection via distinct grouping if necessary, though typical schedules visit a station once per direction. The overlap evaluates the distinct set of stations.

## 14. Snapshot/Provenance Semantics
- The query strictly isolates `TrainStopObservation` rows to the **active timetable snapshot**.
- Requires the `get_active_timetable_snapshot_id()` helper.
- Cross-snapshot contamination is structurally prevented via `snapshot_id` bindings in the CTEs.

## 15. Graph-Build Dependency
**None.**
This metric evaluates topological set overlap via `TrainStopObservation`, not sequential connectivity. Therefore, it does not require an active `RailwayGraphBuild` or `RailwayNetworkEdge` records. It operates purely on the schedule matrix, ensuring robustness even if graph construction fails.

## 16. Proposed API
**GET /api/v1/network/trains/{train_id}/similar**

**Parameters:**
- `limit` (int): default=10, ge=1, le=50
- `min_overlap_stations` (int): default=1, ge=1

**Response Envelope:**
```json
{
  "timetable_snapshot_id": 2,
  "target_train_id": 5,
  "target_train_number": "12345",
  "target_total_stations": 185,
  "limit": 10,
  "min_overlap_stations": 1,
  "items": [
    {
      "train_id": 4932,
      "train_number": "04727",
      "overlap_stations": 184,
      "total_stations": 185,
      "similarity_pct": 98.9
    }
  ]
}
```

## 17. Query Strategy
Set-based PostgreSQL CTE approach:
1. `target_stations`: Select distinct `station_id` for the target train.
2. `other_trains`: Count total distinct stations for all other trains in the snapshot.
3. `intersection`: Join `train_stop_observations` against `target_stations` to count overlapping stations per train.
4. `SELECT`: Compute `ROUND(CAST(overlap AS FLOAT) / CAST(target_total + other_total - overlap AS FLOAT) * 100.0, 1)`.
5. Join to `trains` to fetch canonical numbers.

## 18. Ordering
Strictly deterministic sorting:
`ORDER BY similarity_pct DESC, overlap_count DESC, t.number ASC`

## 19. Resource/Output Bounds
- Bounded entirely to a single snapshot.
- Output bounded by database-side `LIMIT`.
- Input bounded by single `train_id`.

## 20. Performance Methodology
- Verify using `EXPLAIN ANALYZE`.
- Monitor execution time (target < 50ms).
- Ensure Planner utilizes `HashAggregate` and `Hash Join` over sequential scans where optimal, avoiding N+1 loops.
- Verify `Top-N heapsort` memory usage remains under 1MB.

## 21. Real-Data Exploration
Executed on Snapshot 2 local database against Train ID 5:
- **Train 04727**: overlap 184, total 185, similarity 98.9% (Return journey)
- **Train 14708**: overlap 183, total 202, similarity 89.7% (Parallel alternative)
- **Execution Time**: ~32ms.
- Confirmed that the metric effortlessly differentiates between highly overlapping routes and minor tangent intersections.

## 22. EXPLAIN Methodology
The captured plan proved highly efficient:
- Scanned 138,962 `train_stop_observations` via parallel Seq Scan (optimal for massive aggregations).
- Grouped intersections natively in ~7ms.
- Executed in 32ms total.
No new indexes are required.

## 23. Test Strategy
**Service Tests**:
- `test_calculate_train_similarity_perfect_match` (100% overlap)
- `test_calculate_train_similarity_partial` (50% overlap)
- `test_calculate_train_similarity_no_overlap` (0 overlap -> should not appear due to `min_overlap_stations`)
- `test_invalid_train_id` (ValueError)

**API Tests**:
- `test_get_similar_trains_success` (200 OK)
- `test_get_similar_trains_validation` (422 for limit < 1)
- `test_get_similar_trains_not_found` (404 for missing train)
- `test_get_similar_trains_no_snapshot` (503)

## 24. Limitations
- Similarity is strictly topological (shared stations). It does not evaluate time-of-day similarity. A 100% similar train might run 12 hours later.
- Does not enforce identical sequence direction (A->B->C vs C->B->A yield 100% similarity).

## 25. Non-Goals
- We are NOT claiming passenger tickets can be transferred.
- We are NOT claiming these trains run simultaneously.
- We are NOT modeling live operational track sharing.

## 26. Unresolved Questions
- Should directional sequence penalty be applied? *Decision: No, topological Jaccard index cleanly handles undirected overlap, which is more robust for discovering return journeys as natural alternatives.*

## 27. Implementation Sequencing
1. Implement `TrainSimilarityItem` and `TrainSimilarityResponse` schemas.
2. Implement `calculate_train_similarity` in `services/network.py`.
3. Implement `GET /api/v1/network/trains/{train_id}/similar` in `api/v1/network.py`.
4. Add service and API tests.
5. Validate via `EXPLAIN ANALYZE`.
