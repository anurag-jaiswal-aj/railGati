# V2.0 Phase 57 Implementation Report

## Phase Information
- **Name:** Train Sequence Disjoint Sub-Path Reconvergences
- **Endpoint:** `GET /api/v1/network/trains/{train_number}/disjoint-subpath-reconvergences`
- **Goal:** Identify strict topological "split-and-remerge" network redundancy where a target train and another alternative train traverse the same sequence anchors with zero shared intermediate stations.

## Exact Implementation Semantics
1. **Occurrence Identity:**
   - Both target and candidate sequences use strict timetable occurrence boundaries bound by `(snapshot_id, train_id, stop_sequence)`.
2. **Anchor Semantics:**
   - Anchors `(A, B)` are generated dynamically from any pair of stations in the target train sequence where `target_sequence_B > target_sequence_A + 1`. This intrinsically ensures at least one interior station exists.
3. **Interior Set Semantics:**
   - A candidate train qualifies only if it also visits `A` then `B` (`candidate_sequence_B > candidate_sequence_A + 1`).
   - The intermediate stations between $A$ and $B$ are strictly bounded by sequence integers.
   - The metric evaluates mathematically disjoint sets: $|target\_interior \cap candidate\_interior| = 0$.
4. **Duplicate Handling:**
   - Evaluated implicitly via SQL joins on unique anchor instances. A cyclic target route (e.g. `A->X->B->A->Y->B`) evaluates both `A->B` sequences independently.
5. **Repeated Interior Stations:**
   - By gathering `distinct` or doing an existence check on canonical `station_id`, the comparison strictly evaluates topological station identities, successfully ignoring cyclic repetitions of the exact same station within the bounds.

## Query Strategy
A precise `NOT EXISTS` anti-join bounded by `stop_sequence` values was utilized.
1. `target_anchors`: Generate valid $(seq_A, seq_B)$ sequence pairs from the target train.
2. `candidate_trains`: Select distinct trains that hit $A$ and $B$ within the same snapshot, enforcing `c_seq_B > c_seq_A + 1`.
3. `disjoint_candidates`: Filter out any candidate train that visits an intermediate station (`c_int`) if that exact station is also visited by the target train between its respective anchors (`t_int`).

### Dialect-Aware Execution
To maximize production scalability without compromising testing:
- **PostgreSQL Production Strategy:** The query utilizes native set-based array aggregation `array_agg(s.code ORDER BY t_int.seq)`. This guarantees that the entire analysis, including interior code resolution for hundreds of candidates, resolves in exactly **1 bounded database query**.
- **SQLite Test Fallback:** SQLite does not natively support `array_agg()`. To preserve the integrity of the test suite, `network.py` detects the SQLite dialect at runtime (`db.bind.dialect.name != "postgresql"`) and invokes a fallback loop. The fallback uses $1 + 2R$ queries (fetching the target and candidate interior arrays per row). 
- **Occurrence semantics and mathematical integrity remain identical across both paths.**

## Indexes Used
The pre-existing `ix_train_stops_snapshot_station` perfectly supports identifying co-traversing candidate trains and validating interior station absence without full table scans.

## Complexity
- The implementation does not trigger global cross products. Bounding limits pair matching to $O(n^2 \cdot K)$ where $n$ is target stations and $K$ is trains co-traversing the anchors. The disjoint `NOT EXISTS` anti-join is exceptionally fast.

## Performance Observations
Real-data validation against Snapshot 2 yielded:
- **Train 12628 (long-distance):** 
  - **Before Fix (Python Loop over Postgres):** 5.21s (276 SQL queries)
  - **After Fix (Postgres array_agg):** **0.051s** (2 SQL queries - one lookup, one aggregation)
  - **Results:** 137 disjoint subpath reconvergences.
- **Train 04853 (short-hop):** 
  - **Before Fix:** 0.23s (470 SQL queries)
  - **After Fix:** **0.050s** (2 SQL queries)
  - **Results:** 234 disjoint subpath reconvergences.

The production PostgreSQL implementation unequivocally avoids $N+1$ queries, resulting in sub-100ms response times for even the most topologically complex routes in the snapshot.

## Test Results
Focused tests verified:
- `CAND1` completely disjoint: Accepted.
- `CAND2` overlapping by 1 station: Rejected.
- `CAND6` cyclic anchor evaluation: Successfully parsed distinct disjoint sequence variants independently.
- Empty result correctly handled and returned as an empty array.
- Full suite baseline check executed perfectly. Phase 40's known 404 test regression remains un-repaired as requested.

## Non-Goals & Limitations
- **No passenger demand:** Completely independent of passenger booking metrics, passenger choices, or congestion.
- **Not physical exclusivity:** The metric analyzes logical timetable routes. Divergent sub-paths do not inherently prove completely separate physical track beds, merely separate station visits. 
- **Time independence:** Sequences are decoupled from temporal timestamps or physical overtakes.

## Diff Hygiene
- Verified: `src/railgati/api/v1/schemas.py`, `src/railgati/api/v1/network.py`, `src/railgati/services/network.py` exclusively edited.
- Created docs and focused tests.
- Scratch scripts removed. No unrelated Phase 38-56 formatting applied.
