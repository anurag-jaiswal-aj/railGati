# V2.0 Phase 31 Discovery: Network Edge Paired-Service Route Symmetry Analytics

## 1. Objective
Identify the next meaningful, distinct, and technically defensible network analytics capability for RailGati V2.0. The candidate must leverage existing historical/static timetable data, avoid unsupported operational claims, and comply with strict ₹0 budget constraints.

## 2. Existing Phase 1-30 Overlap Audit
RailGati V2.0 Analytics currently provides deep dimensional coverage:
- **Phase 14 (Directional Edge Asymmetry Analytics)**: Measures the raw forward edge occurrence volume versus reverse edge occurrence volume, and the asymmetry between those directed edge volumes. It does not explicitly link which train identities are operationally paired.
- **Phase 18 (Paired-Service Terminal Layover Analytics)**: Links paired trains using `return_train_number` to analyze scheduled cyclic clock gaps strictly at their shared terminal. It does not test reciprocal edge traversal.
- **Phase 25 (Network Train Paired-Service Temporal Symmetry Analytics)**: Compares the scheduled total transit duration of a forward train against its paired return train. It does not test whether the paired return train traverses a particular reciprocal edge.
- **Phase 30 (Station Outbound Dominance Analytics)**: Measures outbound adjacent timetable occurrences from a station and their concentration among destination stations. It does not use paired-service relationships.

**Analytical Gap**: Phase 31 specifically tests "whether a dataset-linked paired return service contains the reciprocal adjacent timetable edge." This explicit paired-service timetable edge reciprocity is absent from existing phases.

## 3. Candidate Analytics Evaluated
1. **Network Station Route Ordinality Analytics**: Evaluates whether a station acts as an early, mid, or late structural node across all inbound routes. *Rejected:* Due to the high prevalence of paired services (88%), the average ordinality for almost all non-terminus stations mathematically normalizes to ~0.50, stripping the metric of analytical variance.
2. **Train Scheduled Peak Non-Stop Transit Analytics**: Identifies the single adjacent edge on a train's route with the absolute highest scheduled duration. *Rejected:* Derivatively overlaps with the network-relative edge evaluations already solved in Phase 28 (Train Relative Edge Slowness).
3. **Network Edge Service Provider Diversity Analytics**: Calculates `distinct_trains / total_occurrences` on an edge. *Rejected:* Because static timetables flatten frequency (no `days_of_run` multipliers), the ratio is universally ~1.0 for all edges, offering no analytical signal.
4. **Network Edge O-D Bridging Analytics**: Applies Phase 22 (Station O-D Bridges) to a specific edge rather than a node. *Rejected:* Too functionally derivative of Phase 22 without offering a new fundamental dimension.
5. **Network Edge Paired-Service Route Symmetry Analytics**: For a directed edge, calculates the proportion of forward timetable train identities whose dataset-linked paired service also contains the reciprocal adjacent timetable edge in the same timetable snapshot. *Selected.*

## 4. Selected Analytics
**Network Edge Paired-Service Route Symmetry Analytics**

## 5. Why Selected
This analytic introduces paired-service timetable edge reciprocity. It definitively computes whether an edge assignment in a timetable is matched by the dataset-linked reciprocal return service. It is mathematically bounded, completely deterministic, requires no migrations, and rigorously adheres to the static dataset without assuming real-world infrastructure properties.

## 6. Exact Timetable/Network Semantics
- **Active Snapshot:** The analytics always operates against the currently active timetable snapshot. Both forward and paired-return traversal must be evaluated within that same active snapshot.
- **Target Edge:** An adjacent scheduled traversal `stop_sequence` -> `stop_sequence + 1` from `from_station` to `to_station`.
- **Paired Identity:** Uses `return_train_number`, which is solely a dataset-provided paired-service identifier.
- **Non-Goals:** It does NOT establish physical continuity, operational continuity, same rake, same locomotive, same crew, passenger continuity, same calendar day, actual turnaround, same physical railway track, same physical infrastructure, physical topology, operational symmetry, capacity, passenger demand, congestion, or real-world operation.

## 7. API Contract
**Endpoint:** `GET /api/v1/network/edges/{from_station}/{to_station}/paired-symmetry`

**Response Payload:**
```json
{
  "from_station_code": "MGS",
  "to_station_code": "JEP",
  "timetable_snapshot_id": 2,
  "total_forward_trains": 46,
  "symmetrical_return_trains": 44,
  "symmetry_ratio": 0.9565217391304348
}
```

## 8. Mathematical Definitions
- `total_forward_trains` = number of DISTINCT train_id values in the active timetable snapshot that have at least one adjacent `A -> B` timetable traversal.
- `symmetrical_return_trains` = number of those DISTINCT forward train identities whose dataset-linked `return_train_number` identifies a train that has at least one adjacent `B -> A` timetable traversal in the same active timetable snapshot.
- `symmetry_ratio` = `symmetrical_return_trains / total_forward_trains`. 
If `total_forward_trains > 0` and `symmetrical_return_trains = 0`, then `symmetry_ratio = 0.0`.

## 9. Distinct-Train Semantics
Each distinct forward train identity is counted at most once in `total_forward_trains`. If the same train traverses A -> B multiple times (e.g. topology loops), it counts exactly once. It must not be counted separately for each occurrence.

## 10. Repeated-Edge Handling
Each distinct forward train identity is counted at most once in `symmetrical_return_trains`. If the paired return train traverses B -> A multiple times in its itinerary, the reciprocal match counts the paired forward train exactly once, explicitly preventing row-multiplication anomalies.

## 11. Deduplicated SQL Strategy
The metric requires rigorous `DISTINCT` isolation to preserve invariants:
```sql
forward_trains AS (
    SELECT DISTINCT
        tso1.train_id AS fwd_train_id,
        to_obs.return_train_number
    FROM train_stop_observations tso1
    JOIN train_stop_observations tso2 ON ...
    JOIN train_observations to_obs ON ...
    WHERE ...
),
successful_returns AS (
    SELECT DISTINCT
        fwd.fwd_train_id
    FROM forward_trains fwd
    JOIN trains rt ON rt.number = fwd.return_train_number
    JOIN train_stop_observations rtso1 ON ...
    JOIN train_stop_observations rtso2 ON ...
    WHERE ...
)
SELECT 
    COUNT(*) AS total_forward_trains,
    COUNT(sr.fwd_train_id) AS symmetrical_return_trains
FROM forward_trains f
LEFT JOIN successful_returns sr ON sr.fwd_train_id = f.fwd_train_id
```

## 12. Error Semantics
- **404 Not Found**: If either station code does not exist in the active snapshot. (Station existence verification MUST precede edge traversal verification to distinguish a nonexistent station from an empty edge).
- **400 Bad Request**: If both stations exist but `total_forward_trains == 0`. The ratio is completely undefined. The API does NOT fabricate a ratio of 0.0.
- **503 Service Unavailable**: If no active timetable snapshot exists.
- **200 OK**: If `total_forward_trains > 0`, even if `symmetrical_return_trains == 0`. (e.g. returns `{... "symmetry_ratio": 0.0}`). This is not an error.

## 13. Active Snapshot Semantics
The analytics always operates against the currently active timetable snapshot. The `from_station`, `to_station`, forward traversal, and return traversal are universally bounded by this isolated snapshot environment. Discovery tests utilized `snapshot_id = 2` solely for local performance validation.

## 14. Real Snapshot 2 Validation
The exact deduplicated queries were verified against local PostgreSQL Snapshot 2:
- **Repeated Edge Hazard**: Actual timetable occurrences exist where a single train traverses the identical directed adjacent edge multiple times. The strict `DISTINCT` structure fully prevents row multiplication.
- **MGS -> JEP**: 46 total forward trains, 44 distinct symmetrical return matches. Ratio: `0.9565217391304348`.
- **NDLS -> CNB**: 0 direct adjacent-edge forward trains. (Qualifies as HTTP 400 - zero denominator).
- **GOGH -> GBY**: 22 total forward trains, 0 distinct symmetrical return matches. Ratio: `0.0`. (Valid HTTP 200).

## 15. EXPLAIN ANALYZE
Executed locally on PostgreSQL (Snapshot 2) for the high-volume `MGS` -> `JEP` edge utilizing the corrected deduplicated strategy:
- **Planning Time**: 2.923 ms
- **Execution Time**: 6.223 ms
- **Major Join Strategy**: Nested Loop over `ix_train_stops_snapshot_station` to gather boundaries, HashAggregate to enforce `DISTINCT`, followed by heavily filtered Nested Loops utilizing `ix_trains_number` and `train_stop_observations_pkey`.
- **Global Sequential Scan**: No global sequential scans occurred.
*(Note: On the current Snapshot 2 dataset, the measured execution time was 6.223 ms).*

## 16. Edge Cases
- **Missing Return Train Identity:** If `return_train_number` is missing, the inner join correctly fails, resulting in 0 reciprocal matches for that train.
- **Return Train Missing Topologies:** If the return train exists but does not traverse B -> A, it correctly evaluates as an asymmetric pair.

## 17. ₹0 Compliance
Executes entirely on existing PostgreSQL B-Tree indexes. Requires no external maps, routing engines, APIs, or schema migrations.

## 18. Explicit Non-Goals
- Does not assert that trains share the same physical railway track, physical infrastructure, or operational routing.
- Does not imply locomotive, rake, crew, or passenger continuity.
- Does not represent actual operational turnaround, geographic route symmetry, capacity, passenger demand, congestion, or real-world operations.

## 19. Implementation Boundaries
- Add `EdgePairedSymmetryResponse` to `schemas.py`.
- Add `calculate_edge_paired_route_symmetry` to `services/network.py`.
- Expose `GET /api/v1/network/edges/{from_station}/{to_station}/paired-symmetry` in `api/v1/network.py`.
- Write targeted tests verifying zero-division trap, missing pairs, and duplicated-edge resistance.

## 20. Approval Gate
Phase 31 Discovery Correction is complete. Implementation is strictly blocked pending manual approval.
