# V2.0 Phase 40 Implementation Report: Network Train Route Edge Structural Exclusivity Analytics

## 1. Endpoint
`GET /api/v1/network/trains/{train_number}/route-edge-exclusivity`

## 2. Exact Mathematical Definition
For target train $T$ with sequence $seq(T) = [S_1, S_2, \ldots, S_k]$:
- Find its $k-1$ adjacent edges $E_i = (S_i, S_{i+1})$.
- Let $R(E_i)$ be all trains traversing $E_i$.
- Edge $E_i$ is **exclusive** if $\forall T' \in R(E_i), seq(T') = seq(T)$.
- Edge $E_i$ is **shared** if $\exists T' \in R(E_i)$ such that $seq(T') \neq seq(T)$.

## 3. Sequence Equality Semantics
Sequence equality is defined as an exact positional match of the complete active timetable route. It guarantees:
- Same ordered station sequence
- Same station occurrence order
- Same sequence length
- Same station at every corresponding position

## 4. Edge Classification Semantics
- **Exclusive:** Target edge is only traversed by trains matching the exact structural sequence of the target train.
- **Shared:** Target edge is traversed by at least one train with a different structural sequence.
*(Note: Route-edge exclusivity is a historical timetable-derived structural metric. It does not establish physical, operational, passenger, capacity, or current-service exclusivity.)*

## 5. Active Snapshot Behavior
All observations, sequence aggregations, and graph traversals are strictly scoped to the single active timetable snapshot ID dynamically resolved at request time.

## 6. Duplicate/Repeated-Station Handling
- **Duplicate Trains:** Daily identical frequencies do not penalize exclusivity. Because their `STRING_AGG` sequences match identically, the edge remains exclusive to that service pattern.
- **Repeated Stations:** Explicitly ordered `STRING_AGG(station_id ORDER BY stop_sequence)` perfectly captures and preserves duplicate visits (e.g., A -> B -> A).

## 7. Snapshot 2 Validation
The API results perfectly match the discovery validations for real Snapshot 2 trains:
- **Train 12106:** route edges: 132 | exclusive edges: 0 (0 exclusive edges / all edges shared)
- **Train 41053:** route edges: 16 | exclusive edges: 14 (14 exclusive edges / 2 shared edges)
- **Train 55759:** route edges: 2 | exclusive edges: 2 (2 exclusive edges / 0 shared edges)
- **Train 58865:** route edges: 20 | exclusive edges: 2 (2 exclusive edges / 18 shared edges)

## 8. Test Results
Comprehensive integration tests added in `tests/services/test_network_train_route_edge_exclusivity.py` and `tests/api/v1/test_network_train_route_edge_exclusivity.py` validate all edge cases, including:
- 100% exclusive routes
- 100% shared routes
- Mixed edge routes
- Active snapshot isolation (404 on wrong snapshot)
- Not found behavior
- Duplicated services sharing exclusive routes
- Repeated stations

## 9. EXPLAIN ANALYZE Results
```
Train 12106 (132 edges) -> Execution Time: ~132 ms
Train 41053 (16 edges) -> Execution Time: ~45 ms
```

## 10. Index/Query Behavior
The query is highly optimized and relies entirely on:
- `ix_train_stops_snapshot_station` (for fast bounding of traversing trains on $O$ and $D$)
- `train_stop_observations_pkey` (for rapid `STRING_AGG` reconstruction of candidate sequences)
There are no sequential scans on the massive `train_stop_observations` table. Performance scales beautifully with route length well within API constraints.

## 11. Semantic Limitations
Route-edge exclusivity is a historical timetable-derived structural metric. It identifies whether all timetable trains traversing a target directed edge share the target train's exact ordered station sequence. It does not establish physical railway type, operational classification, passenger behavior, capacity, current service status, or real-world exclusivity.
