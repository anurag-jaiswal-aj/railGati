# Phase 48 Implementation

## Status
IMPLEMENTED, PENDING REVIEW

## Discovery Reference
Discovery document: `docs/V2_0_PHASE_48_DISCOVERY.md`
Discovery commit: `52f726e`

## Implemented Capability
Network Train Route Terminal Incidence Analytics

## Formal Semantics
Phase 48 introduces a historical timetable-derived structural metric called "train route terminal incidence". 
It calculates the ratio of a target train's occurrences that align with the global set of network terminals in the active timetable snapshot. 

A Network Terminal is defined strictly as a station identity appearing at the minimum or maximum `stop_sequence` position of at least one train occurrence in the active timetable snapshot.

This metric is historically derived from the timetable and does NOT measure:
- passenger demand;
- passenger preference;
- physical railway topology;
- infrastructure terminals;
- operational dependency;
- current/live service;
- reliability;
- congestion.

## API
- Endpoint: `GET /api/v1/network/trains/{train_number}/terminal-incidence`
- Path Parameter: `train_number` (string)
- Schema:
  ```json
  {
      "train_number": "string",
      "route_stop_occurrence_count": 0,
      "distinct_route_station_count": 0,
      "terminal_occurrence_count": 0,
      "distinct_terminal_station_count": 0,
      "incidence_ratio": 0.000
  }
  ```

## Service Implementation
The implementation relies on a highly efficient CTE-based PostgreSQL query that calculates the global network terminals from the active snapshot, and then probes the target train's ordered occurrences against this global set. The occurrences are strictly based on sequence position, accurately handling cyclic routes and repeated station visits.

## Tests
- Added service tests in `tests/services/test_network_train_route_terminal_incidence.py` covering normal routes, cyclic routes, repeated occurrences, missing trains, and inactive snapshot scoping.
- Added API tests in `tests/api/v1/test_network_train_route_terminal_incidence.py` covering successful responses and correct metric calculation.

## Real Snapshot 2 Validation
The query successfully validated against Real Snapshot 2 for the requested trains:
- Train 12951: route=202, distinct_route=202, terminal_occ=31, dist_terminal=31, ratio=0.153
- Train 04853: route=12, distinct_route=6, terminal_occ=4, dist_terminal=2, ratio=0.333
- Train 12001: route=87, distinct_route=87, terminal_occ=13, dist_terminal=13, ratio=0.149

## Performance
An `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` run for Train 12951 demonstrated:
- Planning Time: ~1.0 ms
- Execution Time: ~149 ms
- Major operators: The query successfully deployed `HashAggregate` on `CTE Scan` for the `global_terminals` resolution and a `Hash Join` between the global terminal set and `target_stops`.

## Edge Cases
- Missing target train returns `404 Not Found`.
- No active snapshot returns `503 Service Unavailable`.
- Route containing cyclic patterns maintains full occurrence representation for the incidence calculation.

## Interpretation Limits
The ratio calculation evaluates stop occurrences (sequence positions) over the distinct station identity counts, deliberately preserving the temporal traversal effort of the train in the resulting metric.

## Validation Summary
The Phase 48 implementation adheres strictly to the requirements without altering unrelated files, formatting the repository broadly, or affecting Phase 40 in any way. The pre-existing Phase 40 test failure (`test_api_edge_exclusivity_success`) is retained and preserved in the test suite execution.
