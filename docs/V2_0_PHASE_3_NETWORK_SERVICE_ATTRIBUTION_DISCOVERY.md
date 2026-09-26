# v2.0 Phase 3 — Railway Network Service Attribution Discovery

## 1. Objective
Define the architecture for **Railway Network Service Attribution** (v2.0 Phase 3). The goal is to investigate and document how RailGati can identify and expose the specific historical service-edge occurrences that form the physical topological connections represented by a `RailwayNetworkEdge`. This phase aims to explain *why* an edge exists in the network graph.

## 2. Existing Capabilities
RailGati currently supports:
- Station search and direct journey comparison (v1.0-v1.2).
- Destination discovery (v1.3).
- Bounded network reachability (v2.0 Phase 2A/2B).
- Topology path exploration (v2.0 Phase 2C).

Currently, `RailwayNetworkEdge` provides an aggregated topological connection (`from_station_id`, `to_station_id`, `train_count`, `min_duration_minutes`). However, the existing capabilities do not expose the constituent train services that produced that aggregation. Service Attribution bridges this gap.

## 3. Product Boundary
Service Attribution explains the historical facts producing a network edge. It answers questions like:
- "Which historical service-edge occurrences contributed to the A → B topological edge?"
- "Which specific train numbers and stop sequences materialized this edge in the dataset?"

It explicitly **must NOT** answer:
- "Can a passenger travel from A to B?"
- "Is this train connection valid for my journey today?"

Passenger routing requires complex constraints (transfer semantics, valid connection timings, source-day continuity, etc.) which are beyond the scope of this attribution feature.

## 4. RailwayNetworkEdge ↔ RailwayServiceEdge Relationship
The `RailwayNetworkEdge` is an aggregated materialization of `RailwayServiceEdge` rows.
A `RailwayNetworkEdge(from_station_id, to_station_id)` is built by grouping all `RailwayServiceEdge` rows sharing the same `timetable_snapshot_id`, `from_station_id`, and `to_station_id`.

A specific network edge can be fully reconstructed and explained by querying `RailwayServiceEdge` using:
- `timetable_snapshot_id`
- `from_station_id`
- `to_station_id`

Because this relationship directly corresponds to database schema definitions, redundant mapping structures are unnecessary.

## 5. Train Identity
To accurately describe the services contributing to an edge, the feature must expose canonical train information correctly isolated to the timetable snapshot.

While `Train` is a canonical entity across all time, its names and types can change. `TrainObservation` contains the snapshot-specific metadata. Therefore, the attribution API must join `RailwayServiceEdge` to `TrainObservation` using exactly `timetable_snapshot_id` and `train_id`. The future API must never combine a ServiceEdge from snapshot X with train metadata from snapshot Y.

Attribution must return:
- `train_number` (from `Train`)
- `train_name`, `type`, and `return_train_number` (from `TrainObservation`)

## 6. Stop Occurrence Identity
A single train can traverse the same topological edge multiple times during a journey (e.g., in a cyclic route).
To uniquely identify the contribution to the edge, the attribution must distinguish **service-edge occurrences**. A `RailwayServiceEdge` occurrence is identified exactly by the primary key combination:
- `timetable_snapshot_id`
- `train_id`
- `from_stop_sequence`

Repeated station occurrences by the same train must **not** be collapsed merely because they share a `train_id`, `from_station_id`, and `to_station_id`. If the same train contributes multiple distinct ServiceEdges for the same station pair, they must be preserved as distinct occurrences.

## 7. Snapshot Semantics
Everything in Phase 3 must belong to exactly **one active timetable snapshot**.
The query must tightly join `RailwayServiceEdge` and `TrainObservation` strictly matching the requested `timetable_snapshot_id`.

## 8. Deduplication Semantics
We must distinguish clearly between "service-edge occurrences" and "distinct train services".
- A **service-edge occurrence** is a single physical traversal defined by `from_stop_sequence`.
- A **distinct train service** is the unique identity of the train (`train_id`).

If a train visits the same `from_station` and `to_station` twice in its schedule (e.g., sequence 5 → 6 and later sequence 20 → 21), these are two distinct service-edge occurrences of one distinct train service. The attribution result will include both occurrences separately. No manual collapsing of stop sequences should occur.

## 9. Network Edge Aggregate Validation
The `RailwayNetworkEdge` contains a `train_count` field.
The graph builder implements `train_count` using `func.count(RailwayServiceEdge.train_id)`, which executes a standard SQL `COUNT(*)` over the non-null primary key. It explicitly counts **service-edge occurrences**, not `COUNT(DISTINCT train_id)`.

A local dataset investigation verified this: 174 network edges have a `train_count` that exceeds the number of distinct `train_id`s, precisely because looping trains create multiple distinct service-edge occurrences for the same station pair. This is the correct topological behavior, and the Service Attribution API will natively return every service-edge occurrence, perfectly matching the `train_count` aggregate.

## 10. API Options
Evaluate the endpoint shape:
`GET /api/v1/network/edges/{from_station}/{to_station}/services`

Existing endpoints in RailGati consistently use query parameters for stations (e.g., `GET /api/v1/network/reachable?origin=...`, `GET /api/v1/destinations/direct?origin=...`). To maintain a consistent REST shape, the proposed endpoint is:

`GET /api/v1/network/attribution?origin={origin_code}&destination={destination_code}`

**Behavior:**
- **Snapshot:** Resolves against the currently `ACTIVE` graph build snapshot.
- **Unknown Station:** `404 Not Found`.
- **Nonexistent Edge:** `200 OK` with an empty occurrences array.
- **Graph Unavailable:** `503 Service Unavailable`.
- **Pagination:** See Resource Safety (Section 17).

## 11. Proposed Response Model
```json
{
  "origin": "NDLS",
  "destination": "AGC",
  "timetable_snapshot_id": 2,
  "occurrences_returned": 2,
  "occurrences": [
    {
      "train_number": "12137",
      "train_name": "PUNJAB MAIL",
      "train_type": "SF",
      "from_stop_sequence": 5,
      "to_stop_sequence": 6,
      "departure_time": "05:15",
      "arrival_time": "08:10",
      "duration_minutes": 175
    }
  ]
}
```
Only historical facts documented in the local PostgreSQL dataset are exposed.

## 12. Deterministic Ordering
To ensure a stable, reproducible response, the returned occurrences must be sorted deterministically:
1. `Train.number` ASC (lexicographical sorting of canonical train string).
2. `RailwayServiceEdge.from_stop_sequence` ASC (to deterministically order repeated visits by the same train).

## 13. Performance and Dataset Measurements
Local dataset measurements were captured for an active snapshot:
- **Total `RailwayNetworkEdge` rows**: 19,866
- **Total `RailwayServiceEdge` rows**: 411,863
- **Max `RailwayServiceEdge`s per `RailwayNetworkEdge`**: 143
- **ServiceEdge Distribution**: p50 = 11.0, p90 = 57.0, p99 = 95.0

For the current active historical snapshot, the largest observed station-pair attribution contained 143 `RailwayServiceEdge` rows.

## 14. Database Index Analysis
The likely attribution query is:
```sql
WHERE timetable_snapshot_id = ?
  AND from_station_id = ?
  AND to_station_id = ?
```
The existing `__table_args__` on `RailwayServiceEdge` defines:
`Index("ix_service_edges_to_station", "timetable_snapshot_id", "to_station_id")`

An `EXPLAIN ANALYZE` of the largest observed edge (143 services) demonstrates that PostgreSQL uses this index to scan ~285 rows, filtering down to 143. Existing indexes were benchmarked for the current dataset, and the measured representative query completed in approximately 0.346 ms. No additional index is justified by the current measurements. A future composite index should only be introduced if representative `EXPLAIN ANALYZE` results demonstrate a measurable need.

## 15. Data Consistency Analysis
As verified in Section 9, `RailwayNetworkEdge.train_count` accurately matches the count of `RailwayServiceEdge` occurrences. No data consistency anomalies exist regarding this aggregate; the perceived difference purely stems from the distinction between distinct trains and distinct occurrences.

## 16. Graph Build Relationship
Service Attribution requires the `RailwayGraphBuild.status = ACTIVE`.
While the attribution data could technically be derived directly from `RailwayServiceEdge`, the explicit purpose of this feature is to explain a `RailwayNetworkEdge`. If the network edge is unavailable (because the graph build is `PENDING` or `FAILED`), the foundational topological assertion is absent. Therefore, the API must return `503 Service Unavailable` if an active graph build does not exist.

## 17. Resource Safety
For the current active historical snapshot, the largest observed station-pair attribution contained 143 `RailwayServiceEdge` rows, executing in < 1 ms. These measurements describe the current dataset and do not establish a universal upper bound.

To provide a strict API contract and prevent pathological resource consumption in future unforeseen datasets, the API must introduce an explicit resource bound.
- **Output Bound**: The API will impose a strict limit (e.g., `LIMIT 500`) on returned occurrences.
Because pagination is unnecessary for the current scope (where the absolute maximum is well below 500), pagination logic will be deferred. The API contract explicitly guarantees returning *at most* 500 occurrences, ensuring safety regardless of dataset changes.

## 18. Test Strategy
Future implementations must include tests asserting:
- Valid network edge attribution with single and multiple occurrences.
- Deterministic ordering by `train_number` ASC, `from_stop_sequence` ASC.
- `200 OK` with an empty array for a nonexistent edge.
- Proper inclusion of repeated station occurrences (same train, distinct sequences).
- Exact snapshot isolation for `RailwayServiceEdge`, `TrainObservation`, and `StationObservation`.
- API behavior corresponding to missing graphs (`503`), unknown stations (`404`), and invalid params (`422`).
- Truncation behavior capping outputs at the explicit API bound (e.g., 500).

## 19. Passenger Routing Boundary
Service Attribution explains a historical graph artifact. Knowing that Train 12137 contributes to edge NDLS → AGC establishes a structural graph fact.
It does **NOT** establish:
- passenger-valid transfers
- connection feasibility
- date-specific operation
- service calendars
- itinerary validity

Service Attribution remains explanatory graph intelligence, not itinerary planning.

## 20. Future Routing Foundation
Service Attribution can expose historical service-edge occurrences and their existing timing/source-day fields, but it does NOT itself establish any routing guarantees. It serves purely as a static, structural foundation that future systems might build upon to evaluate time-bound calendars and operations.

## 21. ₹0 Constraint
The architecture relies entirely on the local PostgreSQL dataset. No external routing engines, paid infrastructure, or live railway APIs are required or permitted.

## 22. Explicit Non-Goals
This discovery rigorously excludes:
- Live train status, delays, and PNR tracking.
- Fare and seat availability.
- Dynamic passenger itinerary generation or transfer feasibility analysis.
- Third-party database systems (Neo4j, Redis).
- LLM-based routing logic.

## 23. Implementation Readiness Checklist
- [x] Defined objective and boundaries.
- [x] Evaluated database performance and index requirements.
- [x] Addressed data consistency (train counts).
- [x] Established deterministic ordering rules.
- [x] Finalized JSON payload structure and REST endpoint architecture.
