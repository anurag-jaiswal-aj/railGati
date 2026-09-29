# RailGati V2.0 - Phase 50 Discovery
## Network Station Pair Temporal Overtaking Analytics

### 1. PHASE 50 TITLE
Network Station Pair Temporal Overtaking Analytics

### 2. ANALYTICS QUESTION
"When traveling from Origin to Destination on a shared structural corridor, how often do later-departing trains structurally overtake earlier-departing trains, explicitly differentiating slow and fast passenger services on the timetable?"

### 3. EXACT ENDPOINT
`GET /api/v1/network/station-pairs/{origin}/{destination}/temporal-overtaking`

### 4. PRECISE MATHEMATICAL DEFINITION
For a given timetable snapshot $\mathcal{S}$ and ordered station pair $(O, D)$:
Let $\mathcal{T}(O, D)$ be the set of valid direct traversals, where a traversal $i$ is uniquely identified by the train identity $train\_id$, its origin sequence $s_{o}$, and destination sequence $s_{d}$, with $s_{o} < s_{d}$.
A traversal is temporally valid if $departure\_time$ at $O$ is not null and $arrival\_time$ at $D$ is not null.
For each valid traversal $i \in \mathcal{T}(O, D)$, we define absolute timestamps in minutes relative to the origin of the week:
$Dep_i = (source\_day_o - 1) \times 1440 + hour\_dep_o \times 60 + min\_dep_o$
$Arr_i = (source\_day_d - 1) \times 1440 + hour\_arr_d \times 60 + min\_arr_d$

An **Overtake Event** is a distinct, ordered tuple of traversals $(i, j)$ such that:
- $i \neq j$ (Unique traversals)
- $Dep_j > Dep_i$ (Train $j$ departs $O$ strictly after Train $i$)
- $Arr_j < Arr_i$ (Train $j$ arrives at $D$ strictly before Train $i$)

**Outputs:**
- `total_traversals`: $|\mathcal{T}(O, D)|$
- `overtake_events`: Count of valid overtake tuples $(i, j)$
- `overtaken_trains`: Count of distinct train identities $i$ serving as the "slow" train in any overtake event.
- `overtaking_trains`: Count of distinct train identities $j$ serving as the "fast" train in any overtake event.

### 5. WHY IT IS GENUINELY NEW
This candidate explicitly introduces the **temporal route-role differentiation** and **cross-traversal temporal inversion** dimension.
Unlike any previous phase:
- Phase 17 (O-D travel time) computes isolated durations for independent traversals. It never compares one train's schedule structurally against another's to detect sequence inversions.
- Phase 23 (Temporal Gaps) & Phase 24 (Temporal Bunching) analyze temporal occurrence density at a *single* isolated station, completely ignoring destination arrival inversion.
- Phase 39, 42, 45, 46, 47, 48, and 49 strictly aggregate structural node/edge geometries or probabilities. They operate in a purely topological domain, devoid of sequence timing inversions.
- This phase inherently separates "Express" and "Passenger" topologies purely by comparing their time-distance trajectories on shared segments, extracting network priorities embedded structurally in the timetable.

### 6. SNAPSHOT SEMANTICS
The metric evaluates exactly one active snapshot requested via the path/query parameters. Traversals from disparate snapshots are completely isolated via `snapshot_id = X` scoping. The metric compares $Dep_i$ and $Arr_j$ exclusively within the rigid confines of that single snapshot's static historical timetable.

### 7. CYCLIC / REPEATED-STATION SEMANTICS
Trains that traverse loops and hit the origin or destination multiple times yield multiple distinct traversals $i \in \mathcal{T}(O, D)$ if they satisfy $s_{o} < s_{d}$.
Since a single train could theoretically overtake *itself* on a subsequent cycle (e.g. departing days later and taking a faster route segment), the requirement $i \neq j$ is defined based on structural traversal identity `(train_id)`. We enforce `v1.train_id != v2.train_id` to strictly prevent a train from overtaking itself. Cyclic traversals from distinct trains will accurately be compared using their absolute timetable minutes based on `source_day` unrolling.

### 8. EDGE CASES
- **Missing station / Unknown train:** Returns 404 Not Found.
- **No matching records (no valid direct O-D traversals):** Returns 200 OK with all counts = 0.
- **Missing Time Data:** Any traversal missing `departure_time` at $O$ or `arrival_time` at $D$ is excluded from $\mathcal{T}(O, D)$ as temporal ordering cannot be established.
- **Identical Input Stations ($O = D$):** Validation failure (400 Bad Request) as overtaking requires a non-zero structural trajectory.
- **Simultaneous Events:** If $Dep_j = Dep_i$ or $Arr_j = Arr_i$, it is structurally a tie, not a strict overtake. The inequality definitions $Dep_j > Dep_i$ and $Arr_j < Arr_i$ correctly exclude simultaneous crossings.

### 9. REAL SNAPSHOT 2 DISCOVERY
Discovery executed directly on historical Datameet Snapshot 2:

* **CNB -> NDLS (Kanpur Central -> New Delhi)**
  * Input: Origin `CNB`, Destination `NDLS`
  * Output: `total_traversals`: 39, `overtake_events`: 29, `overtaken_trains`: 9, `overtaking_trains`: 16
  * Interpretation: Out of 39 traversals, 16 distinct "fast" trains overtake 9 distinct "slow" passenger/freight configurations, resulting in 29 unique overtaking interactions on this heavy corridor.

* **NDLS -> CNB (New Delhi -> Kanpur Central)**
  * Input: Origin `NDLS`, Destination `CNB`
  * Output: `total_traversals`: 38, `overtake_events`: 23, `overtaken_trains`: 7, `overtaking_trains`: 14
  * Interpretation: The asymmetric reverse direction has slightly fewer trains and overtaking interactions.

* **LTT -> PUNE (Lokmanya Tilak Terminus -> Pune Junction)**
  * Input: Origin `LTT`, Destination `PUNE`
  * Output: `total_traversals`: 27, `overtake_events`: 5, `overtaken_trains`: 5, `overtaking_trains`: 2
  * Interpretation: A structurally tighter corridor where 2 high-priority express trains overtake 5 slower services across the Ghats.

* **BCT -> BVI (Mumbai Central -> Borivali)**
  * Input: Origin `BCT`, Destination `BVI`
  * Output: `total_traversals`: 23, `overtake_events`: 2, `overtaken_trains`: 2, `overtaking_trains`: 1
  * Interpretation: This is primarily a sequential local line where overtaking is rare. Only 1 fast train overtakes 2 slower local services.

### 10. SQL STRATEGY
The implementation leverages a Common Table Expression (CTE):
1. **CTE `valid_traversals`**: Joins `train_stop_observations` `t1` (origin) and `t2` (destination) on `train_id` and `snapshot_id`, enforcing `t1.stop_sequence < t2.stop_sequence` and `IS NOT NULL` for relevant time columns. It computes absolute minutes from week start utilizing `EXTRACT(HOUR FROM CAST(time AS time))` and `source_day`.
2. **Main Query**: Performs a cross-join (Nested Loop) between `valid_traversals v1` and `valid_traversals v2`, enforcing `v1.train_id != v2.train_id` and the temporal inversion clauses `v2.dep > v1.dep` AND `v2.arr < v1.arr`.
3. **Aggregation**: Computes `COUNT(*)`, `COUNT(DISTINCT v1.train_id)`, and `COUNT(DISTINCT v2.train_id)` simultaneously.

### 11. PERFORMANCE
PostgreSQL `EXPLAIN (ANALYZE, FORMAT JSON)` on Snapshot 2 for `CNB -> NDLS` (a heavy route with 39 valid traversals):
- **Planning Time:** 0.487 ms
- **Execution Time:** 1.216 ms
- **Major Operators:** 
  - `Hash Join` over `ix_train_stops_snapshot_station` to collect `valid_traversals` (0.623 ms, 39 rows).
  - `Nested Loop` executing the Cartesian product on the 39 rows (1.098 ms). 
- **Cardinality Explosion Check:** Since $\mathcal{T}(O, D)$ rarely exceeds 100 trains per snapshot, $O(N^2)$ evaluation is bounded to $< 10,000$ operations in memory, making the `Nested Loop` exceedingly fast and eliminating the risk of a true Cartesian explosion on the whole database.

### 12. API CONTRACT
* **Method:** `GET`
* **Path:** `/api/v1/network/station-pairs/{origin}/{destination}/temporal-overtaking`
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
    "total_traversals": 39,
    "overtake_events": 29,
    "overtaken_trains": 9,
    "overtaking_trains": 16
  }
  ```
* **Errors:**
  * 400 Bad Request: `origin` and `destination` are identical.
  * 404 Not Found: Snapshot or Station does not exist.

### 13. TEST PLAN
- **Happy Path:** Test `CNB` -> `NDLS` asserting 39 traversals and exactly 29 overtakes against Snapshot 2.
- **Zero-Result Case:** Test a pair with valid direct traversals but zero overtakes (assert `total_traversals > 0`, `overtake_events = 0`).
- **No Direct Service:** Test pairs with no connecting trains (assert all counts `0`).
- **Invalid Inputs:** Test 404 for non-existent station codes; test 400 when $O = D$.
- **Temporal Filter Checks:** Ensure trains missing valid `departure_time` at $O$ or `arrival_time` at $D$ are appropriately silently excluded from the set.
- **Snapshot Isolation:** Verify the metric properly restricts the traversal Cartesian product strictly to the requested `snapshot_id`.

### 14. SEMANTIC LIMITATIONS
- **Track Layout Independence:** The metric establishes temporal schedule overtaking but does not prove physical overtaking on identical physical tracks (trains may use divergent parallel route geometries or entirely different tracks belonging to the same abstract station).
- **Scheduled vs Realized:** This is strictly an analysis of the static timetable intent. It makes zero assertions about real-time delays, physical speeds, or daily operational reliability. 
- **Cross-Day Wraparound:** Uses `source_day` natively. However, if a train timetable erroneously lacks proper day-incrementation on boundary-crossing, the structural overtake metric inherits that raw timetable inconsistency.

### 15. IMPLEMENTATION FILE PLAN
- `src/railgati/api/v1/schemas.py` (Add response model schema)
- `src/railgati/api/v1/network.py` (Add new GET endpoint)
- `src/railgati/services/network.py` (Add `get_station_pair_temporal_overtaking` CTE implementation)
- `tests/services/test_network_temporal_overtaking.py` (Add standalone unit tests)
- `tests/api/v1/test_network.py` (Append API validation test)
- `docs/V2_0_PHASE_50_IMPLEMENTATION.md` (Add implementation status document)

### 16. FINAL DECISION

DISCOVERY — NOT APPROVED
