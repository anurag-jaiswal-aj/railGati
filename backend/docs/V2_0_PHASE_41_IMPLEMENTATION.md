# Phase 41 Implementation Report: Network Edge Route Terminal Dispersion Analytics

## 1. Implementation Summary
Phase 41 successfully implemented the **Network Edge Route Terminal Dispersion Analytics** capability. 
This metric assesses the structural diversity of terminal points for trains traversing a specific directed edge `A -> B` within the active timetable snapshot. The implementation provides insight into how a specific edge is utilized as a shared conduit by distinct train identities originating from and bound for diverse endpoints.

## 2. Exact Semantics
For a requested directed adjacent timetable edge `A -> B`:

1.  **Distinct Train Identity Semantics (`T(A,B)`)**: The set of distinct train identities in the active timetable snapshot that contain at least one consecutive stop pair `A -> B`. Repeated traversal of `A -> B` by the same train identity is deduplicated and counts exactly once.
2.  **`traversing_train_count`**: The total count of distinct trains in `T(A,B)`.
3.  **Terminal Identification**: For each selected train identity, the origin is defined as the station at `min(stop_sequence)` and the destination is the station at `max(stop_sequence)`.
4.  **`distinct_origin_count`**: The number of distinct origin stations across all trains in `T(A,B)`.
5.  **`distinct_destination_count`**: The number of distinct destination stations across all trains in `T(A,B)`.

## 3. Endpoint Implemented
- **Route**: `GET /api/v1/network/edges/{from_station_code}/{to_station_code}/route-terminal-dispersion`
- **Controller File**: `src/railgati/api/v1/network.py`
- **Method**: `get_edge_route_terminal_dispersion`

## 4. Service and Schema Changes
- **Service Function**: `calculate_edge_route_terminal_dispersion` added to `src/railgati/services/network.py`.
- **Schema**: `EdgeRouteTerminalDispersionResponse` added to `src/railgati/api/v1/schemas.py`.

## 5. Test Coverage
Extensive testing was added using isolated fixtures (`TEST_API_DISP`) to prevent snapshot contamination:
- **Service Layer**: 
    - `test_dispersion_basic_cases`: Tests multi-train routes, distinct terminal counting, and deduplication (e.g., train traversing edge multiple times).
    - `test_dispersion_no_edge`: Tests missing directed edges.
    - `test_dispersion_unknown_station`: Tests 404 validation.
    - `test_dispersion_active_snapshot_isolation`: Verifies queries respect strict snapshot scoping.
- **API Layer**:
    - Valid HTTP response logic.
    - Error mapping to 404 for missing stations/edges.

**Phase 41 focused tests: PASS.**

**Full backend suite: NOT GREEN due to a pre-existing Phase 40 endpoint/test mismatch (`test_api_edge_exclusivity_success` fails with 404). Phase 40 was not modified during Phase 41.**

## 6. Real Snapshot 2 Validation
The endpoint was successfully validated against Snapshot 2 actuals, exactly matching the required values:

- **SBB -> GZB:**
  - traversing_train_count: 143
  - distinct_origin_count: 32
  - distinct_destination_count: 64

- **MSB -> MSF:**
  - traversing_train_count: 132
  - distinct_origin_count: 11
  - distinct_destination_count: 12

- **AAV -> AGCI:**
  - traversing_train_count: 2
  - distinct_origin_count: 1
  - distinct_destination_count: 1

## 7. Performance (EXPLAIN ANALYZE)
Tested on Snapshot 2 using SBB -> GZB edge (143 distinct traversing trains).

```text
Aggregate  (cost=1467.72..1467.73 rows=1 width=24) (actual time=12.532..12.534 rows=1 loops=1)
  ->  Sort  (cost=1467.69..1467.70 rows=3 width=12) (actual time=12.437..12.446 rows=143 loops=1)
        Sort Key: orig_tso.station_id
        Sort Method: quicksort  Memory: 30kB
        ->  Nested Loop  (cost=621.20..1467.67 rows=3 width=12) (actual time=1.726..12.380 rows=143 loops=1)
...
Planning Time: 1.233 ms
Execution Time: 12.663 ms
```
The query efficiently scales down train bounds and fetches terminals using precise indexed scans over `ix_train_stops_snapshot_station` and primary keys, resulting in excellent execution times.

## 8. Semantic Guardrails Validated
- Remains exclusively historical and timetable-derived.
- Based firmly on active snapshot identities and sequences without mixing snapshot data.
- Avoids terminology indicating passenger demand, actual operations, flow volume, or trunk/branch abstractions.
