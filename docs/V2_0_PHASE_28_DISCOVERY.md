# V2.0 Phase 28 Discovery: Network Train Relative Edge Slowness Analytics

## 1. Objective
Discover and rigorously evaluate the next genuinely useful Network/Train/Station analytics capability for RailGati after the completion of V2.0 Phase 27. The selected capability must provide new analytical value, adhere strictly to the ₹0 budget, rely entirely on historical/static timetable data, and avoid any operational or passenger-inferred language.

## 2. Current V2.0 Baseline
Phase 27 (Network Train Structural Halt Analytics) is fully complete. The codebase currently calculates and ranks scheduled intermediate dwell times for specific canonical trains, safely managing cross-midnight durations and eliminating termini without relying on physical operational assumptions.

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
**Distinctness:** Measures structural relative sequential placement across serving routes, distinct from Hub Centrality (degree-based) or Termini Analytics (raw terminus counts).

## 5. Candidate B: Network Train Relative Edge Slowness Analytics
**Endpoint:** `GET /api/v1/network/trains/{train_number}/relative-edge-slowness`
**Question:** For a specific train, which consecutive scheduled segments (edges) are traversed significantly slower than the scheduled median/average of all other trains traversing those exact same edges?
**Computation:** Retrieves all scheduled structural edges for the target train. Computes the scheduled duration. Scans the timetable for all other trains traversing those exact edges to compute the network average scheduled duration for the edge. Ranks the train's edges by the ratio `train_duration / network_avg_duration DESC`.
**Distinctness:** Phase 17 is OD travel time (network level OD). Phase 20 is Outbound Transit (fastest/slowest out of a single station). This Candidate uniquely evaluates a specific train's entire route against the network baseline for its specific edges.

## 6. Candidate C: Network Station Topological In-Degree vs Out-Degree Asymmetry
**Endpoint:** `GET /api/v1/network/stations/{station_code}/reach-asymmetry`
**Question:** For a specific station, how asymmetric is its direct reachability (distinct outbound destinations vs distinct inbound origins)?
**Computation:** Counts distinct scheduled inbound edges vs distinct scheduled outbound edges. 
**Distinctness:** Edge Asymmetry (Phase 14) measures A-B vs B-A volume. This measures station-level graph structural asymmetry. 

## 7. Candidate Evaluation
- **Candidate A** is computationally very fast and useful, but conceptually quite simple and potentially narrow in its analytical value compared to graph-level relative metrics.
- **Candidate C** is heavily redundant with Phase 7 (Hub Centrality) and Phase 14 (Edge Asymmetry), offering little new analytical depth.
- **Candidate B** is exceptional. It isolates structural bottlenecks for a specific train by contextualizing its scheduled transit time against the network norm for the exact same physical segment. It perfectly encapsulates a "Network Intelligence" metric without relying on external or operational data. Real-data SQL execution proves it is highly performant (sub-100ms) without schema changes.

## 8. Selected Capability
**Network Train Relative Edge Slowness Analytics** (Candidate B).

## 9. Exact Semantics
- Resolve the requested canonical `train_number`.
- Identify all consecutive, valid scheduled intermediate edges (`stop_sequence` $N$ to $N+1$) for the target train where both departure at $N$ and arrival at $N+1$ exist.
- Calculate the `target_duration` using Phase 11 cross-midnight math: `(arrival - departure + 86400) % 86400`.
- Identify all other trains traversing the exact same edges (same source station to same destination station) with valid timings.
- Calculate the average scheduled duration (`network_avg_duration`) for each edge across all serving trains.
- Filter to edges where the target train is slower than average (`slowness_ratio` > 1.0) and sort by the ratio descending.

## 10. Endpoint Proposal
`GET /api/v1/network/trains/{train_number}/relative-edge-slowness`

## 11. Response Contract
```json
{
  "train_number": "15905",
  "timetable_snapshot_id": 2,
  "slow_edges": [
    {
      "source_station_code": "NLS",
      "destination_station_code": "NLR",
      "target_duration_minutes": 6.0,
      "network_average_minutes": 1.44,
      "edge_traffic_count": 88,
      "slowness_ratio": 4.15
    }
  ]
}
```

## 12. SQL/Query Strategy
A multi-CTE approach:
1. `target_edges`: Extract specific edges and `target_duration` for the target train using `train_stop_observations_pkey`.
2. `network_edges`: Use `ix_train_stops_snapshot_station` to find all trains departing the target edges' source stations, joining to the next sequence to verify the destination matches.
3. `network_stats`: Aggregate the network edges to compute `AVG(duration)` and `COUNT(*)`.
4. Final Join: Map `target_edges` to `network_stats`, compute the ratio, filter `> 1.0`, and order descending.

## 13. Edge Cases
- **Missing Timings**: If a train lacks an arrival or departure time for an edge, that edge is cleanly excluded from the slowness evaluation (for both target train and network averages).
- **Single-Train Edges**: If the target train is the *only* train traversing an edge, the average equals the target, resulting in a ratio of 1.0 (excluded from slow edges).
- **Cross-Midnight Transits**: Perfectly handled via established mathematical wrap-around (`+ 86400`).

## 14. Real Snapshot 2 Validation
Manual validation against Snapshot 2 yielded:
**Train 15905 (Vivek Express)**
- `NLS` -> `NLR`: Target 6.0 mins. Network Avg 1.44 mins. Ratio: 4.15 (Traffic: 88 trains).
- `KUK` -> `VZM`: Target 34.0 mins. Network Avg 11.42 mins. Ratio: 2.97 (Traffic: 56 trains).
**Train 12004 (Shatabdi Express)**
- `ULD` -> `PATA`: Target 4.0 mins. Network Avg 3.53 mins. Ratio: 1.13 (Traffic: 93 trains).
*(Shatabdi correctly shows almost no slowness compared to the network average).*

## 15. Performance Analysis
Executed `EXPLAIN ANALYZE` for the longest train (15905) querying all network intersections.
- **Planning Time**: 1.406 ms
- **Execution Time**: 99.770 ms
- **Scan Behavior**: No global sequential scans. The planner utilized a `Nested Loop` leveraging the existing `ix_train_stops_snapshot_station` and `train_stop_observations_pkey` indexes flawlessly, resulting in ~100ms execution across 417,000 observations.

## 16. Existing-Index Analysis
The query natively utilizes:
- `ix_trains_number`
- `train_stop_observations_pkey` `(snapshot_id, train_id, stop_sequence)`
- `ix_train_stops_snapshot_station` `(snapshot_id, station_id)`
No new indexes are required.

## 17. Migration/Infrastructure Assessment
- **Migrations**: NONE required.
- **Infrastructure**: NONE required. (Complies with ₹0 budget).

## 18. Testing Strategy
- Create explicit API integration and Service tests modeling a 3-station route for a target train and a secondary train.
- Assert correct missing-timing exclusions.
- Assert cross-midnight transit calculations.
- Assert that ratios > 1.0 are returned and ordered correctly.

## 19. Semantic Guardrails
- **DO NOT** claim these edges represent actual physical speed bottlenecks.
- **DO NOT** infer "overtaking" or "congestion." This is strictly a relative scheduled timetable duration metric.

## 20. Explicit Non-Goals
- We are not calculating distance or physical speed (km/h).
- We are not altering the underlying dataset.
- We are not processing real-time delays.

## 21. Implementation Scope for the Next Step
- Add endpoint to `api/v1/network.py`.
- Add Pydantic schemas to `schemas.py`.
- Add core service function to `services/network.py`.
- Implement rigorous testing in `tests/api/v1/` and `tests/services/`.
