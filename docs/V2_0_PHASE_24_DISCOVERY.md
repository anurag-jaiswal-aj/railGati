# V2.0 Phase 24 Discovery

## Objective
Discover the next genuinely distinct railway-network analytics capability for RailGati V2.0. The candidate must leverage existing historical/static timetable data, avoid unsupported operational claims, and comply with strict ₹0 budget and architectural constraints.

## Relevant Existing Capability Inventory
- **Edges & Connectivity**: 
  - **Edge Volume (Phase 8)**: Calculates total daily scheduled volume for a specific edge.
  - **Outbound Edge Transit (Phase 20)**: Analyzes the average/min/max scheduled transit *duration* along an outbound edge.
- **Temporal**:
  - **Temporal Concentration (Phase 13)**: Categorizes *Station* traffic into rigid 4-hour chronological blocks (Morning/Night).
  - **Temporal Gaps (Phase 23)**: Analyzes continuous cyclic "dead zones" (longest interval without departures) at a *Station*.

**Gap**: There is no metric that analyzes the micro-temporal density (rolling peak concentration) of trains scheduled to traverse a specific track segment (*Edge*). Users can see the total daily volume of an edge (Phase 8), but cannot determine if that volume is evenly distributed or bottlenecked into massive platoons occurring in narrow time windows.

## Candidate Analytics

### Candidate A: Network Train Leg Spacing Analytics (Micro-Variances)
- **Question**: What is the scheduled travel time variance between consecutive stops on a single train's route?
- **Exact Semantics**: Computes the transit duration between every consecutive stop pair (`stop_sequence i` to `i+1`) for a single train, yielding the longest and shortest non-stop leg durations.
- **Why Distinct**: Phase 21 evaluates the global profile (`total_duration`, `total_stops`) but fails to expose micro-leg variances.
- **Feasibility**: High. Handled via `LEAD(arrival_time)` partitioned by `train_id`.

### Candidate B: Network Route Topological Sinuosity Analytics
- **Question**: How physically indirect is a train's topological path? Does it loop back on itself?
- **Exact Semantics**: Computes the number of stations visited multiple times by the exact same train.
- **Why Distinct**: Phase 19 (Station Reversals) strictly checks for structural reversals (A -> B -> A) on immediately consecutive stops. Sinuosity checks for *any* topological crossover (e.g., A -> B -> C -> D -> A) regardless of sequence adjacency.
- **Feasibility**: High. Handled via `COUNT(station_id) - COUNT(DISTINCT station_id)` grouping by `train_id`.

### Candidate C: Network Edge Temporal Bunching Analytics (Peak Hour Volume)
- **Question**: What is the absolute maximum concentration of scheduled trains across a specific edge within any rolling 60-minute window?
- **Exact Semantics**: For a directed edge (Station A -> Station B), identifies all qualifying target trains, extracts their scheduled departures at Station A, projects them onto a cyclic 24-hour clock (with midnight wraparound), and evaluates a sliding 60-minute window to find the peak scheduled throughput.
- **Why Distinct**:
  - Distinct from Phase 8 (Edge Volume) which returns *total daily* throughput.
  - Distinct from Phase 13 (Temporal Concentration) which arbitrarily slices *Station* traffic into static 4-hour buckets.
  - Distinct from Phase 23 (Temporal Gaps) which measures inactivity gaps at a *Station*. This isolates peak cyclic *Edge* capacity constraints.
- **Feasibility**: Extremely high. Using scalar subqueries over a self-joined subset runs efficiently in Postgres (< 7ms) without sequential scanning.

## Selected Capability
**Network Edge Temporal Bunching Analytics (Peak Hour Volume)**

### Selection Rationale
Candidate C introduces a highly distinct, specialized metric describing localized track-segment scheduling density (Edge Bottlenecks). It leverages advanced cyclic temporal analysis (wraparound bounds) scaled to edges rather than nodes, providing a deep structural insight without requiring new data sources.

## Exact Metric Definitions
- **edge**: A directed sequence from `origin_station_code` to `destination_station_code` strictly bound by `stop_sequence i` and `stop_sequence i+1` for a single train.
- **total_edge_volume**: The total distinct daily train occurrences scheduled to traverse this edge (identical to Phase 8 logic).
- **peak_60min_trains**: The maximum number of trains scheduled to depart the `origin_station` within any continuous 60-minute cyclic window, bound strictly for the `destination_station`.
- **cyclic window**: A continuous 60-minute span evaluated at every discrete departure event. Handles midnight wraparound by virtually extending the clock (e.g. evaluating a window spanning 23:50 to 00:50).

## Endpoint Proposal
**Endpoint**: `GET /api/v1/network/edges/{origin_code}/{destination_code}/temporal-bunching`

**Response Field Proposal**:
```json
{
  "origin_station_code": "CSB",
  "destination_station_code": "NDLS",
  "timetable_snapshot_id": 2,
  "total_edge_volume": 100,
  "peak_60min_trains": 16
}
```

## Query Strategy
1. **Target Trains**: Retrieve matching trains by self-joining `train_stop_observations` (`tso1` and `tso2`) on `train_id`, bounded by `stop_sequence = stop_sequence + 1` and filtering by the queried `origin_code` and `destination_code`.
2. **Clock Extraction**: Convert `tso1.departure_time` to elapsed minutes from midnight (`dep_mins`).
3. **Wraparound Projection**: Create a virtual CTE `expanded_trains` containing `dep_mins` `UNION ALL` `dep_mins + 1440`.
4. **Sliding Window**: For every discrete departure in `edge_trains`, perform a sub-select to count trains in `expanded_trains` where `dep >= origin_dep` AND `dep < origin_dep + 60`.
5. **Aggregation**: `SELECT MAX()` of these counts.

## Edge Cases and Semantic Guardrails
- **No Edge Exists**: Return HTTP 404.
- **NULL departure_time**: Explicitly exclude rows where `tso1.departure_time` is NULL (i.e. terminating trains that technically shouldn't proceed to B anyway).
- **source_day**: Must be entirely ignored. The metric describes the scheduled cyclic density assuming all operating days collapse into a single 24-hour structural clock.

## Real Local Validation Results
Using the local PostgreSQL database, active snapshot 2:
- **CSB -> NDLS**:
  - `total_edge_volume`: 100
  - `peak_60min_trains`: 16 
  *(16% of daily edge volume is concentrated in a single scheduled peak hour!)*
- **NDLS -> CSB**:
  - `total_edge_volume`: 100
  - `peak_60min_trains`: 14

## EXPLAIN ANALYZE Results
Validation against `CSB -> NDLS`:
- **Planning Time**: 1.547 ms
- **Execution Time**: 6.160 ms
- **Details**: No full sequential scan of `train_stop_observations`. Fast index isolation via `ix_train_stops_snapshot_station` identifies candidates instantly, leveraging a `Hash Join` across `stop_sequence` subsets to yield 100 base rows. Sub-queries resolve entirely in-memory using Append/Aggregate loops.

## Non-Goals
This analytic explicitly does NOT claim or infer:
- Passenger demand/congestion.
- Actual live track congestion or real-time train delays.
- Train operational conflicts (the timetable may schedule trains to depart 1 minute apart).

## Future Implementation Boundary
- Implementation requires no database migrations.
- Update `schemas.py` for `EdgeTemporalBunchingResponse`.
- Add `calculate_edge_temporal_bunching` to `services/network.py`.
- Expose the route in `api/v1/network.py`.
- Write API and service unit tests verifying cyclic windows and edge failures.

## Discovery Decision
**Network Edge Temporal Bunching Analytics (Peak Hour Volume)** is APPROVED as the Phase 24 target capability. Discovery is complete; implementation is deferred.
