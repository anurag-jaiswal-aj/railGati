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
- **Symmetry (Phase 15 Overlap Audit)**: This is mathematically dual to Phase 15 but analytically distinct. Phase 15 compares train route station sets. Phase 16 compares station service train sets. It perfectly mirrors Phase 15, completing the bipartite analytical model (Stations -> Trains -> Stations), without being merely a renamed endpoint.
- **Novel Dimension**: Identifies topologically adjacent or paired stations (e.g., twin city stations) purely through schedule structures rather than geographic coordinates.
- **₹0 Feasibility**: Operates entirely within PostgreSQL using elegant set theory, strictly honoring the ₹0 budget.
- **Historical Semantics**: It elegantly sidesteps live operational claims by evaluating pure mathematical overlap of historical scheduled occurrences.

## 8. Exact Mathematical Semantics
The metric computes the topological train-set overlap between a target station $S_t$ and a compared station $S_c$:

**Trains(S)** = DISTINCT train identities having at least one `TrainStopObservation` for station S in the active timetable snapshot.

$$ Jaccard = \frac{| Trains(S_t) \cap Trains(S_c) |}{| Trains(S_t) \cup Trains(S_c) |} \times 100 $$

- Stations with empty service sets cannot accidentally create a division-by-zero case, as they are excluded by the default `min_overlap_trains=1` filter and SQL coalescing rules.
- The union is derived mathematically: `|Trains(S_t)| + |Trains(S_c)| - |Trains(S_t) \cap Trains(S_c)|`.
- No train occurrence count is substituted for distinct train identity; `COUNT(DISTINCT train_id)` is rigorously enforced.

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

## 11. Snapshot Isolation Semantics
- **Timetable Bound**: EVERY CTE/query stage is rigorously constrained to the same active timetable snapshot.
- **Cross-Snapshot Mixing**: There is no possible cross-snapshot mixing between the target station train set, candidate station train sets, intersection calculation, union calculation, or final metadata.
- **Station Snapshot ID**: The API implicitly requires the active timetable `snapshot_id`, which natively applies to both `train_stop_observations` and `station_observations` joining semantics.
- **Graph-Build Dependency**: **None.** This metric evaluates set overlap directly via `TrainStopObservation`. It does not require an active `RailwayGraphBuild`.

## 12. Entity and Occurrence Semantics
- **Repeated Occurrences**: If a train visits the same station multiple times (e.g., A -> B -> A, or a looping A -> A), these visits collapse into a single distinct `train_id`. The train contributes exactly once to that station's service set.
- **Directionality / Order**: Intentionally ignored. Whether a train travels A->B or B->A, reverse train routes do not receive special treatment. The metric is explicitly NOT directional.
- **Return Train Semantics**: `return_train_number` is not used in the similarity calculation, does not increase similarity, does not exclude candidates, and holds zero mathematical role. It is strictly optional descriptive metadata if included in the response.
- **Missing Data**: If the `station_code` does not exist in the active timetable snapshot, the API must return an HTTP 404 Not Found.
- **Self-Match**: Excluded. The target station must NOT be compared against itself (`target_station_id != compared_station_id`).

## 13. Query Design
Set-based PostgreSQL CTE approach avoiding Cartesian N+1 bounds. The SQL cardinality is inherently bounded to overlapping subsets.
1. Resolve target station `station_id` from the public `station_code`.
2. Build target distinct train set (`target_trains`).
3. Build candidate station/train membership sets (`other_stations`).
4. Compute intersection counts (`intersection`).
5. Compute candidate distinct train counts (via `other_stations` group).
6. Derive union mathematically: `target_count + candidate_count - overlap_count`.
7. Calculate Jaccard percentage.
8. Apply minimum overlap filter if present (`WHERE overlap_count >= min_overlap_trains`).
9. Order deterministically.
10. Apply LIMIT.

## 14. Performance Investigation & EXPLAIN Findings
Exploratory benchmarking on the current local snapshot 2 dataset (`~8,989`-station / `~5,207`-train dataset), for target station `NDLS` / ID 1779, yielded:
- **Planning Time**: ~0.349 ms
- **Execution Time**: ~197.644 ms

**Plan Insights**:
- **Target-set scan**: Handled via `Index Scan` on `ix_train_stops_snapshot_station` (cost=412.71, actual time ~0.106ms).
- **Candidate-set scan**: Handled via `Index Scan` on `train_stop_observations_pkey`.
- **Joins**: Uses `Nested Loop` leveraging primary keys, avoiding heavy sequential hash joins.
- **Aggregates**: Utilizes `HashAggregate` for distinct train mapping and `GroupAggregate` for the overlap counting.
- **Sort & LIMIT**: `LIMIT` operates over a `Top-N heapsort` (cost=19217.23). The database-side `LIMIT` effectively bounds the rows returned to Python, but candidate aggregation still completely processes all necessary subset candidates before final ranking.
- **Sequential Scans**: None for the core analytical intersections.

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

**Exact Measured Real-Data Findings**:
- **Target Station**: `NDLS` (ID 1779) in Active Snapshot 2.
- **Distinct Target Train Count**: `298` trains.
- **Top Candidate Station**: `NZM` (Hazrat Nizamuddin).
- **Candidate Distinct Train Count**: `280` trains.
- **Overlap (Intersection)**: `250` trains.
- **Union Calculation**: `298 + 280 - 250 = 328` trains.
- **Calculated Percentage**: `(250 / 328) * 100 = 76.2%`.
- **Plausibility**: `NZM` and `NDLS` are adjacent major hubs in Delhi. It is mathematically and structurally highly plausible that they share 250 scheduled timetable service occurrences, representing topological timetable-service-set similarity.

## 20. Implementation Boundary
- **Status**: Discovery Only.
- **Phase 16 Implementation**: No implementation, migrations, APIs, or services have been started.
- **Phase 17**: No Phase 17 work has been initiated.

## 21. Implementation Sequencing
1. Implement schemas in `schemas.py`.
2. Implement core service function in `services/network.py`.
3. Implement HTTP endpoint in `api/v1/network.py`.
4. Add service and API tests.
5. Verify via `EXPLAIN ANALYZE` and real dataset inspection.

## 22. Deferred/Future Possibilities
- **Spatial Bounds**: Factoring in geographic bounding boxes to limit candidate stations to the local region. Deferred as geospatial data relies on external APIs (violates ₹0 budget constraint currently).
