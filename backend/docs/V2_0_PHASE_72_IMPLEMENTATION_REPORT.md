# RailGati V2.0 Phase 72 Implementation Report

## A. Phase Description

**Feature**: Train Sequence Topological Subgraph Wiener Index
**Endpoint**: `GET /api/v1/network/trains/{train_number}/subgraph-wiener-index`
**Purpose**: Computes the sum of shortest-path distances between all distinct unordered vertex pairs within the target train's induced topological subgraph G[V_T].

This is a purely structural historical timetable-topology metric. It does not measure passenger demand, physical track distance, travel time, operational efficiency, reliability, or scheduling quality.

## B. Formal Definition

For a canonical target train T, let V_T be the distinct set of station identities it visits. Let G[V_T] be the undirected induced subgraph composed only of vertices in V_T and canonical edges strictly bounded by V_T.

If G[V_T] is connected:

W(T) = sum of d_T(u,v) for all unordered pairs {u,v}, u != v

where d_T(u,v) is the exact unweighted shortest-path distance between u and v constrained exclusively within G[V_T].

If G[V_T] is disconnected: subgraph_wiener_index = null.

If |V_T| = 1: subgraph_wiener_index = 0.

## C. Induced-Subgraph Restriction

Shortest paths are computed exclusively using edges and vertices inside G[V_T]. A globally shorter path through a station outside V_T is never used.

## D. Disconnected Behavior

When G[V_T] has more than one connected component:
- subgraph_wiener_index = null
- subgraph_connected = false
- component_count = exact number of connected components

## E. Endpoint

`GET /api/v1/network/trains/{train_number}/subgraph-wiener-index`

## F. Response Schema

Connected:
```json
{
  "train_number": "12345",
  "timetable_snapshot_id": 2,
  "route_station_count": 15,
  "subgraph_wiener_index": 420,
  "subgraph_connected": true,
  "component_count": 1
}
```

Disconnected:
```json
{
  "train_number": "12345",
  "timetable_snapshot_id": 2,
  "route_station_count": 15,
  "subgraph_wiener_index": null,
  "subgraph_connected": false,
  "component_count": 2
}
```

Single station:
```json
{
  "train_number": "12345",
  "timetable_snapshot_id": 2,
  "route_station_count": 1,
  "subgraph_wiener_index": 0,
  "subgraph_connected": true,
  "component_count": 1
}
```

## G. Query Strategy

Three SQL queries per request:
1. SELECT resolving canonical Train metadata.
2. SELECT fetching unique TrainStopObservation stations bounded by the active snapshot ID.
3. SELECT retrieving RailwayNetworkEdge observations filtered with .in_(V_T) constraints.

No N+1 queries. No per-station, per-edge, per-pair, or per-BFS queries.

## H. BFS Algorithm

1. Build adjacency sets from loaded edges.
2. Determine connected components via BFS.
3. If disconnected, return null.
4. If connected, BFS from each vertex. For each BFS source s, sum distances to vertices with canonical station ID > s, ensuring each unordered pair is counted exactly once.
5. Return the exact integer sum.

## I. Complexity

- Time: O(n(n + m_T)) for repeated BFS, where n = |V_T| and m_T = induced edge count.
- Space: O(n + m_T) for the adjacency list.

## J. Explicit Non-Claims

- Does NOT execute in O(1).
- Does NOT provide a universal API latency guarantee.
- Does NOT compute shortest paths across the global physical network.
- Does NOT measure passenger demand, physical track distance, travel time, operational efficiency, reliability, or scheduling quality.

## K. Test Coverage

### Service Tests (16 tests)
1. Single vertex (W=0)
2. Two connected vertices (W=1)
3. Three-node path (W=4)
4. Four-node path (W=10)
5. Triangle (W=3)
6. Square (W=8)
7. Disconnected two components (W=null)
8. Isolated vertex + connected component (W=null)
9. Global shortcut outside V_T (W=4, not 3)
10. Repeated station route (deduplicated)
11. Self-loop (no effect on W)
12. Snapshot isolation (cross-snapshot edges excluded)
13. Unknown train (ValueError)
14. Three disconnected components (component_count=3)
15. Pair-count correctness (W >= n*(n-1)/2)
16. Deterministic repeated calls

### API Tests (3 tests)
17. Connected response schema
18. Disconnected response schema
19. Unknown train 404

## L. Independent Oracle Validation

An independent BFS oracle was implemented directly in the test file. The oracle computes the Wiener index using its own BFS traversal, independent of the production function.

## M. Snapshot2 Validation

Validated against local Snapshot 2 with independent oracle:

| Train | Stations | Connected | Components | Production W | Oracle W | Match | Time |
|-------|----------|-----------|------------|-------------|----------|-------|------|
| 15906 | 689 | True | 1 | 42,826,743 | 42,826,743 | True | 0.198s |
| 12951 | 202 | True | 1 | 1,362,685 | 1,362,685 | True | 0.023s |
| 11013 | 194 | True | 1 | 1,165,051 | 1,165,051 | True | 0.021s |

## N. SQL/Query-Count Validation

Exactly 3 SQL statements per request. No query-per-station, no query-per-edge, no query-per-pair, no query-per-BFS, no global network load.

## O. Known Phase 40 Baseline Failure

Phase 40's missing endpoint causes test_api_edge_exclusivity_success to return 404. This is historically accurate and was not repaired.
