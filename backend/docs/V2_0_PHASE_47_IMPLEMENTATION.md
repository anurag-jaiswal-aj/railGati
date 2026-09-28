# Phase 47 Implementation: Station Pair Route-Boundary Confinement Analytics

## Overview
Phase 47 introduces "Station Pair Route-Boundary Confinement Analytics". This capability analyzes all historical timetable traversal instances between two stations (O -> D) within an active timetable snapshot, classifying them strictly into mutually exclusive operational states based on dataset-derived traversal boundary sequences.

## Formal Semantics
For an origin station `O` and a destination station `D`:
1. Find every valid historical timetable traversal instance, forming the target traversal set.
2. Traversal identity is defined exactly by the tuple: `(train_id, origin_sequence, destination_sequence)`.
3. For each traversal `tt = (train_id, origin_sequence, destination_sequence)`, we derive the train's boundaries `T_min = MIN(stop_sequence)` and `T_max = MAX(stop_sequence)` for that `train_id`.
4. The traversal `tt` is classified into exactly one of the following states:
    * `STRICTLY_BOUNDED`: `origin_sequence == T_min` AND `destination_sequence == T_max`
    * `ORIGIN_BOUNDED`: `origin_sequence == T_min` AND `destination_sequence < T_max`
    * `DESTINATION_BOUNDED`: `origin_sequence > T_min` AND `destination_sequence == T_max`
    * `UNBOUNDED_EMBEDDED`: `origin_sequence > T_min` AND `destination_sequence < T_max`

The response yields the aggregated total counts for each state.

## Implementation Details

### Database / Service Layer
* Extends `src/railgati/services/network.py` by implementing `calculate_station_pair_route_boundary_confinement(db, from_station_code, to_station_code)`.
* Uses highly-optimized Common Table Expressions (CTE) to:
  1. Determine `target_traversals` using `train_stop_observations`.
  2. Compute `train_boundaries`.
  3. Form `classified_traversals` grouping the boundaries into exactly one state using a conditional `CASE`.
  4. Aggregate and yield the mutually exclusive boundary categories.

### API Layer
* Adds endpoint `GET /api/v1/network/stations/{from_station_code}/{to_station_code}/route-boundary-confinement` within `src/railgati/api/v1/network.py`.
* Schema definitions appended to `src/railgati/api/v1/schemas.py`.

### Tests
* **Service:** Added `tests/services/test_network_station_pair_route_boundary_confinement.py`
* **API:** Added `tests/api/v1/test_network_station_pair_route_boundary_confinement.py`

## Verification
* Validated Snapshot 2 ground truth values: `NDLS` -> `HWH` (6, 6, 0, 0, 0), `LTT` -> `PUNE` (27, 0, 4, 6, 17), `NDLS` -> `CNB` (38, 2, 35, 0, 1), `VDR` -> `CDG` (0, 0, 0, 0, 0).
* Verified high-performance index usage via `EXPLAIN (ANALYZE, BUFFERS)` showing ~0.15ms planning and ~1.1ms execution time using `ix_train_stops_snapshot_station` and `train_stop_observations_pkey` index scans without expensive sequential sweeps.
* Fully compliant with Ruff, MyPy, and full test suite regression passing.
