# V2.0 Phase 62 — Discovery

## 1. Objective
Discover and propose the next genuinely non-derivable historical timetable graph structural capability for RailGati V2.0. The proposal must strictly adhere to the PostgreSQL/SQLAlchemy architecture, the ₹0 budget constraint, and the mathematical boundaries established by Phase 15–61. It must avoid subjective language and geographic/passenger assumptions.

## 2. Existing Capability Boundary
A rigorous audit of the Phase 15–61 codebase establishes the current analytical boundaries:
- **Phase 17 (Network O-D Travel Time):** Computes minimum *temporal* scheduled travel time (minutes). It ignores structural hop distance.
- **Phase 19 & 52 (Reversals/Return-Service):** Evaluates exact full-route reversals.
- **Phase 43 (Max Shared Sub-Route):** Computes maximum contiguous shared structural sequences in the *same* direction.
- **Phase 50 (Temporal Order Inversions):** Computes unordered permutations of shared station temporal visits.
- **Phase 56 (Topological Transition Continuity):** Evaluates bypass edges $A \rightarrow C$ for a sequence $A \rightarrow B \rightarrow C$.
- **Phase 60 & 61 (Strict Local Bridges & Single-Station Intersections):** Evaluate strict 1-hop isolated overlaps.

## 3. Candidate A
- **Definition:** Train Route Structural Shortest-Path Divergence. For target Train $T$, calculates $L_{actual} = |V(T)| - 1$ (the actual number of structural edges traversed) and $L_{shortest}$, which is the absolute minimum structural path length (in unweighted hops) between $T$'s Start terminal and End terminal in the entire active network graph. Outputs the absolute difference and ratio.
- **Proposed endpoint:** `GET /api/v1/network/trains/{train_number}/structural-shortest-path-divergence`
- **Closest existing phases:** Phase 17 (Network OD Travel Time), Phase 36 (Transfer-Free Reachability).
- **Derivability audit:** Phase 17 calculates optimal scheduled temporal duration (minutes), which fundamentally diverges from unweighted structural hops (a 5-hop route can be temporally faster than a 3-hop route). No existing capability exposes global unweighted structural shortest path lengths. Non-derivable.
- **Overlap audit:** Structurally different from Phase 17 (temporal) and Phase 43/45 (route similarity). It introduces a macro-level directness metric.
- **Performance feasibility:** Feasible in PostgreSQL via a standard recursive CTE anchored at `Start` and terminating at `End`. For sparse railway graphs, BFS recursive CTEs execute reliably in bounded time without O(N^2) global scans.
- **Decision:** **SELECTED**.

## 4. Candidate B
- **Definition:** Train Route Contiguous Sub-Sequence Reversals. Identifies candidate trains $U$ that traverse a contiguous sequence of at least 3 stations present in target train $T$, but in the exact reverse order.
- **Proposed endpoint:** `GET /api/v1/network/trains/{train_number}/contiguous-sub-sequence-reversals`
- **Closest existing phases:** Phase 43 (Max Shared Sub-Route), Phase 50 (Temporal Order Inversions), Phase 19 (Directional Reversals).
- **Derivability audit:** Phase 50 exposes a scalar integer of unordered temporal inversions, irreversibly destroying contiguous adjacency properties. Phase 43 is strictly unidirectional. A client cannot extract contiguous backward paths.
- **Overlap audit:** Bridges Phase 43 and Phase 50 by enforcing contiguous structural adjacency during reversal.
- **Performance feasibility:** Set-based but SQL run-length encoding logic is moderately complex.
- **Decision:** Rejected (Candidate A offers a broader macro-structural property).

## 5. Candidate C
- **Definition:** Train Sequence Junction Divergences. For every consecutive triplet $A \rightarrow B \rightarrow C$ in target train $T$, computes the number of distinct canonical stations $D$ ($D \neq C$) where a sequence $A \rightarrow B \rightarrow D$ exists in the active network.
- **Proposed endpoint:** `GET /api/v1/network/trains/{train_number}/sequence-junction-divergences`
- **Closest existing phases:** Phase 56 (Topological Transition Continuity).
- **Derivability audit:** No endpoint projects the divergent branches $D$ off an established $A \rightarrow B$ path.
- **Overlap audit:** Clean boundary. Evaluates alternate outgoing branches instead of sequence continuity.
- **Performance feasibility:** Highly performant inner join.
- **Decision:** Rejected (Slightly too localized).

## 6. Candidate D
- **Definition:** Train Route Terminal-Anchored Re-entry (Lasso Motifs). Identifies if a target train $T$ ever traverses a station that belongs to the structural 1-hop neighborhood of its Start terminal, excluding the Start terminal itself.
- **Proposed endpoint:** `GET /api/v1/network/trains/{train_number}/terminal-lasso-motifs`
- **Closest existing phases:** Phase 26 (Train Topology Loops).
- **Derivability audit:** Phase 26 checks exact station revisits (pure loops). No endpoint evaluates a train's entire path against the 1-hop neighborhood of a specific terminal.
- **Overlap audit:** Extends loop detection to neighborhood reentry.
- **Performance feasibility:** Simple set intersection between $V(T)$ and $N(T.start)$.
- **Decision:** Rejected.

## 7. Candidate E
- **Definition:** Train Route Terminal Structural Dependency. Evaluates if the Start terminal of target train $T$ can still reach the End terminal of $T$ in the global active network if the exact sequence of vertices $V(T)$ is completely removed from the graph.
- **Proposed endpoint:** `GET /api/v1/network/trains/{train_number}/terminal-structural-dependency`
- **Closest existing phases:** Phase 36 (Transfer-Free Reachability).
- **Derivability audit:** Global connectivity after removing a specific subgraph is impossible to derive from any 1-hop or 2-hop snapshot capabilities.
- **Overlap audit:** Clean boundary.
- **Performance feasibility:** Requires global recursive CTE pathfinding excluding a variable exclusion set. Performance is riskier than Candidate A.
- **Decision:** Rejected.

## 8. Selected Capability
- **Neutral name:** Train Route Structural Shortest-Path Divergence
- **Exact endpoint:** `GET /api/v1/network/trains/{train_number}/structural-shortest-path-divergence`
- **Formal mathematical definition:**
  For target train $T$ in an active snapshot:
  Let $S$ be the Start terminal station and $E$ be the End terminal station of $T$.
  Let $L_{actual} = |V(T)| - 1$, representing the exact number of structural edges traversed by $T$.
  Let $L_{shortest}$ be the minimum length (in structural edges) of any path from $S$ to $E$ existing in the entire active network graph (independent of any single train).
  Outputs $L_{actual}$, $L_{shortest}$, the absolute difference $(L_{actual} - L_{shortest})$, and the divergence ratio $(L_{actual} / L_{shortest})$.
- **Entity/occurrence semantics:** Based strictly on historical timetable structural connectivity (unweighted graph). 
- **Snapshot semantics:** Path evaluation is strictly confined to edges existing within the same active snapshot.
- **Duplicate semantics:** Repeated consecutive stops or cyclic loops in $T$ contribute natively to $L_{actual}$ since they are traversed edges.
- **Deterministic ordering:** Standard single-object response.
- **Explicit non-claims:** Does NOT measure temporal duration, physical geographical meandering, passenger route preference, or infrastructure track length.
- **Expected response fields:** `train_number`, `timetable_snapshot_id`, `start_station_code`, `end_station_code`, `actual_structural_edges`, `shortest_structural_edges`, `divergence_absolute`, `divergence_ratio`.
- **SQL strategy:** A recursive CTE anchored at the Start terminal, expanding level-by-level across all active snapshot structural edges until the End terminal is reached. The CTE will maintain a `visited` array to prevent infinite loops and bound execution.

## 9. Strict Derivability Audit
Could a client reconstruct the complete intended result exactly from Phase 15–61?
**NO.** No existing RailGati endpoint exposes the global unweighted structural shortest path length between two arbitrary stations. The closest metric, Phase 17 (Network OD Travel Time), relies explicitly on temporal schedules (minutes), and a temporally optimal route frequently differs from a structurally optimal (minimum hop) route. Since the unweighted hop distance is completely absent from all prior responses, it is mathematically non-derivable via sorting, filtering, or grouping existing payloads.

## 10. Strict Overlap Audit
Is this merely a more detailed projection of an existing metric?
**NO.** Phase 17 evaluates temporal flow. Phase 43 evaluates structural similarity between explicitly scheduled train sequences. Phase 36 identifies if a 0-transfer path exists. Phase 62 introduces an entirely new global property: comparing a specific scheduled service against the theoretical topological floor of the network graph.

## 11. Performance Feasibility
The recursive CTE acts as a standard Breadth-First Search (BFS). By anchoring strictly at $T.start$ and expanding only across edges within the specific snapshot, the query remains bounded. Furthermore, the BFS can terminate immediately once $T.end$ is reached at depth $N$. Given typical timetable graphs, this executes well within acceptable thresholds (e.g., < 50ms) without risking $O(N^2)$ global Cartesian products.

## 12. Test Strategy
- Basic direct train ($L_{actual} = L_{shortest}$).
- Divergent train ($L_{actual} > L_{shortest}$).
- Disconnected graph scenario (no alternative path exists).
- Repeated sequence loops inflating $L_{actual}$.
- Snapshot isolation enforcement.
- 404 for unknown train.

## 13. Real Snapshot 2 Validation Strategy
A real train (e.g., `15906`) will be targeted in Snapshot 2. The recursive CTE will compute $L_{shortest}$ natively, and we will verify the result by independently querying the raw `train_stop_observations` table to confirm that $L_{actual}$ matches the exact stop count minus 1, and that an alternative sequence of trains exists establishing the shorter $L_{shortest}$ hop path. No expected values will be invented.

## 14. Phase 62 Scope Boundary
Phase 62 WILL NOT implement temporal shortest paths, geographic distance algorithms (Dijkstra), minimum transfer logic, or contiguous sub-sequence reversals. It is strictly limited to the analytical `GET /api/v1/network/trains/{train_number}/structural-shortest-path-divergence` endpoint.
