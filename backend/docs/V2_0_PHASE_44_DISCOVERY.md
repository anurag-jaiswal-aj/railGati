# RailGati V2.0 – Phase 44 Discovery: Train Route O-D Structural Exclusivity Analytics

## 1. Objective
Discover exactly ONE genuinely new Network Analytics capability for Phase 44 that is mathematically distinct from all previous phases, derives strictly from historical timetable data, and can be evaluated relationally under a ₹0 architecture.

## 2. Phase 1–43 Overlap Audit
This capability must be sharply distinguished from existing phase metrics:
- **Phase 40 (Train Route Edge Structural Exclusivity):** Analyzes strict physical adjacency ($S_i \to S_{i+1}$). A train could have zero exclusive edges (i.e., every track segment is shared) but still provide exclusive multi-stop origin-destination connections.
- **Phase 43 (Train Maximum Shared Sub-Route):** Identifies the longest contiguous identical sub-sequence between two trains.
- **Phase 37 (Train Structural Subsumption):** Checks if the entirety of one route is subsumed by another.
- **Phase 22 (Station O-D Bridges):** Explores destination reachability from a single node, rather than isolating single-train structural criticality across an entire journey.

**Conclusion:** There is currently no endpoint measuring "one-seat ride structural uniqueness" across non-adjacent topologies for a specific train.

## 3. Candidates Considered
- **Network Corridor Density:** Which exact physical structural sequences are traversed by the maximum number of distinct trains?
- **Network Station Triadic Closure for Transfers:** For a station, what ratio of incoming/outgoing direct routes bypass the station?
- **Train Route O-D Structural Exclusivity Analytics:** Identifies Origin-Destination pairs that are serviced exclusively by the target train.

## 4. Rejected Candidates and Reasons
- **Network Corridor Density:** Rejected because calculating arbitrary-length frequent maximal structural sequences requires apriori-style sequence mining or recursive pathfinding traversing the entire graph unconditionally, which violates performance constraints.
- **Network Station Triadic Closure for Transfers:** Rejected because it overlaps directly with Phase 34 (Transit Articulation) and Phase 33 (Neighborhood Triadic Closure).

## 5. Selected Phase 44 Capability
**Train Route O-D Structural Exclusivity Analytics**
Given a target train identity $T$, does it serve any ordered Origin-Destination pair $(O, D)$ (regardless of the number of intermediate stops) that NO OTHER train in the active timetable connects directly?

This metric identifies the "structural criticality" of a train. A train might share all of its physical edges with other trains, yet be the singular structural entity offering a direct timetable connection between a distant origin and destination.

## 6. Formal Mathematical Definition
- Let $S(T) = [s_1, s_2, \dots, s_N]$ be the ordered sequence of station identities visited by the target train $T$.
- Let $P(T) = \{(s_i, s_j) \mid 1 \leq i < j \leq N\}$ represent the complete set of $\binom{N}{2}$ ordered origin-destination pairs serviced by $T$.
- An O-D pair $(s_i, s_j) \in P(T)$ is defined as **shared** if there exists ANY train $U \neq T$ (within the same snapshot) that visits station $s_i$ at sequence $x$ and station $s_j$ at sequence $y$, where $x < y$.
- An O-D pair $(s_i, s_j) \in P(T)$ is defined as **exclusive** if it is not shared by any $U$.
- The metric outputs the set of all exclusive pairs for $T$, returning the distinct ordered station identities $(origin\_station\_id, destination\_station\_id)$. Sequence indices are not retained in the final output, as repeated occurrences of the same station pair collapse into a single unique O-D pair.

## 7. Exact Data Semantics
The query computes all topological pair combinations for the target train and tests their existence within the historical observations of all other distinct trains. The structural sequence order ($i < j$) is strictly preserved.

## 8. Snapshot Semantics
Target train generation and candidate pair evaluation are strictly isolated to the specified active `timetable_snapshot_id`.

## 9. Repeated-Occurrence Semantics
If the target train visits a station multiple times (e.g., $A \to B \to A$), the topological pairs might initially contain duplicate station combinations. The finalized metric counts DISTINCT ordered station pairs, not stop-occurrence pairs. Thus, repeated occurrences of the exact same station pair collapse into one single unique O-D pair in the final result. Furthermore, the evaluation for exclusivity joins on physical `station_id`. If another train visits $A \to B$, it invalidates the exclusivity of the $A \to B$ pair. This mathematically preserves the definition of "exclusive one-seat physical service."

## 10. Tie/Edge-Case Semantics
- **No Exclusive Pairs:** If every O-D combination on the train is shared by at least one other train, the API must return an empty array (length 0).
- **2-Stop Train:** Mathematically identical to Edge Exclusivity.
- **Unknown Target:** Returns HTTP 404.

## 11. Semantic Guardrails
- **Timetable-Structural Metric:** Quantifies historical timetable direct connection uniqueness.
- **Does NOT infer:** Passenger demand, physical track availability, operational network capacity, congestion, or the inability of passengers to simply transfer between non-exclusive trains.

## 12. API Contract
**Endpoint:** `GET /api/v1/network/trains/{train_number}/route-od-exclusivity`

**Response Schema:**
```json
{
  "target_train_number": "11013",
  "timetable_snapshot_id": 2,
  "exclusive_od_pair_count": 2155,
  "exclusive_od_pairs": [
    {
      "origin_station_code": "LTT",
      "destination_station_code": "BLRR"
    }
  ]
}
```

## 13. Query Strategy
1. **target_stops:** Extract stops for the target train.
2. **target_pairs:** Compute the combinations via a self-join (`t1.stop_sequence < t2.stop_sequence`), applying `SELECT DISTINCT` to ensure only distinct station pairs `(o_id, d_id)` are processed, effectively collapsing any duplicate pairs caused by repeated station occurrences.
3. **shared_pairs:** Join `target_pairs` with `train_stop_observations` twice (for origin and destination) where `ts1.train_id = ts2.train_id`, `ts1.stop_sequence < ts2.stop_sequence`, and the train is not the target train. Use `SELECT DISTINCT` to prevent candidate multiplicity from inflating counts.
4. **exclusive_pairs:** Apply a `LEFT JOIN ... WHERE sp.o_id IS NULL` anti-join to subtract shared pairs from target pairs.
5. **Ordering:** Sort deterministically by `origin_station_code ASC, destination_station_code ASC`.

## 14. Snapshot 2 Validation
Exploration against PostgreSQL Snapshot 2 confirmed the metric works natively:
- **Train 12004 (Shatabdi variant):** Yields 0 exclusive O-D pairs (all connections are highly shared).
- **Train 12951 (Rajdhani variant):** Yields 0 exclusive O-D pairs.
- **Train 11013 (Secondary Express with 135 stops):** Yields exactly **2155 exclusive O-D pairs** (e.g., LTT -> BLRR, LTT -> CRLM), definitively proving its unique structural criticality. The original exploratory count of 2158 contained three duplicate station O-D pairs caused by repeated station occurrences, which have been correctly collapsed down to 2155 under the finalized DISTINCT semantics.

## 15. EXPLAIN ANALYZE Findings
Testing the heavy 135-stop boundary case (Train 11013):
- **Planning Time:** 1.276 ms
- **Execution Time:** ~1087 ms
- **Strategy Highlights:** Uses a `Merge Anti Join` effectively. Utilizes `ix_train_stops_snapshot_station` to look up candidates. The query gracefully limits the candidate scan universe exactly to the $\binom{N}{2}$ pairs (approx. 9045 pairs) of the target train, preventing exponential Cartesian explosions across the entire snapshot. It scales with $O(N^2)$ based on the target train's stop count $N$, which is mathematically sound and strictly bounded by physical train lengths (typically $< 150$). No schema modifications or new indexes are required.

## 16. Implementation Boundary
This is Phase 44 discovery. No API logic, schema adjustments, or test implementations are permitted.

## 17. Explicit STOP Condition
Stop immediately after saving and committing this discovery document.
