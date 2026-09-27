# RailGati V2.0 Phase 14: Discovery & Research

**Status**: APPROVED FOR DISCOVERY
**Implementation Status**: PENDING
**Focus**: Network Directional Edge Asymmetry (Flow Imbalance) Analytics

---

## 1. Problem Statement
With Phases 1–13 successfully covering historical timetable structures, node/edge volumes, connectivity, bounding, paths, dwell, route lengths, and time-of-day concentrations, RailGati provides deep insight into node and flow magnitude.

However, all edge-level analytics (Phase 8 Edge Volume) treat physical track segments strictly as isolated directional pipelines. They do not evaluate the structural balance of the track. If a track segment handles 50 transits, Phase 8 reports `50`. It does not inform us whether the reciprocal direction handles 50 transits (a standard bidirectional railway corridor) or 0 transits (a dedicated one-way track or cyclic routing loop).

We need an analytical dimension that identifies **Directional Flow Imbalance** (Cyclical Topology), exposing structural loops in the historical scheduled network.

---

## 2. Capability Map (Phases 1–13)
The current repository accurately models:
- **Topology/Paths**: Graph Build (P1), Reachability (P2), Path Discovery (P3)
- **Service Attribution**: Continuous overlapping services (P4, P5)
- **Corridors**: Sequential overlapping route-segment analytics (P6)
- **Node Volume**: Hub Centrality (transit occurrences) (P7), Termini bounds (P9)
- **Edge Volume**: Directed track occurrence volume (P8)
- **Flow Volume**: O-D historical connectivity flow (P10)
- **Time/Duration**: Scheduled node dwell time (P11)
- **Complexity**: Average scheduled route stop-count (P12)
- **Temporal Distribution**: Calendar-hour occurrence concentration (P13)

---

## 3. Analytical Dimensions Already Covered
- **WHERE**: Stations, Edges, Paths, Corridors, O-D boundaries.
- **HOW MUCH**: Total occurrence volume, distinct edge volume.
- **HOW LONG**: Scheduled node dwell, timetable length.
- **WHEN**: Fixed calendar-hour peaks.

## 4. Remaining Analytical/Product Gap
- **Network Structural Balance (Asymmetry)**: Measuring the difference in scheduled load between a forward topological edge and its exact reciprocal. This distinguishes standard bidirectional corridors from scheduled one-way subgraphs.
- **Scheduled O-D Journey Duration**: Measuring end-to-end historical time elapsed.

---

## 5. Data-Capability Audit
Inspection of `RailwayNetworkEdge` reveals exactly one row per directional sequence pair `(from_station_id, to_station_id)` per snapshot, containing `train_count`.
Because the data aggregates perfectly per direction, pairing `(A->B)` and `(B->A)` using `LEAST()` and `GREATEST()` efficiently exposes bidirectional imbalance.

Exploratory queries on the active dataset confirm extreme asymmetry exists. For example, `SRPB <-> GOGH` has 46 transits in one direction and 0 returning. This 100% asymmetry clearly identifies a scheduled cyclical track loop, an insight impossible to derive from Phase 8 alone.

---

## 6. Candidate Directions

### Candidate 1: Network Directional Edge Asymmetry (Flow Imbalance)
1. **Question**: Which track segments are scheduled as one-way loops vs symmetrical bidirectional corridors?
2. **Why Useful**: Detects cyclic routing and structurally imbalanced physical subgraphs.
3. **Data Used**: `RailwayNetworkEdge` (requires graph build).
4. **Different from Phase 8**: Phase 8 ranks total directional volume independently. Asymmetry ranks relative directional balance (`ABS(fwd - rev) / (fwd + rev)`). A heavily asymmetric edge with low volume (30 vs 0) is buried in Phase 8 but prioritized here.
5. **Semantics**: `asymmetry_pct`.
6. **₹0 Compatible**: Yes.

### Candidate 2: Network O-D Scheduled Journey Duration
1. **Question**: How long does it historically take to travel from an origin to a destination?
2. **Why Useful**: Analyzes network flow velocity.
3. **Data Used**: `TrainStopObservation` sequence bounding.
4. **Different from Phase 10**: Phase 10 provides flow volume. This provides flow duration.
5. **Semantics**: `average_scheduled_duration_hours`.
6. **₹0 Compatible**: Yes.

### Candidate 3: Network Station Service Redundancy
1. **Question**: How many times do unique trains visit the exact same station in their route?
2. **Why Useful**: Identifies figure-8 looping trains.
3. **Data Used**: `TrainStopObservation`.
4. **Why Rejected**: Exploratory queries showed fewer than 30 occurrences network-wide in Snapshot 2. Too niche to be a primary phase.

---

## 7. Selected Phase 14 Scope
**Candidate 1: Network Directional Edge Asymmetry Analytics** is selected.

**Evidence Supporting Selection:**
- Provides a deep topological/structural insight (cyclic track identification).
- Direct mathematical calculation over existing Phase 1 graph materialization (`RailwayNetworkEdge`).
- Readily evaluated via a fast, set-based self-join/grouping in PostgreSQL.
- Fills a clear product gap regarding infrastructure balance.

---

## 8. Exact Semantics
- **Unit of Analysis**: The Bidirectional Edge Pair (Canonical Station A <-> Canonical Station B).
- **vol_ab**: The historical service occurrence count on `RailwayNetworkEdge` where `from_id = LEAST(A,B)` and `to_id = GREATEST(A,B)`.
- **vol_ba**: The historical service occurrence count where `from_id = GREATEST(A,B)` and `to_id = LEAST(A,B)`.
- **Total Volume**: `vol_ab + vol_ba`.
- **Asymmetry Percentage**: `ABS(vol_ab - vol_ba) / total_volume * 100.0`.
- **Minimum Volume Constraint**: Configurable `min_total_volume` to prevent micro-fluctuations (e.g. 1 vs 0 transits) from dominating 100% asymmetry results.

### Explicit Non-Goals
- It does **NOT** measure live train congestion.
- It does **NOT** imply track capacity or physical rail limits (e.g., dual-track vs single-track).
- It is strictly a historical schedule topology metric.

---

## 9. Snapshot / Provenance Semantics
- **Graph-Build Dependency**: **YES**. This explicitly analyzes network edges, so an `ACTIVE` `RailwayGraphBuild` is strictly required.
- **Snapshot Isolation**: The graph build inherently guarantees strict `timetable_snapshot_id` alignment.
- **Station Isolation**: Resolving station names requires an active station dataset snapshot.

---

## 10. Query Strategy
**PostgreSQL Set-Based Strategy:**
1. Filter `railway_network_edges` by the active `graph_build_id` (via timetable snapshot binding).
2. CTE `paired`: Group by `LEAST(from_station_id, to_station_id)` and `GREATEST(...)`. Calculate `vol_ab` and `vol_ba` using conditional `MAX(CASE WHEN...)` or `SUM`.
3. CTE `asymmetry`: Calculate `total_vol` and `asymmetry_pct`.
4. Final SELECT: Join `stations` and `station_observations`, apply `WHERE total_vol >= min_total_volume`, `ORDER BY asymmetry_pct DESC, total_vol DESC`, and `LIMIT`.

**Resource Behavior:**
- Execution completely within database boundaries.
- Relies on existing `railway_network_edges` indexes.

---

## 11. Proposed API

**`GET /api/v1/network/edge-asymmetry`**

**Query Parameters:**
- `limit` (int, default: 50, ge: 1, le: 500)
- `min_total_volume` (int, default: 15, ge: 1, le: 1000): Minimum combined volume required.

**Response Schema:**
```json
{
  "timetable_snapshot_id": 2,
  "limit": 50,
  "min_total_volume": 15,
  "items": [
    {
      "station_a_code": "SRPB",
      "station_a_name": "Srirampur",
      "station_b_code": "GOGH",
      "station_b_name": "Goghat",
      "forward_volume": 46,
      "reverse_volume": 0,
      "total_volume": 46,
      "asymmetry_pct": 100.0
    }
  ]
}
```

---

## 12. Performance Methodology
Implementation will require `EXPLAIN ANALYZE`.
Exploratory measurement indicates:
- Aggregation across ~4,000 distinct bidirectional edges.
- Planning: ~1.5ms. Execution: ~95ms.
- Scalability is bounded by the size of the materialized network edges, which strictly caps at topological constraints (`O(E)`).

---

## 13. Test Strategy
- **Service Tests**: Edge logic (perfect symmetry yielding 0%, total imbalance yielding 100%), limit handling, missing graph exception logic, snapshot isolation.
- **API Tests**: Parameter validation, 422 errors for negative limits, 503 for missing snapshots/graphs, accurate JSON envelope structure.

---

## 14. Real-Data Validation
Executed against Snapshot 2 (`min_total_volume = 10`):
- `SRPB <-> GOGH`: 46 vs 0 (Total 46, Asymmetry 100.0%)
- `CROA <-> FKM`: 0 vs 30 (Total 30, Asymmetry 100.0%)
- `GOGH <-> FKM`: 24 vs 0 (Total 24, Asymmetry 100.0%)
These highlight a clear one-way topological track routing loop in the timetable.

---

## 15. Limitations
- Values at exactly 100% simply indicate no reciprocal scheduled train; they do not dictate physical track absence.
- Cannot infer passenger preference or operational routing limitations.

---

**DISCOVERY ONLY — NO PRODUCTION IMPLEMENTATION.**
