# V2.0 Phase 28 Discovery: Network Train Relative Edge Slowness Analytics

## 1. Objective
Discover and rigorously evaluate the next genuinely useful Network/Train/Station analytics capability for RailGati after the completion of V2.0 Phase 27. The selected capability must provide new analytical value, adhere strictly to the ₹0 budget, rely entirely on historical/static timetable data, and avoid any inferences regarding actual train movement or live railway operations.

## 2. Current V2.0 Baseline
Phase 27 (Network Train Structural Halt Analytics) is fully complete. The codebase currently calculates and ranks scheduled intermediate dwell times for specific canonical trains, safely managing cross-midnight durations and eliminating termini without relying on physical operations assumptions.

## 3. Data Available
The repository operates on a static, historical timetable graph (Snapshot 2), featuring:
- 5,207 trains
- 417,070 train-stop observations
- 8,989 canonical stations
- Valid `arrival_time` and `departure_time` metrics.
- Hard constraints: No scraping, no paid infrastructure, no live operations assumptions.

## 4. Candidate A: Network Station Ordinality Analytics
**Endpoint:** `GET /api/v1/network/stations/{station_code}/ordinality`
**Question:** For a given station, across all trains that serve it, what is the distribution of its scheduled ordinal position?
**Computation:** Determines whether the station typically serves as an Origin, a Destination, or an Early/Mid/Late intermediate structural stop by evaluating `(stop_sequence - min_sequence) / (max_sequence - min_sequence)` for all serving trains.
**Distinctness:** Measures structural relative sequential placement across serving routes.

## 5. Candidate B: Network Train Relative Edge Slowness Analytics
**Endpoint:** `GET /api/v1/network/trains/{train_number}/relative-edge-slowness`
**Question:** For a specific train, which consecutive scheduled segments (adjacent edges) have a longer scheduled transit duration than the timetable average for that exact same adjacent edge?
**Computation:** Retrieves all scheduled adjacent-edge occurrences for the target train. Computes the target scheduled duration for each occurrence. Scans the timetable for all qualifying adjacent-edge occurrences (including the target train) on those exact station pairs to compute the network average scheduled edge duration. Ranks the target train's occurrences by the ratio `target_duration_minutes / network_average_minutes DESC`.
**Distinctness:** Evaluates a specific train's sequential adjacent-edge transit durations relative to the network baseline for its specific edges, utilizing strictly scheduled durations.

## 6. Candidate C: Network Station Topological In-Degree vs Out-Degree Asymmetry
**Endpoint:** `GET /api/v1/network/stations/{station_code}/reach-asymmetry`
**Question:** For a specific station, how asymmetric is its direct reachability (distinct outbound destinations vs distinct inbound origins)?
**Computation:** Counts distinct scheduled inbound edges vs distinct scheduled outbound edges. 
**Distinctness:** Measures station-level graph structural asymmetry. 

## 7. Candidate Evaluation
- **Candidate A** is computationally fast and useful, but conceptually narrow in its analytical scope compared to graph-level relative metrics.
- **Candidate C** overlaps substantially with Phase 7 (Hub Centrality) and Phase 14 (Edge Asymmetry), offering little new analytical depth.
- **Candidate B** provides a schedule-relative comparison of a train's adjacent-edge transit durations against the timetable average for the same adjacent station pair. It perfectly encapsulates a "Network Intelligence" metric without relying on external or operational data. Real-data SQL execution proves it is performant.

## 8. Selected Capability
**Network Train Relative Edge Slowness Analytics** (Candidate B).

## 9. Exact Semantics
- Resolve the requested canonical `train_number`.
- Identify all consecutive, valid scheduled intermediate edges (`stop_sequence` $N$ to $N+1$) for the target train where both departure at $N$ and arrival at $N+1$ exist.
- Each qualifying consecutive stop occurrence is treated as an independent timetable occurrence. Repeated adjacent station-pairs on the same target train are not deduplicated.
- Calculate the `target_duration_minutes` using Phase 11 cross-midnight math: `destination arrival clock minutes - source departure clock minutes` (with `+ 1440` when arrival is earlier than departure). `source_day` is NOT used to reconstruct calendar elapsed time.
- Identify the **Network Baseline**: all qualifying timetable occurrences on the exact same adjacent edge in the same timetable snapshot, **including the target train**.
- A qualifying network occurrence requires a matching source station, a matching destination station, adjacent consecutive stop sequences, and valid arrival/departure timings.
- Calculate the `network_average_minutes` for each edge across the baseline population.
- Calculate the `slowness_ratio` as `target_duration_minutes / network_average_minutes`.
- A ratio > 1.0 indicates a longer scheduled duration than the timetable average. A ratio < 1.0 indicates a shorter scheduled duration.
- Filter to occurrences where the target train is slower than average (`slowness_ratio` > 1.0) and sort by the ratio descending, then by target `stop_sequence` ascending for deterministic tie-breaking.

## 10. Endpoint Proposal
`GET /api/v1/network/trains/{train_number}/relative-edge-slowness`

## 11. Response Contract
```json
{
  "train_number": "15905",
  "timetable_snapshot_id": 2,
  "slow_edges": [
    {
      "target_stop_sequence": 673,
      "source_station_code": "MZA",
      "destination_station_code": "NZR",
      "target_duration_minutes": 12.0,
      "network_average_minutes": 6.16,
      "network_occurrence_count": 19,
      "slowness_ratio": 1.95
    }
  ]
}
```

## 12. SQL/Query Strategy
A multi-CTE approach:
1. `target_edges`: Extract specific occurrences (`target_seq`) and `target_duration` for the target train.
2. `network_edges`: Use `ix_train_stops_snapshot_station` to find all trains departing the target edges' source stations, joining to the next sequence to verify the destination matches. The target train is inherently included.
3. `network_stats`: Aggregate the network edges to compute `AVG(duration)` and `COUNT(*)`.
4. Final Join: Map `target_edges` to `network_stats`, compute the ratio, filter `> 1.0`, and order descending by ratio, then ascending by `target_seq`.

## 13. Edge Cases
- **Missing Timings**: If the target train lacks an arrival or departure time for an occurrence, that occurrence is excluded. If a peer train lacks timings, it is excluded from the network baseline.
- **Single-Train Edges**: If the target train is the *only* train traversing an edge, the network average equals the target duration, resulting in a ratio of 1.0.
- **Zero Average**: If the network average is 0 (e.g., all trains have a 0-minute duration), the ratio calculation handles division-by-zero (via `NULLIF`) and resolves to `NULL` (excluded from slow edges).
- **Cross-Midnight Transits**: Handled via established mathematical wrap-around (`+ 86400`).
- **Repeated Occurrences**: Distinct occurrences (e.g., Train 04853 traversing a segment twice) are preserved individually via their distinct `target_seq`.

## 14. Real Snapshot 2 Validation
Validation against the live active Snapshot 2 dataset confirms the exact semantics:

**Train 15905**
- `MZA` -> `NZR` (Sequence 673): Target 12.0 mins. Network Avg 6.16 mins. Ratio: 1.95 (Occurrences: 19). Target is included in baseline.
- `PGZ` -> `CRY` (Sequence 23): Target 7.0 mins. Network Avg 3.63 mins. Ratio: 1.93 (Occurrences: 51). Target is included in baseline.

**Train 12004**
- `ULD` -> `PATA` (Sequence 48): Target 4.0 mins. Network Avg 3.54 mins. Ratio: 1.13 (Occurrences: 93). Target is included in baseline.

## 15. Performance Analysis
Executed `EXPLAIN ANALYZE` for train 15905 (the longest scheduled sequence in the network).
- **Planning Time**: 1.406 ms
- **Execution Time**: 99.770 ms
- **Scan Behavior**: The planner utilized a `Nested Loop` leveraging the `ix_train_stops_snapshot_station` and `train_stop_observations_pkey` indexes. No global sequential scan occurred across the 417,000-row table.

## 16. Existing-Index Analysis
The query natively utilizes:
- `ix_trains_number`
- `train_stop_observations_pkey` `(snapshot_id, train_id, stop_sequence)`
- `ix_train_stops_snapshot_station` `(snapshot_id, station_id)`

## 17. Migration/Infrastructure Assessment
- **Migrations**: NONE required.
- **Infrastructure**: NONE required.

## 18. Testing Strategy
- Create explicit API integration and Service tests modeling a route for a target train and a secondary train.
- Assert correct missing-timing exclusions for both target occurrences and baseline population.
- Assert cross-midnight transit calculations using the clock-minutes convention.
- Assert repeated adjacent-pair occurrences return as distinct records.

## 19. Semantic Guardrails
This metric describes relative scheduled timetable duration.
It does NOT measure or infer:
- physical speed
- distance
- actual travel time
- live delay
- congestion
- capacity
- passenger demand
- infrastructure bottlenecks
- operational causes

## 20. Explicit Non-Goals
- We are not calculating physical speed (km/h).
- We are not processing real-time delays or physical tracking.
- We are not altering the underlying dataset.

## 21. Implementation Scope for the Next Step
- Add endpoint to `api/v1/network.py`.
- Add Pydantic schemas to `schemas.py`.
- Add core service function to `services/network.py`.
- Implement testing in `tests/api/v1/` and `tests/services/`.
