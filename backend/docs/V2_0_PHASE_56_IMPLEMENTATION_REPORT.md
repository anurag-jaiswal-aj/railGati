# V2.0 Phase 56 Implementation Report

## Overview
Implemented Train Sequence Topological Transition Continuity exactly according to the Phase 56 discovery document. 

- **Phase**: 56
- **Name**: Train Sequence Topological Transition Continuity
- **Endpoint**: `GET /api/v1/network/trains/{train_number}/topological-transition-continuity`

## Semantics
The metric evaluates the 2-hop topological continuity of every chronological 3-station triplet ($S_{i-1} \rightarrow S_i \rightarrow S_{i+1}$) in a target train's route. 

The numerator is the number of timetable train occurrences traversing the full ordered triplet. The denominator is the number of occurrences traversing the first 1-hop edge. 
This provides a true measure of path-preservation that is mathematically distinct from 1-hop edge volumes and perfectly aligns with the historical timetable constraints.

Duplicate cyclic routes are accurately counted using proper sequence identity.
Edge occurrence identity: `(snapshot_id, train_id, stop_sequence)`
2-hop transition occurrence identity: `(snapshot_id, train_id, first_edge_stop_sequence)`

## Query Strategy
A CTE-driven approach was utilized:
1. `target_stops`: Materialized the target train's stop observations indexed by `snapshot_id` and `train_id`.
2. `target_triplets`: Performed two self-joins on `target_stops` using consecutive `stop_sequence` (+1 and +2) to cleanly extract every topological 2-hop sequence. 
3. Correlated subqueries were issued in the final SELECT block against `train_stop_observations` bounded strictly by the target triplet nodes and snapshot, evaluating denominator (1-hop) and numerator (2-hop). 

## Indexes Used
- `idx_train_stop_observations_snapshot_train`
- `idx_train_stop_observations_snapshot_station`

## Test Results
Service tests (`tests/services/test_network_train_topological_transition_continuity.py`) cover:
- Basic 2-hop partial and perfect continuity calculation.
- Short trains with < 3 stops (yields correct empty array response with no aggregate ratio).
- Cyclic train route handling independent 3-station triplets.
- Missing train 404 validation.

API tests validate response shapes across similar scenarios without error.

## Real Data Sanity Check
Executed against train `12628` in Snapshot 2 (274 transitions). Example output:
- NDLS -> CSB -> TKJ: 102 / 102 occurrences (1.0 ratio).
- CSB -> TKJ -> PGMD: 41 / 102 occurrences (~0.401 ratio).
- TKJ -> PGMD -> NZM: 39 / 41 occurrences (~0.951 ratio).
The metric calculates gracefully and aggregates without division by zero.

## Performance Observations
Execution times per real-data requests are optimal (approx. <250ms for 200+ stops) because the database isolates sequence scans to the target train's explicit triplets via fast indexed correlations, rather than forming global cross-products of all timetable pairs.

## Limitations & Non-Goals
- Did not represent this as passenger demand, track congestion, operational continuity or physical path preservation. 
- Did not alter Phase 40 known regression.
- Did not attempt to apply cross-train return associations (`return_train_number`).

## Conclusion
Implementation is complete and adheres faithfully to the Phase 56 discovery mandate.
