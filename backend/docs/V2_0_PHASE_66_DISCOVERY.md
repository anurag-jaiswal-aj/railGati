# Phase 66 — Discovery

## Candidate Generation
The following concepts were evaluated to establish a novel structural analytic:
- Station Transit Articulation / Cut-Vertex Vulnerability
- Edge Redundancy Profile / Max-Flow Disjoint Paths
- Structural Betweenness Centrality
- Station Topological Coreness (k-core decomposition)

## Rejected Candidates
- **Station Transit Articulation**:
  - *Reason Rejected*: Overlaps entirely with Phase 46 (Station Transit Articulation) and Phase 60 (Station Strict Local Bridges). Derivable from existing components.
- **Edge Redundancy Profile / Max-Flow**:
  - *Reason Rejected*: The railway graph's inherent planarity bounds the maximum disjoint paths to $\le 3$. This means the variance is structurally identical to Phase 65 (Edge Topological Resilience Detour), returning only 0, 1, or 2 redundant paths.
- **Structural Betweenness Centrality**:
  - *Reason Rejected*: Fails the performance safety criteria. Pure Python execution of Brandes' algorithm $O(V \cdot E)$ across the 8,500 vertex graph was benchmarked at ~80 seconds, violating the established synchronous transaction limits of the Graph Build lifecycle.

## Selected Analytic
**Station Topological Coreness**
Rationale: It provides a global, recursive measure of structural network cohesion that simple degree metrics cannot capture. A station with high degree (e.g., 5) connected entirely to dead-end leaf stations will correctly decay to a coreness of 1, while a degree 3 station embedded in a triangulated urban mesh will hold a coreness of 3. It distinguishes the true interlinked grid from high-degree peripheral star-nodes.

## Endpoint
`GET /api/v1/network/stations/{station_code}/topological-coreness`

## Formal Definition
The coreness of a vertex $v$ is the largest integer $k$ such that $v$ belongs to the $k$-core of the graph. The $k$-core is the maximal connected subgraph $H$ of $G$ such that every vertex in $H$ has induced degree $deg_H(v) \ge k$.

## Data Semantics
- **Snapshot**: Evaluated exactly on the `ACTIVE` timetable snapshot structural graph.
- **Train/Occurrence/Repetition**: Traversal repetitions by the same train or multiple trains are completely ignored. The graph is unweighted.
- **Edge**: Logical undirected adjacency constructed from `RailwayNetworkEdge` elements.
- **Direction**: Strictly Undirected.
- **Self-Loops**: Discarded. A station cannot contribute to its own coreness limit.

## Novelty / Derivability Audit
This metric cannot be reconstructed from existing Phase 1–65 endpoints. While Phase 7 provides simple Node Degree (Hubs), degree is strictly a local 1-hop property. Coreness requires a global cascading recursive pruning until convergence. A station's coreness is fundamentally independent of its simple degree (e.g., a high-degree station can have a low coreness if its neighbors are easily pruned). 

## Complexity
- **Time**: $O(V + E)$ using the Batagelj-Zaversnik algorithm.
- **Space**: $O(V + E)$ to construct the adjacency list and bin-sort tracking arrays natively in Python memory.

## Real Snapshot 2 Feasibility
Actual database readings confirmed:
- **Vertices**: 8,537
- **Edges**: 10,195 (Canonical Undirected)
- **Precomputation Time**: Exactly **0.01 seconds** natively in Python for the global decomposition. Perfectly safe for integration into the synchronous `RailwayGraphBuild` pipeline.
- **Distribution**:
  - Core 1 (Periphery / Branches): 936 stations
  - Core 2 (Mainline cycles / Corridors): 7,451 stations
  - Core 3 (Dense urban interlinked meshes): 150 stations

## API Design
Request: `GET /api/v1/network/stations/{station_code}/topological-coreness`
Response:
```json
{
  "station_code": "NDLS",
  "coreness": 3,
  "degree": 5
}
```

## Database Design
A new materialized model `RailwayStationTopologicalCoreness`:
- `graph_build_id` (FK)
- `station_id` (FK)
- `coreness` (Integer)
- `degree` (Integer)
Unique Constraint: `(graph_build_id, station_id)`
Indexed for $O(1)$ API lookups.

## Test Strategy
- **Periphery Pruning**: A star graph where the center has degree 5 but leaves have degree 1 must yield a coreness of 1 for all vertices.
- **Dense Mesh**: A fully connected 4-clique must yield a coreness of 3.
- **Disconnected Components**: Separate disconnected components must calculate independently correctly.
- **Missing Build/Station**: Expected 404 / 503 HTTP handling.

## Overlap Audit
Explicitly compared to:
- **Phase 7 (Hubs)**: Evaluates strict raw degree. Fails to account for the structural depth of the neighbors.
- **Phase 58 (Topological Degree Extremes)**: Evaluates the delta of degrees along a train's sequence, completely localized to the adjacent edge.
- **Phase 64 (Topological Perimeter Expansion)**: Measures BFS distance contours from a route, not subgraph structural cohesion.

## Implementation Boundary
Future implementation would place the Batagelj-Zaversnik $O(V+E)$ algorithm immediately following the Tarjan/BFS processes inside `services/graph_builder.py`. The resulting arrays would bulk insert into `RailwayStationTopologicalCoreness`, yielding exactly $O(1)$ dynamic lookups natively at the API tier.

STATUS: DISCOVERY ONLY — IMPLEMENTATION NOT APPROVED
