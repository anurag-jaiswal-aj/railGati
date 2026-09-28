# Phase 42 Implementation Report: Network Edge Route Co-Traversal Affinity Analytics

## 1. Implementation Summary
The Phase 42 discovery for **Network Edge Route Co-Traversal Affinity Analytics** was implemented and validated. The implementation provides a purely structural measurement of route-wide timetable co-occurrence (shared scheduled train identities) across directed timetable edges based on the static historical timetable.

## 2. Exact Formal Semantics
For target directed edge `E = (A,B)`:
- `T(E)` = the set of DISTINCT train identities whose timetable occurrence contains at least one consecutive `A -> B` stop pair in the active timetable snapshot.

For another directed adjacent edge `F = (C,D)`:
- `T(F)` = the set of DISTINCT train identities whose timetable occurrence contains at least one consecutive `C -> D` stop pair in the SAME active timetable snapshot.

The metric is:
`shared_train_count(E,F) = |T(E) ∩ T(F)|`

The metric is a RAW DISTINCT-TRAIN INTERSECTION COUNT.

## 3. Endpoint
`GET /api/v1/network/edges/{from_station_code}/{to_station_code}/route-co-traversal-affinity`

## 4. Schema Changes
Added to `src/railgati/api/v1/schemas.py`:
- `EdgeSharedTraversal`: Contains `from_station_code`, `to_station_code`, and `shared_train_count`.
- `EdgeRouteCoTraversalAffinityResponse`: Top-level response schema including the target edge details, `timetable_snapshot_id`, `traversing_train_count`, and a list of `shared_edges`.

## 5. Service Changes
Added `calculate_edge_route_co_traversal_affinity(db, timetable_snapshot_id, from_station_code, to_station_code, limit)` to `src/railgati/services/network.py`.

## 6. Query Strategy
The query uses Common Table Expressions (CTEs) for set-based performance:
1. `target_trains`: Selects DISTINCT `train_id` traversing the target edge in the active snapshot.
2. `target_train_count`: Counts the total distinct train identities.
3. `other_edges`: Joins `train_stop_observations` against `target_trains` to find all other consecutive edges traversed by those same trains, aggregating with `COUNT(DISTINCT t1.train_id)`.
4. The final projection joins with `stations` to resolve station codes and orders deterministically by `shared_train_count DESC`, origin code `ASC`, destination code `ASC`.

## 7. Deduplication/Repeated-Occurrence Handling
- `DISTINCT t1.train_id` is used at both the `target_trains` CTE and the `other_edges` aggregation step.
- Repeated traversal of the same edge by the same train identity contributes exactly once.
- Repeated traversal of another edge by the same train identity contributes exactly once to that comparison edge's shared count.
- The target edge `A->B` is explicitly excluded from the `other_edges` results.

## 8. Snapshot Handling
The implementation strictly queries using a single `timetable_snapshot_id`. The active snapshot is resolved at the API layer using `get_active_timetable_snapshot_id(db)` and passed down to the service layer.

## 9. Error Behavior
- **Unknown Origin/Destination Station Code**: Raises a 404 Not Found.
- **Valid Stations but No Active Timetable Edge**: Raises a 404 Not Found with the message "Directed edge not found: ... (no active timetable trains)".
- **Valid Target Edge with No Other Co-traversed Edges**: Returns an empty array `[]` for `shared_edges`.

## 10. Focused Test Results
- Service Tests (`tests/services/test_network_edge_route_co_traversal_affinity.py`): 2 passed.
- API Tests (`tests/api/v1/test_network_edge_route_co_traversal_affinity.py`): 2 passed.
All newly implemented tests passed successfully.

## 11. Full Suite Result
- Total Tests: 490
- Passed: 489
- Failed: 1 (The expected Phase 40 test mismatch)

## 12. Ruff/MyPy Result
- MyPy: Passed on the modified files.
- Ruff: Identified standard line-length (`E501`) warnings consistent with the existing repository styling. Whitespace issues were auto-fixed.

## 13. Snapshot 2 Validation
The query was validated against Snapshot 2 matching the exact approved values:

**TARGET: SBB -> GZB**
- Target traversing train identities = 143
- Top co-traversed edges:
  - ANVT -> CNJ = 83
  - CNJ -> SBB = 77
  - ANVR -> ANVT = 67
  - AJR -> DKDE = 64
  - ALJN -> DAQ = 64

**TARGET: MSB -> MSF**
- Target traversing train identities = 132
- Top co-traversed edges include:
  - MSF -> MPKT = 125
  - GWYR -> KTPM = 70

**TARGET: AAV -> AGCI**
- Target traversing train identities = 2
- Approved boundary example:
  - AGCI -> SVL = 2

## 14. EXPLAIN Findings
Execution on SBB -> GZB (Snapshot 2):
- **Planning Time**: 0.359 ms
- **Execution Time**: 29.958 ms
- **Path Highlights**: The planner efficiently used `ix_train_stops_snapshot_station` and `train_stop_observations_pkey` within nested loop joins. No sequential scans were performed on the observations tables.

## 15. Semantic Guardrails
- **IS**: A purely structural measurement of route-wide timetable co-occurrence (shared scheduled train identities across directed timetable edges) based on the static historical timetable.
- **IS NOT**: Jaccard similarity, cosine similarity, correlation, passenger demand, passenger flow, operational dependency, physical track dependency, infrastructure dependency, route redundancy, capacity, congestion, reliability, or current/live service information.

## 16. Known Unrelated Test Failure
The full test suite execution confirmed exactly 1 test failure:
`tests/api/v1/test_network_train_route_edge_exclusivity.py::test_api_edge_exclusivity_success`
This is an existing Phase 40 API/test mismatch and was explicitly left unmodified during Phase 42 implementation as per requirements.
