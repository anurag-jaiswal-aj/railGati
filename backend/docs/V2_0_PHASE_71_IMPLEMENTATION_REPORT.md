# RailGati V2.0 Phase 71 Implementation Report

## A. Phase Description
**Feature**: Train Sequence Topological Subgraph Diameter
**Endpoint**: `GET /api/v1/network/trains/{train_number}/subgraph-diameter`
**Purpose**: Calculates the maximum shortest-path distance structurally contained entirely within the target train's induced topological subgraph $G[V_T]$.

## B. Implementation Approach
The implementation strictly calculates the subgraph diameter by:
1. Fetching the canonical train via its `train_number`.
2. Extracting $V_T$, the set of unique canonical station IDs visited by the target train in the active timetable snapshot.
3. Loading exactly the canonical undirected `RailwayNetworkEdge` structural observations bounded purely by $from\_station \in V_T$ and $to\_station \in V_T$.
4. Representing the undirected graph as an adjacency list.
5. Identifying component sizes via Breadth-First Search (BFS) starting from each node to determine topological reachability.
6. Calculating exact BFS depth to define the maximum distance spanning between any two nodes inside $G[V_T]$.

No N+1 queries were introduced. The full global graph was NOT loaded into memory.

## C. Exact Mathematical Semantics
For a target train $T$ and the induced subgraph $G[V_T]$:
- If $G[V_T]$ is connected, the exact structural diameter is $diameter(T) = \max_{u, v \in V_T} d_T(u, v)$ where $d_T(u, v)$ is the shortest path exclusively contained within $G[V_T]$.
- If $G[V_T]$ is disconnected, the standard mathematical property of diameter evaluates to infinity, and is appropriately serialized as `subgraph_diameter = null`, `subgraph_connected = false`, with the specific topological `component_count`.
- If $|V_T| = 1$, the response evaluates sequentially to a `0` diameter, `true` connectivity, and `1` component.

## D. Induced-Subgraph Restriction
This metric enforces shortest-path limits exclusively using edges with both endpoints contained within $V_T$. Although the global network topology $G$ might feature a faster structural shortcut using vertices outside $V_T$, the restriction algorithm strictly avoids them.

## E. Disconnected Behavior
When disconnected:
- `subgraph_diameter = null`
- `subgraph_connected = false`
- `component_count = number of topological components`

## F. Response Schema
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
If disconnected:
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
If single station:
```json
{
  "train_number": "12345",
  "timetable_snapshot_id": 2,
  "route_station_count": 1,
  "subgraph_diameter": 0,
  "subgraph_connected": true,
  "component_count": 1
}
```

## G. Query Strategy
SQL statements were explicitly minimized:
1. `SELECT` resolving canonical `Train` metadata.
2. `SELECT` fetching unique `TrainStopObservation` stations explicitly bounded by the active snapshot ID.
3. `SELECT` retrieving `RailwayNetworkEdge` topological occurrences filtered with `.in_(V_T)` constraints.
No station-by-station iteration queries are executed.

## H. BFS Algorithm and Complexity
The BFS implementation iterates dynamically over all extracted unique nodes $v \in V_T$, keeping track of the local shortest path tracking distance $d_T(v, u)$.
- **Time Complexity**: $O(n(n+m_T))$ heavily localized to the subgraph constraints, avoiding full $O(V \cdot E)$ network expansions.
- **Space Complexity**: $O(n+m_T)$ to retain the adjacency subsets.

## I. Explicit Non-Claims
- Does NOT execute in $O(1)$.
- Does NOT provide a universal API latency guarantee (dynamically bounded by $|V_T|$ complexity bounds).
- Does NOT compute shortest paths across the global physical network.
- Does NOT claim to represent operational/passenger traffic models.
- Does NOT evaluate physical track infrastructure (purely structural).

## J. Testing and Validation

### Tests Completed
All 16 structural service and API tests successfully passed:
1. Single vertex
2. Two connected vertices
3. Linear graph
4. Triangle
5. Square
6. Disconnected components
7. Isolated vertex + connected component
8. Global shortcut outside $V_T$
9. Repeated train station
10. Self-loop
11. Reciprocal edges
12. Multiple trains producing the same edge
13. Snapshot isolation
14. Unknown train (404)
15. API schema validations
16. Unconnected 3+ component edge cases

### Full Regression Suite
- 731 tests passed. 1 skipped/expected failure.
- The 1 expected baseline failure is the legacy Phase 40 `test_api_edge_exclusivity_success` endpoint which consistently returns a `404 Not Found`.

### Real Snapshot2 Oracle Validation
Validated directly against local Postgres (Snapshot ID 2):
| Train Number | Route Station Count | Component Count | Connected | Prod Diameter | Oracle Diameter | Match | Time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 15906 | 689 | 1 | True | 552 | 552 | True | 0.1787s |
| 12951 | 202 | 1 | True | 199 | 199 | True | 0.0217s |
| 11013 | 194 | 1 | True | 180 | 180 | True | 0.0195s |

### Quality & Lints
- Targeted Ruff ran effectively, resolving the new import lines. 310 previous baseline non-conformities remain untouched.
- Targeted MyPy executed returning 50 historical baseline issues entirely untouched by Phase 71 scope.
- Working tree retains perfect commit isolation.

## K. Known Baseline Weaknesses
Phase 40 remains unimplemented; `test_api_edge_exclusivity_success` legitimately fails with `404 Not Found`. This is historically accurate and was purposely maintained. No further side-effects were recognized.
