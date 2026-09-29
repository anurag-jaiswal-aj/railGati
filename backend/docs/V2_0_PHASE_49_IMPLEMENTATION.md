# Phase 49 Implementation

## Status
PHASE 49 — IMPLEMENTED, PENDING REVIEW

## Discovery Reference
- **Document**: `docs/V2_0_PHASE_49_DISCOVERY.md`
- **Commit**: `1e0beb2`

## Implemented Capability
Network Station Pair Route Extension Analytics

Calculates the footprint of train occurrences serving a specific origin and destination station. Specifically, it measures the timetable-derived station extension structures lying outside the bounds of the O->D pair for that specific traversal.

## Formal Semantics
For an ordered station pair (O, D), using the active timetable snapshot:
1. Valid traversal instances are identified where the train visits O and then D in sequence (`s_o < s_d`).
2. Each traversal instance independently defines its own `Pre` (stations before `s_o`) and `Post` (stations after `s_d`) sequence bounded sets.
3. The resulting pre-origin and post-destination station identities are globally merged and deduplicated.
4. The output provides the distinct traversal occurrence count, the distinct station counts of the `Pre` and `Post` sets, and the total distinct station count of the unioned sets.

## Traversal / Occurrence Semantics
- **Train Identity**: Evaluated independently per valid occurrence. A single train can contribute multiple valid O->D traversal instances.
- **Cyclic/Repeated Traversals**: If a train traverses O->D multiple times, each valid pair (`s_o`, `s_d`) acts as an independent traversal instance for evaluating the pre/post station extensions. Repeated station identities inside a single extension segment are aggregated exactly once.

## API
`GET /api/v1/network/station-pairs/{origin_code}/{destination_code}/route-extension`

**Response Schema** (`StationPairRouteExtensionResponse`):
```json
{
    "origin_station": "CNB",
    "destination_station": "NDLS",
    "traversal_occurrence_count": 39,
    "pre_origin_station_count": 1038,
    "post_destination_station_count": 76,
    "total_extension_station_count": 1114
}
```

## Service Implementation
- Located at `calculate_station_pair_route_extension` in `src/railgati/services/network.py`.
- Utilizes a purely relational, set-based PostgreSQL CTE query.
- Extracts `valid_traversals` using `$s_o < s_d$`.
- Joins observations against the `s_o` bound for the `pre_origin_stops`.
- Joins observations against the `s_d` bound for the `post_dest_stops`.
- Applies set union and aggregate deduplication directly via the SQL execution engine.
- Active timetable isolation guarantees no data leakage between network builds.

## Tests
- **Service Tests**: `tests/services/test_network_station_pair_route_extension.py` includes validation for standard traversals, lack of direct paths, identical station inputs, and cyclical overlapping route traversal identities.
- **API Tests**: `tests/api/v1/test_network_station_pair_route_extension.py` covers endpoint accessibility, input validation (400, 404), and exact response field formats.

## Real Snapshot 2 Validation
The values were independently validated against Snapshot 2 and yielded exact matches:
- NDLS -> CNB: 38 traversals, 28 pre, 1044 post, 1072 total
- CNB -> NDLS: 39 traversals, 1038 pre, 76 post, 1114 total
- GKP -> LKO: 24 traversals, 499 pre, 886 post, 1385 total
- BCT -> BVI: 23 traversals, 0 pre, 477 post, 477 total

## Performance
An `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` execution for the massive `CNB -> NDLS` flow generated:
- **Planning Time**: ~1.3 ms
- **Execution Time**: ~7.8 ms
- **Operators**: The measured query relied heavily on `CTE Scan`, `Hash Join`, and `HashAggregate` operators for fast traversal alignment. Performance observations indicate effective indexing on the `train_stop_observations` composite keys.

## Edge Cases
- **Missing Inputs**: `404 Not Found` if one or both stations do not exist.
- **Zero Traversals**: `404 Not Found` if O and D exist but no direct path connects them.
- **Same Station**: `400 Bad Request` if `origin_code == destination_code`.
- **Missing Snapshot**: `503 Service Unavailable`.

## Interpretation Limits
This metric is explicitly:
- historical
- timetable-derived
- snapshot-scoped
- ordered O→D
- traversal-instance based
- station-identity aggregated

It explicitly does **NOT** measure:
- geographic extent
- physical railway infrastructure
- track coverage
- passenger demand
- passenger preference
- capacity
- operational dependency
- current/live service
- reliability
- congestion

## Validation Summary
- Semantics: Fully compliant.
- Output: Fully compliant.
- Snapshot Integrity: 100% Match.
- Phase Overlap: Distinctly bounded metrics logic.
