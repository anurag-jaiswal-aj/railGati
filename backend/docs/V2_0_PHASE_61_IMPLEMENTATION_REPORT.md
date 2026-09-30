# RailGati V2.0 — Phase 61: Train Route Single-Station Intersection Analytics Implementation Report

## Implementation Summary
Added the `GET /api/v1/network/trains/{train_number}/single-station-intersections` endpoint to identify trains that intersect the target train's canonical station identity set at exactly one station identity. The implementation relies on a set-based PostgreSQL CTE approach to avoid N+1 queries and efficiently filter for exact cardinality overlap.

## Formal Mathematical Definition
For target train $T$ and candidate train $U$ in the same active timetable snapshot:
Let $V(T)$ = distinct station identities visited by $T$.
Let $V(U)$ = distinct station identities visited by $U$.

The candidate train $U$ qualifies iff:
$$ |V(T) \cap V(U)| = 1 $$

## Phase 15 Novelty Boundary
Phase 15 (Train Similarity) calculates scalar overlap bounds (e.g. `overlap_station_count = 1`) but completely discards the canonical station identity (station code) of the intersection. Phase 61 is implemented specifically to retain and project the exact station identity of the intersection (where it occurred) for trains meeting the exact 1-station intersection criterion.

## Database and Query Strategy
A single analytical query handles the entire resolution:
1. `target_stations`: CTE to extract `DISTINCT station_id` for $T$.
2. `intersecting_trains`: CTE to join all other trains ($U \neq T$) stopping at any station in `target_stations`.
3. `qualifying_trains`: Aggregates by `train_id`, grouping to evaluate `HAVING COUNT(DISTINCT station_id) = 1`. This isolates candidate trains intersecting exactly once and captures the single `MIN(station_id)` (which is the only ID).
4. Selects and joins the required station and train nomenclature, fully eliminating N+1 DB round-trips.

## Duplicate / Repeated / Cyclic Semantics
The query employs `COUNT(DISTINCT station_id)`. Thus, if $T$ and $U$ intersect at exactly one station (e.g. `STN_B`), but either train visits `STN_B` multiple times (cyclic loops, out-and-back extensions), they still yield exactly $1$ distinct overlapping station identity and qualify correctly. Zero intersections and $\ge 2$ intersections are structurally excluded by the `HAVING` clause. 

## Test Results
- **Focused Tests:** 6 passed (isolated SQL and FastAPI test validations confirming inclusion/exclusion conditions, repeated visits, empty overlap, and 404 boundaries).
- **Full Suite:** 630 passed, 1 failed (the existing legacy Phase 40 `test_api_edge_exclusivity_success` 404).
- **Ruff:** Completed (ignored 830 baseline issues).
- **MyPy:** Completed (ignored 344 baseline issues).

## Real Snapshot 2 Validation
Validated using an active timetable snapshot script.
- **Target Train:** `15906`
- **Total Route Size:** 698 recorded stops
- **Total Intersecting Trains:** 187
- **Representative Match:** `05697` (Hill Queen Express) sharing station `LMG` exactly once.

## Performance
- **Query Count:** 1 primary analytical SQL execution.
- **Execution Time Measurements:**
  - Train 53328 (Short, 11 distinct stations): ~0.029s (29ms), 55 candidates
  - Train 51830 (Medium, 32 distinct stations): ~0.008s (8ms), 271 candidates
  - Train 15906 (Long, 689 distinct stations): ~0.037s (37ms), 187 candidates
- **Set-Based:** Yes, relies exclusively on hash-aggregates without loop-driven iterations.

## Explicit Non-Claims
The endpoint calculates structural timetable connectivity based strictly on canonical station identities. It makes **no claims** regarding:
- Passenger interchange/transfers
- Physical railway junctions or platform sharing
- Traffic volume, congestion, or delay properties
- Timed operational crossings

## Assurances
- Phase 40 remains untouched.
- Phase 62 has NOT been started.
- All constraints (₹0 budget, modular monolith limits) maintained.
