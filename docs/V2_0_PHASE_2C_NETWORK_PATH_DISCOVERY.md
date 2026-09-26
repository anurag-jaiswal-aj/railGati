# v2.0 Phase 2C — Network Path Exploration Discovery

## 1. Objective
Define the architecture for a bounded railway network path exploration capability. The goal is to answer topological connectivity questions such as "How can the railway network topology connect station A to station B?" by returning valid sequences of topological edges between the two stations.

## 2. Existing Capabilities
The current platform provides:
- Station search and direct journey comparison (v1.0-v1.2).
- Destination discovery (v1.3).
- Bounded network reachability (v2.0 Phase 2A/2B), which identifies *which* stations are reachable within a topological hop bound, but does not provide the *paths* to reach them.

Path exploration fills this gap by materializing the actual sequence of stations connecting an origin to a specific destination.

## 3. Product Boundary
A topology path (e.g., Station A → Station B → Station C) must NOT automatically mean a passenger can travel this route. 
- It simply asserts that the `RailwayNetworkEdge` graph has historical physical connections between these points.
- Passenger routing requires verifying `RailwayServiceEdge` train identity, source-day progression, transfer buffers, and arrival/departure timings. This phase explicitly omits those constraints.

## 4. Graph Model
The existing `RailwayNetworkEdge` provides an aggregated connection between stations (`from_station_id`, `to_station_id`).
- Path exploration will use `RailwayNetworkEdge` to find paths.
- We will rely on PostgreSQL recursive CTEs.

## 5. Path Identity and Semantics
A **topology path identity** is defined as the ordered sequence of canonical station IDs/codes from origin through destination (e.g., `NDLS → AGC → BPL → MAS`). Individual train identities are intentionally NOT part of Phase 2C path identity because `RailwayNetworkEdge` is an aggregated station-to-station graph.

A valid topology path is defined as:
- A sequence of contiguous directed `RailwayNetworkEdge`s starting at the origin and ending at the destination.
- **Simple paths only:** No station can be repeated in the path. Cycle prevention using the existing PostgreSQL array-based visited-station approach will natively enforce this.
- **Self-loop exclusion:** Self-loops (`A → A`) cannot appear in a simple path because they repeat the current station. While they may exist in `RailwayNetworkEdge`, Phase 2C traversal must not include them and they must not create a zero-progress recursive path.
- **Reverse-direction semantics:** A path from A to B only exists if directed `RailwayNetworkEdge` traversal can reach B from A. The existence of B → A does not imply A → B.
- **Origin == Destination:** If the origin equals the destination, the API will return a single 0-hop topology path containing only the origin station (`hop_count = 0`, `stations = [origin]`). This is a graph/topology result only and does not represent a passenger journey.
- **Snapshot isolation:** All edges must belong to the same active timetable snapshot.

## 6. Path Strategy Selection
Phase 2C will initially use the **bounded simple topology paths** strategy:
- PostgreSQL recursive CTE
- Cycle prevention using the array-based visited-station approach
- Maximum hop bound (`max_hops`)
- Maximum returned path count (`max_paths`)

## 7. Resource Safety
The following execution boundaries must be distinguished:
- **`max_hops`**: Bounds the recursion depth.
- **`max_paths`**: Bounds the number of paths returned to the caller. This is an OUTPUT LIMIT and does NOT automatically guarantee that PostgreSQL stops CTE generation after `max_paths` paths. It does not by itself prevent CTE materialization explosion.
- **Cycle prevention**: Bounds repeated-node traversal by preventing infinite loops.
- **Future execution-level safeguards**: Statement timeout, query planning/benchmarking, and potentially a bounded traversal design that terminates generation earlier must be evaluated before claiming strong database-side protection.

Implementation must benchmark worst-case topology queries before productionizing expensive traversals.

## 8. Deterministic Path Ordering
To ensure the selected subset of `max_paths` is predictable, paths must follow a strict deterministic ordering:
1. `hop_count` ASC
2. Ordered station-code sequence lexicographically ASC (e.g., path `A → B → C` is evaluated sequentially against path `A → B → D`).

The implementation must not rely on PostgreSQL's natural recursive CTE output order.

## 9. API Contract Proposal
**Endpoint:** `GET /api/v1/network/path`

**Parameters:**
- `origin`: required, canonical station code, case-insensitive (according to existing station resolution behavior).
- `destination`: required, canonical station code, case-insensitive.
- `max_hops`: optional, default 3, minimum 1, maximum 10.
- `max_paths`: optional, default 10, minimum 1, maximum 50.

**Behavior:**
- Unknown origin → `404 Not Found`
- Unknown destination → `404 Not Found`
- Invalid parameters → `422 Unprocessable Entity`
- Origin == Destination → `200 OK` with one 0-hop path
- Valid disconnected pair → `200 OK` with zero paths
- Missing/PENDING/FAILED graph → `503 Service Unavailable`
- ACTIVE graph → execute topology traversal

Pagination is not introduced for this phase.

## 10. Response Model Proposal
The API conceptually returns:
```json
{
  "origin": "NDLS",
  "destination": "MAS",
  "timetable_snapshot_id": 2,
  "max_hops": 5,
  "max_paths": 10,
  "total_paths_returned": 1,
  "paths": [
    {
      "hop_count": 4,
      "stations": [
        {"station_code": "NDLS", "station_name": "New Delhi"},
        {"station_code": "AGC", "station_name": "Agra Cantt"}
      ]
    }
  ]
}
```
**Truncation Semantics:**
- Return at most `max_paths` paths.
- Paths are ordered deterministically.
- `total_paths_returned` means the number of paths actually returned in the payload. The API makes no claim that `total_paths_returned` equals the mathematical total number of possible paths when truncation occurs.
- The API does not calculate or return a `total_possible_paths` count because doing so could itself trigger runaway CTE execution.

## 11. Snapshot and Graph Availability Semantics
- Requires an `ACTIVE` `RailwayGraphBuild`.
- Missing/PENDING/FAILED builds return `503 Service Unavailable`.
- Station metadata relies on the active station snapshot.
- Unknown stations remain a 404 concern; unavailable graphs remain a 503 concern.

## 12. Benchmark Plan
The implementation must explicitly benchmark:
- Origin == Destination
- Direct one-hop path
- Small multi-hop path
- No path
- Reverse-direction query
- High-connectivity origin/destination
- `max_hops=10`
- `max_paths=50`
- Query where more than 50 paths exist
- Cycle-heavy topology

Measurements must capture:
- Database execution time
- Application execution time
- Number of returned paths
- Response payload size
- EXPLAIN ANALYZE output where appropriate

Phase 2A execution times must not be reused as evidence for Phase 2C performance.

## 13. Database/Index Considerations
Existing indexes will be used initially. Query plans and measured execution times must be evaluated before introducing any additional index. No new index is justified by discovery alone.

## 14. Test Strategy
The future test strategy explicitly includes:
- 0-hop origin == destination
- Direct one-hop path
- Multi-hop path
- No path
- Reverse direction
- Simple-path cycle prevention
- Self-loop exclusion
- Repeated station exclusion
- `max_hops` minimum/maximum
- `max_paths` minimum/maximum
- More than `max_paths` available
- Deterministic ordering
- Path identity
- Snapshot isolation
- Active graph requirement
- Missing graph
- PENDING graph
- FAILED graph
- Station metadata snapshot isolation

## 15. Passenger Routing Boundary
Phase 2C answers a historical topology question:
*"Does the railway network graph contain a bounded directed station path from A to B, and what are bounded topology paths?"*

It does NOT answer:
*"Can a passenger travel from A to B using these trains?"*

Passenger routing remains a later feature requiring `ServiceEdge`, train identity, specific stop occurrences, arrival/departure timing, source-day progression, transfer station occurrences, minimum transfer buffers, and connection feasibility semantics.

## 16. Implementation Readiness Checklist
- [x] Path strategy selected
- [x] Simple-path semantics defined
- [x] `max_hops` bound defined
- [x] `max_paths` output bound defined
- [x] Deterministic ordering defined
- [x] Path identity defined
- [x] Origin == destination defined
- [x] Self-loop semantics defined
- [x] Snapshot semantics defined
- [x] Graph availability semantics defined
- [ ] Service implementation
- [ ] API endpoint implementation
- [ ] Unit and integration tests
- [ ] Benchmark validation
- [ ] Final implementation review
