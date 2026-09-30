# RailGati V2.0 Phase 64 Implementation Report
## Train Route Topological Perimeter Expansion

**Status:** IMPLEMENTED AND VALIDATED
**Date:** 2026-09-30

---

### 1. Objective
Implement the V2.0 Phase 64 endpoint to calculate the Train Route Topological Perimeter Expansion, which evaluates the undirected structural boundary of a train's entire station footprint in the active historical timetable snapshot.

### 2. Files Changed
- `src/railgati/api/v1/network.py`
- `src/railgati/api/v1/schemas.py`
- `src/railgati/services/network.py`
- `tests/api/v1/test_network_train_topological_perimeter_expansion.py`
- `tests/services/test_network_train_topological_perimeter_expansion.py`
- `docs/V2_0_PHASE_64_DISCOVERY.md`
- `docs/V2_0_PHASE_64_IMPLEMENTATION_REPORT.md`

### 3. Exact Mathematical Definition
For a target train $T$ in the active snapshot:
- Let $R(T)$ be the set of DISTINCT station identities visited by $T$.
- Let structural adjacency be strictly **UNDIRECTED**: an active `NetworkEdge` $A \to B$ or $B \to A$ establishes adjacency.
- The perimeter $P(T)$ is the set of distinct station identities outside $R(T)$ structurally adjacent to at least one station in $R(T)$:
$$P(T) = \{ X \mid X \notin R(T), \text{ and } \exists S \in R(T) \text{ connecting } S \text{ and } X \text{ in either direction} \}$$
- `route_station_count` = $|R(T)|$
- `perimeter_station_count` = $|P(T)|$
- `perimeter_expansion_ratio` = $\frac{|P(T)|}{|R(T)|}$

### 4. Exact Semantics & Deduplication Rules
- The calculation is completely bounded to the active timetable snapshot.
- Route stations in $R(T)$ are explicitly deduplicated. Repeated or cyclic visits do not inflate the denominator.
- An external perimeter station adjacent to multiple $R(T)$ stations appears exactly once in $P(T)$.
- Reciprocal edges count as a single adjacency.
- Train direction, timing, and `return_train_number` are strictly irrelevant to this undirected graph structural boundary.

### 5. Explicit Non-Semantics (What it does NOT mean)
This metric is strictly a measurement of **historical timetable topology**. It explicitly does **NOT** represent, measure, or guarantee:
- passenger demand or volume
- passenger catchment size
- usable transfer opportunities, transfer availability, or connection quality
- geographic or physical proximity
- operational importance, reliability, or congestion
- network centrality

### 6. Database Query Strategy
Implemented purely as a highly optimized, set-based PostgreSQL query without N+1 loops:
1. `route_stations` CTE identifies the distinct `station_id` set for the train from `train_stop_observations`.
2. `adjacent_stations` CTE `UNION`s results from `railway_network_edges` by matching either `from_station_id` or `to_station_id` against the `route_stations`.
3. `perimeter_stations` CTE applies `EXCEPT SELECT station_id FROM route_stations` to isolate the strict boundary.
4. Final counts and names are resolved in a single step using canonical `station_observations`.

### 7. Edge-Case Behavior Evaluated
- **Unknown Train / Snapshot Miss:** Explicitly yields HTTP 404.
- **One-stop Train:** Correctly computes the single station's boundary, ratio is mathematically sound.
- **Two-stop Train:** Correctly computes combined boundary excluding the two stops.
- **Cyclic Visits:** Deduplicated natively via `SELECT DISTINCT station_id`.
- **Zero Perimeter:** Handles correctly yielding 0 perimeter and 0.0 ratio (preventing division by zero via `route_count` checks).
- **Reciprocal / Shared NetworkEdges:** Deduplicated natively by the `UNION` and `EXCEPT` clauses.
- **Self-Connected Stations:** Natively eliminated because $R(T)$ members are always excluded via `EXCEPT`.

### 8. Focused Test Results
Both service and API layers comprehensively pass all required assertions (10 service tests, 2 API tests, 12 tests total). The test matrix explicitly guarantees:
1. **Basic Perimeter:** A multi-stop route resolves the combined perimeter correctly.
2. **One-Stop Train:** Safely computes the 1-hop undirected expansion.
3. **Two-Stop Train:** Safely computes boundary excluding the 2 stops.
4. **Repeated/Cyclic Visits:** `test_train_perimeter_cyclic` asserts A->B->A->B evaluates `route_station_count = 2`, natively ignoring repetitions.
5. **Shared Perimeter Station:** `MULTIPLE_IN` is connected to A, B, and C, yet appears exactly once in the response.
6. **Reciprocal Edges:** `W` connects to A in both directions (A->W, W->A), yielding exactly one perimeter station.
7. **Internal Route Edge Exclusion:** The sequence A->B->C->D produces edges A-B, B-C. None of A, B, C, D appear in the perimeter list.
8. **Self-Edge Exclusion:** `test_train_perimeter_self_connected` guarantees self-loop edges on route stations vanish due to the global boundary `EXCEPT` clause.
9. **Zero-Perimeter:** Route length > 0 with no external connections safely yields `perimeter_station_count = 0` and `ratio = 0.0`.
10. **Isolated Station:** Completely isolated stations resolve correctly without errors.
11. **Snapshot Isolation:** `test_train_perimeter_snapshot_isolation` proves edges belonging to a different snapshot do not bleed into the active query.
12. **Deterministic Ordering:** `test_train_perimeter_success_basic` strictly checks the array output matches exact alphabetical canonical code ordering.
13. **API Success:** Endpoint success, request parsing, and schema marshaling function flawlessly.
14. **Unknown Train:** API gracefully yields standard 404 behavior.
15. **No Row Multiplication:** Count logic guarantees row multiplication from dense hubs does not inflate `perimeter_station_count`.
16. **Multiple Trains Isolation:** An independent train `T_OTHER` passing through irrelevant nodes does not affect the target train's structural footprint computation.

### 9. Real-Data Validation Results
Executed successfully against the local PostgreSQL snapshot:
- **Long Train (15905):** `route_station_count`=689, `perimeter_station_count`=77, `ratio`=0.1118, `execution`=24.6ms
- **Short Route (11011):** `route_station_count`=95, `perimeter_station_count`=21, `ratio`=0.2211, `execution`=10.8ms
- **Missing Train (00000):** Handled gracefully with 404 response.

The query relies cleanly on standard `train_stop_observations` and composite `railway_network_edges` indices. Operations remain bounded to the specific train's scale, entirely sidestepping full network graph loading.

### 10. Overlap Audit vs Prior Phases
- **Phase 35 (2-Hop Expansion):** Expands locally from one station. Phase 64 establishes the global union boundary of an entire train service's footprint.
- **Phase 39 (Edge Traversal Dispersion):** Measures traversal volumes.
- **Phase 55 (Sequence Subgraph Density):** Measures edges *strictly internal* to the sequence footprint.
- **Phase 58 (Topological Degree Extremes):** Measures discrete extrema along the path.
- **Phase 60 (Strict Local Bridges):** Measures local 2-hop exclusivity.
- **Phase 62 (Shortest-Path Divergence):** Measures path distances.
- **Phase 63 (Junction Through-Service):** Measures routing at specific junctions.

This metric stands fundamentally distinct as the *external structural neighborhood boundary of an entire train's station footprint*.
