# RailGati V2.0 Phase 32: Network Station Neighborhood Directional Symmetry Analytics

## 1. Objective
Discover and define the 32nd foundational railway analytics capability for RailGati V2.0. The objective is to identify a genuinely new analytical dimension that respects the ₹0 budget, utilizes deterministic historical timetable data, applies precise mathematical semantics, and completely avoids physical/operational assertions.

## 2. Repository and Data-State Inspection
A rigorous inspection of the current RailGati repository and PostgreSQL database (Snapshot 2) was performed:
- **Timetable Snapshot:** Dataset Snapshot 2 is ACTIVE.
- **Train Stop Observations:** ~417,000 active observations.
- **Trains:** ~3,000 scheduled trains.
- **Stations:** Identified strictly by `station_id` resolving to `Station` entities.
- **Graph Topology:** The repository models scheduled edges strictly via `stop_sequence` and `stop_sequence + 1` from `train_stop_observations`.
- **Existing Phases (1-31):** Explored covering Hub Centrality, Edge Volume, O-D Flow, Dwells, Route Complexity, Directional Asymmetry, Train/Station Similarity, Paired-Service metrics, Topologies, Slowness, Outbound Dominance, and Paired-Service Edge Symmetry.
- **Current Endpoints:** Include `GET /api/v1/network/edges/{from_station}/{to_station}/paired-symmetry` (Phase 31).

## 3. Existing Phase 1–31 Capability Map
- **Phase 7, 8, 10:** Node degrees and edge/O-D volumes.
- **Phase 11, 23, 27, 29:** Station time, dwells, gaps, and structural halts.
- **Phase 14, 30:** Imbalance on specific directed edges and outbound volume dominance.
- **Phase 15, 16:** Topological Jaccard similarities between two distinct trains or two distinct stations.
- **Phase 18, 25, 31:** Paired-service layovers, temporal symmetry, and individual edge symmetry.
- **Phase 26:** Train-level topological loops.

## 4. Candidate Analytics
Six distinct candidates were generated and mathematically evaluated:

1. **Network Edge Service Type Homogeneity Analytics**
   - *Question:* For a directed adjacent timetable edge, what proportion of its scheduled train occurrences belong to the single most dominant dataset-provided train type?
   - *Unit:* Adjacent timetable edge.
   - *Overlap/Rejection:* Overlaps heavily with Phase 30 (Outbound Dominance), substituting `train_type` for `destination_id`. Rejected.
2. **Network Station Adjacent Connectivity Reciprocity Analytics (Neighborhood Directional Symmetry)**
   - *Question:* For a given station, what is the Jaccard similarity between its set of distinct immediate outbound destination stations and its set of distinct immediate inbound origin stations?
   - *Unit:* A single station.
   - *Overlap/Rejection:* Entirely distinct from existing phases. Selected.
3. **Network Station Component Isolation Analytics**
   - *Question:* For a given station, what proportion of its scheduled outbound occurrences lead to a station that is a network terminus?
   - *Unit:* A single station.
   - *Overlap/Rejection:* Requires multi-hop evaluation of terminus status which is mathematically brittle if the schedule is fragmented. Overlaps with Phase 9 (Terminus Analytics). Rejected.
4. **Network Station Degree Asymmetry Analytics**
   - *Question:* For a given station, what is the relative imbalance between its absolute number of distinct outbound destinations and absolute number of distinct inbound origins?
   - *Unit:* A single station.
   - *Overlap/Rejection:* Merely subtraction of in/out degrees already easily derivable from Phase 7 (Hub Centrality). Rejected.
5. **Network Train Re-Visitation Analytics**
   - *Question:* For a train identity, what proportion of its scheduled total stops occur at stations it has already visited earlier in its itinerary?
   - *Unit:* A single train identity.
   - *Overlap/Rejection:* Essentially equivalent to Phase 26's loop detection mechanism. Rejected.
6. **Network Station Paired-Service Terminal Coincidence Analytics**
   - *Question:* For a given station, among all paired services originating here, what proportion have their dataset-linked return train terminating at this exact same station?
   - *Unit:* A single station.
   - *Overlap/Rejection:* Narrowly overlaps Phase 18 (Paired-Service Station Analytics). Rejected.

## 5. Phase 14 / 31 Overlap Distinction
The selected candidate is analytically distinct from Phase 14 and Phase 31.
- **Phase 14 (Directional Edge Asymmetry):** Asks "How different are reciprocal edge occurrence volumes?" It compares raw occurrence counts on specific `A -> B` vs `B -> A` directed edge pairs.
- **Phase 31 (Paired-Service Edge Symmetry):** Asks "Among forward train identities on an edge, how many have a dataset-linked reciprocal paired service?" It relies on train identities and `return_train_number` properties.
- **Phase 32 (Neighborhood Directional Symmetry):** Asks "How much overlap exists between the station's distinct adjacent outbound-neighbor set and distinct adjacent inbound-neighbor set?" It evaluates sets of distinct stations topologically connected to the queried station. It does not use edge occurrence volume, train counts, `return_train_number`, or passenger volume.

## 6. Selected Candidate
**Network Station Neighborhood Directional Symmetry Analytics**

## 7. Exact Semantics
- **Unit of Analysis:** A single valid `Station` in the active dataset snapshot.
- **Outbound Neighborhood ($N_{out}$):** The distinct set of station identities $V$ such that an adjacent scheduled timetable edge $S \rightarrow V$ exists.
- **Inbound Neighborhood ($N_{in}$):** The distinct set of station identities $U$ such that an adjacent scheduled timetable edge $U \rightarrow S$ exists.
- **Symmetry Ratio:** Evaluated using the Jaccard index: $J = \frac{| N_{out} \cap N_{in} |}{| N_{out} \cup N_{in} |}$.
- **Occurrence vs Distinct:** Strictly distinct-station-based. Multiple trains traveling $S \rightarrow X$ do not multiply the set membership of $X$.
- **Zero Denominator:** If a station has neither inbound nor outbound scheduled edges (union is 0), the calculation is undefined.

## 8. API Contract
**GET /api/v1/network/stations/{station_code}/neighborhood-symmetry**
- "neighborhood" is explicitly defined as the set of distinct stations connected to the queried station by an adjacent scheduled timetable edge in either direction within the active timetable snapshot.

**Response Fields:**
- `station_code` (str)
- `timetable_snapshot_id` (int)
- `outbound_destinations_count` (int): $|N_{out}|$
- `inbound_origins_count` (int): $|N_{in}|$
- `symmetric_neighbors_count` (int): $|N_{out} \cap N_{in}|$
- `total_neighborhood_size` (int): $|N_{out} \cup N_{in}|$
- `symmetry_ratio` (float): $J$ bounded [0.0, 1.0].

**HTTP Behaviors:**
- **200 OK:** Valid calculation with ratio $\ge 0.0$.
- **400 Bad Request:** Valid station, but it has 0 scheduled inbound AND 0 scheduled outbound edges (Union is 0, mathematically undefined).
- **404 Not Found:** Station code does not exist in the active snapshot.
- **503 Service Unavailable:** No active timetable snapshot available.

## 9. Mathematical Definitions
Let $E$ be the set of all adjacent scheduled edges $(U, V)$ in the snapshot.
For queried station $S$:
$$ N_{out}(S) = \{ V \mid (S, V) \in E \} $$
$$ N_{in}(S) = \{ U \mid (U, S) \in E \} $$

$$ \text{symmetric\_neighbors\_count} = | N_{out}(S) \cap N_{in}(S) | $$
$$ \text{total\_neighborhood\_size} = | N_{out}(S) \cup N_{in}(S) | $$

When $\text{total\_neighborhood\_size} > 0$:
$$ \text{symmetry\_ratio} = \frac{| N_{out}(S) \cap N_{in}(S) |}{| N_{out}(S) \cup N_{in}(S) |} $$
Undefined otherwise.

## 10. Deduplication Semantics
The metric is strictly SET-BASED.
- Train identity is NOT the unit.
- Occurrence count is NOT the unit.
- Edge volume is NOT the unit.
- The distinct station-neighbor relationship IS the unit.
The SQL strategy must use `DISTINCT station_id` when constructing the outbound and inbound CTEs. This is semantically required because a station $X$ belongs to the set $N_{out}(S)$ if AT LEAST ONE timetable occurrence travels $S \rightarrow X$. Fifty occurrences traveling $S \rightarrow X$ do not add $X$ fifty times to the set.

## 11. SQL/Query Strategy
A set-based CTE approach is used to isolate topological sets safely:
1. `outbound`: `SELECT DISTINCT tso2.station_id ... WHERE tso1.station_id = S`
2. `inbound`: `SELECT DISTINCT tso1.station_id ... WHERE tso2.station_id = S`
3. Cross-join aggregates to find total counts.
4. Join `outbound` and `inbound` on `station_id` to compute the intersection size.
5. Compute the union size using `UNION` of the two CTEs.

## 12. EXPLAIN ANALYZE Evidence
On the current Snapshot 2 dataset, PostgreSQL used a mixed strategy and execution took ~34.2 ms (planning time: ~1.3 ms) for a highly connected station (`MGS`).
- The `outbound` CTE utilized a nested loop with index scans on `ix_train_stops_snapshot_station` and `train_stop_observations_pkey`.
- The `inbound` CTE utilized a `Parallel Seq Scan` on `train_stop_observations` joined against an `Index Scan`. A sequential scan occurs here because querying `tso2.station_id = S` to fetch the preceding `tso1` rows requires matching `stop_sequence` mathematically, preventing isolated index use for the preceding rows.
- The `Parallel Seq Scan` executed efficiently across available workers and remains acceptable for this discovery dimension.

## 13. Real Snapshot 2 Validation
The query was validated against actual Snapshot 2 data:
- `MGS` (Mughal Sarai Junction): Out: 8, In: 8, Intersection: 8, Union: 8. Symmetry Ratio: **1.0**
- `BYS` (Barsali): Out: 3, In: 3, Intersection: 3, Union: 3. Symmetry Ratio: **1.0**
- `XX-BECE` (Bhilai East Cabin): Out: 1, In: 1, Intersection: 0, Union: 2. Symmetry Ratio: **0.0**
- `KBGB` (Kahalgaon Bhagalpur Bypass): Isolated station. Union: 0.

## 14. Independent Mathematical Validation
A separate Python script extracted raw snapshot edges and computed the sets manually for `MGS`:
- Python computed: $|N_{out}| = 8$, $|N_{in}| = 8$.
- Python computed: $|N_{out} \cap N_{in}| = 8$, $|N_{out} \cup N_{in}| = 8$.
- Confirmed constraints: $8 \le 8$, $8 \ge 8$, and ratio $8/8 = 1.0$.
Matches SQL CTE results precisely.

## 15. Zero/Undefined Semantics
If the computed union is zero, the ratio is mathematically undefined. Following RailGati API conventions for invalid denominators (e.g., Phase 31 zero-forward bounds), the API will return HTTP 400 Bad Request to indicate no qualifying analytical data exists for the query, rather than silently injecting 0.0.

## 16. Edge Cases
- **Missing Train Identity:** Irrelevant; this metric evaluates set presence.
- **Repeated Edges:** Handled successfully by `DISTINCT` logic.
- **Isolated Station:** Union is 0, returning HTTP 400.
- **Unknown Station Code:** Returns HTTP 404.

## 17. Active Snapshot Semantics
The future implementation MUST use the existing `get_active_timetable_snapshot_id(db)` helper. Snapshot 2 is used in this document for discovery validation only. Both the station identity lookup and edge traversal must strictly enforce the identical active snapshot ID.

## 18. ₹0 Compliance
Executes entirely in native PostgreSQL. Demands zero new schema migrations, supplementary tables, or external requests.

## 19. Explicit Non-Goals
The metric does NOT measure:
- physical track bidirectionality or layout
- geographic direction
- passenger demand, journeys, or transfers
- train frequency or train volume
- edge capacity or congestion
- operational reciprocity, empty rakes, or return-train pairing
- locomotive/rake/crew continuity
- live railway operations

It measures only overlap between distinct adjacent timetable neighbor sets.

## 20. Implementation Boundaries
- Implementation will append `StationNeighborhoodSymmetryResponse` to `schemas.py`.
- Implementation will append `calculate_station_neighborhood_symmetry` to `services/network.py`.
- Implementation will append the `GET` route to `api/v1/network.py`.
- Implementation will provide focused service and API tests mapping edge cases (e.g., 1.0, 0.0, zero-union).

## 21. Approval Gate
This discovery document is submitted for audit. No implementation files have been modified. Once approved, Phase 32 implementation may commence.
