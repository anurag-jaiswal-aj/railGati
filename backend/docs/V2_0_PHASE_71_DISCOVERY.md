# RailGati V2.0 Phase 71 Discovery Report

## A. Candidate Comparison

### Candidate 1: Station Topological Eccentricity
*   **Definition**: The maximum shortest-path distance from a station to any other reachable station in the global canonical undirected network.
*   **Mathematical Property**: Graph eccentricity $e(u) = \max_{v} d_G(u, v)$.
*   **Relevant Existing Phases**: Phase 35 (2-Hop Expansion), Phase 64 (Topological Perimeter Expansion).
*   **Derivability/Overlap**: Phase 64 computes nodes at an exact distance $k$. Eccentricity is the maximum valid $k$. While related, it requires computing the full BFS to find the depth. However, it is fundamentally just the maximum perimeter expansion.
*   **Computational Complexity**: $O(V + E)$ per station using BFS.
*   **Snapshot2 Benchmark**: Tested on 100 random stations; execution took ~0.29s (approx. 2.9ms per station). Average eccentricity in Snapshot2 is ~335.
*   **Decision**: REJECT.

### Candidate 2: Train Sequence Topological Subgraph Articulation Points
*   **Definition**: The number of cut-vertices (articulation points) in the induced subgraph $G[V_T]$ for a train's sequence.
*   **Mathematical Property**: Vertices whose removal increases the number of connected components of $G[V_T]$.
*   **Relevant Existing Phases**: Phase 34 (Transit Articulation), Phase 69 (Edge Vertex-Biconnected Component).
*   **Derivability/Overlap**: Phase 34 already computes articulation points for the global graph. Applying the identical algorithm to an induced subgraph $G[V_T]$ is a trivial projection of existing Phase 34 semantics onto train subgraphs.
*   **Computational Complexity**: $O(V_T + E_T)$ using Tarjan's algorithm on the induced subgraph.
*   **Snapshot2 Benchmark**: Evaluated on 20 trains. Execution took 0.07s total.
*   **Decision**: REJECT.

### Candidate 3: Edge Topological Jaccard Equivalence
*   **Definition**: The Jaccard similarity index between the structural neighborhoods of two adjacent stations $u$ and $v$ forming an edge.
*   **Mathematical Property**: $|N(u) \cap N(v)| / |N(u) \cup N(v)|$.
*   **Relevant Existing Phases**: Phase 33 (Neighborhood Triadic Closure), Phase 67 (Edge Topological Trussness), Phase 70 (Subgraph Triangles).
*   **Derivability/Overlap**: The numerator $|N(u) \cap N(v)|$ is exactly the number of triangles that the edge $(u, v)$ participates in. This property heavily overlaps with Phase 67 and Phase 33, making it structurally derivative of existing triangle-based phases.
*   **Computational Complexity**: $O(|N(u)| + |N(v)|)$ per edge.
*   **Snapshot2 Benchmark**: Evaluated across all 19,865 edges in 0.01s.
*   **Decision**: REJECT.

### Candidate 4: Train Sequence Topological Subgraph Diameter
*   **Definition**: The maximum shortest-path distance between any two vertices in the undirected subgraph $G[V_T]$ induced by the target train's sequence.
*   **Mathematical Property**: Graph diameter of the induced subgraph $D(G[V_T]) = \max_{u,v \in V_T} d_{G[V_T]}(u, v)$.
*   **Relevant Existing Phases**: Phase 55 (Train Sequence Subgraph Density), Phase 62 (Structural Shortest-Path Divergence), Phase 70 (Train Sequence Topological Subgraph Triangles).
*   **Derivability/Overlap**: Subgraph Diameter evaluates the "compactness" of the subgraph. Unlike Phase 62 which measures the global shortest path between the origin and destination, Subgraph Diameter restricts paths strictly to $G[V_T]$ and evaluates all pairs. It cannot be reconstructed from Phase 55's edge density or Phase 70's triangle count.
*   **Computational Complexity**: $O(V_T(V_T + E_T))$ via All-Pairs Shortest Path (APSP) using BFS from every node in the subgraph.
*   **Snapshot2 Benchmark**: Evaluated on 20 trains. Execution took 0.13s (average 6.5ms per train).
*   **Decision**: ACCEPT.

---

## B. Selected Metric
**Train Sequence Topological Subgraph Diameter**

---

## C. Formal Mathematical Definition
For a given target train $T$:
1. Let $V_T$ be the set of distinct station identities visited by $T$.
2. Let $G = (V, E)$ be the canonical unweighted, undirected graph of the active timetable snapshot.
3. Construct the induced subgraph $G[V_T] = (V_T, E_T)$ where $E_T = \{(u, v) \in E \mid u, v \in V_T\}$.
4. For any pair $u,v \in V_T$, the shortest-path distance used by this metric is computed ONLY within the induced subgraph $G[V_T]$. The global network $G$ may contain a shorter path through stations outside $V_T$, but such a path MUST NOT be used. Therefore, let $d_T(u,v)$ be the shortest-path distance between $u$ and $v$ strictly within $G[V_T]$.
5. If $G[V_T]$ is connected, the subgraph diameter is the maximum shortest-path distance over all pairs of vertices within the induced subgraph:
   $diameter(T) = \max_{u, v \in V_T} d_T(u, v)$. This is a route-induced structural diameter, not a global-network diameter.
6. If $G[V_T]$ is disconnected, the standard graph diameter is undefined/infinite. Therefore, the metric exposes `subgraph_diameter = null`.
7. If $G[V_T]$ has exactly one distinct station ($|V_T| = 1$), `subgraph_diameter = 0`, `subgraph_connected = true`, and `component_count = 1`.

---

## D. Endpoint Proposal
**GET /api/v1/network/trains/{train_number}/subgraph-diameter**

---

## E. Input / Output Schema

**Request Parameters:**
- `train_number` (Path, str): Canonical train number.

**Response Schema (`TrainSequenceSubgraphDiameterResponse`):**
```json
{
  "train_number": "12345",
  "timetable_snapshot_id": 2,
  "route_station_count": 15,
  "subgraph_diameter": 8,
  "subgraph_connected": true,
  "component_count": 1
}
```
If the induced subgraph is disconnected, the response is:
```json
{
  "train_number": "12345",
  "timetable_snapshot_id": 2,
  "route_station_count": 15,
  "subgraph_diameter": null,
  "subgraph_connected": false,
  "component_count": 2
}
```

---

## F. Semantics
- **Graph Input**: Canonical undirected `RailwayNetworkEdge` graph for the active snapshot.
- **Vertex Identity**: Distinct canonical station IDs visited by the train ($V_T$).
- **Edge Identity**: Undirected edges in $G$ whose endpoints are both in $V_T$.
- **Snapshot Scope**: Edges and train observations must belong to the same active dataset snapshot.
- **Repeated Stations**: A train route is collapsed into a distinct set of station identities ($V_T$). Repeated visits do not duplicate vertices.
- **Self-Loops**: Ignored structurally as they do not affect shortest path distances.
- **Duplicate Edges**: The graph is unweighted and canonical. Multi-edges collapse into a single topological edge.
- **Connectivity**:
  - If $G[V_T]$ is connected: `diameter = max_{u,v} d_T(u,v)`.
  - If $G[V_T]$ is disconnected: `subgraph_diameter = null`, `subgraph_connected = false`, `component_count = number of connected components`.
- **Empty/Small Graphs**:
  - If $|V_T| = 1$, `subgraph_diameter = 0`, `subgraph_connected = true`, and `component_count = 1`.
  - If $|V_T| = 0$, follow existing train semantics (returns 404 or raises error since a valid train has at least two stops).
- **Unknown Train**: Returns HTTP 404.

---

## G. Explicit Non-Claims
- This metric does NOT measure the geographical or temporal duration of the train.
- It does NOT evaluate global shortest paths (paths cannot leave $V_T$).
- It does NOT measure robustness against edge failures.
- It is NOT guaranteed to equal the train's physical stop sequence length minus one (chords lower the diameter).

---

## H. Existing Phase Derivability Audit

- **Phase 62 (Train Route Structural Shortest-Path Divergence)**: Phase 62 compares the target train's actual route length against the **global** network shortest path between its endpoints. Phase 71 instead computes the maximum pairwise shortest-path distance **within** the train-induced subgraph $G[V_T]$.
- **Phase 55 (Train Sequence Subgraph Density)**: Density measures edge concentration (ratio of edges to possible edges). It does not measure maximum pairwise shortest-path distance.
- **Phase 70 (Train Sequence Topological Subgraph Triangles)**: Triangle counts evaluate 3-clique structure, which is completely distinct from the induced-subgraph diameter.
- **Phase 64 (Train Route Topological Perimeter Expansion)**: Perimeter measures the external neighbors of the train's route station set at distance $k$, not internal pairwise distances within the route itself.

---

## I. Snapshot2 Benchmark
Evaluated using a pure Python BFS routine on the local PostgreSQL Snapshot2 database ($V=8537$, $E=19865$ canonical edges).

| Train | $|V_T|$ | Diameter | Compute Time |
|---|---|---|---|
| 12951 | 202 | 196 | ~15ms |
| 11013 | 194 | 185 | ~12ms |
| 12001 | 87 | 86 | ~5ms |

**Conclusion**: The benchmark used a sample of 20 trains. The observed sample timings were approximately 5–15 ms/train. This demonstrates feasibility for the sampled routes. It does NOT establish a guaranteed per-request latency for every train across the entire 5,207-train population. Actual latency will dynamically depend on $|V_T|$, induced-edge density, and database query cost.

---

## J. Computational Complexity
- **Time Complexity**: For a target train with $n = |V_T|$ and $m_T = |E_T|$, constructing $G[V_T]$ depends on the database query. Repeated BFS from every vertex is $O(n(n + m_T))$. For a connected induced subgraph this computes the exact diameter.
- **Space/Memory**: $O(n + m_T)$ to hold the adjacency list of the induced subgraph.

---

## K. Test Strategy
1. **Single vertex**: -> diameter 0, connected true, components 1
2. **Two connected vertices**: -> diameter 1
3. **Linear A-B-C-D**: -> diameter 3
4. **Triangle**: -> diameter 1
5. **Square**: -> diameter 2
6. **Disconnected A-B and C-D**: -> diameter null, connected false, components 2
7. **Isolated vertex plus connected component**: -> diameter null
8. **Repeated train station occurrences**: -> station identity deduplication
9. **Global shortcut through station outside V_T**: -> MUST NOT affect induced-subgraph diameter
10. **Snapshot isolation**: -> edges and observations must respect snapshot
11. **Phase 40 Regression**: Verify `test_api_edge_exclusivity_success` continues to safely fail with 404.

---

## L. Implementation Strategy
1. Add `TrainSequenceSubgraphDiameterResponse` schema.
2. In `network` service, execute 3 queries:
   - Resolve train by number.
   - Fetch unique station IDs visited by the train into a set $V_T$.
   - Fetch `RailwayNetworkEdge` records filtered by `from_station_id IN V_T AND to_station_id IN V_T`.
3. Construct an in-memory undirected adjacency list `dict[int, set[int]]`.
4. Iterate over every vertex $v \in V_T$. Execute a standard BFS queue to find the max distance from $v$.
5. Return the maximum of all BFS depths.

---

## M. Risks and Edge Cases
- **Disconnected Subgraph**: If the snapshot generation process or data anomaly results in a disconnected $G[V_T]$, the standard graph diameter is mathematically undefined. The implementation must explicitly catch this by verifying component count via BFS, returning `subgraph_diameter = null` and `subgraph_connected = false`.
- **Self-Loops / Duplicates**: Easily handled by `set` semantics in the adjacency list.

---

## N. Acceptance Criteria
1. The endpoint calculates exact subgraph diameter dynamically.
2. Response includes `route_length` and `subgraph_diameter`.
3. Time complexity is isolated to $O(V_T (V_T + E_T))$ and performs no N+1 queries.
4. Phase 40 remains untouched.
5. Code passes MyPy and Ruff linting without introducing new baseline errors.

---

## O. Final Recommendation
ACCEPT. The Train Sequence Topological Subgraph Diameter metric introduces a novel structural invariant that strictly evaluates the compactness of a train's topological footprint. It operates with exceptional performance, requires no external data, and mathematically departs from previous density, divergence, and triangle-counting metrics.
