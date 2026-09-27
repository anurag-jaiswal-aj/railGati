# V2.0 Phase 36 Discovery: Network Station Transfer-Free Reachability (TFR) Analytics

## 1. Phase Objective
The objective of Phase 36 is to implement a robust, bounded structural network capability. Transfer-Free Outbound Reach (TFOR) measures the number of distinct downstream stations that are visited by at least one timetable train occurrence that also visits the selected station, without requiring a train change.

## 2. Candidate Capabilities Investigated
During discovery, several genuinely distinct capability categories were evaluated to ensure compliance with the "no cosmetic aggregation" and "no renamed depths" constraints:
1. **Network Edge Local Bypass Redundancy:** Evaluates the number of 2-hop alternate routes bridging a single scheduled edge $(A, B)$. (Rejected to avoid semantic overlap with Phase 34 Transit Articulation).
2. **Edge O-D Embeddedness Analytics:** Evaluates the number of globally unique Origin-Destination pairs whose trains traverse a specific local edge. (Strong candidate, but closely aligned with Phase 20 O-D Bridges logic applied to an edge).
3. **Network Component Structure (Neighborhood Fragmentation):** Evaluates if removing $S$ disconnects its outbound neighbors into disjoint components. (Rejected due to O(N^2) recursive component discovery complexity in native SQL).
4. **Network Station Transfer-Free Reachability (TFR) Analytics:** Evaluates the cardinality of the full downstream reachable set accessible via the same train. (Selected).

## 3. Selected Capability
**Network Station Transfer-Free Reachability (TFR) Analytics**
This capability projects the topological edge graph into a hypergraph (where trains form continuous edges) to compute the timetable-derived structural reachability size of a node, independently of its immediate timetable neighbors.

## 4. Problem / Question Answered
*“How many distinct downstream stations are visited by at least one timetable train occurrence that also visits the selected station, without requiring a train change, and how does this compare to the station's immediate outbound timetable neighbors?”*

## 5. Explicit Overlap Audit (Phases 1–35)
- **vs Phase 1/2 (Reachability/Bounded Paths):** Phase 1 uses topological edge adjacency recursively (multi-hop). TFR uses strict `train_id` bounds.
- **vs Phase 3 (Continuous Services):** Phase 3 evaluates whether there is a direct train from $O$ to a specific $D$. TFR evaluates the total count of all unique $D$s reachable on continuous train occurrences from $O$.
- **vs Phase 5 (Hub Centrality):** Hub Centrality counts raw topological degree ($N_1$) and train volume. TFR counts unique stations globally reachable on the same train.
- **vs Phase 18 (Outbound Transit):** Phase 18 computes service to immediate 1-hop neighbors only.
- **vs Phase 20 (Station O-D Bridges):** 
  Phase 20 extracts terminal origin/destination structure for services traversing the station, while Phase 36 counts the complete set of distinct downstream timetable stations reachable on those same continuous train occurrences.
  For a timetable service: A → S → B → C → D
  Phase 20 O-D bridge representation for S: A → D
  Phase 36 TFOR downstream stations for S: B, C, D
- **vs Phase 35 (2-Hop Reachability):** Phase 35 expands exactly two topological hops. TFR expands unbounded topologically, but is strictly bounded by train route length.

## 6. Why the Selected Capability is Distinct
TFR provides a completely new spatial dimension to station analytics. A station might have a topological outbound degree ($N_1$) of only 2 (e.g., it is a minor station on a main line). However, if many long-distance express trains stop there, its TFOR could be 1,000+. The ratio of TFOR to $N_1$ reveals whether a station acts as a "long-range gateway" or a "local shuttle stop."

## 7. Exact Semantics
For a target station $S$:
1. **$N_1$ (Topological Outbound Degree):** The number of distinct immediate outbound timetable neighbors of the selected station.
2. **TFOR (Transfer-Free Outbound Reach):** The count of distinct stations $Z$ (where $Z \neq S$) such that there exists a train where $S$ precedes $Z$ in the stop sequence.
3. **Reachability Span Ratio (TFOR / $N_1$):** Measures the average network penetration per outbound corridor.

## 8. Mathematical Definition
Let $T$ be the set of all active trains in the timetable graph.
Let $seq(t, S)$ be the stop sequence of train $t$ at station $S$.

TFOR(S) = number of distinct stations T such that at least one train occurrence visits S and later visits T in the same timetable service, with no transfer.

Reachability Span Ratio = TFOR(S) / |N1(S)|

The ratio is undefined when |N1(S)| = 0.

## 9. Data Dependencies
- `DatasetSnapshot` (Status = ACTIVE).
- `Station` and `StationObservation` (for validation).
- `TrainStopObservation` (for `train_id`, `station_id`, `snapshot_id`, and `stop_sequence`).

## 10. Snapshot Semantics
- Station metadata is resolved using the **Active Station Snapshot**.
- Timetable paths are strictly bound to the **Active Timetable Snapshot**. No cross-snapshot joining is permitted.

## 11. API Proposal
```http
GET /api/v1/network/stations/{station_code}/transfer-free-reach
```

## 12. Response Fields
```json
{
  "station_code": "MGS",
  "station_name": "PT. DEEN DAYAL UPADHYAYA JN.",
  "topological_outbound_degree": 8,
  "transfer_free_outbound_reach": 3428,
  "reachability_span_ratio": 428.5
}
```

## 13. Error Semantics
- **404 Not Found**: Station code does not exist.
- **503 Service Unavailable**: No active timetable snapshot.
- **400 Bad Request**: $N_1 = 0$ (Terminal station with no departures; TFOR is mathematically undefined).

## 14. Query / Algorithm Design
Implemented via natively bounded CTEs:
```sql
WITH target AS (
    SELECT id FROM stations WHERE code = :station_code
),
n1 AS (
    SELECT DISTINCT t2.station_id
    FROM train_stop_observations t1
    JOIN train_stop_observations t2 
      ON t1.train_id = t2.train_id 
     AND t1.snapshot_id = t2.snapshot_id 
     AND t1.stop_sequence + 1 = t2.stop_sequence
    WHERE t1.snapshot_id = :snapshot_id
      AND t1.station_id = (SELECT id FROM target)
),
tfor AS (
    SELECT DISTINCT t2.station_id
    FROM train_stop_observations t1
    JOIN train_stop_observations t2 
      ON t1.train_id = t2.train_id 
     AND t1.snapshot_id = t2.snapshot_id 
     AND t1.stop_sequence < t2.stop_sequence
    WHERE t1.snapshot_id = :snapshot_id
      AND t1.station_id = (SELECT id FROM target)
      AND t2.station_id != (SELECT id FROM target)
)
SELECT 
    (SELECT COUNT(*) FROM n1) as n1_count,
    (SELECT COUNT(*) FROM tfor) as tfor_count
```

## 15. Complexity Analysis
- **Time Complexity:** $O(|V_S| \cdot L)$, where $|V_S|$ is the number of trains stopping at $S$, and $L$ is the average remaining route length of those trains.
- **Space Complexity:** $O(|N_{TFOR}|)$, upper-bounded by the total number of stations in the timetable graph.

## 16. Worst-Case Behavior
The maximum possible TFOR is bounded by $|V| - 1$ (the total number of stations in the graph). Because there is no recursive `UNION ALL`, the maximum iterations are exactly 1 relational join. The query scales predictably regardless of network depth.

## 17. Performance Analysis
The query relies entirely on two existing indexes:
- `ix_train_stops_snapshot_station` to find all trains stopping at $S$.
- `train_stop_observations_pkey` (`snapshot_id`, `train_id`, `stop_sequence`) to traverse downstream stops.
No new indexes are required. No speculative migrations are needed.

## 18. Real Snapshot 2 Validation
The query was executed against the verified active Snapshot 2 dataset:
- **MGS (Major Hub):** $N_1 = 8$, TFOR = 3428, Ratio = 428.50 (Time: 14.6ms)
- **NDLS (Capital Hub):** $N_1 = 2$, TFOR = 3482, Ratio = 1741.00 (Time: 17.4ms)
- **BYS (Intermediate Station):** $N_1 = 3$, TFOR = 2443, Ratio = 814.33 (Time: 15.3ms)
- **XX-BECE (Minor Cabin):** $N_1 = 1$, TFOR = 221, Ratio = 221.00 (Time: 2.5ms)

## 19. Boundary Cases
- **Shuttle Terminus ($N_1 = 1$, TFOR = 1):** A station where the only departing trains terminate immediately at the next stop. Ratio = 1.0.
- **Absolute Terminus ($N_1 = 0$):** No departing trains. API will raise a 400 Bad Request to protect the ratio calculation.

## 20. Non-Goals
This is a historical/static, timetable-derived structural metric.
It does NOT measure:
- passenger accessibility;
- passenger demand;
- actual passenger journeys;
- physical railway connectivity;
- operational continuity;
- real-world travel feasibility.

- Does not compute "1-transfer" or "2-transfer" reachability (this requires computationally expensive combinatorial joins).

## 21. ₹0 Constraints
Fully computable in-memory within the existing PostgreSQL database. Uses the verified historical timetable data. No external LLMs, graph engines, or commercial APIs required.

## 22. Implementation Boundaries
- Use `Session` from `railgati.db`.
- Return exact `StationTransferFreeReachResponse` Pydantic model.
- Strictly adhere to `calculate_station_transfer_free_reach` naming in `src/railgati/services/network.py`.

## 23. Planned Tests
1. `test_transfer_free_reach_normal`: Verify $N_1$ and TFOR against a mock 5-station linear route and a branching route.
2. `test_transfer_free_reach_shuttle`: Verify Ratio = 1.0 for a 2-station shuttle train.
3. `test_transfer_free_reach_terminal`: Verify 400 Bad Request when $N_1 = 0$.
4. `test_transfer_free_reach_missing_station`: Verify 404 response.
5. `test_transfer_free_reach_no_active_snapshot`: Verify 503 response.

## 24. Approval Gate
This discovery document must be reviewed by the product owner before Phase 36 implementation begins. Do not implement Phase 36 code.
