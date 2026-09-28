# RailGati V2.0 – Phase 44 Implementation: Train Route O-D Structural Exclusivity Analytics

## 1. Objective
Implement the Phase 44 Network Analytics capability discovered in `V2_0_PHASE_44_DISCOVERY.md`.
The goal is to calculate the "Train Route O-D Structural Exclusivity" for a given target train identity $T$. This metric identifies ordered Origin-Destination station pairs that are exclusively serviced by the target train and no other distinct train identity in the same ordered direction.

## 2. Endpoint
`GET /api/v1/network/trains/{train_number}/od-exclusivity`

## 3. Formal Metric Definition
- Target train $T$ has an ordered sequence of stop occurrences: $S(T) = [s_1, s_2, \dots, s_N]$.
- The set of all possible ordered O-D pairs for $T$ is $P(T) = \{(s_i, s_j) \mid 1 \leq i < j \leq N\}$.
- A pair $(s_i, s_j) \in P(T)$ is considered **SHARED** if there exists a candidate train $U \neq T$ in the active timetable snapshot that visits station $s_i$ at some sequence $x$ and station $s_j$ at some sequence $y$, with $x < y$.
- A pair is **EXCLUSIVE** if it is not shared.
- The endpoint returns all EXCLUSIVE ordered O-D pairs for the target train, retaining specific stop sequence numbers to preserve multiple visits to the same station.

## 4. Exact Train/Station/Snapshot Semantics
- **Train Identity:** Train identity is matched by `Train.id`. A candidate train must be a distinct entity from the target train ($U \neq T$). The target train does not invalidate its own exclusivity. If a candidate train satisfies an O-D pair through multiple occurrences, it is treated as a single sharing entity.
- **Direction:** Ordering matters natively. $A \to B$ is distinct from $B \to A$. Candidate trains operating in reverse do not share the target pair.
- **Snapshot Isolation:** Only stop observations from the currently active timetable snapshot are evaluated.
- **Result Completeness:** The complete set of exclusive pairs is returned. No arbitrary `LIMIT`, pagination, or truncation is applied.

## 5. Query Strategy
The operation is executed natively in PostgreSQL using a `WITH` CTE and `Merge Anti Join` strategy:
1. `target_stops`: Retrieves all stop occurrences for the target train.
2. `target_pairs`: Creates an $O(N^2)$ cross product of `target_stops` where `o_seq < d_seq`.
3. `shared_pairs`: Joins `target_pairs` with the `train_stop_observations` table for all candidate trains ($U \neq T$) where candidate origin sequence < candidate destination sequence.
4. `exclusive_pairs`: Performs a `LEFT JOIN` on `shared_pairs` matching `o_id` and `d_id` where `shared_pairs.o_id IS NULL`, thereby establishing the Native Anti-Join pattern.

## 6. Service Implementation
Implemented in `src/railgati/services/network.py` as `calculate_train_route_od_exclusivity(db, train_number)`.
It encapsulates the active snapshot retrieval, train identity resolution, and the execution of the relational CTE.

## 7. API Implementation
Implemented in `src/railgati/api/v1/network.py` as `get_train_od_exclusivity(train_number, db)`.
Schemas `TrainODExclusivityPairItem` and `TrainODExclusivityResponse` were added to `src/railgati/api/v1/schemas.py`.

## 8. Test Coverage
- API Tests: `tests/api/v1/test_network_train_od_exclusivity.py`
- Service Tests: `tests/services/test_network_train_od_exclusivity.py`

Tests cover explicit edge cases:
- Normal train with exclusive pairs.
- Target train with multiple visits to the same station ($A \to B \to A \to C$).
- Candidate trains serving reverse routes ($B \to A$).
- Candidate trains sharing multi-stop subroutes.
- Target train not invalidating itself.
- Target train with exactly zero exclusive pairs.

## 9. Snapshot 2 Validation
The exact discovery values were faithfully reproduced against `railgati_dev` Snapshot 2:
- **Train 12004:** 0 exclusive pairs.
- **Train 12951:** 0 exclusive pairs.
- **Train 11013:** 2,158 exclusive pairs (e.g., LTT -> BLRR, LTT -> CRLM, LTT -> HLE).

## 10. EXPLAIN ANALYZE
For boundary case Train 11013 (135 stops, ~9,045 target pairs):
- **Planning Time:** 0.210 ms
- **Execution Time:** 932.020 ms
- **Major Indexes Used:** `train_stop_observations_pkey`, `ix_train_stops_snapshot_station`
- **Join/Anti-Join Strategy:** The query successfully leverages `Merge Anti Join` against a materialized internal `Sort` block of candidate combinations, scaling smoothly without recursive exhaustion.

## 11. Performance Observations
The execution scales effectively within the target train's $O(N^2)$ bound. Rather than nested looping across the entire network graph, PostgreSQL uses `Merge Anti Join` combining the target's explicit pairs with the `ix_train_stops_snapshot_station` index to isolate candidate overlaps natively in under 1 second.

## 12. Semantic Guardrails
All API documentation, schema descriptions, and implementation comments explicitly enforce the concept: "Historical timetable-derived structural O-D exclusivity for a target train identity." The output does not imply physical track exclusivity, passenger one-seat isolation, or operational real-time reality.

## 13. Known Limitations
- High numbers of candidate overlapping routes combined with extremely long target trains ($N > 200$) will slightly increase execution time due to the Cartesian pair generation step internally, though it remains bound entirely by the network snapshot limits.
- The `Merge Anti Join` logic intentionally collapses candidate station visits into unique IDs, meaning two distinct candidate occurrences satisfying $A \to B$ are cleanly deduped correctly.

## 14. Files Changed
- `src/railgati/api/v1/schemas.py`
- `src/railgati/services/network.py`
- `src/railgati/api/v1/network.py`
- `tests/api/v1/test_network_train_od_exclusivity.py`
- `tests/services/test_network_train_od_exclusivity.py`

## 15. Final Validation
- Full test suite passed.
- Ruff passed.
- MyPy passed (respecting pre-existing repository baseline errors).
- Discovery assertions matched perfectly.
- Clean working tree maintained.
- Phase 45 has NOT been started.
