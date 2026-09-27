# RailGati V2.0 Phase 19 Discovery

## 1. Objective
Discover and define the next coherent Network Analytics capability for RailGati V2.0. The capability must provide a materially distinct analytical dimension, leverage existing historical static timetable data without requiring graph/infrastructure changes, and adhere strictly to the constraints established in Phases 1–18.

## 2. Existing-System Context
The V2.0 analytics surface currently includes:
- Topological & Component Analytics (Reachability, Paths, Continuous Services, Corridors, Termini, Hubs)
- Volume & Flow Analytics (Edge Volume, O-D Flow)
- Duration & Timing Analytics (Dwells, Travel-Time, Paired-Service Scheduled Layovers)
- Structural Analysis (Route Complexity, Temporal Concentration, Edge Asymmetry)
- Similarity Analytics (Train Route Similarity, Station Service Similarity)

## 3. Capabilities Already Implemented
Phase 18 introduced *Network Station Paired-Service Analytics*, linking disparate train identities via `return_train_number` to analyze cyclic scheduled clock gaps at termini. It established strict limitations against inferring physical rake continuity or actual elapsed turnaround. Phase 19 must not duplicate these dataset-pairing mechanisms or temporal wait-time analyses.

## 4. Candidate Capabilities
We evaluated three primary candidates for Phase 19:

**Candidate 1: Network O-D Service Route Diversity Analytics**
- *Question*: Between two major stations, how many distinct topological sequences (sub-paths) do the trains connecting them actually use?
- *Overlap*: Phase 10 aggregates historical flow volume. Phase 7 isolates continuous corridors. Phase 15 compares structural similarities of trains. This would aggregate the actual sub-paths used for an O-D pair.

**Candidate 2: Network Station Directional Reversal Analytics**
- *Question*: Which stations act as structural reversal hubs (loco reversals or dead-end stations) where a train arrives from and departs to the identical adjacent station?
- *Overlap*: Completely distinct. Prior routing analytics assess generic paths or continuous flow. Directional asymmetry assesses volume imbalance. This isolates a localized topological U-turn within a single train's continuous historical schedule.

**Candidate 3: Network Edge Transit Speed Analytics**
- *Question*: What is the average scheduled clock gap (transit time) between two adjacent stations for all trains traversing that single edge?
- *Overlap*: Phase 11 calculates station wait times. Phase 17 calculates end-to-end O-D travel times. This would measure the single-edge traversal time across trains.

## 5. Selected Capability
**Network Station Directional Reversal Analytics**

## 6. Why It Is Distinct
Unlike Hub Centrality (which measures in/out degree volume), Edge Asymmetry (which measures directional volume imbalance), or Station Dwell (which measures wait time), Reversal Analytics identifies a purely structural operational phenomenon: loco-reversals or dead-end pull-outs. It relies entirely on the topological sequence of stops for a *single continuous train identity*, finding cases where the sequence folds back on itself structurally. It does not require dataset pairing (`return_train_number`), temporal calculations, or cross-train volume aggregation.

## 7. Scope
- Analyze a target station to identify all historical trains in the snapshot that perform a topological reversal at that station.
- Return the aggregate count and the list of reversing trains, including the adjoining station they arrived from and returned to.

## 8. Out-of-Scope Behavior
- **Physical Rake/Loco Direction**: Does not track actual locomotive placements or physical train coupling.
- **Elapsed Reversal Time**: Does not calculate the time taken to reverse the train (dwell analytics already handles transit wait times).
- **Live Train Direction**: Does not reflect real-time live network directionality or delays.
- **Passenger Routing**: Does not imply passengers are expected to ride through the reversal.

## 9. Unit of Analysis
A continuous sequence of three stops for a single train (`sequence n-1, n, n+1`) where the `station_id` at `n-1` is identical to the `station_id` at `n+1`, and `n` is the target station.

## 10. Data Sources / Tables
- `stations`: To resolve the canonical station codes.
- `train_stop_observations`: To evaluate the sequential `station_id` sequence for each train using window functions.
- `trains`: To resolve the canonical train numbers.

## 11. Exact Semantics
- **Reversal Stop**: An intermediate stop on a train's path where the immediately preceding stop's station and the immediately succeeding stop's station are identical.
- **Valid Match**: Requires the target station to be the reversal stop (`n`).
- **Data Boundary**: Limited strictly to the continuous `stop_sequence` within a single `train_id` in the active snapshot.

## 12. Repeated-Occurrence Semantics
If a train loops significantly and reverses at the same station multiple times within its sequence (highly anomalous but mathematically possible), each distinct triplet sequence `(A -> B -> A)` constitutes a valid reversal event. Reversals are evaluated on the ordered observation sequence without silent deduplication.

## 13. Directionality Semantics
The feature evaluates topological sequence directionality (`station A -> station B -> station A`). It identifies a U-turn in the logical dataset path. It makes no claims regarding compass direction (North/South) or rail track gauge assignment.

## 14. Timing Semantics
The capability returns the scheduled `arrival_time` and `departure_time` at the target reversal station for context, but it performs no temporal mathematics. The analysis is purely structural/topological.

## 15. Snapshot Semantics
- Evaluates purely against the active timetable snapshot ID.
- Resolves station metadata using the active station snapshot.
- Reversal boundaries do not cross snapshots.

## 16. Query Design
To avoid full-table window functions over the entire timetable, the query first isolates trains that stop at the target station, then retrieves the full sequences only for those specific trains:

```sql
WITH target_trains AS (
    SELECT train_id
    FROM train_stop_observations
    WHERE snapshot_id = :snapshot_id AND station_id = :station_id
),
stops AS (
    SELECT tso.train_id, tso.stop_sequence, tso.station_id, tso.arrival_time, tso.departure_time,
           LAG(tso.station_id) OVER (PARTITION BY tso.train_id ORDER BY tso.stop_sequence) as prev_station_id,
           LEAD(tso.station_id) OVER (PARTITION BY tso.train_id ORDER BY tso.stop_sequence) as next_station_id
    FROM train_stop_observations tso
    JOIN target_trains tt ON tso.train_id = tt.train_id
    WHERE tso.snapshot_id = :snapshot_id
)
SELECT tr.number as train_number, s_adj.code as adjoining_station, stops.arrival_time, stops.departure_time
FROM stops
JOIN trains tr ON tr.id = stops.train_id
JOIN stations s_tgt ON s_tgt.id = stops.station_id
JOIN stations s_adj ON s_adj.id = stops.prev_station_id
WHERE stops.prev_station_id = stops.next_station_id
  AND s_tgt.code = :station_code
ORDER BY tr.number;
```

- **Graph DB Requirement**: None.
- **Recursive CTE Requirement**: None.
- **New Index Requirement**: None.

## 17. API Proposal
**Endpoint**: `GET /api/v1/network/stations/{station_code}/reversals`

**Parameters**:
- `station_code` (Path): Canonical station code (e.g., "VSKP").

## 18. Response Schema
```json
{
  "station_code": "VSKP",
  "station_name": "Visakhapatnam",
  "timetable_snapshot_id": 2,
  "reversal_count": 83,
  "reversing_trains": [
    {
      "train_number": "11019",
      "adjoining_station_code": "MIPM",
      "arrival_time": "20:55:00",
      "departure_time": "21:15:00"
    }
  ]
}
```

## 19. Validation/Error Semantics
- 200 OK: Valid station, returns reversal data (or empty if zero reversals occur).
- 400 Bad Request: General query failure.
- 404 Not Found: If the station code does not exist.
- 422 Unprocessable Entity: Handled by FastAPI for empty/invalid strings.
- 503 Service Unavailable: If no active timetable snapshot exists.

## 20. Real-Data Investigation
Running the optimized query on active Snapshot 2 for Station `VSKP` (Visakhapatnam), a notorious dead-end junction:
- **Total trains serving VSKP**: 139
- **Reversing trains at VSKP**: 83
- **Sample Result**: Train `11019` arrives from `MIPM` (Marripalem) at `20:55:00` and departs back to `MIPM` at `21:15:00`.
The dataset correctly and robustly surfaces the historical topological reversals without manual geographical configuration.

## 21. EXPLAIN ANALYZE Results
Execution against local PostgreSQL for Station `VSKP` (Snapshot 2):
- **Planning Time**: 2.074 ms
- **Execution Time**: 37.481 ms
- **Actual Row Counts**: 83 valid reversals from the 36,253 sequence rows belonging to trains serving VSKP.
- **Index Scans**: Exclusively uses `Index Scan using ix_train_stops_snapshot_station` to find the target trains, followed by a fast loop on `train_stop_observations_pkey` `(snapshot_id, train_id)` to pull their full paths.
- **Sequential Scans**: 0.
- **Window Functions**: QuickSort limits memory overhead (~3MB) by processing only the isolated subset of trains.

## 22. Index Investigation
The existing index architecture is highly efficient. Filtering target trains leverages `ix_train_stops_snapshot_station`, and retrieving their paths leverages the `train_stop_observations_pkey` (which is naturally clustered by `snapshot_id` and `train_id`). No new index is justified.

## 23. Test Plan
- `test_api_network_reversals_success`: Verifies standard reversal calculation (A -> B -> A).
- `test_api_network_reversals_empty`: Ensures 200 OK with `[]` for a station with straight-through traffic only.
- `test_api_network_reversals_invalid_station`: Verifies 404 behavior.
- `test_service_network_reversals_isolation`: Validates the logic strictly respects the active snapshot ID.
- `test_service_network_reversals_terminal_exclusion`: Verifies that a train starting or ending at a station (sequences 1 or MAX) does not register as a reversal.

## 24. Risks
- **Data Anomalies**: If the dataset contains missing intermediate stops (e.g., A -> C -> A instead of A -> B -> C -> A), the analytic will correctly register a reversal over the *known* stops, which is mathematically sound but might obscure the micro-geography. This is an accepted limitation of timetable data.

## 25. Unresolved Questions
- None. The schema guarantees the availability of `stop_sequence` and `station_id`.

## 26. Historical/Static Limitations
As emphasized throughout this document, this capability **cannot and does not** infer true physical locomotive decoupling, real-time live routing diversions, or actual station track layouts. It purely extracts historical scheduled topological sequence reversals.

## 27. Implementation Sequencing
1. Create `ReversingTrainItem` and `ReversalResponse` in `schemas.py`.
2. Implement `calculate_station_reversals` in `services/network.py` with SQLAlchemy text execution for PostgreSQL and SQLite fallback.
3. Wire the endpoint `GET /api/v1/network/stations/{station_code}/reversals` in `api/v1/network.py`.
4. Write test files (`test_network_reversals.py`) for API and Services.
