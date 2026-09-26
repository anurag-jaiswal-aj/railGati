# v2.0 Phase 8 Discovery: Network Edge Volume Analytics

**STATUS:** DISCOVERY ONLY.
**IMPLEMENTATION:** DEFERRED.

## 1. Objective
Design the next analytical capability on top of the RailGati v2.0 network graph foundation to compute and expose Topological Edge Volume (Segment Centrality). This capability must identify the historically most frequently traversed direct physical segments (adjacent station pairs) in the active network snapshot using deterministic edge weights.

## 2. Problem Statement
Phase 7 ("Network Hub Centrality Analytics") elevated network analytics to the node level, allowing us to structurally rank stations by their topological degree and adjacent service-edge occurrences. However, we currently lack a macroscopic mechanism to rank the graph's *edges*. Analytical systems need to identify the busiest physical historical track segments (e.g., global bottlenecks or primary arteries) without exhaustively aggregating arbitrary O-D corridors (Phase 6). We must expose edge-level centrality directly from the pre-computed `RailwayNetworkEdge` foundation.

## 3. Why It Follows Phase 7
Phase 7 structurally ranked graph **nodes** (stations). Phase 8 logically completes basic macroscopic graph analytics by ranking graph **edges** (segments). This relies entirely on the `RailwayNetworkEdge` materialization established in Phase 1, utilizing the `train_count` property. It requires zero new graph-building overhead, adheres to the ₹0 constraints, and adds significant historical network intelligence.

## 4. Analytical Metrics
Topological Edge Volume determines the structural historical load on a specific physical directed track segment.
- **Service Occurrence Volume**: The `train_count` on a single directed `RailwayNetworkEdge`. This is the aggregate count of continuous historical service occurrences (`RailwayServiceEdge`) that physically traverse the segment from `from_station` directly to `to_station`.
- **CRITICAL REMINDER**: This is an occurrence count, not a count of distinct trains, and definitely not a passenger count.

## 5. Explicit Scope
- Create a new endpoint `GET /api/v1/network/edges/volume` to return the highest-ranked directed graph edges by service occurrence volume.
- Retrieve the edge weights (`train_count`) directly from the active `RailwayNetworkEdge` materialization.
- Require an `ACTIVE` `RailwayGraphBuild` to ensure structural alignment.
- Maintain strict `timetable_snapshot_id` isolation.
- Use the active station snapshot for `from_station` and `to_station` metadata resolution.

## 6. Explicit Non-Scope
- **Live/Dynamic Segment Traffic:** Edge volumes are structurally fixed for the historical timetable snapshot. It does not account for live train cancellations, dynamic rerouting, or real-time track occupation.
- **Betweenness / Closeness Edge Centrality:** Calculating all-pairs shortest paths to compute edge betweenness centrality is explicitly deferred.
- **Passenger Crowding:** Cannot infer passenger volume, demand, or ticket sales on the segment.
- **Operational Feasibility:** Does not infer that the track segment is currently operational or open to traffic today.

## 7. Data / Query Model
The required data is natively materialized and uniquely keyed by `(timetable_snapshot_id, from_station_id, to_station_id)` in `railway_network_edges`.

**Conceptual Query Stage:**
1. **Edge Selection:** `SELECT from_station_id, to_station_id, train_count FROM railway_network_edges WHERE timetable_snapshot_id = :active_snapshot`
2. **Metadata Resolution:** Double `INNER JOIN` to `stations` and `station_observations` to resolve the canonical codes and names for both `from_station_id` and `to_station_id`.
3. **Sorting & Limit:** Apply deterministic sorting to return the top `N` records.

## 8. Proposed API
**Endpoint:** `GET /api/v1/network/edges/volume`
**Method:** GET

**Query Parameters:**
- `limit` (integer, default 50): Number of edges to return. Valid range is 1 to 500.

**Sort Semantics (Deterministic):**
Because `limit` will likely be applied to a globally sorted list, the sort must be perfectly deterministic to prevent pagination/offset bleeding (if pagination is ever added) and to ensure stable analytical results.
- **Sort Order:** `train_count DESC, from_station_code ASC, to_station_code ASC`

**Response Structure:**
```json
{
  "timetable_snapshot_id": 1,
  "edges": [
    {
      "from_station_code": "KYN",
      "from_station_name": "Kalyan Junction",
      "to_station_code": "TNA",
      "to_station_name": "Thane",
      "service_occurrence_volume": 143
    }
  ]
}
```

## 9. Error Semantics
- **503 Service Unavailable**: Raised if no active timetable snapshot exists, if no active station snapshot exists, or if the corresponding `RailwayGraphBuild` is not `ACTIVE`.
- **422 Unprocessable Entity**: Raised if `limit` exceeds the maximum allowed bound.

## 10. Performance Considerations & Measurement Methodology
Since `railway_network_edges` contains around 20,000 to 40,000 edges per snapshot, sorting the entire snapshot's edges by volume can be executed highly efficiently.
- **Database bounds:** The query will likely perform a `Seq Scan` on `railway_network_edges` (filtered by snapshot), followed by a `Top-N heapsort` and `Hash Join`s to the metadata tables.
- **Validation:** EXPLAIN ANALYZE must be executed during implementation to verify:
  1. Planning Time
  2. Execution Time
  3. Proper utilization of Top-N heapsort avoiding full in-memory Sorts if possible.
  4. Number of rows scanned vs rows returned.
  5. Index usage (verifying if `(timetable_snapshot_id)` primary key prefix provides sufficient bounding).
- **Application Load:** If the database handles the limit and sort (via `ORDER BY ... LIMIT`), the payload transferred to Python will be strictly bounded by `limit` (e.g., 50 rows).

## 11. Test Strategy (Future Implementation)
The eventual implementation must contain focused tests covering:
- **Normal case:** Valid retrieval of top edges.
- **Empty result:** Behavior when the network graph has 0 edges.
- **Snapshot isolation:** Ensuring edges from inactive/other snapshots do not leak.
- **Graph-build validation:** Ensuring a 503 is thrown for a missing or `FAILED` graph build.
- **Deterministic ordering:** Verifying tie-breaking on `from_station_code` and `to_station_code`.
- **Invalid parameters:** `limit < 1` or `limit > 500`.

## 12. Candidate Directions Considered
Before selecting Edge Volume Analytics, the following candidates were evaluated:
- **Network Subgraph / Component Connectivity:** Partitioning the network to find isolated broad-gauge vs narrow-gauge clusters. Rejected due to the high complexity of recursive CTEs and minimal historical/analytical value compared to edge loading.
- **Historical Service Frequency Analytics:** Analyzing the topology of train runs themselves (e.g., identifying the physical longest-running train occurrence). Rejected as it overlaps heavily with Phase 6 and deviates from the node/edge structural analytics established in Phase 7.
- **Selection Justification:** Edge Volume Analytics is the exact edge-equivalent of Phase 7's node Hub Centrality. It reuses the exact same models, fits cleanly into a fast PostgreSQL query, and exposes highly requested macroscopic track-load intelligence.

*(End of Discovery)*
