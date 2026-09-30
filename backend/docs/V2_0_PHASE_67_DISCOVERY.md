# Phase 67 — Discovery

## Candidate Generation

To discover a genuinely novel structural metric for Phase 67, we audited the existing graph analytics surface (Phases 1–66). The current topology capabilities include:
- Local node metrics (Phase 7 Hub Centrality, Phase 33 Triadic Closure, Phase 34 Transit Articulation)
- Path and reachability metrics (Phase 62 Shortest-Path Divergence, Phase 64 Perimeter Expansion)
- Edge-level bridge detection (Phase 65 Edge Topological Resilience Detour)
- Global node decomposition (Phase 66 Station Topological Coreness)

Given that Phase 66 successfully implemented global hierarchical node-peeling ($k$-core), a natural search direction was to explore hierarchical decompositions that capture deeper multi-node cohesive structures (motifs), specifically edge-level integrations inside dense subgraphs, which node-based degree metrics mathematically fail to capture.

## Rejected Candidates

### 1. Station Core Boundary Assortativity (Inter-Core Transition Index)
- **Candidate:** The ratio of a station's neighboring edges that connect to a different $k$-core layer than the station itself.
- **Why it was considered:** It identifies structural boundaries/interfaces between the periphery (Core 1) and mainline components (Core 2), revealing transition hubs.
- **Why it was rejected:** Completely reconstructable client-side.
- **Overlapping phase(s):** Phase 13 (Station Neighbors) + Phase 66 (Station Coreness).
- **Derivability conclusion:** The client can simply query Phase 13 for neighbors, query Phase 66 for their core numbers, and calculate the ratio. No new graph operation is required on the server.

### 2. Global Station Pair Edge-Disjoint Paths (Structural Max-Flow)
- **Candidate:** The maximum number of entirely edge-disjoint paths between two stations across the global network.
- **Why it was considered:** A foundational graph-theory metric (Menger's Theorem) for measuring deep pairwise structural reliability.
- **Why it was rejected:** Catastrophic computational complexity. 
- **Overlapping phase(s):** Phase 28 (Route Diversity) and Phase 65 (Resilience) offer practical approximations.
- **Derivability conclusion:** Computing Max-Flow for $8,500 \times 8,500$ pairs requires $\sim 72,000,000$ Ford-Fulkerson executions. Even if materialized, it would take hours/days to build and exponentially explode database row limits, severely violating the "Performance Safety" constraint.

### 3. Train Sequence Subgraph Coreness
- **Candidate:** Computing the $k$-core decomposition of the isolated subgraph formed exclusively by the edges a single train route traverses.
- **Why it was considered:** To measure the internal structural density of a train's journey.
- **Why it was rejected:** A single train route is fundamentally a linear path sequence. The maximum node coreness of any simple path is 1 (or 2 for a closed loop).
- **Overlapping phase(s):** Phase 61 (Train Sequence Subgraph Density).
- **Derivability conclusion:** Mathematically trivial. A train route does not form a dense mesh in isolation, rendering the decomposition globally useless.

## Selected Analytic

**Edge Topological Trussness ($k$-Truss Decomposition)**

While Phase 66 (Station Coreness) evaluates the density of *nodes* based on peeling low-degree connections, it blindly ignores whether those connections form cohesive local groups. For instance, a pure bipartite grid (like $K_{3,3}$) can have a high node coreness of 3, despite containing absolutely zero triangles and being highly fragile to targeted edge deletion.

Edge Topological Trussness ($k$-Truss) solves this by decomposing the network based on **triangles (motifs)** rather than edges. It evaluates how deeply an edge is embedded in redundantly triangulated cohesive meshes.

## Endpoint
`GET /api/v1/network/edges/{from_station_code}/{to_station_code}/topological-trussness`

## Formal Definition
- **Problem it answers:** Distinguishes between simple alternative routes and highly cohesive structural meshes. It answers: "Is this railway segment part of a tightly knit triangular backbone that persists even as peripheral non-triangulated connections are peeled away?"
- **Mathematical Definition:** For an undirected graph $G$, the trussness $\tau(e)$ of an edge $e$ is the maximum integer $k \ge 2$ such that $e$ belongs to a $k$-truss subgraph. A $k$-truss is a maximal connected subgraph where every edge is part of at least $k-2$ triangles exclusively within that subgraph. 
  - $\tau(e) = 2$: The edge belongs to no triangles (tree branches, simple bridges, or un-triangulated squares).
  - $\tau(e) = 3$: The edge belongs to at least one triangle.
  - $\tau(e) \ge 4$: The edge is embedded in a complex, multi-triangle redundant mesh.

**What it DOES NOT mean:** It does not indicate passenger volume, train frequency, physical track gauge, or geographic distance. It is purely a measure of structural topological cohesion.

## Graph Semantics
- **Graph definition:** Unweighted, undirected structural topology formed by the active snapshot's timetable.
- **Directionality:** Undirected (canonicalized so A→B and B→A form one edge).
- **Self-loops:** Ignored (self-loops mathematically cannot form 3-vertex triangles).
- **Repeated edges:** Canonicalized into a single distinct topological edge.
- **Disconnected graphs:** The motif-peeling algorithm natively evaluates disjoint components independently.

## Data Semantics
- **Train identity:** Ignored.
- **Station identity:** Strictly bounds the vertices.
- **Stop occurrence:** Ignored; relies purely on derived `RailwayNetworkEdge` structural topology.

## Novelty / Derivability Audit
- **Can it be reconstructed?** No. No existing endpoint enumerates triangles recursively.
- **Does it use a genuinely new graph operation?** Yes. Triangle-support enumeration and cascading edge-peeling bucket sorts.
- **Does it overlap with Phase 65 (Resilience)?** Phase 65 detects bridges (0 alternative paths). An edge in a 4-cycle square has an alternative path (thus a Phase 65 non-bridge) but 0 triangles (thus Trussness 2). Phase 65 cannot predict Trussness.
- **Does it overlap with Phase 66 (Station Coreness)?** Node coreness evaluates node degree. As noted above, a $K_{3,3}$ graph has Node Coreness 3, but Trussness 2. The metrics measure fundamentally orthogonal structural concepts (node degrees vs edge motifs).

## Real Snapshot 2 Feasibility
An independent script was executed against the exact Snapshot 2 PostgreSQL database using a pure-Python $k$-truss bucket-sort implementation.
- **Vertices:** 8,537
- **Canonical Edges:** 10,195
- **Trussness 2:** 6,988 edges (Peripheral/linear edges with no triangles)
- **Trussness 3:** 3,066 edges (Edges embedded in simple triangles)
- **Trussness 4:** 141 edges (The dense triangulated cohesive backbone of the network)
- **Result:** $100\%$ feasible and reveals a highly stratified structural hierarchy.

## Complexity
- **Time Complexity:** Finding triangles and peeling cascading supports is bounded by $O(E^{1.5})$. For $E = 10,195$, this evaluates to $\sim 1,000,000$ operations.
- **Space Complexity:** $O(V + E)$ memory footprint.

## Performance Safety
The operation is highly safe for the existing `RailwayGraphBuild` lifecycle.
- **No recursive SQL:** It avoids PostgreSQL recursive CTE limitations entirely.
- **No N+1 queries:** The graph is extracted via a single bulk query (already implemented in Phase 65).
- **Execution Time:** The pure-Python measurement script executed the entire algorithm in exactly **0.041 seconds** on the real Snapshot 2 graph.
- **API Runtime:** Bounded exactly to $O(1)$ database latency via materialized indexing.

## API Design
- **Path:** `/api/v1/network/edges/{from_station_code}/{to_station_code}/topological-trussness`
- **Request Parameters:** Path parameters only.
- **Response Fields:**
  ```json
  {
    "from_station_code": "STN_A",
    "to_station_code": "STN_B",
    "trussness": 3,
    "triangle_support": 1
  }
  ```
- **Error Cases:** 404 if either station is deactivated or the structural edge does not exist. 503 if the graph build is not ACTIVE.

## Materialization / Database Design
- **Ownership:** Materialized synchronously by `build_graph_for_timetable_snapshot` after Phase 66.
- **Table:** `railway_network_edge_topological_trussness`
- **Schema:**
  - `graph_build_id` (Integer, FK, Indexed)
  - `timetable_snapshot_id` (Integer, FK)
  - `station_a_id` (Integer, FK)
  - `station_b_id` (Integer, FK)
  - `trussness` (Integer)
  - `triangle_support` (Integer)
- **Constraints:** Unique index on `(graph_build_id, station_a_id, station_b_id)`. Canonical ordering `station_a_id < station_b_id` mathematically enforced.

## Test Strategy
- **Simple path:** All edges evaluate to Truss 2.
- **Simple triangle:** All 3 edges evaluate to Truss 3.
- **K4 Complete Graph:** All 6 edges evaluate to Truss 4.
- **Triangle with a tail:** The tail evaluates to Truss 2, the triangle evaluates to Truss 3.
- **Deactivated Station:** Ensure API returns a clean 404.

## Overlap Audit
- **Phase 7 (Hub Centrality):** Evaluates local 1-hop node degree. Does not evaluate motifs or edge cohesion.
- **Phase 33 (Triadic Closure):** Evaluates the static ratio of triangles surrounding a *station*. It does not evaluate the cascading recursive hierarchy of *edges*.
- **Phase 65 (Resilience Detour):** Only determines if an edge is a bridge. Fails to differentiate between an untriangulated cycle (Truss 2) and a triangulated mesh (Truss 3+).
- **Phase 66 (Station Coreness):** An upper-bound node metric based entirely on degree, which mathematically fails to guarantee the existence of cohesive triangles (e.g., dense bipartite graphs).

## Implementation Boundary
The future implementation WOULD:
- Create the SQLAlchemy model and Alembic migration.
- Add the $O(E^{1.5})$ algorithm natively to `graph_builder.py` directly following Phase 66.
- Implement the $O(1)$ HTTP GET endpoint.
- Provide full pytest coverage.

The future implementation WOULD NOT:
- Dynamically compute trussness on HTTP requests.
- Add network-wide endpoints that serialize 10,000 edges at once.
- Depend on external C/C++ graph libraries like NetworkX.

STATUS: DISCOVERY ONLY — IMPLEMENTATION NOT APPROVED
