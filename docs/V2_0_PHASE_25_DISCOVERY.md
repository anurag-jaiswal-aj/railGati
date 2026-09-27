# V2.0 Phase 25 Discovery

## Objective
Discover the next genuinely distinct railway-network analytics capability for RailGati V2.0. The candidate must leverage existing historical/static timetable data, avoid unsupported operational claims, and comply with strict ₹0 budget and architectural constraints.

## Relevant Existing Capability Inventory
- **Route & Path Duration**:
  - **O-D Travel Time (Phase 17)**: Analyzes the travel time bounding any structural O-D pair.
  - **Outbound Edge Transit (Phase 20)**: Analyzes the scheduled transit duration along an adjacent edge.
  - **Train Route Profile (Phase 21)**: Analyzes the absolute scheduled duration (`total_duration_minutes`) of a single specific train route.
- **Paired Services**:
  - **Paired-Service Layovers (Phase 18)**: Links a train to its `return_train_number` to analyze the scheduled layover time gap specifically *at the terminal station* between the arriving service and departing service.
  - **Edge Asymmetry (Phase 14)**: Measures *volume* asymmetry (count of trains A->B vs B->A), not temporal symmetry.

**Gap**: There is no capability that measures the macroscopic **structural temporal symmetry** of paired routes. We can analyze a single train's duration (Phase 21) or the layover gap between paired trains (Phase 18), but we cannot easily answer if the forward journey and return journey structurally schedule the same amount of time traversing the network.

## Candidate Analytics

### Candidate A: Network Station Terminus Asymmetry Analytics (Source/Sink Anomaly)
- **Question**: Does this station act purely as a terminus "sink" where trains end but don't begin, or a "source" where trains begin but don't end?
- **Exact Semantics**: Computes `originating_volume - terminating_volume` for a given station.
- **Why Distinct**: Phase 9 (Termini) outputs the list of stations that act as termini and the total volume, but does not identify anomalous directional imbalances (e.g., train graveyards). Phase 14 applies to *Edges*, not nodes.
- **Feasibility**: High. Handled via `MIN`/`MAX` stop sequence counts grouped by station.

### Candidate B: Network Train Route Topological Sinuosity Analytics (Looping)
- **Question**: How indirectly does a train traverse its topological route? Does it visit the same station multiple times, or loop around?
- **Exact Semantics**: Computes the number of stations visited multiple times by the exact same train (`total_stops - unique_stations`).
- **Why Distinct**: Phase 19 (Station Reversals) strictly checks for structural reversals (A -> B -> A) on immediately consecutive stops. Sinuosity checks for *any* topological crossover.
- **Feasibility**: Very High. Handled via `COUNT(station_id) - COUNT(DISTINCT station_id)` grouping by `train_id`.

### Candidate C: Network Train Paired-Service Temporal Symmetry Analytics (Route Duration Symmetry)
- **Question**: Do paired return services schedule equal structural transit time in both directions? (Does Train A take exactly the same number of scheduled minutes as its return Train B?)
- **Exact Semantics**: Links a requested train to its structural pair via `train_observations.return_train_number`. Calculates `total_duration_minutes` for both the forward and return journeys independently using `source_day` offset logic, and outputs the absolute `duration_asymmetry_minutes`.
- **Why Distinct**:
  - Distinct from Phase 21 (Route Profile) which analyzes only one train.
  - Distinct from Phase 18 (Paired Layovers) which measures the wait time *at the terminal* rather than comparing transit duration.
  - Distinct from Phase 14 (Edge Asymmetry) which measures *volume* on a directed edge.
- **Feasibility**: High. Re-uses the scalar `source_day` duration logic from Phase 21 while employing the `return_train_number` linkage from Phase 18. Execution occurs via nested SubPlans without full sequential scans.

## Selected Capability
**Network Train Paired-Service Temporal Symmetry Analytics**

### Selection Rationale
Candidate C fulfills the directive to deeply explore `return_train_number` semantics while completely avoiding overlap. Comparing the structural scheduled travel time of a forward journey against its reverse journey introduces a brilliant network-level validation of timetable symmetry. The database natively supports this without migration, as ~88% of trains (4,608 out of 5,207) correctly populate the `return_train_number` field.

## Exact Metric Definitions
- **forward_train_duration**: The absolute scheduled duration in minutes of the requested train, calculated from its first valid `departure_time` to its final valid `arrival_time`, properly incremented by `(source_day_last - source_day_first) * 1440`.
- **return_train_duration**: The absolute scheduled duration in minutes of the explicitly linked return train.
- **duration_asymmetry_minutes**: `ABS(forward_train_duration - return_train_duration)`.
- **return_train_number**: The exact train identity mapped via `train_observations.return_train_number` in the active snapshot.

## Endpoint Proposal
**Endpoint**: `GET /api/v1/network/trains/{train_number}/paired-symmetry`

**Response Field Proposal**:
```json
{
  "train_number": "12301",
  "return_train_number": "12302",
  "timetable_snapshot_id": 2,
  "forward_train_duration": 1020,
  "return_train_duration": 1015,
  "duration_asymmetry_minutes": 5
}
```

## Query Strategy
1. **Forward Bounds**: Using CTEs, retrieve `MIN(stop_sequence)` and `MAX(stop_sequence)` for the requested train in the active snapshot. Calculate `forward_train_duration` using `EXTRACT(EPOCH FROM ...)/60` and `source_day` scaling.
2. **Linkage**: Retrieve the canonical `return_train_number` from `train_observations` for the requested train in the active snapshot.
3. **Return Bounds**: Execute the exact same bounded logic (Step 1) against the matched `return_train_number`.
4. **Aggregation**: Output both durations and the absolute difference.

## Snapshot/Provenance Semantics
The query MUST execute strictly within the bounds of a single active `DatasetSnapshot`. If the requested train is present but its paired `return_train_number` service does not physically exist in the *same* snapshot, the query must fail gracefully.

## Edge Cases and Semantic Guardrails
- **No Return Train Defined**: If `return_train_number` is NULL, return HTTP 404 (No paired service found).
- **Return Train Missing in Snapshot**: If the returned train identity is missing from the active snapshot, return HTTP 404.
- **Insufficient Stop Data**: If either train has fewer than 2 stops with valid times, it cannot form a duration bounding box. Return HTTP 404.
- **Directional Geometry Assumption**: This metric structurally compares durations. It explicitly does *not* assert that the return train follows the exact reverse physical track geometry, only that it represents the canonical operational pair.

## Real Local Validation Results
Using the local PostgreSQL database, active snapshot 2:
- **Train 12301**:
  - `forward_train_duration`: 1020 minutes
  - `return_train_duration`: 1015 minutes
  - `duration_asymmetry_minutes`: 5 minutes
- **Train 12004**:
  - `forward_train_duration`: 410 minutes
  - `return_train_duration`: 395 minutes
  - `duration_asymmetry_minutes`: 15 minutes

## EXPLAIN ANALYZE Results
Validation against `12301` via local Postgres:
- **Planning Time**: 3.716 ms
- **Execution Time**: 1.135 ms
- **Details**: No full sequential scan of `train_stop_observations`. Fast index isolation via `ix_trains_number` and `train_stop_observations_pkey` resolves the limits near-instantly using Nested Loop Left Joins and Hash Aggregations bounded to a single train. The query footprint requires just ~24kB of intermediate memory.

## Non-Goals
This analytic explicitly does NOT claim or infer:
- Actual physical travel distances (trains may use different physical paths).
- Live/real-time delay symmetry.
- Physical locomotive or rake linkage (a train may not use the physical wagons of its pair).
- Passenger operational reliability.

## Future Implementation Boundary
- Implementation requires no database migrations.
- Add schema `PairedSymmetryResponse` to `schemas.py`.
- Add `calculate_paired_service_symmetry` to `services/network.py`.
- Expose the route in `api/v1/network.py`.
- Write API and service unit tests verifying isolated snapshot scoping and missing pair handling.

## Discovery Decision
**Network Train Paired-Service Temporal Symmetry Analytics** is APPROVED as the Phase 25 target capability. Discovery is complete; implementation is deferred.
