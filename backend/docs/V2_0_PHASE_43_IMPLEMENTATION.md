# RailGati V2.0 – Phase 43 Implementation: Train Maximum Shared Sub-Route Analytics

## 1. Objective
Implement the Phase 43 network analytics capability: **Train Maximum Shared Sub-Route Analytics**, which identifies the maximum contiguous length of identically ordered sequence of stations that a target train shares with any other distinct candidate train within the historical timetable structure.

## 2. Endpoint
`GET /api/v1/network/trains/{train_number}/maximum-shared-sub-route`

## 3. Formal Metric Semantics
- **Target Train ($T$):** The train identity to inspect.
- **Candidate Train ($U$):** Any other train identity ($U \neq T$) present in the identical timetable snapshot.
- **Shared Sub-Route ($L$):** A set of consecutive stops $S_T(i...i+L-1) = S_U(j...j+L-1)$ representing exact structural alignment.
- **Result:** Returns all candidate trains $U$ tied for the global maximum shared length $L$, exposing the count alongside the starting and ending station codes of the overlap.

## 4. Database/Query Strategy
The exact query strategy proposed in the discovery document was safely implemented.
1. `target_stops` CTE extracts the stops and stop sequences of the target train.
2. `shared_segments` CTE joins candidate train observations, identifying exact sub-routes by leveraging `GROUP BY t2.train_id, tr2.number, (target.stop_sequence - candidate.stop_sequence)`.
3. `ranked_segments` CTE applies `RANK() OVER (ORDER BY shared_len DESC)` to correctly identify all instances tied for the global maximum length.
4. A final `SELECT DISTINCT` safely de-duplicates occurrences where the exact same target structural locus might inadvertently match the same candidate multiple times (if the candidate route repeats sections, although mathematically separated by offsets).

## 5. Service Implementation
Implemented `calculate_train_max_shared_sub_route` in `src/railgati/services/network.py`.
- Incorporates strict active timetable snapshot resolution.
- Validates that the target train exists within the active snapshot observation table.

## 6. API Implementation
Implemented `get_train_max_shared_sub_route` in `src/railgati/api/v1/network.py`.
- Includes `TrainMaxSharedSubRouteItem` and `TrainMaxSharedSubRouteResponse` in `src/railgati/api/v1/schemas.py`.

## 7. Test Coverage
Added robust service tests in `tests/services/test_network_train_max_shared_sub_route.py` and API tests in `tests/api/v1/test_network_train_max_shared_sub_route.py` validating:
1. Expected extraction of tied maximums.
2. Guaranteed filtering of non-contiguous alignments.
3. Guaranteed filtering of reverse-direction sequence alignments.
4. Correct extraction of repeated identical sequences leveraging `SELECT DISTINCT`.
5. 404 behavior for unknown trains.

## 8. Snapshot 2 Validation
The finalized service was explicitly tested against the real PostgreSQL Snapshot 2 timetable with perfect parity to discovery:
- **Target 12004:** shared_length = 74, start = NDLS, end = LKO. Matches: 12420, 12556, 12566.
- **Target 12951:** shared_length = 202, start = BCT, end = NDLS. Matches: 19023.
- **Target 11013:** shared_length = 124, start = LTT, end = GY. Matches: 11027, 16381.

## 9. Performance / EXPLAIN ANALYZE
The query was re-evaluated against Train 12004:
- **Planning:** ~0.619 ms
- **Execution:** ~7.564 ms
- **Observations:** No sequential scans. `HashAggregate` on the offset difference continues to efficiently group alignments directly in-memory, requiring under 1MB of memory. Candidate matching remains strictly relational and purely deterministic. No arbitrary LIMITs were employed during candidate evaluation.

## 10. Semantic Guardrails
This is a purely historical timetable-derived structural metric indicating strictly: **"maximum contiguous station-sequence overlap between distinct train identities in the active historical timetable snapshot."**
It explicitly does NOT signify:
- Shared physical railway track or physical infrastructure availability.
- Possibility of passenger transfer or temporal/operational alignment.
- Express corridor designation or mainline vs branch assignments.

## 11. Files Changed
- `src/railgati/api/v1/schemas.py`
- `src/railgati/api/v1/network.py`
- `src/railgati/services/network.py`
- `tests/api/v1/test_network_train_max_shared_sub_route.py`
- `tests/services/test_network_train_max_shared_sub_route.py`

## 12. Known Limitations
None.

## 13. Final Validation
All Phase 43 unit tests successfully passed. The full repository test suite succeeded (excluding one pre-existing known Phase 40 failure). MyPy type-checking reports no newly introduced typing errors within the modified file sections. Ruff formatting is clean on added tests. Snapshot 2 real-data outcomes match mathematical expectations precisely. No arbitrary limits were introduced. Phase 43 implementation is finalized.
