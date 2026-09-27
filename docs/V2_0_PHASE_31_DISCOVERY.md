# V2.0 Phase 31 Discovery: Network Edge Paired-Service Route Symmetry Analytics

## 1. Objective
Identify the next meaningful, distinct, and technically defensible network analytics capability for RailGati V2.0. The candidate must leverage existing historical/static timetable data, avoid unsupported operational claims, and comply with strict ₹0 budget constraints.

## 2. Existing Phase 1-30 Overlap Audit
RailGati V2.0 Analytics currently provides deep dimensional coverage:
- **Phase 14 (Directional Edge Asymmetry Analytics)**: Measures the raw *occurrence volume* imbalance (count of A->B trains vs B->A trains). It does not explicitly link which trains are operationally paired.
- **Phase 18 (Paired-Service Terminal Layover Analytics)**: Links paired trains to analyze layover duration strictly at their shared terminal. It does not evaluate edge-by-edge traversal.
- **Phase 25 (Network Train Paired-Service Temporal Symmetry Analytics)**: Compares the scheduled *total transit duration* of a train's forward journey against its paired return journey. It does not analyze spatial/topological routing alignment.
- **Phase 30 (Station Outbound Dominance Analytics)**: Identifies the most voluminous destination directly adjacent to a station.

**Analytical Gap**: There is currently no macroscopic topological metric that evaluates structural route reciprocity at the edge level. We know if A->B has more traffic than B->A (Phase 14), but we cannot answer: *"Are the specific trains traveling A->B paired with return services that actually use the exact same structural edge (B->A) on their way back?"*

## 3. Candidate Analytics Evaluated
1. **Network Station Route Ordinality Analytics**: Evaluates whether a station acts as an early, mid, or late structural node across all inbound routes. *Rejected:* Due to the high prevalence of paired services (88%), the average ordinality for almost all non-terminus stations mathematically normalizes to ~0.50, stripping the metric of analytical variance.
2. **Train Scheduled Peak Non-Stop Transit Analytics**: Identifies the single adjacent edge on a train's route with the absolute highest scheduled duration. *Rejected:* Derivatively overlaps with the network-relative edge evaluation already solved in Phase 28 (Train Relative Edge Slowness).
3. **Network Edge Service Provider Diversity Analytics**: Calculates `distinct_trains / total_occurrences` on an edge. *Rejected:* Because static timetables flatten frequency (no `days_of_run` multipliers), the ratio is universally ~1.0 for all edges, offering no analytical signal.
4. **Network Edge O-D Bridging Analytics**: Applies Phase 22 (Station O-D Bridges) to a specific edge rather than a node. *Rejected:* Too functionally derivative of Phase 22 without offering a new fundamental dimension.
5. **Network Edge Paired-Service Route Symmetry Analytics**: For a directed edge, calculates the proportion of forward trains whose explicitly paired return-services traverse the exact same edge in reverse. *Selected.*

## 4. Selected Analytics
**Network Edge Paired-Service Route Symmetry Analytics**

## 5. Why Selected
This analytic introduces a novel topological dimension: **Structural Edge Reciprocity**. It leverages the canonical `return_train_number` to definitively prove whether a timetable edge is operated symmetrically (trains return via the same path) or asymmetrically (trains return via an alternate route). It is computationally bounded, fully deterministic, requires no migrations, and is mathematically isolated from passenger demand or physical track capacity inferences.

## 6. API Contract
**Endpoint:** `GET /api/v1/network/edges/{from_station}/{to_station}/paired-symmetry`

**Response Payload:**
```json
{
  "from_station_code": "MGS",
  "to_station_code": "JEP",
  "timetable_snapshot_id": 2,
  "total_forward_trains": 46,
  "symmetrical_return_trains": 44,
  "symmetry_ratio": 0.9565
}
```

## 7. Data Semantics
- **Active Snapshot:** Derived cleanly via `get_active_timetable_snapshot_id`.
- **Target Edge:** An adjacent traversal `stop_sequence` -> `stop_sequence + 1` from `from_station` to `to_station`.
- **Forward Trains:** The count of unique `train_id`s in the active snapshot traversing the target edge.
- **Valid Return Match:** A forward train has a symmetrical return if its canonical `return_train_number` (from `train_observations`) traverses `to_station` -> `from_station` at `stop_sequence` -> `stop_sequence + 1` in the identical active snapshot.
- **Undefined Case:** If `total_forward_trains` is 0, the API returns a 400 Bad Request indicating no qualifying forward trains exist for the specified edge.

## 8. Mathematical Definitions
- `total_forward_trains` = Count of distinct active `train_id`s traversing `A -> B`.
- `symmetrical_return_trains` = Count of distinct active `train_id`s traversing `A -> B` where their `return_train_number` traverses `B -> A`.
- `symmetry_ratio` = `symmetrical_return_trains / total_forward_trains`. (Division by zero explicitly trapped).

## 9. SQL/Query Strategy
A multi-stage correlated subquery utilizing CTEs:
1. `fwd_edge`: Isolates all `train_id`s traversing `A -> B` by self-joining `train_stop_observations` on `seq + 1`. Joins to `train_observations` to extract the `return_train_number`.
2. `valid_returns`: Inner joins `fwd_edge` to `trains` (on `return_train_number`) and self-joins `train_stop_observations` again to verify the `B -> A` traversal condition.
3. **Aggregation Stage**: Left joins `fwd_edge` to `valid_returns` on `fwd_train_id`, yielding the total count, symmetrical count, and ratio.

## 10. Edge Cases
- **Missing Return Train Identity:** If `return_train_number` is missing or null for a forward train, it simply fails the `valid_returns` inner join and safely counts as asymmetrical (0).
- **Missing Return Timetable Stops:** If the return train exists but lacks stop timings/sequences that match `B -> A`, it safely counts as asymmetrical.
- **No Forward Traffic:** API explicitly traps HTTP 400.
- **Topology Loops:** Handled natively because distinct `train_id` counts are used, avoiding occurrence multiplier anomalies.

## 11. Error Semantics
- **404 Not Found**: If either station code does not exist.
- **400 Bad Request**: If `total_forward_trains == 0` (No qualifying data).
- **503 Service Unavailable**: If no active timetable snapshot exists.

## 12. Performance Analysis
Executed locally on PostgreSQL (Snapshot 2) for the high-volume `MGS` -> `JEP` edge:
- **Planning Time**: 3.754 ms
- **Execution Time**: 63.016 ms
- **Query Plan**: Zero global sequential scans. The planner leverages `ix_train_stops_snapshot_station` to isolate the `A -> B` slice, hashes the results, and utilizes `train_stop_observations_pkey` and `ix_trains_number` for instant nested-loop verification of the return edges. Intermediate memory consumption is < 25kB.

## 13. Real Snapshot 2 Validation
Verified mathematically against Snapshot 2 static data:
- **MGS -> JEP**: 46 forward trains. 44 have paired returns traversing JEP -> MGS. Ratio: `0.9565`.
- **NDLS -> CNB**: 0 direct adjacent-edge forward trains. (Requires routing via GZB/etc.)

## 14. ₹0 Compliance
Executes entirely on existing PostgreSQL B-Tree indexes within milliseconds. Requires no external maps, routing engines, APIs, or schema migrations.

## 15. Implementation Boundaries
- Add `EdgePairedSymmetryResponse` to `schemas.py`.
- Add `calculate_edge_paired_route_symmetry` to `services/network.py`.
- Expose `GET /api/v1/network/edges/{from_station}/{to_station}/paired-symmetry` in `api/v1/network.py`.
- Write targeted API and Service tests verifying zero-division trap and symmetry matches.

## 16. Explicit Non-Goals
- Does not confirm that trains use the exact physical track layout (only confirms the station node topology).
- Does not claim that paired services cross at the same time of day.
- Does not infer passenger flow balance.

## 17. Approval Gate
Phase 31 Discovery is complete. Implementation is strictly blocked pending manual approval.
