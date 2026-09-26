# v2.0 Phase 7 Discovery: Network Hub Centrality Analytics

## 1. Objective
Design the next analytical capability on top of the RailGati v2.0 network graph foundation to compute and expose Topological Hub Centrality. This capability must identify the most structurally connected stations (hubs) in the active historical network snapshot using deterministic topological degree metrics and adjacent service-edge occurrence weights.

## 2. Problem Statement
Phases 2 through 6 provide deep graph traversal, path finding, and continuous corridor discovery between specific origin-destination pairs. However, there is no macroscopic mechanism to analyze the *overall structure* of the railway network. Analytical systems need to identify which stations act as primary structural hubs, which are dead-ends, and which carry the most historical adjacent service-edge occurrences without performing exhaustive O(N^2) origin-to-destination pathfinding.

## 3. Why It Follows Phase 6
Phase 6 ("Network Corridor Analytics") successfully aggregated sequential topologies bounded by specific start and end nodes. Phase 7 elevates the analytics to the node level (Network Hub Centrality), allowing us to structurally rank the entire topological node map. This relies directly on the `RailwayNetworkEdge` foundation established in Phase 1 and exercised heavily in Phases 2-6.

## 4. Analytical Metrics
Topological centrality determines the structural importance of a node in a graph. For a directed railway network, we define:
- **Topological Out-Degree**: The number of unique stations physically reachable directly from the hub (count of distinct outgoing `RailwayNetworkEdge`s).
- **Topological In-Degree**: The number of unique stations that can directly reach the hub (count of distinct incoming `RailwayNetworkEdge`s).
- **Total Topological Degree**: The sum of in-degree and out-degree.
- **Inbound Service Occurrence Volume**: The sum of `train_count` on all incoming `RailwayNetworkEdge`s. (Note: `train_count` is an occurrence count derived from `RailwayServiceEdge` aggregation, not a count of distinct trains).
- **Outbound Service Occurrence Volume**: The sum of `train_count` on all outgoing `RailwayNetworkEdge`s.
- **Combined Adjacent-Edge Occurrence Volume**: The sum of inbound and outbound service occurrence volumes. **CRITICAL:** This is an adjacent-edge weight metric, not a distinct train count. A single continuous historical train occurrence passing through a hub will contribute to both an inbound edge and an outbound edge, thus being double-counted in this combined metric.

## 5. Explicit Scope
- Create a new endpoint `GET /api/v1/network/hubs` to return the highest-ranked stations by centrality.
- Compute topological in-degree and out-degree per station dynamically from the active `RailwayNetworkEdge` materialization.
- Compute the service occurrence volumes (sum of `train_count`) for incoming/outgoing edges.
- Only graph-connected stations (stations with at least one in-degree or out-degree in the current snapshot) will be returned. Isolated stations with zero degree are omitted.
- Require an `ACTIVE` `RailwayGraphBuild` to ensure structural alignment.
- Maintain strict `timetable_snapshot_id` isolation.
- Use the active station snapshot for metadata resolution.

## 6. Explicit Non-Scope
- **Live/Dynamic Hub Analytics:** Metrics are structurally fixed for the historical timetable snapshot. It does not account for live train cancellations, delays, or current availability.
- **Betweenness / Closeness Centrality:** Calculating all-pairs shortest paths to compute betweenness centrality is deferred. Phase 7 focuses exclusively on Degree Centrality.
- **Passenger Crowding:** Cannot infer passenger volume, demand, foot traffic, station popularity, or actual traffic flow; this metric purely measures historical topological tracks and adjacent service-edge occurrences.

## 7. Data / Query Model
The required data is natively materialized in `railway_network_edges` and `stations`.
A single SQL aggregation CTE can compute the centrality metrics.

**Conceptual Query Stage:**
1. **Out-Degree Aggregation:** `GROUP BY from_station_id` yielding `COUNT(*)` (out-degree) and `SUM(train_count)` (outbound service occurrence volume).
2. **In-Degree Aggregation:** `GROUP BY to_station_id` yielding `COUNT(*)` (in-degree) and `SUM(train_count)` (inbound service occurrence volume).
3. **Merge & Resolve:** Join the two aggregations on `station_id` (via FULL OUTER JOIN) and join with `stations` to resolve canonical codes and names.

## 8. Proposed API
**Endpoint:** `GET /api/v1/network/hubs`
**Method:** GET

**Query Parameters:**
- `limit` (integer, default 50): Number of hubs to return. Valid range is 1 to 500.
- `sort_by` (enum: `out_degree`, `in_degree`, `service_volume`; default `service_volume`): The metric to rank the hubs by.

**Sort Semantics (Deterministic):**
- `sort_by=out_degree`: `out_degree DESC, total_topological_degree DESC, combined_occurrence_volume DESC, station_code ASC`
- `sort_by=in_degree`: `in_degree DESC, total_topological_degree DESC, combined_occurrence_volume DESC, station_code ASC`
- `sort_by=service_volume`: `combined_occurrence_volume DESC, total_topological_degree DESC, station_code ASC`

**Response Structure:**
```json
{
  "timetable_snapshot_id": 1,
  "hubs": [
    {
      "station_code": "NDLS",
      "station_name": "New Delhi",
      "out_degree": 42,
      "in_degree": 42,
      "total_topological_degree": 84,
      "outbound_service_occurrence_volume": 415,
      "inbound_service_occurrence_volume": 410,
      "combined_occurrence_volume": 825
    }
  ]
}
```

## 9. Error Semantics
- **503 Service Unavailable**: Raised if no active snapshot exists or if the corresponding `RailwayGraphBuild` is not `ACTIVE`.
- **422 Unprocessable Entity**: Raised if `limit` exceeds 500 or `sort_by` is invalid.

## 10. Performance Considerations
Because `railway_network_edges` contains around 20,000 to 40,000 edges per snapshot, scanning the entire table and performing two `GROUP BY` aggregations must be benchmarked using EXPLAIN ANALYZE. Performance relies on the primary key index `(timetable_snapshot_id, from_station_id, to_station_id)` which provides an efficient path for scanning boundaries of a specific snapshot. We expect bounded database work proportional to $O(E)$, but exact millisecond execution times will depend on empirical measurements.

## 11. Implementation Sequence (Future)
1. Define Pydantic models for `HubCentralityItem` and `HubCentralityResponse` in `schemas.py`.
2. Implement `calculate_hub_centrality(db, snapshot_id, limit, sort_by)` in `services/network.py`.
3. Add router endpoint `GET /api/v1/network/hubs` in `api/v1/network.py`.
4. Implement rigorous isolated tests for correctness and sorting semantics in `tests/services/test_network_hubs.py`.

*(End of Discovery)*
