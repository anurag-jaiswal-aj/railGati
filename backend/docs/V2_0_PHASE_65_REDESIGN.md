# RailGati V2.0 Phase 65 Redesign
## Edge Topological Resilience Detour (Materialized Analytics)

**Status:** RE-DESIGN REQUIRED — DISCOVERY/ARCHITECTURE ONLY

---

### 1. Current Problem
The dynamic implementation of Phase 65 via standard PostgreSQL `WITH RECURSIVE` CTE was rejected due to severe state-expansion flaws on dense networks.
Standard SQL `UNION` recursively deduplicates based on the exact query state. Because standard BFS in SQL requires maintaining the `depth` as part of the state, `UNION` only deduplicates identical `(node, depth)` tuples, failing to deduplicate identical nodes reached globally at differing depths. In the active nationwide network, querying highly interconnected nodes forces the same station to re-expand continuously. This triggers recursive exponential simple-path evaluation limits, driving up memory footprints until the PostgreSQL engine forcibly terminates the connection under resource pressure (`server closed the connection unexpectedly`).

### 2. Feasibility Evidence (Real Snapshot 2 Graph Validation)
A rigorous read-only Python benchmark script evaluated the live Snapshot 2 undirected railway graph:
- **Unique station vertices:** 8,537
- **Canonical undirected structural edges:** 10,195
- **Connected components (Global):** 2
- **Structural bridges (cut-edges):** 1,187
- **Non-bridge edges:** 9,008
- **2-edge-connected components (2-ECC):** 1,189
- **Largest 2-edge-connected component size:** 7,004 vertices
- **Average 2-edge-connected component size:** 7.18 vertices
- **Performance:** Exact graph extraction, Tarjan's bridge evaluation, and 9,008 subsequent exact BFS traversals executed cleanly in **~7.0 seconds** wall-clock time with a peak memory footprint of **18.68 MB**.

### 3. Formal Exact Metric
For an undirected structural edge $e=\{A,B\}$:
- $G$ = active snapshot's undirected structural timetable graph.
- $G-e$ = the graph strictly after removing BOTH reciprocal directed `RailwayNetworkEdge` representations ($A \rightarrow B$ and $B \rightarrow A$), assuming both exist.
- `detour_distance(e)` = shortest unweighted path length from $A$ to $B$ strictly in $G-e$.
- If no path exists, `detour_distance` = `null` and `is_structural_bridge` = `true`.
- Otherwise, `is_structural_bridge` = `false` and `detour_distance` guarantees the mathematically exact minimum replacement path length.
- **Cycle Relationship:** `shortest_cycle_length` = `detour_distance + 1` natively for any non-bridge edge. Bridge detection establishes edges not resident in any cycle.

### 4. Proposed Precomputation Algorithm
The solution strictly executes a multi-stage graph-theoretic analysis within a native Python runtime exactly once per graph build:
1. **Graph Extraction & Canonicalization:** `RailwayNetworkEdge` directional rows are loaded and converted into one uniform undirected adjacency list. Self-edges are explicitly discarded. Reciprocal targets seamlessly collapse into one canonical $A < B$ representation.
2. **Tarjan's Bridge Detection ($O(V+E)$):** Evaluated strictly once globally. Safely identifies all cut-edges (structural bridges) in $G$. These edges receive `detour_distance = null`.
3. **2-Edge-Connected Component Decomposition:** The graph $G - \text{bridges}$ decomposes into completely independent 2-edge-connected components.
4. **Exact BFS ($O(V_{ecc} + E_{ecc})$ per edge):** For every non-bridge edge $e$, an exact unweighted Breadth-First Search executes safely in Python. Crucially, the BFS traversal is mathematically constrained **strictly inside the 2-edge-connected component** containing $e$. This strictly avoids global scanning and prevents path-enumeration explosion, providing the exact optimal path utilizing native $O(1)$ visited sets.
- **Memory Complexity:** $O(V+E)$ exactly to maintain the structures.
- **Worst-Case Time Complexity:** $\sum_{e \in E_{non\_bridge}} O(V_{ecc} + E_{ecc})$, which for real rail topologies reliably evaluates bounded clusters in seconds.

### 5. Final Data Model Recommendation
A new dedicated derived analytics table will be created. The repository currently maintains `dataset_snapshots` and `railway_graph_builds`. `railway_network_edges` holds no `id` primary key, meaning a mapping table must definitively isolate canonical station IDs and lifecycle bounds.

**Table:** `railway_network_edge_resilience`
- `timetable_snapshot_id`: Integer, FK to `dataset_snapshots.id`.
- `graph_build_id`: Integer, FK to `railway_graph_builds.id`.
- `station_a_id`: Integer, FK to `stations.id`.
- `station_b_id`: Integer, FK to `stations.id`.
- `detour_distance`: Integer (nullable).
- `detour_exists`: Boolean (non-null).
- `is_structural_bridge`: Boolean (non-null).
- `created_at`: Datetime.

**Uniqueness Invariants:** 
- Canonical Station Ordering: `station_a_id < station_b_id`.
- Unique Constraint: `UNIQUE(graph_build_id, station_a_id, station_b_id)`.
- Exact snapshot isolation ensures zero duplication. Reciprocal directional edges naturally share one analytical result row natively without duplication ambiguity.

### 6. Build Failure Semantics
The precomputation runs **after** `RailwayNetworkEdge` insertion and **before** `RailwayGraphBuild` status transitions to `COMPLETED`.
- Atomicity: The BFS computation and bulk insertion execute together within the active graph-build lifecycle transaction boundary.
- If resilience analysis errors, the entire Graph Build lifecycle safely cascades to `FAILED`. No partially materialized dataset or missing analytics table can ever be queried or served through the API as a "COMPLETED" build.

### 7. API Lookup Design
**Endpoint:** `GET /api/v1/network/edges/{from_station_code}/{to_station_code}/topological-resilience-detour`
The API completely removes on-demand computation traversals in favor of a sub-millisecond lookup:
1. `from_station_code` and `to_station_code` mapped to canonical $A$ and $B$.
2. Lookup active `dataset_snapshots.id` and its `COMPLETED` `railway_graph_builds.id`.
3. Filter `railway_network_edge_resilience` against canonical bounds.
- **404 Behavior:** Standard response if the stations do not exist, the structural edge does not exist, or the completed graph build resilience row is missing.
- **Success:** Yields `null`/`true` for cut-edges and an exact positive integer for alternative non-bridges.

### 8. Migration and Backfill Plan
- **Migration:** A standard Alembic migration introduces `railway_network_edge_resilience` and necessary structural canonical indexes.
- **Backfill:** A dedicated management command (CLI script) executes the Tarjan/BFS Python pipeline on demand strictly targeted at the existing `COMPLETED` Snapshot 2 Graph Build to populate the database without requiring an entire snapshot regeneration.

### 9. Overlap Audit
- **Phase 34 (Transit Articulation):** Measures node severance resulting in graph division. Phase 65 natively targets *specific physical adjacencies* (edge resilience), finding exact alternate path lengths.
- **Phase 60 (Strict Local Bridges):** Identifies overlapping 1-hop sequences for one station. Phase 65 computes true structural cut-edges across the entire connected network topology.
- **Phase 62 (Shortest-Path Divergence):** Measures macro-distance from Start to End terminal. Phase 65 strictly computes adjacency detours directly around an existing edge.
- **Phase 64 (Topological Perimeter):** Measures graph traversal footprint size.

### 10. Document Status
STATUS: RE-DESIGN REQUIRED — DISCOVERY/ARCHITECTURE ONLY
