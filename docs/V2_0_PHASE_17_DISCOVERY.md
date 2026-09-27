# V2.0 PHASE 17 DISCOVERY: Network O-D Travel Time Analytics

## 1. Phase Objective
The objective of V2.0 Phase 17 is to extract and aggregate the continuous scheduled travel duration (travel time) between any two arbitrary, non-adjacent stations (Origin-Destination pairs) directly connected by continuous train services.

## 2. Status
Discovery Only. No implementation, tests, or APIs have been created.

## 3. V2.0 Context & Existing Capability Map
The RailGati V2.0 analytics suite currently provides several structural and topological dimensions, but heavily relies on occurrence counts, set similarities, and path definitions.

**Existing Dimensions:**
- **Phases 2-5**: Network Path reachability, bounding, and attribution (hop-counts).
- **Phase 6**: Corridors (topological groups).
- **Phases 7, 8, 10**: Centrality, edge volume, O-D flow volumes (train count volumes).
- **Phase 9**: Terminus roles.
- **Phase 11**: Station Dwell Analytics (wait times at a single node).
- **Phase 12, 13**: Route complexity and Temporal concentration (peak hours at a single node).
- **Phase 14**: Edge Flow Asymmetry.
- **Phases 15, 16**: Train/Station Route Set Similarity (Jaccard overlaps).

**Missing Dimension**: None of the above capabilities measure the *temporal span of a continuous path*. Phase 10 calculates the *volume* of trains between an O-D pair, and Phase 8 handles the *velocity/duration* strictly for immediate edges (adjacent nodes). Phase 17 bridges this gap by calculating transit durations across multi-hop continuous services.

## 4. Candidate Directions Considered
Four candidates were identified exploring genuinely new analytical dimensions:
1. **Network O-D Travel Time Analytics**: Calculating the minimum, maximum, and average travel duration across all continuous services connecting an origin and destination.
2. **Train Journey Duration Analytics**: Calculating the total end-to-end scheduled transit duration of a train from its first origin to its final terminus.
3. **Bounded Temporal Reachability (Isochrone)**: Finding all stations reachable from an origin station within a strictly bounded duration (e.g. 120 minutes).
4. **Train Stopping Pattern Alignment (Sequence Similarity)**: Calculating the longest common continuous sequence of stops between two trains (in contrast to Phase 15's unordered set overlap).

## 5. Candidate Comparison & Selection Rationale
**Selected Candidate**: **Network O-D Travel Time Analytics**

**Rationale**:
- **Novelty**: Adds a critical missing temporal dimension (journey duration) across multi-hop services.
- **Semantic Precision**: Resolves day-crossing arithmetic robustly using `source_day` without needing a complex pathing engine.
- **Usefulness**: Answering "How long does it take to travel from A to B?" is fundamentally more useful to end users than raw flow volumes (Phase 10) or Jaccard similarities (Phases 15/16).
- **Performance**: As proven in exploration, calculating exact durations from direct relational self-joins takes `<15ms` in PostgreSQL utilizing existing indexes, keeping it well within the ₹0 budget and latency limits.
- Bounded Temporal Reachability (Isochrone) was discarded because recursive time accumulation in CTEs risks exponential explosion and performance degradation without a dedicated Graph DB.

## 6. Scope & Non-Goals
**Scope**:
- Calculate travel time (min, max, avg) between a specified origin station and destination station for all continuous train services in the active timetable snapshot.
- Handle day crossings natively using `source_day`.
- Exclude missing data points (NULL timings).

**Non-Goals**:
- Do not implement transfer-inclusive journeys (multi-train trips). This strictly measures continuous service (one train).
- Do not predict real-world delays or live operation speeds.
- Do not attempt to calculate geographic distance or train speed (KM/H), as geospatial segment metrics are unavailable in the current dataset.

## 7. Data Sources & Tables
- `train_stop_observations`: Contains the ordered `stop_sequence`, `arrival_time`, `departure_time`, and `source_day` per `train_id`.
- `stations`: To resolve station codes to internal IDs.
- `station_observations`: To retrieve canonical station names for the active snapshot.

## 8. Snapshot Semantics
- The query must strictly isolate to the active `timetable_snapshot_id`.
- Temporal attributes (`arrival_time`, `departure_time`, `source_day`) must only be extracted from observations belonging to the active snapshot.

## 9. Exact Metric Definitions
- **Duration (Minutes)**: Evaluated per valid train connecting the Origin (O) and Destination (D) where O's stop sequence < D's stop sequence.
  - Formula: `((D.source_day - O.source_day) * 1440) + (EXTRACT(EPOCH FROM D.arrival_time::time)/60) - (EXTRACT(EPOCH FROM O.departure_time::time)/60)`.
- **Minimum Duration**: The lowest calculated duration among valid trains.
- **Maximum Duration**: The highest calculated duration among valid trains.
- **Average Duration**: The arithmetic mean of all calculated durations, rounded to 1 decimal place.
- **Fastest Train Count**: Number of trains achieving exactly the minimum duration.

## 10. Graph-Build Dependency
- **Zero Graph Dependency**: This capability operates entirely through relational bounds on the `train_stop_observations` table. It does not require `RailwayNetworkEdge`, `RailwayServiceEdge`, or recursive graphing logic.

## 11. Repeated-Occurrence & Directionality Semantics
- **Directionality**: Directed. O-D metrics from `NDLS` -> `CNB` only look at trains where `NDLS.stop_sequence < CNB.stop_sequence`.
- **Repeated Occurrences**: If a train loops and visits a station multiple times, the query relies on the earliest valid departure from O and the earliest valid arrival at D, or evaluates all valid pairs. For simplicity, filtering on `tso1.stop_sequence < tso2.stop_sequence` evaluates all valid sequential pairings of a looping train.

## 12. Time & Missing-Data Semantics
- Exclude pairs where `tso1.departure_time` is NULL or `tso2.arrival_time` is NULL, as accurate duration cannot be computed.

## 13. Query Design
**Expected SQL/CTE Stages**:
1. **Target Identification**: Resolve Origin and Destination station codes to their primary IDs.
2. **Intersection Join**: `JOIN train_stop_observations tso1` with `tso2` on `train_id`, filtered by `snapshot_id = :snapshot_id`.
3. **Sequence Bound**: Filter where `tso1.station_id = O`, `tso2.station_id = D`, and `tso1.stop_sequence < tso2.stop_sequence`.
4. **Time Bound**: Filter where `tso1.departure_time IS NOT NULL` and `tso2.arrival_time IS NOT NULL`.
5. **Aggregation**: `COUNT(DISTINCT train_id)`, `MIN(duration)`, `MAX(duration)`, `AVG(duration)`.

## 14. Performance Investigation & EXPLAIN Findings
Exploratory benchmarking on active local snapshot 2 (`~8,989` stations, `~5,207` trains) for O-D pair `NDLS` (ID 8534) to `CNB` (ID 1779) yielded:
- **Planning Time**: 1.615 ms
- **Execution Time**: 9.052 ms

**Plan Insights**:
- **Index Usage**: Explicitly uses `ix_train_stops_snapshot_station` to instantly isolate valid observations for both NDLS and CNB.
- **Join Strategy**: Employs an efficient `Merge Join` over the resulting subsets ordered by `train_id`.
- **Sequential Scans**: Zero full-table sequential scans. The query remains extremely bound to the indexed subsets.
- **Scalability**: The Cartesian product risk is neutralized because the self-join is scoped entirely to a strict intersection of `train_id` on two pre-filtered station index scans.

## 15. API Proposal
**GET /api/v1/network/stations/{from_station_code}/travel-time/{to_station_code}**

**Request Parameters**:
- `from_station_code` (str): Origin station code.
- `to_station_code` (str): Destination station code.

**Response Schema**:
```json
{
  "timetable_snapshot_id": 2,
  "from_station_code": "NDLS",
  "from_station_name": "New Delhi",
  "to_station_code": "CNB",
  "to_station_name": "Kanpur Central",
  "total_continuous_trains": 38,
  "min_duration_minutes": 274,
  "max_duration_minutes": 435,
  "avg_duration_minutes": 340.3
}
```

**HTTP Error Semantics**:
- `404 Not Found`: Either `from_station_code` or `to_station_code` does not exist in the active snapshot.
- `400 Bad Request`: `from_station_code` equals `to_station_code` (self-loop duration is meaningless).

## 16. Real-Data Validation
**Local testing using actual Snapshot 2 data**:
- **O-D Pair**: `NDLS` to `CNB`
- **Total Trains**: 38 continuous services.
- **Min Duration**: 274 minutes (4h 34m).
- **Max Duration**: 435 minutes (7h 15m).
- **Avg Duration**: ~340.3 minutes.

## 17. Testing Strategy
- **Normal Case**: Verify duration arithmetic exactly matches expected outputs for known NDLS->CNB schedules.
- **Missing Data**: Ensure trains lacking `arrival_time` or `departure_time` do not crash the aggregation or yield negative numbers.
- **Day Crossings**: Ensure a train arriving the next day correctly factors in the `1440` minute multiplier from `source_day`.
- **Reverse Direction**: Validate `from_station=CNB` to `to_station=NDLS` accurately segregates trains going the opposite way.
- **Self-Loop Exclusion**: Assert `400 Bad Request` if origin and destination codes are identical.
- **Zero Trains**: Verify a valid 200 OK response with `null` metrics if the stations exist but share no continuous trains.

## 18. Historical/Static Disclaimer
**MANDATORY**: This capability computes scheduled temporal travel duration derived exclusively from historical static timetable constraints. It explicitly does NOT reflect live train speed, geographic distance, delays, real-time rerouting, or real-world passenger operational reliability.

## 19. ₹0 Compliance
This metric adheres to the strict ₹0 constraint. No external distance APIs (like Google Maps) or paid geospatial mapping services are queried; all mathematical extraction occurs within PostgreSQL using relative epoch timestamps.

## 20. Implementation Sequencing
1. Implement Pydantic request/response schemas.
2. Implement service logic containing the CTE/Aggregation in `services/network.py`.
3. Wire the endpoint in `api/v1/network.py`.
4. Create localized unit and service boundary tests.
5. Execute API integration tests and perform final real-data profiling.
6. Verify non-regression against Phases 1-16.

## 21. Deferred/Future Possibilities
- **Transfer Isochrones**: Factoring multi-hop, multi-train transfers into travel time aggregation is deferred due to unbounded combinatorial explosion risks.
