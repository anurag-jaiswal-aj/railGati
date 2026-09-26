# v2.0 Phase 7 Discovery: Network Hub Centrality Analytics

## 1. Objective
Design the next analytical capability on top of the RailGati v2.0 network graph foundation to compute and expose Topological Hub Centrality. This capability must identify the most structurally connected stations (hubs) in the active historical network snapshot using deterministic degree and service-weight centrality metrics.

## 2. Problem Statement
Phases 2 through 6 provide deep graph traversal, path finding, and continuous corridor discovery between specific origin-destination pairs. However, there is no macroscopic mechanism to analyze the *overall structure* of the railway network. Analytical systems need to identify which stations act as primary structural hubs, which are dead-ends, and which carry the most distinct historical service volume without performing exhaustive O(N^2) origin-to-destination pathfinding.

## 3. Why It Follows Phase 6
Phase 6 ("Network Corridor Analytics") successfully aggregated sequential topologies bounded by specific start and end nodes. Phase 7 elevates the analytics to the node level (Network Hub Centrality), allowing us to structurally rank the entire topological node map. This relies directly on the `RailwayNetworkEdge` foundation established in Phase 1 and exercised heavily in Phases 2-6.

## 4. Analytical Metrics
Centrality determines the importance of a node in a graph. For a directed railway network, we define:
- **Topological Out-Degree**: The number of unique stations physically reachable directly from the hub (count of distinct outgoing `RailwayNetworkEdge`s).
- **Topological In-Degree**: The number of unique stations that can directly reach the hub (count of distinct incoming `RailwayNetworkEdge`s).
- **Service Volume Weight**: The total number of continuous historical train occurrences flowing through the hub. This is computed by aggregating the `train_count` weights present on the `RailwayNetworkEdge`s.

## 5. Explicit Scope
- Create a new endpoint `GET /api/v1/network/hubs` (or `/centrality`) to return the highest-ranked stations by centrality.
- Compute topological in-degree and out-degree per station dynamically from the active `RailwayNetworkEdge` materialization.
- Compute the service volume weight (sum of `train_count`) for incoming/outgoing edges.
- Allow sorting by `out_degree`, `in_degree`, or `service_volume`.
- Require an `ACTIVE` `RailwayGraphBuild` to ensure structural alignment.
- Maintain strict `timetable_snapshot_id` isolation.

## 6. Explicit Non-Scope
- **Live/Dynamic Hub Analytics:** Centrality is structurally fixed for the historical timetable snapshot. It does not account for live train cancellations or temporary line closures.
- **Betweenness / Closeness Centrality:** Calculating all-pairs shortest paths (Floyd-Warshall / Brandes) to compute betweenness centrality is deferred. Phase 7 focuses exclusively on Degree Centrality which is deterministically $O(E)$ and aligns with the ₹0 performance budget.
- **Passenger Crowding:** Cannot infer passenger volume or foot traffic; this metric purely measures historical train occurrences and topological tracks.

## 7. Data / Query Model
The required data is natively materialized in `railway_network_edges` and `stations`.
A single SQL aggregation CTE can compute the centrality metrics efficiently.

**Conceptual Query Stage:**
1. **Out-Degree Aggregation:** `GROUP BY from_station_id` yielding `COUNT(*)` (out-degree) and `SUM(train_count)` (outbound service weight).
2. **In-Degree Aggregation:** `GROUP BY to_station_id` yielding `COUNT(*)` (in-degree) and `SUM(train_count)` (inbound service weight).
3. **Merge & Resolve:** Join the two aggregations on `station_id` and join with `stations` to resolve canonical codes and names.

## 8. Proposed API
**Endpoint:** `GET /api/v1/network/hubs`
**Method:** GET

**Query Parameters:**
- `limit` (integer, default 50): Number of hubs to return.
- `sort_by` (enum: `out_degree`, `in_degree`, `service_volume`; default `service_volume`): The metric to rank the hubs by.

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
      "outbound_service_volume": 415,
      "inbound_service_volume": 410,
      "total_service_volume": 825
    },
    {
      "station_code": "CNB",
      "station_name": "Kanpur Central",
      "out_degree": 38,
      "in_degree": 39,
      "outbound_service_volume": 390,
      "inbound_service_volume": 385,
      "total_service_volume": 775
    }
  ]
}
```

## 9. Error Semantics
- **503 Service Unavailable**: Raised if no active snapshot exists or if the corresponding `RailwayGraphBuild` is not `ACTIVE`.

## 10. Performance Considerations
Because `railway_network_edges` contains around 20,000 to 40,000 edges per snapshot, scanning the entire table and performing two `GROUP BY` aggregations will easily execute in sub-millisecond to low-millisecond time using standard PostgreSQL / SQLite execution plans. No new indexes are required; the existing B-Tree index on `timetable_snapshot_id` allows rapid heap scans for the relevant snapshot.

## 11. Implementation Sequence (Future)
1. Define Pydantic models for `HubCentralityItem` and `HubCentralityResponse` in `schemas.py`.
2. Implement `calculate_hub_centrality(db, snapshot_id, limit, sort_by)` in `services/network.py`.
3. Add router endpoint `GET /api/v1/network/hubs` in `api/v1/network.py`.
4. Implement rigorous isolated tests for correctness and sorting semantics in `tests/services/test_network_hubs.py`.

*(End of Discovery)*
