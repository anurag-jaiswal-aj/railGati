# RailGati V2.0 Phase 80 Discovery

## 1. Phase 80 Title
Network Station Pair Topological Edge Connectivity (Min-Cut / Max-Flow)

## 2. Candidate Shortlist
1. **Network Station Pair Topological Edge Connectivity (Min-Cut)** - The minimum number of edges to disconnect two stations (equivalently, the max number of edge-disjoint paths).
2. **Train Route Topological Coreness Gradient** - The progression of topological k-core density along a train's path.
3. **Station Pair Topological Structural Route Shortest Path Ratio** - The ratio of topological shortest path to direct train actual edge length.

## 3. Selected Candidate
Network Station Pair Topological Edge Connectivity (Min-Cut / Max-Flow)

## 4. Problem / Use Case
Quantifying the absolute structural redundancy and fault tolerance between two cities (stations) in the railway network. If the topological edge connectivity (min-cut) is 1, a single track failure severs all topological connection between the two stations. If the connectivity is 4, it would require 4 independent, simultaneous edge failures to disconnect them. This measures how robustly two parts of the timetable-topological structure are knit together.

## 5. Exact Mathematical / Algorithmic Definition
Let $G = (V, E)$ be the unweighted, undirected canonical timetable graph for the active snapshot. 
Given source station $s$ and target station $t$:
The Topological Edge Connectivity $\lambda(s, t)$ is the minimum number of edges whose removal disconnects $s$ and $t$. 
By Menger's Theorem, this is mathematically identical to the maximum number of mutually edge-disjoint paths from $s$ to $t$.
This is computed by applying an Edmonds-Karp Max-Flow algorithm where each undirected edge has a capacity of exactly 1.

## 6. Data Semantics
- **Active Snapshot Scope**: Graph is strictly derived from the active `timetable_snapshot_id`.
- **Graph Directionality**: Undirected canonical edges.
- **Station Identity**: Uses absolute `station_id` internally, resolved from public station codes.
- **Self-Loops**: Filtered/ignored (capacity 0).
- **Missing Timing**: Irrelevant (purely topological structure).
- **Disconnected Components**: If $s$ and $t$ are in separate disconnected components, $\lambda(s, t) = 0$.
- **Zero/One-Edge Routes**: N/A, evaluates absolute topology.

## 7. Railway Intelligence Value
- **Network Understanding**: Maps the resilience and bottlenecks of the macroscopic network.
- **Route Comparison**: Allows structural comparison between paths with massive topological redundancy versus those prone to single-point isolations.
- **Future ML/Product**: Powerful graph feature representing origin-destination structural connectivity without tracking infinite physical train iterations.

## 8. Closest Existing Phases
- **Phase 79**: Train Route Topological Global Bridge Exposure.
- **Phase 74**: Edge Topological Bridge Bipartition Size.
- **Phase 69**: Edge Topological Biconnected Component Size.
- **Phase 65**: Topological Resilience Detour.
- **Phase 45**: Station Pair Route Diversity.
- **Phase 35**: Station 2-Hop Reachability Expansion.
- **Phase 34**: Network Station Transit Articulation.

## 9. Detailed Novelty / Overlap Audit
- **Phase 65** measures the length of the shortest alternate detour explicitly after removing one local edge. It does not measure the absolute number of disjoint alternative paths.
- **Phase 69** and **Phase 74** evaluate *single edges* (their block size and bipartition impact), whereas Phase 80 evaluates the relationship between *any two arbitrary stations*.
- **Phase 79** measures a specific train route's fraction of traversed global bridges (1-cuts). Phase 80 calculates the precise min-cut size (which can be >1) for any two points, completely independent of any train route.
- **Phase 34** evaluates whether removing a station disconnects the network (vertex cut), whereas Phase 80 evaluates edge disjoint paths between two endpoints (edge cut).
- Phase 80 answers arbitrary station-pair global edge connectivity and can return $\lambda > 1$ for pairs connected through multiple edge-disjoint paths.

## 10. Derivability Audit
**Mathematically Derivable, Server-Side Analytical Aggregate.**
A client could technically reconstruct this metric by fetching the entire canonical edge list of the network and executing an Edmonds-Karp maximum flow algorithm client-side. However, forcing clients to repeatedly fetch the full global topology for simple Station Pair intelligence requires repeated client orchestration. A server-side aggregate delivers the algorithmic intelligence immediately. (Note: computation is algorithmically $O(V \cdot E^2)$, not $O(1)$, but the scalar response size is minimal).

## 11. Candidate Alternatives
- **Train Route Topological Coreness Volatility**: Evaluates how a train bounces between structural k-cores.
- **Station Pair Multipath Shortest-Path Subsumption**: Overlaps with Phase 74 and Phase 73 (Shortest-Path Divergence).

## 12. Rejected Alternatives and Reasons
- Coreness Volatility was rejected because topological coreness in sparse railway networks (Phase 66) is heavily skewed; the majority of stations share identical low cores, meaning volatility would flatline at 0 for most routes.

## 13. Snapshot 2 Evidence
Evaluated Edmonds-Karp Max-Flow on the undirected canonical graph for 1,000 randomly selected station pairs in Snapshot 2.
- **Population**: 1,000 random pairs from 8,537 stations.
- **Runtime**: Average **~11ms per pair** (Median 9.92ms, P99 37.94ms).
- **Distribution (True Edge Connectivity $\lambda$)**:
  - Cut = 0 (Disconnected): 0.3%
  - Cut = 1 (Highly Vulnerable): 33.4%
  - Cut = 2 (Standard Biconnected Core): 64.5%
  - Cut = 3: 1.6%
  - Cut = 4: 0.1%
  - Cut = 5 (Max Observed): 0.1%
- **Conclusion**: The metric is cleanly distributed. The massive concentration at 2 represents pairs safely within the standard double-path/biconnected cycles of the Indian Railway structural core, while exactly 33.4% of pairs remain vulnerable to a single edge sever.

## 14. Complexity
- **Time**: $O(V \cdot E^2)$ via Edmonds-Karp BFS, though empirically for this specific sparse graph topology it resolves extremely efficiently ($\approx 10\text{-}40\text{ms}$).
- **Space**: $O(V + E)$ to hold the residual capacity matrix.

## 15. Query / Data-Access Strategy
Fetch all canonical edges from `RailwayNetworkEdge` for the active `timetable_snapshot_id`. Build an undirected adjacency list in memory. Execute Edmonds-Karp algorithm per request. A Gomory-Hu tree preprocessing architecture was evaluated, but since it requires $\approx 95$ seconds of blocking preprocessing, and per-request execution is merely $10\text{ms}$, immediate per-request Edmonds-Karp is strongly recommended for standard dynamic API workloads.

## 16. Proposed API Endpoint
`GET /api/v1/network/station-pairs/{origin_code}/{destination_code}/topological-edge-connectivity`

## 17. Proposed Response Schema
```json
{
  "origin_station_code": "str",
  "destination_station_code": "str",
  "timetable_snapshot_id": "int",
  "topological_edge_connectivity": "int | null"
}
```

## 18. Edge Cases
- $s == t$: Returns `null` (undefined, as connecting a station to itself requires 0 edges and forms infinite disjoint paths).
- Disconnected $s$ and $t$: Returns `0`.
- Missing/Invalid station codes: Standard HTTP 404.

## 19. Correctness Strategy
Unit tests against an independent Oracle executing Max-Flow on hardcoded dictionary-based mock graphs (ring graphs, barbell graphs, single-edge graphs).

## 20. Performance Strategy
Since the canonical edge list is ~10k edges, fetching it via SQLAlchemy takes ~250ms. The Max-Flow execution takes ~10ms. Total latency is completely dominated by the database fetch, keeping overall endpoint execution bounded inside an acceptable analytical response window.

## 21. ₹0 Compliance
Strictly ₹0 compliant. Evaluates exclusively against the local open-source graph state without external APIs or LLMs.

## 22. Explicit Non-Goals
- We are not claiming infrastructure can physically withstand $\lambda$ failures.
- We are not claiming trains will operationally reroute $\lambda$ times.
- Service reliability does not follow directly from this purely topological metric.

## 23. Final Recommendation
APPROVE FOR IMPLEMENTATION.
