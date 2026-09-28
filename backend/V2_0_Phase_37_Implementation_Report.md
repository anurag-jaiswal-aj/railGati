# V2.0 Phase 37 Implementation Report

## Objective
Implement Phase 37: Network Train Route Structural Subsumption Analytics. 
The capability accurately measures timetable-derived structural route-sequence containment between trains in a specific snapshot.

## Implementation Details

### API Endpoint
- **Method & Path:** `GET /api/v1/network/trains/{train_number}/structural-subsumption`
- **Response Schema:** `TrainStructuralSubsumptionResponse`
- **Location:** `backend/src/railgati/api/v1/network.py` and `backend/src/railgati/api/v1/schemas.py`

### Backend Service logic
- **Location:** `backend/src/railgati/services/network.py` -> `calculate_train_structural_subsumption`
- **Mechanism:** Leverages set-based relational division techniques in PostgreSQL.
    - Uses `ix_train_stops_snapshot_station` to efficiently locate candidate trains intersecting the first and last station of the target sequence.
    - Computes sequence alignment offsets via `ROW_NUMBER()` functions.
    - Counts matched contiguous stop sequences by comparing ranks and verifying exact subset alignment without using `STRING_AGG` or string matching.

### Performance
The endpoint was benchmarked using `EXPLAIN ANALYZE` on a snapshot of timetable data:
- **Test train (58202 - 15 stops):** Execution time ~10ms.
- Planner successfully utilizes `ix_train_stops_snapshot_station` indices instead of sequential scanning the complete stop occurrences table.

## Tests
- Comprehensive test coverage implemented across both unit (`tests/services/test_network_train_structural_subsumption.py`) and API layer (`tests/api/v1/test_network_train_structural_subsumption.py`).
- 15-point test suite specifically validating:
    - Basic subsumption
    - Reverse-order rejections
    - Contiguous requirement failures
    - Repeated stations
    - Identity uniqueness
    - Ambiguous duplicate train lookups
- `ruff` linter and `mypy` strict type checks fully pass.
