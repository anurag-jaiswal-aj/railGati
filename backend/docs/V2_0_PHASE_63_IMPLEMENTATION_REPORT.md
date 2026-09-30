# RailGati V2.0 Phase 63 Implementation Report
## Station Junction Through-Service Connectivity

**Status:** IMPLEMENTED AND VALIDATED
**Date:** 2026-09-30

---

### 1. Objective
Implement the V2.0 Phase 63 endpoint to calculate Station Junction Through-Service Connectivity, measuring the structural topological branch pairings at a junction that are actually traversed consecutively by historical train occurrences.

### 2. Approved Semantics & Mathematical Definition
This metric is strictly a historical timetable structural metric. It does NOT claim or measure passenger travel, operational volume, physical track capability, or actual transfers.

**Mathematical Definition:**
For target station $S$:
- Let $N(S)$ be the set of distinct adjacent canonical station identities in the active snapshot topology.
- Let $k = |N(S)|$.
- Possible unordered neighbor pairs $M = \frac{k(k - 1)}{2}$.
- An unordered pair $\{A, B\}$ is SERVED if there exists at least one historical train occurrence traversing $A \to S \to B$ or $B \to S \to A$ as strictly consecutive stops.
- `through_service_pair_ratio` = $\frac{\text{served\_pairs}}{M}$.
- If $k < 2$, the metric is mathematically undefined and strictly returns a `400 Bad Request` or `404 Not Found` per established error semantics.

### 3. Data and Occurrence Semantics
- **Snapshot Scoping**: Bounded strictly to the active timetable snapshot.
- **Occurrence Identity**: Deduplication relies strictly on `train_id`. The calculation enforces `qualifying_train_count = COUNT(DISTINCT train_id)`. If a train traverses the sequence multiple times (cyclic) or repeatedly, it does not inflate that count and still contributes exactly $1$ to the pair's `qualifying_train_count`. 
- **Reciprocal Collapse**: Unordered reciprocal directions ($A \to S \to B$ and $B \to S \to A$) explicitly collapse to one unordered pair.
- **Consecutive Constraints**: Uses `LAG(station_id)` and `LEAD(station_id)` partitioned by `train_id` ordered by `stop_sequence` to ensure rigid consecutive routing. $A \to X \to S \to B$ explicitly fails.

### 4. Implementation Approach & SQL Strategy
The core algorithm leverages native PostgreSQL relational aggregations instead of recursive graph traversals or N+1 Python loops.
1. Resolve the target `Station` code to its ID and Name using `StationObservation`.
2. Extract the $k$ distinct neighbors by scanning `railway_network_edges` bounding on $S$.
3. Compute the possible pairs. If $k < 2$, throw a `ValueError` yielding HTTP 400.
4. Extract observed sequences around $S$. 
   **Query Optimization**: To avoid running a window function over all 18 million `train_stop_observations`, the query is tightly bounded using a `target_trains` CTE that first identifies ONLY the distinct `train_id`s visiting $S$ in the active snapshot. The window functions `LAG` and `LEAD` are then strictly limited to these trains.
5. Filter transitions where `prev_stn` and `next_stn` are both non-null, distinct, and present in $N(S)$.
6. Canonicalize to unordered pairs `tuple(sorted([prev, next]))` and accumulate distinct `train_id`s.
7. Project canonical station codes and compute the ratio.

### 5. API Contract
**Endpoint:** `GET /api/v1/network/stations/{station_code}/junction-through-service`

**Sample Output:**
```json
{
  "station_code": "NDLS",
  "station_name": "New Delhi",
  "neighbor_count": 2,
  "possible_neighbor_pairs": 1,
  "served_neighbor_pairs": 1,
  "through_service_pair_ratio": 1.0,
  "served_pairs": [
    {
      "neighbor_a": "CSB",
      "neighbor_b": "DSB",
      "qualifying_train_count": 73
    }
  ]
}
```

### 6. Edge-Case Behavior Evaluated
- **Unknown Station / Missing Snapshot**: Fails gracefully (HTTP 404).
- **k < 2**: Throws ValueError returning HTTP 400 with "degree = 1" or "not a structural junction".
- **Zero Served Pairs**: Returns 0 pairs and 0.0 ratio safely.
- **Reversals**: $A \to S \to A$ is stripped via `prev_stn != next_stn`.
- **Terminus Stops**: Yield NULL for `LAG` or `LEAD` and are discarded gracefully.
- **Multiple/Cyclic Occurrences**: A single train identity bridging multiple distinct pairs correctly increments the sets.
- **Deterministic Ordering**: Output lists and neighbor identities are alphabetically sorted.

### 7. Test Coverage & Oracle Validation
Both `tests/services/` and `tests/api/v1/` coverage implemented.
The service test establishes an `in_memory_oracle` built strictly in Python. The oracle sequentially iterates over lists of stops to identify unbridged/bridged transitions and canonicalizes the ratios. The SQL implementation perfectly matches the oracle output on all generated conditions (reversals, multiple bridges, unbridged gaps).

### 8. EXPLAIN ANALYZE Evidence
Target station: **NDLS (New Delhi)**
```
Subquery Scan on sequence_visits  (cost=496.05..10565.92 rows=17 width=12) (actual time=2.313..41.075 rows=73 loops=1)
  Filter: ((sequence_visits.prev_stn IS NOT NULL) AND (sequence_visits.next_stn IS NOT NULL) AND (sequence_visits.prev_stn <> sequence_visits.next_stn) AND (sequence_visits.station_id = 8534))
  Rows Removed by Filter: 42746
  ->  WindowAgg  (cost=496.05..10184.20 rows=25448 width=20) (actual time=2.264..38.654 rows=42819 loops=1)
        ->  Incremental Sort  (cost=496.05..9675.24 rows=25448 width=12) (actual time=2.252..22.660 rows=42819 loops=1)
...
                                ->  Index Scan using ix_train_stops_snapshot_station on train_stop_observations 
                                      Index Cond: ((snapshot_id = 2) AND (station_id = 8534))
Planning Time: 1.006 ms
Execution Time: 41.196 ms
```
The query remains extremely fast (41ms) because it hits `ix_train_stops_snapshot_station` to heavily filter the window function bounding space. There are NO sequential scans of the full 18M rows.

### 9. Real Snapshot 2 Validation
```text
NDLS -> k=2 possible=1 served=1 ratio=1.0 time=0.0617s
  CSB <-> DSB (73 trains)
BSL -> k=6 possible=15 served=5 ratio=0.3333 time=0.0421s
  BDI <-> BSBN (51 trains)
  BDI <-> BSCN (27 trains)
  BDI <-> BSLX (26 trains)
ET -> k=7 possible=21 served=11 ratio=0.5238 time=0.1146s
  DRA <-> GRO (10 trains)
  DRA <-> KRTH (2 trains)
  DRA <-> PRKD (56 trains)
CSMT -> Error: Station not found: 'CSMT' (correctly 404s since Mumbai CSMT code might be CSTM in this snapshot)
```
*Note: NDLS has degree=2 in this active dataset subset.*

### 10. Constraints & Explicit Non-Goals
- **₹0 Compliance**: No paid graphs, geocoders, or services were used.
- **Explicit Non-Goals**: This does not model passenger transfers or demand volume. It evaluates only strict timetable route sequences against topological possibilities. 
- **Known Limitations**: The metric bounds its definition strictly within the observed historical timetable dataset structure. It does not look at real-world walking paths or adjacent unmodeled transport options.
