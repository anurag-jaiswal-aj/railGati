# V2.0 PHASE 17 DISCOVERY: Network O-D Travel Time Analytics

## 1. Title
V2.0 PHASE 17 DISCOVERY: Network O-D Travel Time Analytics

## 2. Status
Discovery Only. No implementation, migrations, tests, or APIs have been created. Phase 18 is not started.

## 3. Objective
The objective of V2.0 Phase 17 is to extract and aggregate the continuous scheduled travel duration (travel time) between any two arbitrary, non-adjacent stations (Origin-Destination pairs) directly connected by continuous train services.

## 4. Existing V2.0 Context
The RailGati V2.0 analytics suite currently provides several structural and topological dimensions, but heavily relies on occurrence counts, set similarities, and path definitions.
- **Phases 2-5**: Network Path reachability, bounding, and attribution (hop-counts).
- **Phase 6**: Corridors (topological groups).
- **Phases 7, 8, 10**: Centrality, edge volume, O-D flow volumes. Phase 8 measures historical network-edge service occurrence volume. Phase 10 measures O-D train count volumes.
- **Phase 9**: Terminus roles.
- **Phase 11**: Station Dwell Analytics (wait times at a single node).
- **Phases 12, 13**: Route complexity and Temporal concentration (peak hours at a single node).
- **Phase 14**: Edge Flow Asymmetry.
- **Phases 15, 16**: Train/Station Route Set Similarity (Jaccard overlaps).

## 5. Candidate Directions
1. **Network O-D Travel Time Analytics**: Calculating travel duration across all continuous services connecting an origin and destination.
2. **Train Journey Duration Analytics**: Total end-to-end scheduled transit duration of a train from first origin to final terminus.
3. **Bounded Temporal Reachability (Isochrone)**: Finding all stations reachable within a strictly bounded duration.
4. **Train Stopping Pattern Alignment (Sequence Similarity)**: The longest common continuous sequence of stops between two trains.

## 6. Candidate Comparison
Candidate 1 adds a highly useful temporal dimension missing from the existing suite. Candidate 3 was rejected due to exponential performance risks without a Graph DB. Candidate 4 overlaps conceptually with Phase 15 but uses ordering. Candidate 2 is useful but narrower in scope than Candidate 1.

## 7. Selected Direction
**Network O-D Travel Time Analytics (Station Pair Duration Analytics)**

## 8. Selection Rationale
- **Novelty**: Answers "How long does it take?" across multi-hop services, adding a missing continuous temporal duration dimension.
- **Semantic Precision**: Resolves day-crossing arithmetic robustly using `source_day` without needing a complex pathing engine.
- **Implementation & Performance**: Operates safely and quickly within PostgreSQL (`< 15ms` local benchmarks) natively.
- **Data Support**: Fully supported by historical timetable properties.

## 9. Scope
- Calculate travel time (min, max, avg) and valid O-D occurrence counts between a specified origin station and destination station for all continuous train services in the active timetable snapshot.
- Handle day crossings natively using `source_day`.

## 10. Non-Goals
- Do not implement transfer-inclusive journeys (multi-train trips). This strictly measures continuous service (one train).
- Do not predict real-world delays, live operation speeds, or passenger demand.
- Do not calculate geographic distances or train speed (KM/H).
- Do not mix snapshots.

## 11. Data Sources/Tables
- `train_stop_observations`: Contains the ordered `stop_sequence`, `arrival_time`, `departure_time`, and `source_day` per `train_id`.
- `stations`: To resolve station codes to internal IDs.
- `station_observations`: To retrieve canonical station names for the active snapshot.

## 12. Snapshot Semantics
- Every train-stop lookup MUST use the same active timetable snapshot.
- Origin observation, destination observation, train identity, aggregation, and station metadata are strictly snapshot-consistent.

## 13. Exact Unit of Analysis
The unit of analysis is a **qualifying origin-destination occurrence pair**.
This means:
- Origin station O
- Destination station D
- Same train
- `origin.stop_sequence < destination.stop_sequence`

Every pair meeting these criteria constitutes one valid O-D observation segment.

## 14. Exact Duration Formula
`((destination.source_day - origin.source_day) * 1440) + (EXTRACT(EPOCH FROM destination.arrival_time::time)/60) - (EXTRACT(EPOCH FROM origin.departure_time::time)/60)`

## 15. Repeated Occurrence Semantics
If a train visits the origin or destination multiple times (e.g., A → B → A → C), **every** valid occurrence pair where `origin.stop_sequence < destination.stop_sequence` is selected and contributes as an independent analytical unit.
- They are not collapsed to one train.
- They count separately.
- E.g., if a train loops MTD → DNA → MTD → DNA, there could be 3 valid MTD → DNA occurrence pairs (seq 1->2, 1->4, 3->4). All valid pairs are aggregated.

## 16. Directionality
- O → D is independent from D → O.
- Reverse-direction observations are not merged. The query explicitly preserves direction via the `<` sequence constraint.

## 17. Return-Train Semantics
`return_train_number` is metadata only. It does not merge reverse directions, alter duration, alter counts, or deduplicate services.

## 18. Missing-Data Semantics
- `origin departure_time NULL`: Exclude the observation pair.
- `destination arrival_time NULL`: Exclude the observation pair.
- `origin source_day NULL` or `destination source_day NULL`: Exclude.
- Invalid clock values / Negative computed duration: Exclude.
- Zero duration: Retain.
- Overnight/day-crossing: Safely computed via `source_day` arithmetic.

## 19. Query Design
The query is a direct CTE performing a self-join bounded heavily by index constraints.
- Joins `train_stop_observations` to itself.
- Filters by active `snapshot_id`, origin station, destination station, and sequence constraint.
- Aggregates the resulting intersection natively.

## 20. Cardinality Considerations
Expected cardinality:
- Origin observation rows: Typically `100-500` rows.
- Destination observation rows: Typically `100-500` rows.
- Joined train pairs: Because the self-join is constrained by `train_id`, `snapshot_id`, and `stop_sequence`, the intersection typically yields `<100` valid duration observations.
- Final aggregation: 1 row.
The query cannot accidentally create a huge Cartesian product because it is explicitly bound by train identity and exact station bounds on both sides of the self-join.

## 21. SQL/CTE Stages
1. **Target Identification**: Resolve Origin and Destination codes.
2. **Intersection CTE (`od_trains`)**: Join `tso1` and `tso2` on `train_id` where `snapshot_id` matches, `tso1.station_id = O`, `tso2.station_id = D`, `tso1.stop_sequence < tso2.stop_sequence`, and times are `IS NOT NULL`.
3. **Aggregation**: `COUNT(train_id)`, `COUNT(DISTINCT train_id)`, `MIN(duration)`, `MAX(duration)`, `AVG(duration)`.

## 22. API Proposal
`GET /api/v1/network/stations/{from_station_code}/travel-time/{to_station_code}`
Returns exactly one aggregate object for the ordered O-D pair.

## 23. Request Parameters
- Path: `from_station_code` (str), `to_station_code` (str).
- Optional: None.
- Limit: Not applicable (single aggregate).

## 24. Response Schema
```json
{
  "timetable_snapshot_id": 2,
  "from_station_code": "NDLS",
  "from_station_name": "New Delhi",
  "to_station_code": "CNB",
  "to_station_name": "Kanpur Central",
  "qualifying_occurrence_count": 38,
  "distinct_train_count": 38,
  "min_duration_minutes": 274,
  "max_duration_minutes": 435,
  "avg_duration_minutes": 340.3
}
```

## 25. Error Semantics
- `404 Not Found`: Either `from_station_code` or `to_station_code` does not exist in the active snapshot.
- `400 Bad Request`: `from_station_code` equals `to_station_code` (self-loop duration is mathematically invalid here).
- Empty Result: If the stations exist but share zero qualifying trains, returns HTTP 200 with counts = 0 and durations = `null`.

## 26. Graph Dependency
Zero graph dependency. This operates purely on `train_stop_observations`. `RailwayGraphBuild`, `RailwayNetworkEdge`, and `RailwayServiceEdge` are completely unnecessary.

## 27. Performance Investigation
Current local benchmark executing the O-D intersection CTE shows extremely favorable characteristics utilizing `ix_train_stops_snapshot_station`.

## 28. EXPLAIN Findings
For `NDLS` → `CNB` on active snapshot 2:
- **Planning Time**: 1.615 ms
- **Execution Time**: 9.052 ms
- **Actual Rows**: 38 resulting from a `Merge Join` bounded by two `Index Scans`.
- **Scan Methods**: `Index Scan` on `ix_train_stops_snapshot_station` (filtering `arrival_time`/`departure_time IS NOT NULL`).
- **Sequential Scans**: None.
- **Join Methods**: `Merge Join`.
- **Aggregate Methods**: Standard SQL scalar aggregates.
- **Sort Methods**: `quicksort` (Memory: ~40kB).

## 29. Real-Data Validation
Snapshot 2 calculations explicitly verified via PostgreSQL:
- **NDLS → CNB**: 38 qualifying occurrences, 38 distinct trains. Min 274 min, Max 435 min, Avg 340.3 min.
- **CNB → NDLS** (Reverse): 39 qualifying occurrences, 39 distinct trains. Min 288 min, Max 660 min, Avg 363.2 min.
- **MTD → DNA** (Repeated station example): 25 qualifying occurrences, 23 distinct trains. Min 29 min, Max 60 min, Avg 38.2 min.
- **NDLS → DNA** (No valid journey): 0 occurrences.

## 30. Testing Strategy
- **Normal O-D pair**: Verify min, max, avg arithmetic.
- **Reverse O-D pair**: Ensure counts and durations differ from the forward direction.
- **Same station**: Ensure 400 Bad Request.
- **No qualifying train**: Ensure 200 OK with `null` durations and 0 counts.
- **One qualifying train**: Ensure min == max == avg.
- **Multiple trains**: Validate floating point average rounding.
- **Repeated origin/destination station**: Ensure multiple valid pairs per train aggregate correctly (e.g., MTD -> DNA).
- **Loop route**: Ensure deterministic parsing of sequence permutations.
- **Missing arrival/departure/source_day**: Verify exclusion.
- **Overnight/day crossing**: Ensure `(source_day * 1440)` arithmetic computes properly.
- **Invalid/negative duration**: Verify exclusion.
- **Snapshot isolation**: Ensure only active snapshot data is evaluated.
- **Return_train_number**: Ensure it is ignored gracefully.

## 31. Historical/Static Disclaimer
**MANDATORY**: This metric calculates scheduled temporal duration characteristics derived strictly from the historical timetable static dataset. It does **NOT** represent live journey duration, actual operating time, delay, reliability, passenger travel time, traffic/congestion, geographic distance, current service, current timetable, guaranteed itinerary, or calendar/day-specific operation.

## 32. ₹0 Compliance
No paid APIs, maps, or external routing engines are required. Operates completely natively within the local PostgreSQL instance.

## 33. Implementation Sequencing
1. Implement Pydantic request/response schemas.
2. Implement service logic containing the CTE/Aggregation in `services/network.py`.
3. Wire the endpoint in `api/v1/network.py`.
4. Create focused tests per the Test Strategy.
5. Execute API tests.
6. Real-data validation and EXPLAIN verification.
7. Full regression suite run.
8. Quality checks.

## 34. Deferred/Future Work
- Multi-train transfer duration analytics (finding total trip time across multiple connections).

---
*Phase 17 vs Existing Analytics Overlap Assessment*:
Phase 17 calculates scheduled temporal duration characteristics for an ordered O-D station pair. It differs fundamentally from:
- **Phase 5**: Path attribution focuses on verifying graph completeness for a single train, not temporal aggregation across all trains.
- **Phase 8**: Edge volume strictly measures train count volume on adjacent nodes, not travel duration across arbitrary non-adjacent nodes.
- **Phase 10**: O-D Flow volume measures the *count of trains* connecting an origin and destination, lacking any duration analytics.
- **Phase 11**: Station dwell calculates wait time at a single station node, not travel time between two nodes.
