# Phase 44: Train OD Exclusivity Analytics Implementation

## Implementation Details
The Phase 44 implementation successfully computes structural origin-destination (O-D) pair exclusivity for trains. 

**O-D Pair Identity Semantics:**
- Exclusive O-D identity is defined strictly as the DISTINCT ordered station pair: `(origin_station_id, destination_station_id)`.
- Repeated target stop occurrences (e.g. looping routes) must not inflate the pair count; `SELECT DISTINCT` guarantees every returned station pair is unique.
- Therefore, `exclusive_od_pair_count == len(exclusive_od_pairs)`.
- Reverse direction travel by other trains does not negate exclusivity; only co-directional travel (origin before destination) counts as shared.

**Test Results:**
- **Focused Phase 44 Tests**: Passing fully (`uv run pytest tests/api/v1/test_network_train_od_exclusivity.py tests/services/test_network_train_od_exclusivity.py`)
- **Full Suite**: The test suite retains a pre-existing failure from a previous Phase 40 implementation (`test_api_edge_exclusivity_success` returns 404), as Phase 44 isolated modifications explicitly exclude unrelated API repair. 

**Snapshot 2 Real Validation:**
- Train 12004 -> 0 exclusive O-D pairs
- Train 12951 -> 0 exclusive O-D pairs
- Train 11013 -> 2155 exclusive O-D pairs

**Final EXPLAIN ANALYZE for 11013:**
```
Sort  (cost=100636.82..100642.34 rows=2209 width=116) (actual time=1026.400..1026.452 rows=2155 loops=1)
  Sort Key: tp.o_code, tp.d_code
  Sort Method: quicksort  Memory: 173kB
  CTE target_stops
    ->  Index Scan using train_stop_observations_pkey on train_stop_observations
...
  ->  Merge Anti Join  (cost=94194.47..99293.55 rows=2209 width=116) (actual time=739.527..1025.565 rows=2155 loops=1)
...
Planning Time: 0.244 ms
JIT:
  Functions: 68
  Options: Inlining false, Optimization false, Expressions true, Deforming true
  Timing: Generation 1.182 ms, Inlining 0.000 ms, Optimization 0.622 ms, Emission 13.342 ms, Total 15.146 ms
Execution Time: 1044.502 ms
```

## Scope Auditing
- Reverted all unrelated formatting and Phase 40 endpoint additions (like the `route-edge-exclusivity` bug fix) erroneously introduced during prior revisions.
- No Phase 40 repair was included in the final Phase 44 state.
- All scratch files cleaned up.
