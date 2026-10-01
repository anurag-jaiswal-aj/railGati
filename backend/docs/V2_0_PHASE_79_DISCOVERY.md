# RailGati V2.0 Phase 79 Discovery

## 1. Phase 79 Title
Train Route Topological Global Bridge Exposure

## 2. Selected Candidate
Train Route Topological Global Bridge Exposure Fraction (and Count).

## 3. Problem / Use Case
Identifying structurally vulnerable train routes. A global bridge in a railway network is an edge whose removal strictly disconnects the active canonical network graph into two separate components. Traversing a global bridge means that if that specific edge (track) fails due to flooding, congestion, or maintenance, there is mathematically no topological detour available in the entire timetable network. High exposure indicates a brittle, branch-line-dependent service, while 0.0 bridge exposure means none of the train's distinct traversed canonical edges are global bridges. This does not imply that the route is purely cyclic, meshed, or operationally redundant.

## 4. Exact Mathematical Definition
Let $E_R$ be the set of distinct undirected canonical edges traversed by the train route. 
Let $B$ be the set of all undirected global bridges in the canonical network graph.
The metric returns:
- `total_route_distinct_edges`: $|E_R|$
- `global_bridge_edges_count`: $|E_R \cap B|$
- `global_bridge_exposure_fraction`: $\frac{|E_R \cap B|}{|E_R|}$

## 5. Data Semantics
- **Input**: Train identity (`train_number`), timetable `snapshot_id`.
- **Graph Directionality**: Undirected canonical edges.
- **Repeated Edges**: Deduplicated. $E_R$ is a mathematical set of edges. Exposure is a structural property of the path, not a frequency count.
- **Edge Cases**: If a train consists of only 1 station, $|E_R| = 0$, so the fraction is undefined (`None`).
- **Disconnected Components**: Evaluated strictly on the active timetable's canonical graph.

## 6. Why it is useful for RailGati
It provides a direct, highly interpretable topological metric of route fragility. This serves as a foundational feature for future reliability modelling, anomaly detection, and segmenting routes based on their structural global bridge exposure.

## 7. Closest Existing Phases
- **Phase 75**: Train Topological Biconnected Block Traversal Count.
- **Phase 38**: Edge Topological Bridge Bipartition Size (`test_network_edge_topological_bridge_bipartition_size.py`).

## 8. Novelty / Overlap Audit
- Phase 75 counts the total number of biconnected blocks a train touches, but it does NOT differentiate between crossing a massive 50-station mesh cycle and crossing a brittle bridge edge. A train traversing 10 consecutive bridges has a block count of 10. A train traversing 10 large interconnected cycles also has a block count of 10. The proposed Phase 79 metric specifically isolates vulnerability exposure, making it strictly orthogonal to block count.
- The existing edge bipartition endpoint evaluates a *single* user-provided edge. It does not evaluate a train route sequence.

## 9. Derivability Audit
**Mathematically Derivable, Server-Side Analytical Aggregate.** 
A client could theoretically reconstruct this by fetching the train's route edges ($O(L)$) and making an $O(L)$ series of N+1 HTTP requests to the single-edge bipartition API to check if each edge is a bridge. It is mathematically derivable from existing edge-level bridge analytics, but valuable as a server-side train-route aggregate because reconstructing it client-side would require repeated edge-level requests and repeated global-topology access. A server-side aggregate can execute this efficiently.

## 10. Candidate Alternatives Considered
- Station Topological Local Clustering Coefficient.
- Network Edge Neighborhood Overlap.

## 11. Rejected Alternatives and Reasons
- **Station Local Clustering Coefficient**: Rejected. Empirical evidence from Phase 78 (where Local Efficiency was rejected) demonstrated that ~69% of stations in the Indian rail network lack any triangles due to sparse, tree-like branching topologies. This would force the local clustering coefficient to be exactly 0.0 for the overwhelming majority of stations, making it a poor metric.
- **Network Edge Neighborhood Overlap**: Rejected for identical sparsity/0-triangle reasons.

## 12. Snapshot 2 Benchmark / Evidence
An ad-hoc evaluation over the 5,207 active valid multi-stop trains in Snapshot 2 revealed:
- Global Bridges in network: 1,187 / 19,866 edges (6.0%)
- Trains with 0.0 bridge exposure: 3,137 (60.2%)
- Trains with 1.0 (100%) bridge exposure: 259 (5.0%)
- Trains with mixed exposure: ~1,811 (34.8%)
This confirms the metric exhibits excellent discriminatory power. 40% of the network's trains face some level of topological bottleneck vulnerability.

## 13. Complexity Estimate
- $O(V+E)$ to execute Tarjan's bridge-finding algorithm on the active graph in memory.
- $O(L)$ to intersect the train's unique route edges.
- Overall latency expected around ~5-15ms.

## 14. Expected Query / Data-Access Strategy
Fetch all canonical edges from `RailwayNetworkEdge` for the active `snapshot_id`. Build an adjacency list in Python, execute a recursive Tarjan's DFS to identify the bridge set $B$, and intersect it with the deduplicated sequential edges from `TrainStopObservation`.

## 15. API Endpoint Proposal
`GET /api/v1/network/trains/{train_number}/topological-global-bridge-exposure`

## 16. Response Schema Proposal
```json
{
  "train_number": "str",
  "timetable_snapshot_id": "int",
  "total_route_distinct_edges": "int",
  "global_bridge_edges_count": "int",
  "global_bridge_exposure_fraction": "float | null"
}
```

## 17. Edge Cases
Trains with 0 valid edges (1 stop) return `global_bridge_exposure_fraction: null`.

## 18. Correctness Strategy
Unit tests against an independent Oracle executing Tarjan's algorithm on hardcoded dictionary-based mock graphs containing both cycles and cut-edges.

## 19. Performance Strategy
Since the canonical edge list is small (~10-20k edges), pulling it into memory and evaluating Tarjan's algorithm takes milliseconds, avoiding any expensive dynamic SQL recursive CTEs.

## 20. ₹0 Compliance
Fully compliant. Operates exclusively on local historical timetable structures without external APIs or paid services.

## 21. Explicit Non-Goals
- We are not simulating actual train rerouting in the event of failure.
- We are not predicting the physical probability of a track failure.

## 22. Final Recommendation
APPROVE FOR IMPLEMENTATION.
