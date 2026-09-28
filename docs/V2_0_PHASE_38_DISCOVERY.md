# V2.0 Phase 38 Discovery: Network Train Route Topological Bypass Analytics

## 1. Phase Objective
Identify, evaluate, and formally define the next railway-network intelligence capability (Phase 38) that is genuinely distinct from all completed V2.0 phases, adhering strictly to the timetable-derived structural network graph and operating natively within PostgreSQL.

## 2. Candidate Capabilities Investigated
During discovery, multiple potential capabilities were evaluated and explicitly rejected to avoid overlap:
1. **Station Structural Bridge-Edge Analysis:** (Rejected) Dynamically computing true bridges on a dense directed timetable graph is extremely computationally expensive in pure SQL and prone to degenerating into full DFS algorithms.
2. **Train Route Edge Exclusivity Analytics:** (Rejected) Too similar to simply aggregating basic edge volumes (Phase 7) or train similarity (Phase 14).
3. **Network Train Route Structural Outbound Frontier:** (Rejected) Explicitly violates the constraint avoiding "another bounded-hop expansion metric" (similar to Phase 34/35/36).
4. **Train Route Topological Bypass Analytics:** (Selected) Evaluates the internal topological cohesiveness of a route against the broader network graph, asking whether the timetable structure contains direct short-circuits (bypasses) that skip intermediate stops of the train.

## 3. Selected Capability
**Network Train Route Topological Bypass Analytics**

## 4. Problem/Question Being Answered
*Does a specific train route operate over a sequence of stops where the broader network topology contains structural shortcuts?*

This capability quantifies the number of distinct structural "short-circuits" (bypasses) available over the train's specific sequence of stops. It measures whether the network topology could theoretically support faster transit between points on the train's route by skipping intermediate stops, even if the specific train being queried stops everywhere.

## 5. Explicit Overlap Audit (Phases 1–37)
- **Phase 37 (Subsumption):** Checks if the *entire* route is contained within another train. Bypass checks if *parts* of the route are skipped by individual edges of *any* train.
- **Phase 33 (Transit Articulation):** Evaluates if a station is a strict cut-vertex between its inbound and outbound neighborhoods. Bypass evaluates parallel routing across multiple stops of a single sequence.
- **Phase 25 (Topology Loops):** Finds self-intersections (`A -> ... -> A`). Bypass finds structural short-circuits (`A -> ... -> B` where a scheduled direct edge `A -> B` exists).
- **Phases 34–36 (Reachability/Expansion):** Focus on bounded outbound frontier expansion (new stations reached). Bypass evaluates structural cohesion *internal* to the queried route sequence.
- **Phase 16 (Travel Time):** Evaluates temporal duration. Bypass evaluates pure graph adjacency.

## 6. Why the Selected Capability is Distinct
It represents the first metric to evaluate the *internal topological cohesiveness* of a train route against the global graph context. It identifies local detour behaviors structurally without relying on physical geographic coordinates or passenger routing heuristics.

## 7. Exact Semantics
For a target train $T$, its scheduled ordered stop sequence is $S_1, S_2, \dots, S_k$.
A topological bypass exists if there is at least one scheduled edge $(S_i, S_j)$ in the active timetable snapshot (contributed by any train) such that $j > i + 1$.
The capability counts the number of distinct structural bypass edges $(S_i, S_j)$ that exist across the entirety of $T$'s route.

## 8. Mathematical Definition
Let $seq(T) = [S_1, S_2, \dots, S_k]$ be the ordered sequence of stations visited by train $T$.
Let $E$ be the set of all distinct scheduled directed edges $(u, v)$ in the active timetable snapshot.
The set of topological bypasses for $T$ is:
$$ B(T) = \{ (S_i, S_j) \mid 1 \le i < j - 1 < k \text{ and } (S_i, S_j) \in E \} $$
The metric returned is $|B(T)|$.

## 9. Data Dependencies
- `trains`: For target train resolution.
- `train_stop_observations`: For retrieving the target stop sequence and verifying the existence of bypass edges across the network.

## 10. Snapshot Semantics
The query is strictly bounded to the active `timetable_snapshot_id`. Bypasses must exist as scheduled edges within the same dataset snapshot.

## 11. API Proposal
**GET** `/api/v1/network/trains/{train_number}/topological-bypasses`

## 12. Response Fields
```json
{
  "train_number": "string",
  "timetable_snapshot_id": "integer",
  "route_length": "integer",
  "bypass_edge_count": "integer",
  "has_topological_bypasses": "boolean"
}
```

## 13. Error Semantics
- `404 Not Found`: If the train number does not exist in the active timetable snapshot.
- `503 Service Unavailable`: If no active timetable snapshot is found.
- `400 Bad Request`: For generic or unexpected query failures.

## 14. Query/Algorithm Design
A purely relational query leveraging CTEs:
1. `target_seq`: Retrieve the ordered stations and ranks for the target train.
2. `target_pairs`: Generate all valid pairs $(S_i, S_j)$ from `target_seq` where $j > i + 1$.
3. `bypasses`: Join `target_pairs` with `train_stop_observations` to verify if the edge $(S_i, S_j)$ exists in the snapshot.

## 15. Complexity Analysis
For a train visiting $K$ stations, there are $O(K^2)$ potential bypass pairs.
The nested loop evaluates whether each pair $(S_i, S_j)$ forms a valid edge in the snapshot graph. The existence check is $O(1)$ on average leveraging indexed lookups. Total time complexity per request is $O(K^2)$, heavily bounded by the maximum train route length.

## 16. Worst-case Behavior
The worst-case scenario is the longest train in the network (e.g., Train 12318 with 394 stops). The algorithm will evaluate $\approx 77,421$ pairs.

## 17. Performance Analysis (Real Snapshot 2 Validation)
An `EXPLAIN ANALYZE` run on the worst-case Train 12318 (394 stops) resulted in an execution time of **80.45 ms**.
The query planner highly optimizes the operation by:
- utilizing `ix_train_stops_snapshot_station` to fetch all outbound edges from the target stations.
- performing a highly efficient in-memory Hash Join to filter destinations against the target sequence.
No schema changes or new indexes are required to maintain sub-100ms performance.

## 18. Real Snapshot 2 Validation
Independent discovery testing yielded the following authoritative verification targets for the final implementation:
- **Train 58202 (15 stops):** 0 bypass edges (Pure linear corridor).
- **Train 51145 (2 stops):** 0 bypass edges (Mathematically impossible, $K \le 2$).
- **Train 55512 (15 stops):** 0 bypass edges.
- **Train 51916 (15 stops):** 4 bypass edges.
- **Train 16779 (124 stops):** 24 bypass edges.
- **Train 12720 (250 stops):** 36 bypass edges.
- **Train 12318 (394 stops):** 82 bypass edges.

## 19. Boundary Cases
- **Train with $\le 2$ stops:** Mathematically cannot have a bypass ($j > i + 1$ requires at least 3 stops). Returns 0.
- **Duplicate stations in route:** Ranks disambiguate position; if $A \to B \to A$ exists and the network contains $A \to A$, it counts as a bypass. Handled safely by distinct edge sets.

## 20. Non-Goals
- Does not measure passenger journey alternatives.
- Does not evaluate temporal feasibility (whether the bypass train actually arrives earlier).
- Does not identify physical tracks or geographic detours.

## 21. ₹0 Constraints
Strictly relies on the local PostgreSQL database using historical snapshot data. Requires no external dependencies, paid APIs, or external graph infrastructure.

## 22. Implementation Boundaries
- Create endpoint in `backend/src/railgati/api/v1/network.py`.
- Add schema in `backend/src/railgati/api/v1/schemas.py`.
- Implement service in `backend/src/railgati/services/network.py`.
- Add tests in `tests/api/v1/` and `tests/services/`.

## 23. Planned Tests
- `test_topological_bypasses_normal_case`: Standard route with bypasses.
- `test_topological_bypasses_no_bypasses`: Route structurally lacking bypasses.
- `test_topological_bypasses_short_train`: Train with 2 stops (returns 0).
- `test_topological_bypasses_unknown_train`: Raises 404.
- `test_topological_bypasses_active_snapshot`: Verifies snapshot isolation.
- `test_topological_bypasses_ambiguous_identity`: Deterministic resolution for duplicate train records.

## 24. Approval Gate
This discovery document is submitted for review. Do not proceed to implementation (Phase 38) until explicitly authorized.
