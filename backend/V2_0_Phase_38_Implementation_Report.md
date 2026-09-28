# V2.0 Phase 38 Implementation Report

## Objective
Implement Phase 38: Network Train Route Topological Bypass Analytics.
The capability evaluates a target train's ordered route against the broader active timetable adjacency graph and finds network edges that connect non-consecutive positions of that target route.

## Implementation Details

### API Endpoint
- **Method & Path:** `GET /api/v1/network/trains/{train_number}/topological-bypasses`
- **Response Schema:** `TrainTopologicalBypassResponse`
- **Location:** `backend/src/railgati/api/v1/network.py` and `backend/src/railgati/api/v1/schemas.py`

### Backend Service Logic
- **Location:** `backend/src/railgati/services/network.py` -> `calculate_train_topological_bypasses`
- **Mechanism:** Leverages relational SQL CTEs in PostgreSQL.
    - Resolves the target train and active snapshot.
    - Uses `ROW_NUMBER()` to assign ranks to stops in `train_stop_observations`.
    - Generates all valid non-consecutive pairs ($j > i + 1$).
    - Joins these pairs against `train_stop_observations` to verify if any train provides an adjacent edge between them.
    - Uses `DISTINCT` to ensure multiple trains providing the same bypass edge are only counted once.

### Performance
The endpoint was benchmarked using `EXPLAIN ANALYZE` on a snapshot of timetable data:
- **Worst-case train (12318 - 394 stops):** Execution time ~80 ms.
- Planner successfully utilizes `ix_train_stops_snapshot_station` to fetch all outbound edges and performs an efficient Hash Join. No full sequential scan over the timetable occurs.

## Real Snapshot 2 Validation
Independent validation was performed using actual active Snapshot 2 data, matching the discovery findings perfectly:
- **Train 58202:** 0 bypass edges
- **Train 51145:** 0 bypass edges
- **Train 55512:** 0 bypass edges
- **Train 51916:** 4 bypass edges
- **Train 16779:** 24 bypass edges
- **Train 12720:** 36 bypass edges
- **Train 12318:** 82 bypass edges

## Tests
- Comprehensive test coverage implemented across both unit (`tests/services/test_network_topological_bypasses.py`) and API layer (`tests/api/v1/test_network_topological_bypasses.py`).
- Focused test suite covers:
    - Normal case with multiple bypasses.
    - No bypass edges.
    - Short train mathematically incapable of bypasses.
    - Duplicate station visits handling.
    - Duplicate trains providing the same bypass handling (counted once).
    - Reverse direction edge handling (must not count).
    - Active snapshot scoping.
    - Train not found scenarios.
- `ruff` linter and `mypy` strict type checks fully pass.

## Semantic Meaning
**"Structural bypass" is a historical timetable-derived graph metric.**
It does NOT represent:
- physical railway shortcuts
- passenger route alternatives
- faster journeys
- operational redundancy
- capacity
- congestion
- reliability
- passenger demand
- real-world network resilience
