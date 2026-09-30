# Phase 68 — Discovery

## Candidate Generation
To identify a genuinely novel structural metric, we examined the topology of the undirected `RailwayNetworkEdge` graph, specifically seeking higher-order structural motifs that complement recent discoveries.

We generated the following candidates:
1. **Station Topological Branching Factor (Local Betti Number 0)**: The number of connected components in the subgraph induced by a station's neighborhood. It measures how many independent, non-intersecting corridors radiate from a station.
2. **Edge Topological Quadrangle Support (Chordless C4 Participation)**: The exact number of chordless 4-cycles (C4) that contain a given edge. It measures the number of distinct "parallel corridors" or "ladder-like" topological redundancies that bypass the edge using exactly 3 hops, without being short-circuited by a triangle.
3. **Station Topological Eccentricity**: The maximum shortest-path distance from a station to any other reachable station in the network.
4. **Edge Topological Dispersion**: The density of connections exclusively among the common neighbors of an edge.

## Rejected Candidates

### Candidate: Station Topological Eccentricity
- **Why considered**: Identifies the absolute topological center and extreme periphery of the network.
- **Overlapping phase(s)**: Phase 64 (Topological Perimeter Expansion) measures a similar concept for train routes.
- **Derivability analysis**: Cannot be derived from existing endpoints, but clients could theoretically piece it together if they aggressively map shortest paths.
- **Performance concern**: Requires $O(V \cdot (V+E))$ computation (all-pairs shortest path or $V$ BFS traversals). While feasible in Python ($\approx 1.5 \times 10^8$ operations), it scales poorly.
- **Rejection reason**: Performance risks and overlap with existing path-based perimeter concepts.

### Candidate: Station Topological Branching Factor
- **Why considered**: Beautifully elegant metric ($O(V \cdot d_{max}^2)$) measuring the number of isolated branching corridors radiating from a hub.
- **Overlapping phase(s)**: Phase 33 (Station Neighborhood Triadic Closure), Phase 60 (Strict Local Bridges).
- **Derivability analysis**: A strict local bridge guarantees a component of size 1, and triadic closure measures global neighborhood density, but the exact component count cannot be reconstructed.
- **Performance concern**: None. Executes in <0.01s on Snapshot 2.
- **Rejection reason**: While excellent, it is highly correlated with degree and local bridges. A station with 4 strict local bridges necessarily has at least 4 neighborhood components. We want something that reveals structures deeper than 1-hop branching.

### Candidate: Edge Topological Dispersion
- **Why considered**: Measures whether the common neighbors of an edge are connected to each other (clique) or disconnected (structural holes).
- **Overlapping phase(s)**: Phase 67 (Edge Topological Trussness), Phase 33 (Triadic Closure).
- **Derivability analysis**: Heavily relies on the exact same common-neighbor set as Phase 67 triangle support. 
- **Rejection reason**: Too conceptually close to existing triadic and k-truss metrics.

## Selected Analytic
**Edge Topological Quadrangle Support**

## Endpoint
`GET /api/v1/network/edges/{from_station_code}/{to_station_code}/topological-quadrangle-support`

## Problem Statement
Railway networks frequently feature "grid-like" or "ladder-like" topologies (parallel mainlines with periodic cross-connections). In such structures, pure triangular redundancy (measured by Phase 67 Trussness or Phase 33 Triadic Closure) is often zero. 

If a track segment is closed, operations rely on alternate corridors. If an alternate corridor forms a triangle, the detour is 2 hops. If it forms a grid, the detour is 3 hops (a quadrangle). Phase 65 (Resilience Detour) can tell us if the *shortest* detour is 3 hops, but it does not tell us *how many* parallel 3-hop options exist. 

Edge Topological Quadrangle Support counts the exact number of chordless 4-cycles containing an edge, precisely quantifying this non-triangular, grid-based structural redundancy.

## Formal Definition
For a canonical undirected edge $e = (u, v)$ in graph $G = (V, E)$:

1. Let $N(u)$ be the neighbors of $u$, and $N(v)$ be the neighbors of $v$.
2. The exclusive neighborhood of $u$ with respect to $v$ is $N_{ex}(u) = N(u) \setminus N(v) \setminus \{v\}$.
3. The exclusive neighborhood of $v$ with respect to $u$ is $N_{ex}(v) = N(v) \setminus N(u) \setminus \{u\}$.
4. The **Quadrangle Support** of $e$ is the number of edges existing between the set $N_{ex}(u)$ and the set $N_{ex}(v)$.

Each such edge $(x, y)$ where $x \in N_{ex}(u)$ and $y \in N_{ex}(v)$ forms exactly one chordless 4-cycle: $u - x - y - v - u$. It is guaranteed to be chordless because $x \notin N(v)$ and $y \notin N(u)$.

## Graph Semantics
- Graph is constructed from active canonical undirected `RailwayNetworkEdge` records for the snapshot.
- Edges are unweighted and topological.
- Self-loops are excluded.
- Directionality is ignored (canonicalized).

## Data Semantics
The metric purely reflects historical timetable topology. It does **not** indicate:
- Physical track switching capability
- Passenger demand on the parallel routes
- Train scheduling feasibility on the detour
- Geographic straight-line parallelism

## Novelty / Derivability Audit
- **Phase 67 (Trussness)**: Measures $k$-truss embedding based strictly on triangles (length 3 cycles). Quadrangle support measures length 4 chordless cycles. They are orthogonal topological motifs.
- **Phase 65 (Resilience Detour)**: Computes the *minimum* alternative path length. If the detour is 3, Quadrangle Support is $\ge 1$. However, Phase 65 does not count the number of such paths. Quadrangle support reveals the *width* (redundancy) of this specific grid-like topology.
- **Phase 60 (Strict Local Bridges)**: A strict local bridge has 0 triangles. It might have 0, 1, or 10 quadrangles. 
- **Derivability**: No existing API exposes edges between exclusive neighborhoods. It cannot be reconstructed without downloading the entire graph.

## Real Snapshot 2 Feasibility
An isolated benchmark script was executed against the real PostgreSQL Snapshot 2.
- **Canonical Edges**: 10,195
- **Expected Result Cardinality**: 10,195 rows
- **Actual Runtime**: 0.0071s in pure Python.
- **Distribution**:
  - Support 0: 9,505 edges
  - Support 1: 604 edges
  - Support 2: 71 edges
  - Support 3: 14 edges
  - Support 4: 1 edge
- The graph materialization is trivial to integrate into `RailwayGraphBuild`.

## Complexity
For an edge $(u, v)$, computing exclusive neighborhoods takes $O(d(u) + d(v))$ using hash sets. 
Counting edges between the sets takes $O(|N_{ex}(u)| \cdot |N_{ex}(v)|)$ checks, which is bounded by $O(d_{max}^2)$.
Total complexity for all edges is $O(E \cdot d_{max}^2)$. 
Given $E \approx 10,000$ and average degree $\approx 2.4$, this is effectively $O(E)$ in practice.

## Performance Safety
- **No path enumeration**: The algorithm only inspects 1-hop neighborhoods and their immediate intersections.
- **No N+1 SQL**: The entire canonical graph is loaded in a single query (existing behavior) and processed in memory.
- **Materialization**: The $O(E \cdot d_{max}^2)$ operation takes $<0.01$ seconds and easily fits within the existing async materialization worker.

## API Design
**Endpoint**: `GET /api/v1/network/edges/{from_station_code}/{to_station_code}/topological-quadrangle-support`

**Response**:
```json
{
  "from_station_code": "STN1",
  "to_station_code": "STN2",
  "quadrangle_support": 2
}
```

**Errors**:
- 400 if `from_station_code == to_station_code`
- 404 if edge does not exist
- 503 if graph build is pending/failed

## Materialization / Database Design
Table: `railway_network_edge_topological_quadrangle_support`
- `graph_build_id` (FK)
- `station_a_id` (FK)
- `station_b_id` (FK)
- `quadrangle_support` (Integer)

Constraints:
- `station_a_id < station_b_id`
- Unique `(graph_build_id, station_a_id, station_b_id)`

## Test Strategy
- **Graph A (Single Edge)**: Support = 0.
- **Graph B (Triangle)**: Support = 0 (exclusive neighborhoods are empty).
- **Graph C (Square A-B-C-D-A)**: Support for every edge = 1.
- **Graph D (Grid)**: Verify support for internal edges (2) vs boundary edges (1).
- **Graph E (Chorded Square)**: If a square has a diagonal (triangle), the quadrangle support drops to 0 because the neighborhoods are no longer exclusive.

## Overlap Audit
- **Phase 33 (Triadic Closure)**: Focuses on triangles. Quadrangle Support strictly filters out triangles via exclusive neighborhoods.
- **Phase 65 (Resilience Detour)**: Focuses on the minimum path distance upon failure. Quadrangle support counts a specific structural motif (chordless 4-cycles) independent of whether a longer/shorter path exists elsewhere.
- **Phase 67 (Trussness)**: Evaluates recursive embedding in dense triangular meshes. Quadrangle Support evaluates embedding in sparse grid/ladder meshes. 

The metric exposes completely distinct topological information that clients cannot synthesize.

## Implementation Boundary
Future implementation would:
- Create the SQLAlchemy model and Alembic migration.
- Add the metric computation strictly to `RailwayGraphBuild`.
- Implement the read-only service and API endpoint.
- Provide full test coverage.

Implementation will **not** modify train routing, demand logic, or real-time systems.

STATUS: DISCOVERY ONLY — IMPLEMENTATION NOT APPROVED
