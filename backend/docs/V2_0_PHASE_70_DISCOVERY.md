# RailGati V2.0 Phase 70 Discovery

## A. Phase 70 Candidate Comparison

We evaluated three highly distinct topological capabilities.

1. **Station Topological Eccentricity**
   - *Concept*: Maximum shortest-path distance to any reachable station.
   - *Benchmark*: Proved feasible via Python BFS on Snapshot 2 in 13.1 seconds.
   - *Status*: **Rejected**. While technically feasible, Phase 68 explicitly previously rejected it for perceived performance risks. Furthermore, it risks conceptual overlap with path-based perimeters in Phase 64.

2. **Structural Betweenness Centrality**
   - *Concept*: Ratio of all-pairs shortest paths passing through a station.
   - *Benchmark*: Brandes' algorithm required 53.6 seconds on Snapshot 2.
   - *Status*: **Rejected**. Honors the Phase 66 rejection due to exceeding the synchronous Graph Build lifecycle bounds.

3. **Train Sequence Topological Subgraph Triangles**
   - *Concept*: The exact count of 3-cycles (triangles) present strictly within the subgraph induced by a train's entire sequence of stops.
   - *Benchmark*: Completed globally for all 5,207 active Snapshot 2 trains in 2.2 seconds.
   - *Status*: **Accepted**. Mathematically rigorous, extremely fast, and reveals a completely new dimension of train route structure.

## B. Selected Metric
**Train Sequence Topological Subgraph Triangles**

## C. Formal Definition
For a target train $T$, let its ordered sequence of scheduled stops yield the set of distinct station vertices $V_T$. 
Let the global canonical undirected timetable graph for the same snapshot be $G = (V, E)$.
Construct the induced subgraph $G[V_T] = (V_T, E_T)$, where $E_T = \{(u, v) \in E \mid u \in V_T \text{ and } v \in V_T\}$.
The **Train Sequence Topological Subgraph Triangles** is exactly the number of distinct 3-cliques (triangles) in $G[V_T]$.

A triangle exists in $G[V_T]$ if and only if three distinct stations $u, v, w \in V_T$ are mutually adjacent in the global network $G$.

## D. Endpoint Proposal
`GET /api/v1/network/trains/{train_number}/subgraph-triangles`

## E. Input / Output Schema
**Path Parameters:**
- `train_number` (string)

**Query Parameters:**
- `timetable_snapshot_id` (integer, optional)

**Response (200 OK):**
```json
{
  "train_number": "12345",
  "timetable_snapshot_id": 2,
  "route_length": 15,
  "subgraph_triangles": 7
}
```

## F. Semantics and Explicit Non-Claims
- **Directionality**: The global network is collapsed into canonical undirected edges before evaluating adjacencies.
- **Route Edges**: Triangles do not have to be formed exclusively by the train's own consecutive path. Any global edge connecting two stations in $V_T$ is eligible.
- **Sequence Order**: The order of stops is irrelevant for the triangle count; it strictly evaluates the set of visited stations $V_T$.
- **Explicit Non-Claims**: 
  - This metric does NOT measure physical track triangles or Y-junctions.
  - It does NOT imply train scheduling reliability, travel time, or passenger traffic.
  - It does NOT measure topological bypasses (Phase 39) unless those bypasses participate in a 3-cycle.

## G. Existing-Phase Derivability Audit
- **Phase 55 (Train Sequence Subgraph Density)**: Density ($2E / (V(V-1))$) measures the raw edge fraction. It cannot distinguish between a highly bipartite route (0 triangles) and a highly clustered route (many triangles) with the same edge density.
- **Phase 33 (Network Station Neighborhood Triadic Closure Analytics)**: Calculates triangles centered on a specific *station's* neighbors, not bounded by a *train's* route.
- **Phase 67 (Edge Topological Trussness)**: Evaluates recursive triangles globally anchored to a specific *edge*. The existing Phase 67 endpoint does not expose sufficient route-restricted triangle information to reconstruct this metric directly. Phase 67 evaluates edge trussness globally and does not expose the third-vertex membership required to count triangles whose three vertices all belong to the target train's station set.
- **Conclusion**: The metric is fundamentally novel and absolutely non-derivable from existing endpoints.

## H. Snapshot 2 Benchmark
A pure Python graph algorithm isolated on Snapshot 2 yielded:
- **Graph State**: 8,537 vertices, 10,195 canonical edges.
- **Trains Evaluated**: 5,207 distinct routes.
- **Total Execution Time**: Approximately 2.20 seconds total across all trains.
- **Complexity**: $O(|V_T|^3)$ per train for the proposed naive triangle-counting implementation. The Snapshot2 benchmark demonstrates practical feasibility for the observed route sizes, while the algorithm remains cubic in the number of distinct stations in the target train route.
- **Output Cardinality**: Exactly 1 scalar result per train.
- **Distribution Sample**: 
  - Top values: 90, 85, 83, 78, 77 (Massive routes traversing dense urban/interlinked meshes)
  - Median value: 1
  - Zeros: Common for short localized or purely linear spoke trains.

## I. Test Strategy
- **Graph A (Linear Route)**: Train visits A-B-C-D with no other connections. Triangles = 0.
- **Graph B (Chorded Bypass)**: Train visits A-B-C. A global edge exists between A-C. Triangles = 1.
- **Graph C (Non-Route 3rd Node)**: Train visits A-B. A global triangle exists A-B-Z. Z is not in the train's route. Triangles = 0.
- **Missing Train/Snapshot**: Standard 404 behavior.

## J. Implementation Strategy
- **Dynamic Calculation**: The benchmark evaluated all 5,207 Snapshot2 trains in approximately 2.20 seconds, averaging approximately 0.42 seconds per 1,000 trains / approximately 0.42 ms per train across the aggregate workload. This aggregate average must NOT be presented as a guaranteed individual API latency. Individual train request latency may vary with route size and database query cost. Therefore, it can be computed dynamically on-the-fly in `services/network.py` upon API request.
- **Query Flow**:
  1. Fetch $V_T$ (distinct `station_id`s for the train in the snapshot).
  2. Query `RailwayNetworkEdge` for all canonical edges where BOTH `from_station_id` $\in V_T$ AND `to_station_id` $\in V_T$.
  3. Load these edges into a local adjacency set.
  4. Perform a simple $O(|V_T|^3)$ triangle count iteration in Python.
  5. Return result.
- **Migrations**: No new tables needed.

## K. Risks / Edge Cases
- **Cyclic/Loop Trains**: Handled natively since $V_T$ is a distinct set of station identities. Repeat visits do not inflate the triangle count.
- **Self-Loops**: Filtered out when constructing the canonical undirected edges.
- **Short Routes**: Any route with $< 3$ distinct stations trivially returns 0.

## L. Acceptance Criteria
- Discovery report is approved.
- API endpoint implemented with exact semantics.
- Service function performs bounded subgraph extraction and exactly counts triangles.
- Tests cover the non-route 3rd node exclusion explicitly.

## M. Final Recommendation
**Highly Recommended**. Train Sequence Topological Subgraph Triangles provides an elegant, highly performant measure of the structural "meshiness" of a train's traversal region that is fundamentally invisible to pure density or path metrics.
