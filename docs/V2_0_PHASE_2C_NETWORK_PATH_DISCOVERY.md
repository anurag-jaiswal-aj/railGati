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
- We will rely on PostgreSQL recursive CTEs, avoiding external graph databases (e.g., Neo4j) or Python network libraries (e.g., NetworkX), keeping memory footprints and complexity low within the ₹0 budget constraint.

## 5. Path Semantics
A valid topology path is defined as:
- A sequence of contiguous directed `RailwayNetworkEdge`s starting at the origin and ending at the destination.
- **Simple paths only:** No station can be repeated in the path (cycles and self-loops are rejected).
- **Snapshot isolation:** All edges must belong to the same active timetable snapshot.
- Reverse-direction paths are only valid if directed edges exist in both directions.
- Origin = Destination requests evaluate to trivial 0-hop paths (or empty sets, depending on exact implementation decisions).

## 6. Path Explosion and Resource Bounds
Finding all paths between two nodes in a highly connected graph results in combinatorial explosion. 
- Returning every possible path is unsafe.
- We must enforce bounds: a `max_hops` limit and a `max_paths` limit to safeguard the database and API payload size. 
- The `max_paths` limit is a product safety bound, preventing runaway CTE materialization and extreme API payload sizes, rather than a statement about the physical property of the railway network.

## 7. Candidate Path Strategies
- **A. All bounded simple paths:** Computes all valid paths up to `max_hops`. Highly susceptible to path explosion; may hit the `max_paths` limit unpredictably.
- **B. One shortest-hop topology path:** Trivial to compute and returns minimal data, but fails to answer "how else can I get there?".
- **C. K shortest-hop topology paths:** Computes the K paths with the fewest topological hops. Offers a balance between utility and bounds, though strict CTE formulation for K-shortest paths introduces complexity compared to depth-bounded graph exploration.
- **D. Shortest paths up to length L:** Find the shortest path length L, then return all paths of length L.

The final implementation will evaluate these trade-offs to select a concrete candidate scope, carefully balancing execution predictability with the utility of the returned paths.

## 8. Proposed Phase Scope
Implement bounded topological path exploration that returns topology paths up to a specified `max_hops` bound, aggressively capped at `max_paths` to preserve strict database safety limits. 

## 9. API Contract Proposal
**Endpoint:** `GET /api/v1/network/path`

**Parameters:**
- `origin`: string (required) - Canonical origin station code
- `destination`: string (required) - Canonical destination station code
- `max_hops`: integer (optional, default 3, max 10)
- `max_paths`: integer (optional, default 10, max 50)

**Validation:** 
- Missing/invalid params yield `422 Unprocessable Entity`.
- Unknown stations yield `404 Not Found`.

## 10. Response Model Proposal
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
        {"station_code": "AGC", "station_name": "Agra Cantt"},
        {"station_code": "BPL", "station_name": "Bhopal"},
        {"station_code": "NGP", "station_name": "Nagpur"},
        {"station_code": "MAS", "station_name": "Chennai Central"}
      ]
    }
  ]
}
```
Does not expose fake journey duration, transfer feasibility, live status, or train identities.

## 11. Snapshot and Graph Availability Semantics
- Follows existing conventions from `snapshots.py` and Phase 2B.
- Requires an `ACTIVE` `RailwayGraphBuild`.
- Missing/PENDING/FAILED builds return `503 Service Unavailable`.
- Station metadata exclusively relies on the active station snapshot.

## 12. Performance and Benchmark Plan
A benchmark methodology must be established to empirically measure:
- Low-hop path query (origin and destination are closely connected)
- Medium-hop path query (3-4 hops)
- No-path query (disconnected subgraph or destination too far)
- High-path-count query (traversing between major hubs)
- Worst-case bounded query
Metrics to capture: database execution time, returned path count, and response payload size.

## 13. Database/Index Considerations
Existing indexes on `RailwayNetworkEdge` (`timetable_snapshot_id, from_station_id`) are likely sufficient for CTE execution. No new indexes are proposed until empirical benchmark query plans demonstrate a measurable need.

## 14. Security and Resource Safety
To prevent abuse (e.g., exhaustive traversal requests between highly connected stations), the API will enforce strict validation bounds (`max_hops <= 10`, `max_paths <= 50`). These product safety limits ensure adherence to the ₹0 budget by preventing excessive database CPU and memory consumption.

## 15. Test Strategy
Tests will be defined for:
- Direct topology path
- Multi-hop topology path
- No path
- Reverse direction
- Cycle prevention (using array-based visited tracking)
- Repeated station topology
- Self-loop
- Same origin/destination
- max_hops boundary
- max_paths boundary
- Snapshot isolation (timetable and station metadata)
- Graph unavailable (503 translations)
- Deterministic ordering
- Path identity
- Path explosion limits

## 16. Passenger Routing Boundary
Topology path exploration relies exclusively on `RailwayNetworkEdge`. Passenger routing requires `RailwayServiceEdge` to validate train continuity, precise timings, and minimum transfer buffers. Phase 2C will not evaluate these criteria and absolutely cannot be used as a passenger travel itinerary.

## 17. Dependencies
- Depends on the existing `RailwayNetworkEdge` PostgreSQL schema.
- Depends on existing snapshot resolution APIs (`get_active_timetable_snapshot_id`, `get_active_station_snapshot_id`).

## 18. Explicit Non-Goals
- Passenger itinerary optimization
- Shortest-path journey times
- Fares, seat availability, train cancellations
- Live operational data usage
- Introduction of an external graph database (e.g., Neo4j)

## 19. Implementation Readiness Checklist
- [ ] Discovery approved
- [ ] CTE traversal algorithm finalized
- [ ] Service implementation
- [ ] API endpoint implementation
- [ ] Unit and Integration tests passing
