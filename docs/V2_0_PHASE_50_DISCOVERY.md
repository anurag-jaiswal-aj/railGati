# RailGati V2.0 - Phase 50 Discovery
## Network Station-Pair Temporal Order Inversion Analytics

### 1. PHASE 50 TITLE
Network Station-Pair Temporal Order Inversion Analytics

### 2. ANALYTICS QUESTION
"For an ordered sequence of two stations on a shared structural corridor, how often does a scheduled timetable inversion occur where one traversal instance departs strictly later than another but arrives strictly earlier?"

### 3. EXACT ENDPOINT
`GET /api/v1/network/station-pairs/{origin}/{destination}/temporal-order-inversions`

### 4. PRECISE MATHEMATICAL DEFINITION
For a given active timetable snapshot $\mathcal{S}$ and an ordered station pair $O \to D$:

A **traversal instance** $i$ is uniquely identified by the tuple:
$(train\_id, s_{o}, s_{d})$
where $s_{o}$ is the stop sequence at $O$ and $s_{d}$ is the stop sequence at $D$, such that $s_{o} < s_{d}$.
A traversal is temporally valid if both $departure\_time$ at $O$ and $arrival\_time$ at $D$ are non-null, and $source\_day$ is non-null for both stops.

For each valid traversal instance $i$, the absolute timestamps in minutes relative to the start of the scheduled run are computed as:
- $Dep_i = (source\_day_o - 1) \times 1440 + hour\_dep_o \times 60 + min\_dep_o$
- $Arr_i = (source\_day_d - 1) \times 1440 + hour\_arr_d \times 60 + min\_arr_d$

A **Scheduled Temporal Order Inversion Pair** is an ordered tuple of distinct traversal instances $(A, B)$ such that:
1. $Dep_A < Dep_B$ (A departs strictly earlier than B)
AND
2. $Arr_A > Arr_B$ (A arrives strictly later than B)

**Outputs:**
- `total_valid_traversal_count`: The number of valid distinct traversal instances.
- `inversion_pair_count`: The number of valid distinct inversion pairs $(A, B)$.
- `distinct_inverted_train_count`: The number of unique train identities ($train\_id$) that participate in at least one inversion pair (either as A or B).

### 5. WHY IT IS GENUINELY NEW
This candidate introduces the **cross-traversal temporal inversion** dimension.
Unlike any previous phase:
- Phase 17 (O-D travel time) computes isolated durations for independent traversals.
- Phase 23 (Temporal Gaps) & Phase 24 (Temporal Bunching) analyze temporal occurrence density at a *single* isolated station, completely ignoring destination arrival relationships.
- Phase 39, 42, 45, 46, 47, 48, and 49 strictly aggregate structural node/edge geometries or probabilities in a purely topological domain, devoid of sequence timing inversions.
- This metric structurally compares timing trajectories of entirely separate train instances on shared segments, extracting network schedule inversion properties embedded in the timetable.

### 6. SNAPSHOT SEMANTICS
The metric evaluates exactly one active snapshot requested via the path/query parameters. Traversals from disparate snapshots are completely isolated via `snapshot_id = X` scoping. The metric compares $Dep_i$ and $Arr_j$ exclusively within the rigid confines of that single snapshot's static historical timetable.

### 7. CYCLIC / REPEATED-STATION SEMANTICS
Trains traversing loops and visiting the origin or destination multiple times yield multiple distinct valid traversal instances (e.g. $O(1) \to X \to D(3) \to O(6) \to D(8)$).
- Valid instances: $(train\_id, 1, 3)$, $(train\_id, 1, 8)$, and $(train\_id, 6, 8)$.
- Invalid instances: $(train\_id, 6, 3)$ is mathematically excluded because $s_{o} = 6 \not< s_{d} = 3$.
Each valid instance is independently timestamped based on its specific `source_day` and local arrival/departure times.
Two distinct traversal occurrences of the *same* train identity may be compared, provided they are distinct instances. If a train physically loops and runs the corridor twice, it is treated as two scheduled traversals capable of forming an inversion pair with each other or other trains.

### 8. EDGE CASES
- **Same-time Boundaries:** 
  - $Dep_A == Dep_B$: Excluded. If they depart simultaneously, $Dep_A < Dep_B$ is false. Simultaneous departures do not establish a scheduled initial order.
  - $Arr_A == Arr_B$: Excluded. If they arrive simultaneously, $Arr_A > Arr_B$ is false.
- **Missing Timing Data:** A traversal is silently excluded if $departure\_time$ at $O$, $arrival\_time$ at $D$, or $source\_day$ for either is null.
- **Missing Station / Unknown Train:** Returns 404 Not Found.
- **Identical Input Stations ($O = D$):** Validation failure (400 Bad Request) as traversals must cover a topological distance.
- **Zero Valid Traversals:** Returns 200 OK with all counts = 0.
- **Pair Counting Symmetry:** The mathematical definition enforces an arbitrary deterministic initial ordering ($Dep_A < Dep_B$). This makes it impossible for both $(A, B)$ and $(B, A)$ to be counted. An inversion pair is uniquely defined exactly once.
- **Multiple Inversions:** A single traversal instance can participate in multiple inversion pairs (e.g., A is inverted relative to B and C). This contributes +2 to `inversion_pair_count`, but only +1 (or +2/3) to `distinct_inverted_train_count`.

### 9. REAL SNAPSHOT 2 DISCOVERY
Discovery executed directly on historical Datameet Snapshot 2 using the precise relational semantics defined above:

* **CNB -> NDLS (Kanpur Central -> New Delhi)**
  * Input: Origin `CNB`, Destination `NDLS`
  * Output: 
    - `total_valid_traversal_count`: 39
    - `inversion_pair_count`: 29
    - `distinct_inverted_train_count`: 25
  * Interpretation: The timetable schedules 39 distinct traversals between these stations. Across these traversals, there are 29 distinct scheduled inversion pairs involving 25 distinct train identities.

* **LTT -> PUNE (Lokmanya Tilak Terminus -> Pune Junction)**
  * Input: Origin `LTT`, Destination `PUNE`
  * Output: 
    - `total_valid_traversal_count`: 27
    - `inversion_pair_count`: 5
    - `distinct_inverted_train_count`: 7
  * Interpretation: The timetable dictates only 5 inversion pairs among the 27 traversals, involving 7 trains whose scheduled relative ordering inverts between origin and destination.

* **BCT -> BVI (Mumbai Central -> Borivali)**
  * Input: Origin `BCT`, Destination `BVI`
  * Output:
    - `total_valid_traversal_count`: 23
    - `inversion_pair_count`: 2
    - `distinct_inverted_train_count`: 3
  * Interpretation: As a sequential commuter segment, temporal inversions are extremely rare, producing only 2 scheduled inversion pairs.

* **HWH -> PNBE (Howrah -> Patna)**
  * Input: Origin `HWH`, Destination `PNBE`
  * Output:
    - `total_valid_traversal_count`: 11
    - `inversion_pair_count`: 2
    - `distinct_inverted_train_count`: 3

### 10. SQL STRATEGY
The implementation leverages a Common Table Expression (CTE):
1. **CTE `valid_traversals`**: Joins `train_stop_observations` `t1` (origin) and `t2` (destination) on `train_id` and `snapshot_id`, enforcing `t1.stop_sequence < t2.stop_sequence` and ensuring time/day columns are not null. It computes absolute minutes from run-start utilizing `EXTRACT(HOUR FROM CAST(time AS time))` and `source_day`.
2. **Main Query**: Performs a cross-join (Nested Loop) between `valid_traversals v1` and `valid_traversals v2`. It ensures distinct traversal instances using `(v1.train_id != v2.train_id OR v1.s_o != v2.s_o OR v1.s_d != v2.s_d)` and applies the inversion clauses `v1.abs_dep_mins < v2.abs_dep_mins AND v1.abs_arr_mins > v2.abs_arr_mins`.
3. **Aggregation**: Computes `COUNT(*)` for pairs and a `UNION` subquery for `COUNT(DISTINCT train_id)` across the pairs.

### 11. PERFORMANCE
PostgreSQL `EXPLAIN (ANALYZE, FORMAT JSON)` on Snapshot 2 for `CNB -> NDLS` (a heavy route with 39 valid traversals):
- **Planning Time:** 0.400 ms
- **Execution Time:** 1.468 ms
- **Major Operators:** 
  - `Hash Join` over `ix_train_stops_snapshot_station` to collect `valid_traversals` (0.903 ms).
  - `Nested Loop` executing the pairwise evaluation (1.300 ms total elapsed to parent). 
- **Cardinality Explosion Check:** The $O(N^2)$ pairwise comparison is indeed the dominant cost of this query. However, because $N$ (the number of valid traversals for a given O-D pair) rarely exceeds 100 on the historical timetable, the inner nested loop requires at most $\sim 10,000$ cheap comparisons. This does not cause meaningful cardinality explosion, as demonstrated by the sub-2ms execution time for 39 traversals.

### 12. API CONTRACT
* **Method:** `GET`
* **Path:** `/api/v1/network/station-pairs/{origin}/{destination}/temporal-order-inversions`
* **Parameters:**
  * `snapshot_id` (query, required, int)
  * `origin` (path, string)
  * `destination` (path, string)
* **Response Schema (200 OK):**
  ```json
  {
    "snapshot_id": 2,
    "origin": "CNB",
    "destination": "NDLS",
    "total_valid_traversal_count": 39,
    "inversion_pair_count": 29,
    "distinct_inverted_train_count": 25
  }
  ```

### 13. TEST PLAN
- **Happy Path:** Test `CNB` -> `NDLS` asserting 39 traversals and exactly 29 inversion pairs against Snapshot 2.
- **Zero-Result Case:** Test a pair with valid direct traversals but zero inversion pairs (assert `total_valid_traversal_count > 0`, `inversion_pair_count = 0`).
- **No Direct Service:** Test pairs with no connecting trains (assert all counts `0`).
- **Invalid Inputs:** Test 404 for non-existent station codes; test 400 when $O = D$.
- **Cyclic Semantics:** Verify that repeated stations yielding $s_o < s_d$ are uniquely counted as separate instances in the CTE.
- **Snapshot Isolation:** Verify the metric restricts the traversal evaluation strictly to the requested `snapshot_id`.

### 14. SEMANTIC LIMITATIONS
This metric measures scheduled temporal order inversion between timetable traversal instances. It does not establish physical train overtaking, actual train positions, congestion, infrastructure capacity, operational priority, or real-time railway conditions.

### 15. IMPLEMENTATION FILE PLAN
- `src/railgati/api/v1/schemas.py`
- `src/railgati/api/v1/network.py`
- `src/railgati/services/network.py`
- `tests/services/test_network_temporal_inversion.py`
- `tests/api/v1/test_network_temporal_inversion.py`

### 16. FINAL DECISION

DISCOVERY — NOT APPROVED
