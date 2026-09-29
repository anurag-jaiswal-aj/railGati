# V2.0 Phase 58 Implementation Report

## Phase Information
- **Name:** Train Sequence Topological Degree Extremes
- **Endpoint:** `GET /api/v1/network/trains/{train_number}/topological-degree-extremes`
- **Goal:** Evaluate the discrete local-extrema of global station degree along the ordered sequence of a specific train.

## Exact Implementation Semantics
1. **Occurrence Identity:**
   - Both `snapshot_id` and `stop_sequence` are preserved. Every stop occurrence along the target train's sequence is evaluated independently as an ordered sequence of events.
2. **Station Identity and Global Degree ($D(S)$):**
   - The station code is used to determine global topological degree.
   - Degree is calculated as the count of distinct adjacent station identities in the active snapshot across the entire network, normalizing directional relationships $A \to B$ and $B \to A$ into an undirected neighborhood $A \leftrightarrow B$.
   - **Isolated Station Handling:** An appropriate `LEFT JOIN` onto `station_degrees` combined with `COALESCE(sd.global_degree, 0)` guarantees that a station missing any timetable edges receives a global degree of `0`.
3. **Plateaus and Strict Comparisons:**
   - Classification relies on strict inequality. Any equal-degree plateau (e.g. `2 -> 5 -> 5 -> 2`) marks all instances of that degree as `TRANSIT`.
4. **Terminals (Short Routes):**
   - $S_1$ and $S_n$ are definitively classified as `TERMINAL`.
   - **One-stop routes:** The single occurrence receives exactly one `TERMINAL` classification. All other metric counts (maxima, minima, transit) evaluate to exactly `0`.
   - **Two-stop routes:** The two occurrences receive exactly two `TERMINAL` classifications. All other metric counts evaluate to exactly `0`.
5. **Repeated/Cyclic Routes:**
   - Cycles like $A \to B \to A \to C$ independently evaluate both $A$ occurrences against their respective sequence neighbors.

## Query Strategy
The analytical calculation is set-based and performed in a single primary database execution without any N+1 loops in the application layer.

1. **CTE 1 (`edge_pairs` / `undirected_edges`):**
   - Collects all adjacent station pairs in the snapshot from `train_stop_observations`, forming an undirected neighborhood.
2. **CTE 2 (`station_degrees`):**
   - Counts distinct adjacent stations grouped by `station_id` to establish the global topological degree for each station.
3. **CTE 3 (`target_seq`):**
   - Retrieves the ordered stop occurrences for the target train, utilizing a `LEFT JOIN` to `station_degrees` to handle isolated cases. Applies the `LAG()` and `LEAD()` window functions over the `stop_sequence`.
4. **Final Projection:**
   - A strict `CASE` statement executes the local extrema classification logic (`LOCAL_MAXIMUM`, `LOCAL_MINIMUM`, `TRANSIT`, or `TERMINAL`).

This design leverages universally compatible SQL capabilities to ensure seamless execution on both PostgreSQL and SQLite.

## Lookup Semantics
The `Train` canonical entity is explicitly snapshot-independent. However, network sequence validation queries the `train_stop_observations` table directly by joining on the canonical `Train.id` and enforcing a strict scope against `snapshot_id`. The endpoint correctly resolves `snapshot_id = get_active_timetable_snapshot_id(db)`.

## Testing Performed
1. **Service Tests:** `tests/services/test_network_train_topological_degree_extremes.py` completely verifies:
   - Strict maximum and strict minimum classifications.
   - Plateau maximum and minimum logic.
   - Monotonic sequences.
   - Short routes (isolated 1-stop routes with global degree 0, and 2-stop routes).
   - Cyclic/repeated route evaluation.
2. **API Tests:** `tests/api/v1/test_network_train_topological_degree_extremes.py` verifies standard integration behavior (response schema, success, 404 behavior, correct snapshot semantics).
3. **Full Suite Check:** Confirmed working locally. The only remaining test failure is the known Phase 40 API 404, which is explicitly expected.

## Real-Data Validation
Validation performed against real timetable Snapshot 2 using standard Python orchestration.
- **Train Number:** `12628`
- **Total Stops:** `276`
- **Maxima:** `30`
- **Minima:** `11`
- **Transit:** `233`
- **Initial Profile:**
```json
  1: {'stop_sequence': 1, 'station_code': 'NDLS', 'global_degree': 2, 'classification_type': 'TERMINAL'}
  2: {'stop_sequence': 2, 'station_code': 'CSB', 'global_degree': 2, 'classification_type': 'TRANSIT'}
  3: {'stop_sequence': 3, 'station_code': 'TKJ', 'global_degree': 4, 'classification_type': 'TRANSIT'}
  4: {'stop_sequence': 4, 'station_code': 'PGMD', 'global_degree': 4, 'classification_type': 'TRANSIT'}
  5: {'stop_sequence': 5, 'station_code': 'NZM', 'global_degree': 4, 'classification_type': 'TRANSIT'}
```

## Known Limitations / Non-Claims
- This metric represents the mathematical topological sequence of the network timetable.
- It **does not** infer passenger demand, operational criticality, train scheduling reliability, actual executed traffic, or physical infrastructural articulation points.
