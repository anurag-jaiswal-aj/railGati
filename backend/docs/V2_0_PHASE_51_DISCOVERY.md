# V2.0 Phase 51 Discovery

**Status:** DISCOVERY
**Objective:** Identify, define, and evaluate a structurally profound and previously unimplemented railway-network analytic for Phase 51, adhering strictly to the constraints of static timetable data, zero budget, and zero dependency on AI or physical operations data.

---

## 1. Problem Statement
Current implementations analyze station pair routing (paths), temporal inversions, and route extensions. However, we lack a metric that structurally evaluates the **service hierarchy** (or stratification) along a specific corridor. Do all trains connecting Station A and Station B operate with the same local structural pattern, or does the network bifurcate into distinct tiers of express and local services? We need a pure topological-stop metric to classify the homogeneity of service on any scheduled corridor.

## 2. Proposed Metric
**ANALYTIC NAME:** Network Station-Pair Intermediate Halt Stratification Analytics

**PURPOSE:**
To calculate the dispersion in the number of intermediate halts made by all distinct train services operating between an origin and destination station pair. It measures whether the corridor is perfectly homogeneous (all services stop identically) or highly stratified (a mix of express bypasses and local all-stop services).

## 3. Exact Semantics
**Entities Involved:**
- Origin Station `O`, Destination Station `D`
- Trains intersecting `O` and `D` in the same structural direction within the same dataset snapshot.

**Required Tables & Columns:**
- `stations`: `id`, `code`
- `train_stop_observations`: `train_id`, `snapshot_id`, `station_id`, `stop_sequence`

**Logic & Rules:**
- **Grouping:** All trains connecting O and D (where `s_o < s_d`).
- **Calculation:** For each traversal, the intermediate halt count is calculated strictly as `(s_d - s_o - 1)`.
- **Deduplication:** Repeated station visits or cyclic routes are uniquely identified by their sequence positions.
- **Snapshot Semantics:** Enforced by strict `snapshot_id` equality.
- **Aggregations:**
  - `total_traversal_count`: Count of valid traversals.
  - `min_halts`: Minimum halt count.
  - `max_halts`: Maximum halt count.
  - `distinct_halt_strata_count`: Count of unique halt count values (`COUNT(DISTINCT halt_count)`), representing the number of discrete service tiers.
  - `is_perfectly_homogeneous`: Boolean, true strictly when `min_halts == max_halts`.

## 4. Endpoint Proposal
**Endpoint:** `GET /api/v1/network/station-pairs/{origin_code}/{destination_code}/intermediate-halt-stratification`

## 5. Response Contract
```json
{
  "origin_station_code": "str",
  "destination_station_code": "str",
  "timetable_snapshot_id": "int",
  "total_traversal_count": "int",
  "min_halts": "int",
  "max_halts": "int",
  "distinct_halt_strata_count": "int",
  "is_perfectly_homogeneous": "bool"
}
```

## 6. Edge Cases
- **Missing station/train/edge/pair:** Triggers `404 Not Found` for missing stations.
- **Zero qualifying records:** Successful `200 OK` response returning zeros/nulls where applicable, indicating no connectivity.
- **Origin == Destination:** Triggers `400 Bad Request`.
- **Cyclic Stations:** Managed inherently because the SQL enforces strictly `s_o < s_d` on the sequence index.
- **Missing Timing Data:** Not applicable; this relies purely on `stop_sequence` structural topography, not temporal fields.

## 7. Distinctness from Phases 1–50
- **Distinct from Route Diversity (Phase 45):** Route Diversity enumerates the exact paths (A->B->C vs A->E->C). Halt Stratification aggregates purely on the quantitative topological *hop distance* regardless of the specific path taken.
- **Distinct from Structural Halts (Phase 39):** Phase 39 calculates outliers across a single Train's route. Phase 51 calculates structural dispersion across an O-D Pair.
- **Distinct from Temporal Inversions (Phase 50):** Phase 50 examines chronological overtaking; Phase 51 examines purely topological stop-skipping hierarchy.

## 8. Snapshot 2 Real-Data Discovery
Tested against the active real snapshot (Snapshot 2).

* **CNB -> NDLS**
  - Total Traversals: 39
  - Min Halts: 59
  - Max Halts: 67
  - Strata Count: 4
  - Homogeneous: False

* **LTT -> PUNE**
  - Total Traversals: 27
  - Min Halts: 42
  - Max Halts: 46
  - Strata Count: 2
  - Homogeneous: False

* **HWH -> PNBE**
  - Total Traversals: 11
  - Min Halts: 93
  - Max Halts: 98
  - Strata Count: 4
  - Homogeneous: False

* **BCT -> BVI**
  - Total Traversals: 23
  - Min Halts: 16
  - Max Halts: 16
  - Strata Count: 1
  - Homogeneous: True (Every train makes identically 16 intermediate stops).

## 9. Performance Discovery
Executed `EXPLAIN ANALYZE` on PostgreSQL for the representative `CNB -> NDLS` query.
- **Planning Time:** 1.399 ms
- **Execution Time:** 0.866 ms
- **Major Query Strategy:** `Hash Join` between two `Index Scans` on `ix_train_stops_snapshot_station`, followed by in-memory Quicksort.
- **Sequential Scans:** None.
- **Complexity:** Roughly `O(N)` where N is the number of trains stopping at the origin/destination, due to the efficiency of the Hash Join on indexed subsets. Highly performant.

## 10. Data Quality / Limitations
- **Pass-through Ambiguity:** The Datameet timetable records scheduled halts only. It does not record "pass-throughs" (stations physically passed without stopping). Therefore, this metric measures "Scheduled Halt Stratification", not physical line geometry.
- **Data Completeness:** Missing sequence data would corrupt the calculation, but the ingestion pipeline (Phase 3) guarantees monotonically increasing `stop_sequence`.

## 11. ₹0 Compliance
This metric requires strictly existing PostgreSQL aggregation functions (`COUNT`, `MIN`, `MAX`, `COUNT DISTINCT`) over the local static `train_stop_observations` table. No external APIs, LLMs, or paid infrastructure are required.

## 12. Recommendation
Highly recommended for Phase 51 Implementation. It answers a fundamental question about network stratification (express vs local corridors) using an elegantly simple, high-performance query that leverages the existing topological schema perfectly.
