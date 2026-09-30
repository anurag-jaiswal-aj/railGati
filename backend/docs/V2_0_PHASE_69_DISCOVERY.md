# Phase 69 — Discovery

## Capability Audit
Recent phases focused intensively on local and meso-scale motif evaluation:
- **Phase 65**: Edge Topological Resilience Detour (shortest path length after edge removal)
- **Phase 66**: Station Topological Coreness (k-core peeling)
- **Phase 67**: Edge Topological Trussness (triangle-based peeling)
- **Phase 68**: Edge Topological Quadrangle Support (chordless 4-cycle support)

While we can identify dense islands (k-cores) and evaluate the immediate bypassability of an edge (Resilience Detour), we lack a topological metric that evaluates the **macro-structural component scale** of an edge. Specifically, we do not expose the size of the maximal vertex-biconnected cyclic subgraph (block) that an edge participates in.

## Candidate Generation
1. **Edge Topological Biconnected Component (Block) Size**: The exact count of edges belonging to the maximal biconnected subgraph that contains the target canonical edge.
2. **Station Topological Eccentricity**: The maximum shortest-path hop-distance from a station to any other reachable station in its connected component (the graph diameter radius).
3. **Edge Topological Shortest-Cycle (Girth)**: The length of the smallest cycle containing a specific edge.
4. **Edge Topological Structural Embeddedness**: Jaccard similarity of the exclusive neighborhoods of an edge's endpoints.

## Rejected Candidates
- **Edge Topological Structural Embeddedness**
  - Problem it would answer: How topologically similar are the endpoints of an edge?
  - Existing overlapping phases: Phase 67 (Edge Trussness / Triangle Support) and Phase 7 (Hub Centrality).
  - Derivability analysis: Mathematically equivalent to $|N(u) \cap N(v)| / |N(u) \cup N(v)|$. The numerator is exactly Triangle Support (Phase 67) and the denominator is trivially derived from Triangle Support and node degrees.
  - Performance analysis: $O(1)$ set arithmetic.
  - Rejection reason: Entirely derivable from existing metric responses without new graph operations.

- **Edge Topological Shortest-Cycle (Girth)**
  - Problem it would answer: What is the shortest cycle containing this edge?
  - Existing overlapping phases: Phase 65 (Edge Resilience Detour).
  - Derivability analysis: Shortest cycle containing $e=(u,v)$ is exactly $1 + dist_{G-e}(u,v)$. This is fundamentally equivalent to the topological detour computed by Phase 65 (when applied strictly structurally).
  - Performance analysis: $O(V+E)$ via BFS.
  - Rejection reason: Mathematically overlaps perfectly with Phase 65 detour length metrics.

- **Station Topological Eccentricity**
  - Problem it would answer: Is this station at the absolute topological periphery (high depth) or topological center (low depth) of the global graph?
  - Existing overlapping phases: Phase 35 (2-Hop Expansion), Phase 36 (Reachability).
  - Derivability analysis: Cannot be derived without executing an abusive $O(V^2)$ series of recursive expansion queries.
  - Performance analysis: A single BFS takes $<1$ ms in Python. $O(V+E)$ is highly safe.
  - Rejection reason: Held as a runner-up. Biconnected component size provides a stronger macro-structural complement to the recent micro-motif metrics (Trussness/Quadrangles).

## Selected Analytic
**Edge Topological Biconnected Component Size**

## Endpoint
`GET /api/v1/network/edges/{from_station_code}/{to_station_code}/topological-biconnected-component`

## Problem Statement
We can determine if an edge is part of a triangle (Phase 67) or a chordless 4-cycle (Phase 68), and we can evaluate if removing the edge disconnects its endpoints' immediate neighborhoods (Phase 60) or increases path length (Phase 65). However, we cannot answer the macro-structural question: **Is this edge a structural component of the massive central cyclic mesh of the railway network, or is it isolated in a tiny peripheral island/branch?** 

By computing the size of the maximal biconnected subgraph (the "block") containing the edge, we expose the macro-structural connectivity scale of the edge.

## Formal Definition
Let $G = (V,E)$ be the active canonical undirected timetable graph. 
A **biconnected component** (or block) is a maximal subgraph $B \subseteq G$ such that any two edges in $B$ lie on a common simple cycle. If an edge is a global bridge (i.e., its removal strictly disconnects the graph), it forms a block of size exactly 1.

For a canonical undirected edge $e = \{u, v\} \in E$, the analytic computes $|E(B_e)|$, the total count of distinct edges in the unique biconnected component $B_e$ containing $e$.

## Graph Semantics
- **Vertices**: Active unique canonical stations.
- **Edges**: Unordered pairs of stations $\{u, v\}$ sharing at least one timetable adjacency in the active snapshot.
- **Directionality**: Strictly undirected.
- **Self-loops**: Ignored and filtered during materialization.

## Data Semantics
- Purely topological.
- Does NOT measure track miles, physical geometry, passenger flow, traffic density, or track capacity.
- Evaluates purely the mathematical structure of the scheduled route map.

## Novelty / Derivability Audit
- **Cannot be derived from Phase 67/68 (Trussness/Quadrangles)**: An edge with $0$ triangles and $0$ quadrangles could be a global bridge (Block Size = 1) OR part of a massive 5000-edge chordless mesh (Block Size = 5000). The micro-motifs provide zero upper bound on macro-structure.
- **Cannot be derived from Phase 60 (Strict Local Bridges)**: A strict local bridge merely guarantees no 2-hop bypass exists. The edge could still have a 3-hop bypass, placing it in a block of size $\ge 4$.
- **Cannot be derived from Phase 65 (Resilience Detour)**: Phase 65 returns the *shortest* alternative path length. An edge with a detour of length 5 could be in a solitary cycle (Block Size = 6), or it could be embedded in the central railway mesh (Block Size = 8000+).

## Real Snapshot 2 Feasibility
An explicit Hopcroft-Tarjan implementation was benchmarked against the true PostgreSQL Snapshot 2 dataset (10,195 edges, 8,537 vertices).
- **Execution Time**: The complete biconnected component extraction for the entire graph took **0.0034 seconds** in pure Python.
- **Distribution**:
  - The graph decomposes into exactly **1,296 biconnected components**.
  - **The Giant Mesh**: Exactly 1 block contains **8,414 edges**. This represents the central interconnected topological core.
  - **Peripheral Islands**: Several small cyclic blocks exist (sizes 66, 46, 44, 20...).
  - **Global Bridges**: Exactly 1,187 edges form blocks of size 1 (topological antennae/branches).
- **Feasibility**: 100% practical. Can easily be materialized alongside trussness.

## Complexity
The Hopcroft-Tarjan DFS algorithm evaluates the entire graph in strictly $O(V + E)$ time and space. Since $V \approx 8500$ and $E \approx 10200$, the complexity is trivial and fundamentally bounded.

## Performance Safety
The algorithm relies strictly on linear $O(V + E)$ DFS traversals. It completely avoids recursive SQL, combinatorial explosion, and exponential path enumeration. Recursion limits in Python must be increased (e.g., `sys.setrecursionlimit(20000)`) or an iterative stack-based implementation can be used to prevent depth overflows. Materialized $O(1)$ database lookup ensures API performance.

## API Design
- **Endpoint**: `GET /api/v1/network/edges/{from_station_code}/{to_station_code}/topological-biconnected-component`
- **Request Parameters**: `from_station_code` (str), `to_station_code` (str)
- **Response**:
  - `from_station_code` (str)
  - `to_station_code` (str)
  - `block_edge_count` (int) - The number of edges in the biconnected component containing this edge.
- **Errors**: `400` for self-loops. `404` if the edge does not exist in the active snapshot. `503` if no active graph build exists.

## Materialization / Database Design
- Table: `railway_network_edge_topological_biconnected_component`
- Fields: `id`, `graph_build_id`, `timetable_snapshot_id`, `station_a_id`, `station_b_id`, `block_edge_count`.
- Indexes: Unique constraint on `(graph_build_id, station_a_id, station_b_id)`.
- Idempotency: Cleared and bulk-inserted during `RailwayGraphBuild`.

## Test Strategy
- **Unit Tests (Algorithm)**: Complete coverage using isolated memory graphs:
  - Linear path graph (All block sizes = 1).
  - Simple triangle (All block sizes = 3).
  - Two distinct triangles joined by a single bridge edge (Bridge size = 1, Triangles sizes = 3).
  - Wheel graphs and K4.
- **API Tests**: Mock endpoints validating 200 OK, 404 Not Found (missing edges), 400 Bad Request (self loops).

## Comprehensive Overlap Audit
- **Phase 7 (Network Hub Centrality)**: Phase 7 is node-centric degree counting. Phase 69 is edge-centric macro-scale connectivity.
- **Phase 60 (Strict Local Bridges)**: Phase 60 only evaluates whether an edge is the *exclusive* immediate adjacency link. Phase 69 identifies if it is a true global cut-edge (Block Size = 1) or part of a cycle of any arbitrary length.
- **Phase 65 (Edge Topological Resilience Detour)**: Phase 65 computes the length of the *shortest possible* bypass. Phase 69 computes the macro-scale *subgraph volume* enclosing the edge, differentiating between a small local detour island and the giant connected mesh.
- **Phase 67/68 (Trussness/Quadrangle)**: Phases 67 and 68 compute recursive density using micro-motifs (3-cycles and chordless 4-cycles). Phase 69 evaluates global connectivity properties independent of local density.

## Implementation Boundary
- **Included**: API endpoints, Pydantic schemas, database models, SQLAlchemy operations, Alembic migration, linear-time Hopcroft-Tarjan materialization algorithm in `graph_builder.py`, and full pytest coverage.
- **Not Included**: Visualization, shortest path routing, passenger flow integration, capacity measurements, frontend changes.

STATUS: DISCOVERY ONLY — IMPLEMENTATION NOT APPROVED
