# V2.0 Phase 55 Implementation Report

## Implemented Endpoint
`GET /api/v1/network/trains/{train_number}/sequence-subgraph-density`

## Exact Semantics Implemented
The redesigned metric measures the directed subgraph density of a train's topological sequence mapped against the global timetable network.
- **Route Vertices**: Distinct chronologically ordered sequence occurrences $V = \{1, 2, \dots, n\}$.
- **Global Edges**: Topological adjacency pairs traversed by any train in the active snapshot.
- **Pairs Evaluated**: All $n(n-1)$ possible sequence pairs $(i, j)$ where $i \neq j$.
- **Forward Chords**: Network edges skipping ahead ($j > i+1$).
- **Backward Chords**: Network edges returning back ($j < i$).
- **Density**: The actual count divided by the mathematically possible combinations for the specific dimension, normalized to `[0.0, 1.0]`.

## Implementation Approach
- Added `TrainSequenceSubgraphDensityResponse` Pydantic model with strict validation according to the discovery doc.
- Developed `calculate_train_sequence_subgraph_density` service logic using declarative PostgreSQL CTEs to process the active network subgraph directly in the database.
- Implemented robust `n` occurrence scaling, zero-handling, and combinatorial fractional densities strictly adhering to the `(n-1)(n-2)/2` and `n(n-1)/2` bounding space equations.
- Handled global error state routing (`HTTPException 503`, `ValueError`) robustly in the FastAPI endpoint layer.

## Repeated/Cyclic Handling
Cyclic stops inherently spawn unique occurrence indices. `ts1.seq != ts2.seq` prevents self-evaluation without incorrectly excluding combinations mapping to the same physical `station_id`. This rigorously satisfies the mathematical mandate, ensuring that return iterations compound combinatorially without database structural breakdown.

## Distinction from Phase 38
Phase 38 operates explicitly on distinct physical station geometries (`station_id = A`, `station_id = B`) and evaluates raw bypass edge presence. Phase 55 establishes the topological density mapped sequentially across the mathematical length of the train's sequence ($n$), fully interpreting the density of reverse graph combinations entirely ignored by Phase 38's design.

## Test Results
- **Focused Service Tests**: 4 tests mapping normal, cyclic, short, and missing trains. Passed.
- **Focused API Tests**: 2 tests enforcing endpoint behavior and 503 snapshot awareness. Passed.
- **Full Backend Tests**: Executed cleanly.

## Snapshot 2 Validation Values
Validated against Snapshot 2 explicitly:
- **12951**: $F_{actual}=2$, $B_{actual}=203 \implies D_{fwd} \approx 0.000099, D_{bwd} \approx 0.00999$
- **19019**: $F_{actual}=7$, $B_{actual}=242 \implies D_{fwd} \approx 0.000252, D_{bwd} \approx 0.00865$
- **16688**: $F_{actual}=9$, $B_{actual}=497 \implies D_{fwd} \approx 0.000076, D_{bwd} \approx 0.00421$
- **04853**: $n=12$, $F_{actual}=13$, $B_{actual}=24 \implies D_{fwd} \approx 0.236, D_{bwd} \approx 0.363$

## EXPLAIN ANALYZE Results
Executed using Train `12951` on Snapshot 2.
- **Planning Time**: 0.314 ms
- **Execution Time**: 479.309 ms
- **Major Plan Shape**: The plan uses a `Hash Left Join` bridging the train's internal target sequence combinations against a `HashAggregate` global edge hash table.
- **Sequential Scans**: Workers invoke `Parallel Seq Scan` to extract `train_stop_observations` restricted to `snapshot_id=2`.
- **Global Edge Materialization**: The global edges are materialized entirely using `Parallel Seq Scan` across multiple workers.
- **Disk Spill**: No temporary disk spill for the hash table is observed in the plan, as it completes entirely in memory.

## Known Pre-Existing Phase 40 Failure
The full suite evaluation successfully ran all tests. The repository maintains the single intentionally unresolved failure from Phase 40 (`test_api_edge_exclusivity_success`) which expects a 200 but receives a 404 since that module is incomplete.

## Files Changed
- **Modified**: `src/railgati/api/v1/schemas.py`, `src/railgati/api/v1/network.py`, `src/railgati/services/network.py`
- **Created**: `tests/services/test_network_train_sequence_subgraph_density.py`, `tests/api/v1/test_network_train_sequence_subgraph_density.py`, `docs/V2_0_PHASE_55_IMPLEMENTATION_REPORT.md`
