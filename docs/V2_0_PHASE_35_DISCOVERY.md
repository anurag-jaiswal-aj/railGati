# RailGati V2.0 Phase 35 Discovery

## 1. Phase Objective
The objective of Phase 35 is to discover, validate, and formally define exactly ONE new railway-network intelligence capability that introduces a materially distinct analytical dimension. The capability must be purely derived from the historical timetable, adhere to the ₹0 budget constraint, and be computationally feasible in PostgreSQL.

## 2. Candidate Capability
**Network Station 2-Hop Reachability Expansion Analytics**

Proposed API endpoint:
`GET /api/v1/network/stations/{station_code}/reachability-expansion`

## 3. Problem/Question Answered
This metric answers: *How rapidly does the scheduled railway network branch out or "fan out" from this station?*
It measures the topological growth rate of the network frontier from distance 1 (immediate neighbors) to distance 2 (neighbors of neighbors). A high ratio indicates the station serves as a gateway to a highly branched, expansive sub-network. A low ratio (≤ 1.0) indicates the station primarily feeds into linear corridors or terminal dead-ends.

## 4. Candidate Exploration
During discovery, multiple categories were explored, including train-service overlap, edge bypass routing, and connected components.
- Bypasses (express vs. local routes on an edge) were rejected because they merely adapt the alternate-path dependency logic already solved in Phase 34, violating the distinction requirement.
- Full connected-component sizes (global reachability) were rejected because unbounded recursive CTEs over the whole active graph are computationally dangerous.
- Bounded 2-hop expansion was selected because it is perfectly bounded, extremely fast to compute natively in SQL, and introduces a foundational network-science concept (Neighborhood Expansion Rate) untouched by previous phases.

## 5. Explicit Overlap Audit against Phases 1–34
- **vs Hub Centrality (Phase 5):** Phase 5 ranks stations by total degree or volume. Expansion measures the *derivative* (ratio) of network breadth at distance 2, not the raw node size.
- **vs Triadic Closure (Phase 33):** Phase 33 measures connections *within* $N_{out}$ (homophily/clustering). Expansion measures completely *new* stations accessible beyond $N_{out}$ (graph frontier growth).
- **vs Outbound Dominance (Phase 28):** Phase 28 measures the skew of train volume toward a single adjacent edge. Expansion relies purely on unique station counts, ignoring volume.
- **vs Transit Articulation (Phase 34):** Phase 34 evaluates bypass redundancy between $N_{in}$ and $N_{out}$. Expansion evaluates outbound depth penetration.

## 6. Why the Selected Capability is Distinct
It is the first metric in RailGati to quantify bounded network-frontier growth (the ratio of the 2-hop boundary size to the 1-hop boundary size).

## 7. Exact Semantics
For a target station $S$ in the active timetable:
1. **$N_1(S)$ (1-Hop Frontier):** The set of all unique stations immediately following $S$ in any scheduled train route.
2. **$N_2(S)$ (2-Hop Frontier):** The set of all unique stations immediately following any station in $N_1(S)$, with the strict exclusions:
   - The station $S$ itself is excluded (no loops back to origin).
   - Any station already present in $N_1(S)$ is excluded (only strictly new frontier nodes are counted).
3. **Expansion Ratio:** $|N_2(S)| / |N_1(S)|$.

## 8. Mathematical Definition
Let $E$ be the set of active directed edges $(u, v)$ in the timetable graph.
- $N_1(S) = \{ v \mid (S, v) \in E \}$
- $N_2(S) = \{ w \mid \exists v \in N_1(S) : (v, w) \in E \} \setminus (N_1(S) \cup \{S\})$
- `expansion_ratio` = $|N_2(S)| / |N_1(S)|$

## 9. Data Dependencies
- Depends strictly on the `train_stop_observations` table to establish scheduled edges.
- Depends on `stations` and `station_observations` for identity and naming.

## 10. Snapshot Semantics
- Timetable graph derivation must use the globally active timetable snapshot.
- Station metadata resolution must strictly scope to the globally active station snapshot.

## 11. API Proposal
```
GET /api/v1/network/stations/{station_code}/reachability-expansion
```

## 12. Response Fields
```json
{
  "station_code": "MGS",
  "station_name": "Mughal Sarai Junction",
  "timetable_snapshot_id": 2,
  "n1_count": 8,
  "n2_count": 7,
  "expansion_ratio": 0.875
}
```

## 13. Error Semantics
- **404 Not Found:** Target station not found in the active station snapshot.
- **503 Service Unavailable:** No active timetable snapshot available.
- **400 Bad Request:** `n1_count == 0` (e.g., a terminal station with no outbound departures). The ratio is mathematically undefined.

## 14. Query/Algorithm Design
Implemented natively in PostgreSQL using CTEs:
1. `n1` CTE: Select distinct successor stations for $S$.
2. `n2` CTE: Select distinct successor stations for `n1`, applying `WHERE station_id != S AND station_id NOT IN (SELECT id FROM n1)`.
3. Compute counts of `n1` and `n2`, avoiding sequential scans by relying on existing composite index bounds.

## 15. Complexity Analysis
The algorithm is bounded strictly to $O(|N_1| \times D_{out(N_1)})$. Because the depth is strictly capped at $K=2$, the candidate generation scales with the immediate neighborhood degree rather than the full graph size $O(V+E)$. This avoids the exponential explosion risk of unbounded recursion.

## 16. Worst-Case Behavior
The worst case occurs at a massive hub where $N_1$ is large, requiring index lookups for each neighbor. Because maximum physical railway degree is naturally bounded (typically $< 20$), the query executes well within sub-second thresholds.

## 17. Performance Analysis
- Validated via `EXPLAIN ANALYZE` natively on PostgreSQL.
- Execution heavily leverages the existing `ix_train_stops_snapshot_station` index.
- Execution time for MGS (one of the largest hubs) is approximately ~4.5ms, with zero sequential table scans.

## 18. Real Snapshot 2 Validation
Verified on the active Snapshot 2 dataset:
- **MGS (Mughal Sarai Junction):** N1 = 8, N2 = 7. Ratio = 0.88. (A massive hub where radiating corridors quickly stabilize, meaning fewer *new* stations appear at distance 2).
- **BYS (Barsali):** N1 = 3, N2 = 3. Ratio = 1.00. (A standard linear progression with equal expansion).
- **HWH (Howrah):** N1 = 4, N2 = 4. Ratio = 1.00.
- **XX-BECE (Bhilai East Cabin):** N1 = 1, N2 = 2. Ratio = 2.00. (A junction point where a single inbound path explicitly branches out to two distinct outbound destinations).

## 19. Boundary Cases
- **Terminal Stations:** $N_1 = 0$. Endpoint will return HTTP 400 (Ratio undefined).
- **Linear Dead-ends:** $N_1 = 1$, but that neighbor has no outbound edges, yielding $N_2 = 0$. Ratio = 0.0 (Network collapses).
- **Closed Loops:** If a station loops back immediately to itself or to $N_1$, those are explicitly excluded from $N_2$ to prevent artificial expansion inflation.

## 20. Non-Goals
This metric measures scheduled topological graph branching. It does NOT claim:
- physical track junction layout geometry;
- passenger transfer capability or ticketing rules;
- route congestion or flow volume.

## 21. ₹0 Constraints
Evaluates purely inside PostgreSQL on the existing dataset. Zero external dependencies.

## 22. Implementation Boundaries
- Phase 35 must be implemented in isolation.
- No new indexes are required.
- Do not implement until Phase 35 discovery is fully approved.

## 23. Planned Tests
1. Normal expansion (N1 > 0, N2 > 0).
2. Terminal station (N1 = 0) yielding HTTP 400.
3. Network collapse (N2 = 0) yielding Ratio 0.0.
4. Exclusions (S itself, and N1 stations) are correctly omitted from N2.
5. Duplicate trains do not artificially inflate N1 or N2 counts.
6. Unknown station yields HTTP 404.
7. Active station and timetable snapshot logic correctly scopes data and prevents stale leaks.

## 24. Approval Gate
This document validates a mathematically distinct, performance-safe, and real-data-verified capability for Phase 35.
