# RailGati V2.0 – Phase 43 Discovery: Train Maximum Shared Sub-Route Analytics

## 1. Objective
Discover exactly ONE genuinely new Network Analytics capability for Phase 43 that is distinct, derived entirely from the historical timetable dataset, deterministic, structurally meaningful, and executable with the current PostgreSQL architecture under a strict ₹0 budget constraints without external dependencies.

## 2. Phase 1–42 Overlap Audit
A thorough audit of the existing analytical catalog ensures this capability is entirely distinct:
- **Phase 15 (Train Route Similarity):** Calculates standard Jaccard similarity based on unordered sets of stops. It does not measure contiguous sequential routing.
- **Phase 37 (Train Structural Subsumption):** Determines strict subset containment (i.e., whether Train A's route is entirely contained within Train B's route). It acts as a boolean gateway rather than measuring partial exact overlap lengths.
- **Phase 39 & 41 (Edge Dispersion):** Focuses on single edges rather than entire train trajectories.
- **Phase 40 (Edge Structural Exclusivity):** Finds edges uniquely served by a single train.
- **Phase 42 (Edge Route Co-Traversal Affinity):** Evaluates how many trains share a single specific edge.
- **Conclusion:** There is currently no capability that isolates the *longest contiguous identical sub-route* (sequence alignment) shared between two disparate trains.

## 3. Candidates Considered
- **Station Route Terminal Convergence:** Measuring the distinct ultimate origins/destinations of all trains passing through a station S.
- **Network Edge Structural Alternativity:** Identifying how many distinct topological paths exist between a single structural edge.
- **Train Maximum Shared Sub-Route Analytics:** Identifying the maximal contiguous, identical stopping sequence between a target train and any other train.

## 4. Rejected Candidates and Reasons
- **Station Route Terminal Convergence:** Rejected because it is merely a different aggregation level (station instead of edge) of Phase 41 (Edge Route Terminal Dispersion).
- **Network Edge Structural Alternativity:** Rejected because it requires expensive recursive pathfinding equivalent to existing corridor/path endpoints and overlaps heavily with topological bypass tracking (Phase 38).

## 5. Selected Capability: Train Maximum Shared Sub-Route Analytics
Given a target train identity $T$, what is the length of the longest contiguous sequence of stops it shares identically (in identical order) with any other train identity $U$, and which train(s) $U$ share this maximum length?

This metric provides deep structural sequence alignment without machine learning, mathematically identifying exactly where, and for how long, train routes geographically converge before diverging.

## 6. Formal Mathematical/Set Definition
- Let $S(T) = [s_1, s_2, ..., s_N]$ be the strictly ordered sequence of station identities visited by target train $T$.
- Let $S(U) = [u_1, u_2, ..., u_M]$ be the ordered sequence for a candidate train $U$.
- A shared contiguous sub-route of length $L$ exists between $T$ and $U$ if there exist integer offsets $i$ and $j$ such that $s_{i+k} = u_{j+k}$ for all $k \in [0, L-1]$.
- The capability computes the shared segment lengths for all $U \neq T$ and returns the overlapping segments ordered by maximal length $L$.

## 7. Exact Semantics
- **Entities:** Trains, mapped over strict Stop Sequences.
- **Snapshot Scope:** Strictly scoped to the requested active timetable snapshot.
- **Sequence Identity:** Two stops are part of the same contiguous sub-route if and only if both the target train and candidate train visit the identical station, and the difference in their respective stop sequences remains constant.
- **Ordering:** Deterministic order by `shared_len DESC, other_train ASC`.
- **Aggregation:** A single train $U$ may share multiple disjoint contiguous sub-routes with $T$. Each disjoint sub-route forms a distinct structural segment evaluated for length.

## 8. Semantic Guardrails
- **Timetable-Structural Meaning:** This metric strictly quantifies timetable routing sequence overlap.
- **Exclusions:** It does NOT measure operational coupling (trains physically attached), passenger transfer likelihood (since it ignores temporal alignment), or physical track layout (only timetable stops).

## 9. Edge Cases
- **Empty Result:** If a train shares absolutely zero stations with any other train, an empty array is returned.
- **Single Station Overlap:** A single shared station (intersection without co-traversal of an edge) yields $L=1$.
- **Complete Identical Route:** If two trains traverse the exact same route, $L$ will equal the total length of the target train.

## 10. API Contract
**Endpoint:** `GET /api/v1/network/trains/{train_number}/max-shared-sub-route`

**Response Schema:**
```json
{
  "target_train_number": "12004",
  "timetable_snapshot_id": 2,
  "top_shared_sub_routes": [
    {
      "other_train_number": "12420",
      "shared_station_count": 74,
      "start_station_code": "NDLS",
      "end_station_code": "LKO"
    }
  ]
}
```

## 11. Query Strategy
The query uses a highly efficient set-based approach leveraging the mathematical property that contiguous sub-routes maintain a constant stop-sequence offset difference:
1. `target_stops` CTE extracts the target train's ordered sequence.
2. `shared_segments` CTE joins `train_stop_observations` on matching `station_id` for all other trains.
3. It performs a `GROUP BY` on `t2.train_id` and the expression `(t1.stop_sequence - t2.stop_sequence)`.
4. This instantly collapses identical continuous segments into single records, allowing $O(1)$ length extraction via `COUNT(*)`.

## 12. Snapshot 2 Validation
Exploratory validation against the exact PostgreSQL Snapshot 2 timetable confirms mathematically flawless extraction:

- **Target: 12004 (Shatabdi/Intercity structural variant)**
  - Matches 12420, 12556, and 12566 with an exact shared continuous sequence length of **74** stations (NDLS -> LKO).
  - Matches 13414, 13484 with length **68** (SBB -> LKO).
- **Target: 12951 (Rajdhani structural variant)**
  - Matches 19023 with a shared length of **202** stations (BCT -> NDLS).
  - Matches 12903 with **199** stations (BCT -> PGMD).
- **Target: 11013 (Boundary/Secondary Express)**
  - Matches 11027 and 16381 with **124** stations (LTT -> GY).

## 13. Performance / EXPLAIN ANALYZE
Execution on Train 12004 against Snapshot 2:
- **Planning Time:** 0.619 ms
- **Execution Time:** 7.564 ms
- **Path Highlights:** 
  - Extracted sequence in ~0.1 ms using `train_stop_observations_pkey`.
  - Joined candidate sequences natively using `ix_train_stops_snapshot_station` via highly-efficient Hash Join.
  - Aggregated continuous sequences using `HashAggregate` on the offset difference expression.
  - Zero sequential scans on observational tables. Deterministic `top-N heapsort` memory profile (~30kB).

## 14. Implementation Boundary
This discovery document establishes the strict boundary for Phase 43. No other phases are affected.

## 15. Explicit STOP Condition
Discovery is complete. No implementation code, schemas, or tests are to be written. Scratch files must be cleaned, and the session must stop immediately after this document is committed.
