# V2.0 PHASE 16 DISCOVERY: Station Service Similarity Analytics

**DISCOVERY ONLY — NO PRODUCTION IMPLEMENTATION.**

## 1. Problem Statement
RailGati Phase 15 successfully introduced **Train Route Similarity**, allowing users to identify trains with topologically overlapping station sets. However, the network analytics suite lacks the symmetrical capability: identifying structurally "twin" stations based on the overlapping set of trains that serve them. 

When users ask, "Which historical stations share the exact same long-distance train corridors as this station?", existing metrics fall short. Hub Centrality (Phase 7) only measures volume, and Network Path (Phases 2-3) only measures reachability. We need a definitive mathematical metric of structural topological overlap between scheduled station occurrences.

## 2. Phase 1–15 Capability Boundary
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
- **Phase 15**: Train Route Similarity

## 3. Analytical Coverage Audit
- **Topology**: Covered (reachability, paths, train similarity).
- **Volume**: Covered (edges, nodes, O-D flows).
- **Temporal**: Covered (dwell, concentration).
- **Directionality**: Covered (asymmetry).
- **Station Structural Comparison**: **Absent**. No feature computes holistic similarity between distinct stations based on their serving trains.

## 4. Candidate Directions Considered
During discovery, three Phase 16 candidates were evaluated against the historical dataset:

1. **Station Service Similarity (Jaccard Index Analytics)**: Topological overlap of scheduled trains serving two stations.
2. **Station Terminus Reach (Outward Direct Reach)**: The distinct set of final destinations reachable directly from a station without transfers.
3. **Station Service Composition (Train Type Profile)**: The distribution of train types (e.g., SF, EXP) serving a station.

## 5. Candidate Comparison

| Dimension | Station Service Similarity | Station Terminus Reach | Station Service Composition |
| :--- | :--- | :--- | :--- |
| **Product Question** | Which stations share the most identical scheduled train services? | What distinct final destinations can I reach directly? | What is the historical mix of train types stopping here? |
| **Data Required** | `TrainStopObservation.train_id` | `TrainStopObservation.stop_sequence` | `TrainObservation.type` |
| **Graph Dependency**| None | None | None |
| **Distinction** | Structural network overlap | Reachability overlap | Trivial categorical aggregation |
| **Performance** | ~197 ms | ~135 ms | ~1 ms |
| **Verdict** | **Selected** | Overlaps heavily with Phase 10 / Phase 6 | Too trivial, lacks deep structural insight |

## 6. Selected Phase 16 Scope
**Station Service Similarity (Jaccard Index Analytics)**

Provide a network endpoint that, given a target railway station code, calculates the historical timetable train-set similarity (Jaccard Index) against all other scheduled stations in the active timetable snapshot.

## 7. Why This Direction Was Selected
- **Symmetry**: It perfectly mirrors Phase 15 (Train Similarity), completing the bipartite analytical model (Stations -> Trains -> Stations).
- **Novel Dimension**: Identifies topologically adjacent or paired stations (e.g., twin city stations) purely through schedule structures rather than geographic coordinates.
- **₹0 Feasibility**: Operates entirely within PostgreSQL using elegant set theory, strictly honoring the ₹0 budget.
- **Historical Semantics**: It elegantly sidesteps live operational claims by evaluating pure mathematical overlap of historical scheduled occurrences.

## 8. Exact Metric Definitions
The metric computes the topological train-set overlap between a target station $S_t$ and a compared station $S_c$:
$$ Jaccard = \frac{| Trains(S_t) \cap Trains(S_c) |}{| Trains(S_t) \cup Trains(S_c) |} \times 100 $$
Expressed strictly as a percentage rounded to one decimal place.

## 9. Explicit Non-Goals
This is strictly a TOPOLOGICAL TRAIN-SET similarity metric. It intentionally ignores:
- Geographic distance or coordinate proximity.
- Station platform capacity or physical infrastructure.
- Passenger demand, ticketing, or substitution.
- Live operational active service conditions or connectivity quality.

High similarity scores merely identify mathematically overlapping scheduled service sets, they do NOT imply stations are geographically close or operationally linked.

## 10. Data Sources / Tables
- `train_stop_observations` (Core relationships)
- `stations` (Code resolution)
- `station_observations` (Name resolution)

## 11. Snapshot Semantics
- **Timetable Bound**: The query strictly resolves and enforces the active timetable snapshot ID exactly once.
- **Graph-Build Dependency**: **None.** This metric evaluates set overlap directly via `TrainStopObservation`. It does not require an active `RailwayGraphBuild`.

## 12. Entity and Occurrence Semantics
- **Repeated Occurrences**: If a train visits the same station multiple times (e.g., a looping journey), these visits must mathematically collapse into a single distinct `train_id`. Jaccard similarity measures the distinct set of scheduled trains.
- **Directionality / Order**: Ignored. Whether a train travels A->B or B->A, it is equally part of both stations' train sets.
- **Return Train Semantics**: Not explicitly weighted. Reverse services are distinct trains and will naturally factor into the overlap if they serve both stations.
- **Missing Data**: If the `station_code` does not exist in the active timetable snapshot, the API must return an HTTP 404 Not Found.
- **Self-Match**: Excluded. The target station must NOT be compared against itself (`target_station_id != compared_station_id`).

## 13. Query Design
Set-based PostgreSQL CTE approach avoiding Cartesian N+1 bounds:
1. `target_trains`: Select `DISTINCT train_id` for the target station ID.
2. `target_count`: Aggregate `COUNT(*)` of `target_trains`.
3. `other_stations`: Select `station_id`, `COUNT(DISTINCT train_id)` for all other stations.
4. `intersection`: Join `train_stop_observations` against `target_trains` and aggregate `COUNT(DISTINCT tso.train_id)` as `overlap_count`.
5. Calculate `union_count`: `(target_count + compared_count - overlap_count)`.
6. Calculate `similarity_pct`: `ROUND((overlap_count * 100.0) / union_count, 1)`.

## 14. Performance Investigation & EXPLAIN Findings
Exploratory benchmarking on the local dataset (Snapshot 2, target station `NDLS` / ID 1779, 298 distinct trains) yielded:
- **Planning Time**: ~0.349 ms
- **Execution Time**: ~197.644 ms

**Plan Insights**:
- Relies heavily on `train_stop_observations_pkey` (snapshot_id, train_id) and `ix_train_stops_snapshot_station` to perform rapid `Index Scan` operations.
- Avoids full sequential scans of `train_stop_observations`.
- Utilizes an efficient `GroupAggregate` and `Top-N heapsort` to order and limit the payload purely in the database layer.

## 15. Proposed API
**GET /api/v1/network/stations/{station_code}/similar**

**Parameters:**
- `limit` (int): minimum 1, maximum 50, default 10.
- `min_overlap_trains` (int): minimum 1, default 1. (Candidates with 0 overlap are entirely excluded).

**Response Schema:**
```json
{
  "timetable_snapshot_id": 2,
  "target_station_code": "NDLS",
  "target_station_name": "New Delhi",
  "target_train_count": 298,
  "limit": 10,
  "min_overlap_trains": 1,
  "items": [
    {
      "station_code": "NZM",
      "station_name": "Hazrat Nizamuddin",
      "overlap_train_count": 250,
      "compared_train_count": 280,
      "union_train_count": 328,
      "similarity_pct": 76.2
    }
  ]
}
```

## 16. Deterministic Ordering
Strictly deterministic sorting enforced on the database side:
1. `similarity_pct DESC`
2. `overlap_train_count DESC`
3. `union_train_count ASC`
4. `station_code ASC`

## 17. HTTP Error Semantics
- `404 Not Found`: Target `station_code` not found in active snapshot.
- `422 Unprocessable Content`: Invalid `limit` bounds.

## 18. Testing Strategy
- **Normal Case**: Verify intersection/union math with known overlapping stations.
- **Self-Match Exclusion**: Assert the target station never appears in `items`.
- **Zero Overlap**: Assert stations with 0 shared trains are dropped when `min_overlap_trains=1`.
- **Snapshot Isolation**: Ensure trains/stations from inactive snapshots do not leak into counts.
- **Repeated Occurrences**: Ensure duplicate `TrainStopObservation` visits collapse via `DISTINCT`.
- **Limit Bounds**: Assert `422` on limit > 50 or < 1.

## 19. Real-Data Validation Plan
Test manually against the local database (e.g., target `NDLS`) to confirm intersection and union arithmetic exactly match the theoretical Jaccard formula for the top result.

## 20. Implementation Sequencing
1. Implement schemas in `schemas.py`.
2. Implement core service function in `services/network.py`.
3. Implement HTTP endpoint in `api/v1/network.py`.
4. Add service and API tests.
5. Verify via `EXPLAIN ANALYZE` and real dataset inspection.

## 21. Deferred/Future Possibilities
- **Spatial Bounds**: Factoring in geographic bounding boxes to limit candidate stations to the local region. Deferred as geospatial data relies on external APIs (violates ₹0 budget constraint currently).
