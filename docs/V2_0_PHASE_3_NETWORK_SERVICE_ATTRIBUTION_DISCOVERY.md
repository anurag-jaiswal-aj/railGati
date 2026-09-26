# v2.0 Phase 3 — Railway Network Service Attribution Discovery

## 1. Objective
Define the architecture for **Railway Network Service Attribution** (v2.0 Phase 3). The goal is to investigate and document how RailGati can identify and expose the specific historical train services (and their stop occurrences) that form the physical topological connections represented by a `RailwayNetworkEdge`. This phase aims to explain *why* an edge exists in the network graph.

## 2. Existing Capabilities
RailGati currently supports:
- Station search and direct journey comparison (v1.0-v1.2).
- Destination discovery (v1.3).
- Bounded network reachability (v2.0 Phase 2A/2B).
- Topology path exploration (v2.0 Phase 2C).

Currently, `RailwayNetworkEdge` provides an aggregated topological connection (`from_station_id`, `to_station_id`, `train_count`, `min_duration_minutes`). However, the existing capabilities do not expose the constituent train services that produced that aggregation. Service Attribution bridges this gap.

## 3. Product Boundary
Service Attribution explains the historical facts producing a network edge. It answers questions like:
- "Which historical train services contributed to the A → B topological edge?"
- "Which specific train numbers and stop sequences materialized this edge in the dataset?"

It explicitly **must NOT** answer:
- "Can a passenger travel from A to B?"
- "Is this train connection valid for my journey today?"

Passenger routing requires complex constraints (transfer semantics, valid connection timings, source-day continuity, etc.) which are beyond the scope of this attribution feature.

## 4. RailwayNetworkEdge ↔ RailwayServiceEdge Relationship
The `RailwayNetworkEdge` is an aggregated materialization of `RailwayServiceEdge`s.
A `RailwayNetworkEdge(from_station_id, to_station_id)` is built by grouping all `RailwayServiceEdge` rows sharing the same `timetable_snapshot_id`, `from_station_id`, and `to_station_id`.

A specific network edge can be fully reconstructed and explained by querying `RailwayServiceEdge` using:
- `timetable_snapshot_id`
- `from_station_id`
- `to_station_id`

Because this relationship directly corresponds to database schema definitions (no missing linking tables), redundant mapping structures are unnecessary. The relationship can be evaluated at runtime through a localized index scan.

## 5. Train Identity
To accurately describe the services contributing to an edge, the feature must expose canonical train information natively isolated to the timetable snapshot.
Attribution must return:
- `train_number` (from `Train`)
- `train_name`, `type`, and `return_train_number` (from `TrainObservation`)

Current/live external railway data must not be used. All identity attributes must strictly join on `timetable_snapshot_id` to guarantee historical correctness.

## 6. Stop Occurrence Identity
A single train can traverse the same topological edge multiple times during a journey (e.g., in a cyclic route).
To uniquely identify the contribution to the edge, the attribution must preserve:
- `train_id` (or `train_number`)
- `from_stop_sequence`
- `to_stop_sequence`

Repeated station occurrences by the same train must **not** be collapsed. They are distinct historical service edges and represent independent contributions to the network graph.

## 7. Snapshot Semantics
Everything in Phase 3 must belong to exactly **one active timetable snapshot**.
The query must tightly join `RailwayServiceEdge` and `TrainObservation` strictly matching the requested `timetable_snapshot_id`. Mixing train metadata from a newer snapshot with edges from an older snapshot is prohibited and breaks historical integrity.

## 8. Deduplication Semantics
A "distinct train service" in the context of attribution is defined as a unique combination of:
- `train_id`
- `from_stop_sequence`

If a train visits the same `from_station` and `to_station` twice in its schedule (e.g., sequence 5 → 6 and later sequence 20 → 21), these are two distinct services. The attribution result will include both occurrences separately. No manual collapsing of stop sequences should occur.

## 9. Network Edge Aggregate Validation
The `RailwayNetworkEdge` contains a `train_count` field. Service Attribution will:
**A. Merely expose the contributing train services.**
It will act as an analytical read-only feature. The attribution query provides the underlying list of services whose count corresponds structurally to the `train_count` generated during `RailwayGraphBuild`. Discrepancies represent dataset characteristics (such as loops) rather than errors to be dynamically recalculated at read time.

## 10. API Options
A proposed endpoint shape consistent with the project is:
`GET /api/v1/network/edges/{from_station}/{to_station}/services`

**Parameters:**
- `from_station`: Canonical station code (path parameter, case-insensitive).
- `to_station`: Canonical station code (path parameter, case-insensitive).

**Behavior:**
- **Snapshot:** Resolves against the currently `ACTIVE` graph build snapshot.
- **Pagination:** Not necessary. The maximum measured services per edge in the real dataset is 143. This fits easily into a single unpaginated JSON response without resource concerns.
- **Unknown Station:** `404 Not Found`.
- **Nonexistent Edge:** `200 OK` with an empty services array.
- **Graph Unavailable:** `503 Service Unavailable`.

## 11. Proposed Response Model
```json
{
  "from_station": "NDLS",
  "to_station": "AGC",
  "timetable_snapshot_id": 2,
  "services_returned": 2,
  "services": [
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
To ensure a stable, reproducible response, the returned services must be sorted deterministically:
1. `Train.number` ASC (lexicographical sorting of canonical train string).
2. `RailwayServiceEdge.from_stop_sequence` ASC (to deterministically order repeated visits by the same train).

## 13. Performance and Dataset Measurements
Local dataset measurements were captured for an active snapshot:
- **Total `RailwayNetworkEdge` rows**: 19,866
- **Total `RailwayServiceEdge` rows**: 411,863
- **Max `RailwayServiceEdge`s per `RailwayNetworkEdge`**: 143
- **ServiceEdge Distribution**: p50 = 11.0, p90 = 57.0, p99 = 95.0

Because the maximum payload size requires serializing at most ~150 objects, the query execution time is roughly ~1ms and the JSON payload remains under 30KB. Pagination is technically unjustified.

## 14. Database Index Analysis
The query requires filtering `RailwayServiceEdge` by `timetable_snapshot_id`, `from_station_id`, and `to_station_id`.
The existing `__table_args__` on `RailwayServiceEdge` defines:
`Index("ix_service_edges_to_station", "timetable_snapshot_id", "to_station_id")`

An `EXPLAIN ANALYZE` of the worst-case edge (143 services) demonstrates that PostgreSQL uses this index to scan ~285 rows, filtering down to 143, executing in **0.346 ms**.
Because performance is heavily sub-millisecond, **no new composite index is justified**. The existing indexes are definitively adequate.

## 15. Data Consistency Analysis
Investigation revealed 174 network edges where `RailwayNetworkEdge.train_count` does not match `COUNT(DISTINCT train_id)` in `RailwayServiceEdge`.
**Finding:** This is an expected mathematical property of the graph structure. `RailwayNetworkEdge.train_count` is defined in `graph_builder.py` as `func.count(RailwayServiceEdge.train_id)`, which represents the number of *service edge occurrences*, not the distinct number of unique trains. If a single train repeats a segment consecutively (e.g. loops), it correctly increments `train_count` multiple times. No dynamic correction is needed.

## 16. Graph Build Relationship
Service Attribution requires the `RailwayGraphBuild.status = ACTIVE`.
Although `RailwayServiceEdge` data exists during a `PENDING` state, network edge discovery intrinsically requires topological trust. Serving attribution for an incomplete graph risks exposing partial truths to the caller. Thus, the feature aligns with Phase 2 capabilities and returns `503 Service Unavailable` if the graph build is absent or inactive.

## 17. Resource Safety
Due to empirical measurements, resource risks are extremely low:
- Maximum bounds naturally cap at approximately ~150 elements per API call.
- The index execution scans minimal rows (worst-case <300 rows).
- Output bounding (`LIMIT`) is unnecessary for database execution safety, though an output bound (e.g., `LIMIT 500`) could be added strictly to prevent theoretical malicious database bloat in unforeseen future datasets.

## 18. Test Strategy
Future implementations must include tests asserting:
- Valid network edge attribution with single and multiple services.
- Deterministic ordering by `train_number` ASC, `from_stop_sequence` ASC.
- `200 OK` with an empty array for a nonexistent edge.
- Proper inclusion of repeated station occurrences (same train, distinct sequences).
- Exact snapshot isolation for both `RailwayServiceEdge` and `TrainObservation`.
- API behavior corresponding to missing graphs (`503`), unknown stations (`404`), and invalid params (`422`).

## 19. Passenger Routing Boundary
Knowing that Train 12137 contributes to edge NDLS → AGC establishes a structural graph fact, but it **does not** imply routing feasibility.
It does not guarantee seat availability, platform transfer buffers, day-of-week operation, or temporal alignment with a passenger's itinerary. Service Attribution remains explanatory graph intelligence.

## 20. Future Routing Foundation
While this phase is purely explanatory, the deterministic isolation of `RailwayServiceEdge` occurrences provides the foundational primitive necessary for future passenger routing. Future routing systems will invoke exact service-edge traversals (constrained by time and day) rather than generic `RailwayNetworkEdge` paths.

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
