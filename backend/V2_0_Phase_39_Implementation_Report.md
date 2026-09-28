# V2.0 Phase 39 Implementation Report

## Objective
Implement Phase 39: Network Edge Traversal Dispersion Analytics.
The capability evaluates the structural dispersion (convergence and bifurcation) of trains traversing a specific directed network edge $A \to B$.

## Implementation Details

### API Endpoint
- **Method & Path:** `GET /api/v1/network/edges/{from_station_code}/{to_station_code}/traversal-dispersion`
- **Response Schema:** `EdgeTraversalDispersionResponse`
- **Location:** `backend/src/railgati/api/v1/network.py` and `backend/src/railgati/api/v1/schemas.py`

### Backend Service Logic
- **Location:** `backend/src/railgati/services/network.py` -> `calculate_edge_traversal_dispersion`
- **Mechanism:** Leverages an efficient relational query in PostgreSQL using a Common Table Expression (CTE).
    - Resolves the target edge $A \to B$ occurrences within the active snapshot.
    - Aggregates the occurrences volume.
    - Uses `COUNT(DISTINCT t_prev.station_id)` via a self-join to sequence $i-1$ for `convergence_count`.
    - Uses `NOT EXISTS` at sequence $i-1$ for `originating_count`.
    - Uses `COUNT(DISTINCT t_next.station_id)` via a self-join to sequence $i+1$ (relative to destination) for `bifurcation_count`.
    - Uses `NOT EXISTS` at sequence $i+1$ (relative to destination) for `terminating_count`.

### Performance
The endpoint was benchmarked using `EXPLAIN ANALYZE` on a snapshot of timetable data:
- **Worst-case tested edge (SBB -> GZB):** Execution time ~12 ms.
- Planner successfully utilizes `ix_train_stops_snapshot_station` to fetch all inbound occurrences and performs rapid nested-loop joins with index-only scans to evaluate $seq-1$ and $seq+1$ conditions. No full sequential scan over the timetable occurs.

## Real Snapshot 2 Validation
Independent validation was performed using actual active Snapshot 2 data, matching the discovery findings perfectly:
- **SBB -> GZB:** edge volume: 143, convergence: 6, bifurcation: 5, originating: 0, terminating: 1
- **MSB -> MSF:** edge volume: 132, convergence: 1, bifurcation: 2, originating: 119, terminating: 0
- **DI -> THK:** edge volume: 121, convergence: 2, bifurcation: 1, originating: 0, terminating: 0
- **BWN -> TIT:** edge volume: 118, convergence: 1, bifurcation: 1, originating: 16, terminating: 0

## Tests
- Comprehensive test coverage implemented across both unit (`tests/services/test_network_edge_traversal_dispersion.py`) and API layer (`tests/api/v1/test_network_edge_traversal_dispersion.py`).
- Focused test suite covers:
    - Normal case with multiple bypasses/divergences.
    - Duplicate identical train routes properly collapsing into single convergence/bifurcation identity counts.
    - Directional distinction verification ($A \to B \neq B \to A$).
    - Originating and terminating train handling.
    - Error conditions (unknown station, nonexistent edge).
    - Active snapshot scoping boundary.
- `ruff` linter and `mypy` strict type checks fully pass.

## Semantic Meaning
**"Traversal dispersion" is a purely historical timetable-derived structural metric.**
It quantifies the scheduled routing connectivity around an edge.

It does NOT represent:
- passenger flow
- passenger demand
- physical junction topology
- current railway operations
- congestion
- capacity
- reliability
- operational dependency
- real-world resilience
- current 2026 railway behavior
