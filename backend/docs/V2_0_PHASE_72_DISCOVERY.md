# RailGati V2.0 Phase 72 Discovery Report

## A. Candidate Comparison

We evaluated four distinct structural properties of the train's induced topological subgraph $G[V_T]$:

1. **Train Sequence Topological Subgraph Radius**
   - **Precise Definition**: The minimum eccentricity among all vertices in $G[V_T]$.
   - **Mathematical Property**: Identifies how central the most central node is within the subgraph.
   - **Closest Phase**: Phase 71 (Subgraph Diameter, which measures maximum eccentricity).
   - **Derivability**: Cannot be derived from diameter; requires computing minimums rather than maximums.
   - **Complexity**: $O(|V_T|(|V_T| + |E_T|))$ via BFS.
   - **Benchmark**: Highly variable (e.g., Train 15906 = 276, Train 11013 = 90). Execution ~0.16s for the largest train.
   - **Decision**: REJECT. Conceptually too similar to Phase 71 (merely the complement extremum of the exact same distribution).

2. **Train Sequence Topological Subgraph Girth**
   - **Precise Definition**: The length of the shortest cycle in $G[V_T]$.
   - **Mathematical Property**: Local topological sparsity.
   - **Closest Phase**: Phase 70 (Subgraph Triangles).
   - **Derivability**: While Phase 70 identifies if girth is exactly 3 (if triangles > 0), it cannot resolve girths of 4, 5, or infinity (forests) when triangles = 0.
   - **Complexity**: $O(|V_T|(|V_T| + |E_T|))$.
   - **Benchmark**: Extremely flat output distribution. Because train subgraphs frequently share canonical track segments inducing triangles, the girth evaluates almost uniformly to `3` for major express trains.
   - **Decision**: REJECT. Insufficient real-world variance in Snapshot 2 to justify a dedicated endpoint.

3. **Train Sequence Topological Subgraph Degeneracy (Maximum Coreness)**
   - **Precise Definition**: The maximum $k$ for which a $k$-core exists strictly within $G[V_T]$.
   - **Mathematical Property**: Subgraph cohesion / sparsity.
   - **Closest Phase**: Phase 66 (Station Topological Coreness - global).
   - **Derivability**: Global coreness (Phase 66) cannot deduce induced subgraph coreness due to edges outside $V_T$.
   - **Complexity**: $O(|V_T| + |E_T|)$ via standard node peeling.
   - **Benchmark**: Outputs evaluate uniformly to `2` for major trains. Induced train routes topologically resemble trees and simple cycles, lacking dense high-$k$ cohesive blocks.
   - **Decision**: REJECT. Insufficient variance.

4. **Train Sequence Topological Subgraph Wiener Index**
   - **Precise Definition**: The sum of the shortest-path distances between all distinct pairs of vertices within $G[V_T]$.
   - **Mathematical Property**: Global topological compactness / structural transmission cost.
   - **Closest Phase**: Phase 71 (Subgraph Diameter) and Phase 62 (Structural Shortest-Path Divergence).
   - **Derivability**: Cannot be derived from diameter, density, or bounding properties. It represents the exact total integration of all internal topological paths.
   - **Complexity**: $O(|V_T|(|V_T| + |E_T|))$ via All-Pairs Shortest Path (APSP) using BFS.
   - **Benchmark**: High combinatorial variance across Snapshot 2. (Train 15906: ~42.8M, Train 12951: ~1.36M). Computes in <0.17s.
   - **Decision**: ACCEPT.

## B. Selected Metric

**Train Sequence Topological Subgraph Wiener Index**

## C. Formal Mathematical Definition

For a canonical target train $T$, let $V_T$ be the distinct set of station identities it visits.
Let $G[V_T]$ be the undirected induced subgraph composed only of vertices in $V_T$ and canonical edges strictly bounded by $V_T$.

If $G[V_T]$ is connected, the Wiener Index $W$ is defined as:
$$W(G[V_T]) = \frac{1}{2} \sum_{u \in V_T} \sum_{v \in V_T} d_T(u, v)$$
where $d_T(u, v)$ is the exact unweighted shortest-path distance between $u$ and $v$ constrained exclusively within $G[V_T]$.

If $G[V_T]$ is disconnected, the path distance between disjoint components is formally infinite. The standard graph-theoretic convention resolves $W$ to undefined/infinite.

## D. Endpoint Proposal

`GET /api/v1/network/trains/{train_number}/subgraph-wiener-index`

## E. Input / Output Schema

**Request**:
- Path parameter: `train_number` (string)

**Response Model**: `TrainSequenceSubgraphWienerIndexResponse`
```json
{
  "train_number": "string",
  "timetable_snapshot_id": "integer",
  "route_station_count": "integer",
  "subgraph_wiener_index": "integer | null",
  "subgraph_connected": "boolean",
  "component_count": "integer"
}
```

## F. Semantics

- **Input Graph**: Undirected canonical timetable network isolated to the active snapshot.
- **Vertex Identity**: Canonical Station IDs.
- **Edge Identity**: Unweighted, simple undirected graph elements.
- **Repeated Stations**: Flattened into a set of distinct vertex identities ($V_T$).
- **Disconnected Subgraphs**: Output `subgraph_wiener_index = null`, `subgraph_connected = false`, and accurately report the `component_count`.
- **Single Station ($|V_T| = 1$)**: Resolves to `subgraph_wiener_index = 0`, `subgraph_connected = true`, `component_count = 1`.
- **Unknown Train**: Standard HTTP 404.

## G. Explicit Non-Claims

- Does NOT measure physical route distance (kilometers).
- Does NOT execute in $O(1)$.
- Does NOT evaluate paths using nodes outside the induced boundary $G[V_T]$.
- Does NOT claim to represent operational transit times or scheduling efficiency.

## H. Existing Phase Derivability Audit

The Wiener Index cannot be reconstructed from:
- **Phase 55 (Density)**: Density only provides the global edge ratio, ignoring how edges are structurally distributed to form paths.
- **Phase 70 (Triangles)**: Identifies 3-cliques but cannot project the macro-level path sum.
- **Phase 71 (Diameter)**: Provides the strict upper bound (maximum shortest path). Two subgraphs can share the same diameter but have drastically different average path lengths / Wiener Indices (e.g., a path graph vs a heavily clustered graph with a single long tendril).
- **Phase 62 (Shortest-Path Divergence)**: Compares specific adjacent sequence stops against global paths, rather than aggregating all-pairs combinations internally.

## I. Snapshot2 Benchmark

Evaluated locally against Snapshot 2:
- **Train 15906** (Route Length 689): `42,826,743` (Execution: `~0.17s`)
- **Train 12101** (Route Length 298): `3,619,783` (Execution: `~0.03s`)
- **Train 12951** (Route Length 202): `1,362,685` (Execution: `~0.012s`)
- **Train 11013** (Route Length 194): `1,165,051` (Execution: `~0.011s`)

The metric demonstrates substantial combinatorial variance and executes well within acceptable single-request bounds.

## J. Computational Complexity

- **Algorithm**: Breadth-First Search (BFS) executed from every distinct vertex $v \in V_T$.
- **Time**: $O(|V_T| \cdot (|V_T| + |E_T|))$. This is highly optimized as it is tightly constrained by the size of the subgraph, skipping all $O(V \cdot E)$ global computations.
- **Space**: $O(|V_T| + |E_T|)$ for representing the isolated adjacency list in memory.

## K. Test Strategy

- `test_wiener_index_single_vertex`: Returns 0.
- `test_wiener_index_path`: Path of 4 nodes (Wiener index = 10).
- `test_wiener_index_square`: Cycle of 4 nodes (Wiener index = 8).
- `test_wiener_index_disconnected`: Properly resolves to `null`.
- `test_wiener_index_snapshot_isolation`: Edges leaking across snapshots must not alter the internal sum.
- `test_api_wiener_index_unknown_train`: 404 isolation.

## L. Implementation Strategy

Dynamic API computation pattern identical to Phase 71:
1. `SELECT` canonical train.
2. `SELECT` distinct stations explicitly bounded by snapshot ID.
3. `SELECT` edges bounding both `from_station` and `to_station` in $V_T$.
4. Materialize isolated dictionary adjacency list.
5. BFS component verification.
6. If connected, loop BFS for all roots, summing distances, dividing by 2 to respect undirected symmetry.

## M. Risks and Edge Cases

- **N+1 Queries**: Must be strictly avoided by bulk-loading the edge subset using `IN (...)`.
- **Double Counting**: The summation accumulates $d_T(u,v)$ and $d_T(v,u)$. Must ensure division by 2 occurs globally at the end, handling integer division properly.

## N. Acceptance Criteria

1. Endpoint implemented matching the defined schema.
2. Returns standard `404` for missing Phase 40 legacy compliance explicitly left unbroken.
3. Algorithm dynamically avoids $O(V_{global} \cdot E_{global})$ expansions.
4. Correct disconnected component `null` mapping.
5. Pytest suite completely clean.

## O. Final Recommendation

Implement Phase 72 as defined.
