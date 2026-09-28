# RailGati V2.0 – Phase 46 Discovery: Station Pair Intermediate Flow Concentration

**STATUS**: DISCOVERY (NOT IMPLEMENTED)

## 1. Objective
Discover and formalize exactly one new, mathematically justified V2.0 network analytics capability that provides novel timetable structural intelligence, independent of physical geospatial/track infrastructure, using the historical active timetable snapshot.

## 2. Selected Capability: Station Pair Intermediate Hub Concentration
### Proposed Endpoint
`GET /api/v1/network/stations/{from_station_code}/{to_station_code}/intermediate-hubs`

### Problem Statement
When travelling from an origin $O$ to a destination $D$ via scheduled direct services, the actual structural path taken by different trains varies significantly due to detours, alternate trunk lines, or varying service designations (e.g. bypass vs stopping). 
While Phase 45 provides complete exact topological paths, it does not easily reveal individual station bottleneck concentrations. This proposed metric answers: *For a given $(O, D)$ pair, which individual intermediate stations are statistically the most structurally unavoidable (high flow concentration) versus which are rarely traversed detours (sparse concentration)?*

### Formal Metric Definition
- Let $\mathbb{T}$ be the set of all active trains in the given snapshot.
- For a requested $(O, D)$ pair, define a **valid traversal instance** as a tuple $(T, x, y)$ where train $T \in \mathbb{T}$ stops at $O$ at sequence index $x$, stops at $D$ at sequence index $y$, and $x < y$.
- For each valid traversal instance $(T, x, y)$, extract the set of all intermediate stops $S_i$ visited at sequence index $i$ such that $x < i < y$.
- Aggregate over all valid traversal instances to compute two strictly distinct metrics per intermediate station $S$:
  - **`traversal_instance_count`**: The number of unique traversal instances $(T, x, y)$ that include $S$ at least once.
  - **`occurrence_count`**: The total absolute number of times $S$ was visited across all valid traversals (handles intra-traversal cyclomatic loops).

## 3. Semantics
- **Inputs**: `from_station_code`, `to_station_code`.
- **Outputs**: 
  - `timetable_snapshot_id` (int)
  - `total_traversal_instances` (int, base denominator for concentration)
  - `intermediate_hubs`: Array of `StationPairHubItem` sorted deterministically.
- **Sorting/Tie-Breaking**: Sorted by `traversal_instance_count` (DESC), then `occurrence_count` (DESC), then `station_code` (ASC).
- **Invalid Inputs**: Returns HTTP 404 Not Found if either station does not exist in the active global station definitions.
- **Zero-Result Behavior**: If $O$ and $D$ have no valid connecting traversal instances, or if they are purely adjacent with no intermediate stops, the endpoint correctly returns an empty `intermediate_hubs` array and `total_traversal_instances = 0`.
- **Repeated-Station Semantics**: If a train loops such that it visits $S$ multiple times between $O$ and $D$ (e.g., $O \to S \to X \to S \to D$), the `occurrence_count` for $S$ increments by 2, but the `traversal_instance_count` strictly increments by 1.
- **Train Identity**: Multiple valid bounds $(x_1<y_1)$ and $(x_2<y_2)$ from the *same* train are treated as entirely distinct traversal instances mathematically. Cross-train bounds are explicitly isolated by `train_id` AND `snapshot_id`.
- **Snapshot Isolation**: Station metadata relies on the active station snapshot, while schedule boundaries rely strictly on the active timetable snapshot.

## 4. Relationship & Overlap with Existing Phases
- **Phase 45 (Station Pair Route Diversity)**: Phase 45 strictly produces ordered, exact whole-path signatures (e.g. exactly identifying the string `[A, B, C, D]`). It treats identical paths with one detour as completely distinct sets. Phase 46 flattens this complexity, aggregating raw node-level throughput concentration directly.
- **Phase 22 (Station O-D Bridges)**: Phase 22 strictly detects *mandatory* structural cut-vertices (stations with a 100% traversal rate). Phase 46 provides a continuous distribution spectrum, revealing 90% trunk lines and 1% detours, which Phase 22 explicitly ignores.
- **Phase 30 (Station Outbound Dominance) & 41 (Edge Terminal Dispersion)**: These are node-local or edge-local dispersion metrics. Phase 46 is strictly bound by a specific end-to-end $O \to D$ constraint.

## 5. Non-Claims & Strict Limitations
- This metric relies entirely on **scheduled stops**. Trains bypassing a station without a recorded topological stop do NOT contribute to the concentration count.
- This is a measurement of **structural schedule capacity**, NOT passenger ticket demand, real-world foot traffic, physical track infrastructure congestion, or active GPS operational bottlenecks.
- The `traversal_instance_count` does not reflect train frequency per week; it strictly measures unique traversal signatures recorded in the timetable snapshot.

## 6. Real-Data Discovery (Snapshot 2 Validation)
Executed on the local PostgreSQL Snapshot 2 database.
- **High-Volume Case (`NDLS` $\to$ `HWH`)**:
  - Traversed by 6 total direct instances.
  - Returns exactly 159 intermediate hubs.
  - Highly concentrated trunk hubs (e.g., `ASN`, `ALD`, `CNB`) hit exactly 6/6 `traversal_instance_count` and 6 `occurrence_count`.
- **Detour/Variant Case (`LTT` $\to$ `PUNE`)**:
  - Traversed by 27 total direct instances.
  - High-concentration trunk: `ABH`, `AKRD`, `BND` (27/27 traversals).
  - Sparse detours identified: `BGWI`, `MHLC`, `NAGC`, `NNCN`, `SLRW`, `TKW` all show exactly 1 traversal instance each. This perfectly exposes the structural utility of the metric to find variant routing.
- **Empty/Adjacent Case (`VDR` $\to$ `CDG`)**:
  - Returns 0 hubs and 0 instances.
- **Unknown Station Case (`NDLS` $\to$ `MMCT`)**:
  - `MMCT` does not exist in the active metadata (`BCT` is used instead). Validation strictly enforces HTTP 404 rather than evaluating a null SQL bound.

## 7. Performance (EXPLAIN ANALYZE)
Running on the high-volume `NDLS` $\to$ `HWH` case:
- **Planning Time**: ~2.524 ms
- **Execution Time**: ~9.156 ms
- **Operators**: Employs a highly efficient `Hash Join` over indexed subsets (`ix_train_stops_snapshot_station`) to isolate the $O$ and $D$ bounding sequences, followed by a `Nested Loop` scanning only the strictly bounded `ts.stop_sequence > tt.o_seq AND ts.stop_sequence < tt.d_seq`.
- **Memory footprint**: The final `Sort` and `GroupAggregate` consumed merely `124kB` of memory. No full-table sequential scans occurred.

## 8. Implementation Feasibility
- **Schema & Migrations**: Requires zero migrations. Existing tables `train_stop_observations` and `stations` natively support this exact logic.
- **Indexes**: The existing `ix_train_stops_snapshot_station` index is sufficient and heavily utilized. No new indexes are required.
- **Processing**: The metric is extremely efficient to compute purely database-side using a `WITH` CTE bounding clause, `GROUP BY`, and `COUNT(DISTINCT ...)`.

## 9. Test Strategy (For Future Implementation)
1. **Empty Result Test**: Pair with no connections returns `[]` and `0`.
2. **Missing Station Test**: 404 propagation for invalid codes.
3. **Loop Verification Test**: Mock a train $A \to B \to A \to D$. Verify $B$'s `occurrence_count` vs `traversal_instance_count` correctly handles the loop without inflating the denominator.
4. **Ordering Test**: Verify the multi-column tie-breaking logic (`traversal DESC, occurrence DESC, code ASC`) is perfectly deterministic.
5. **Cross-Train Isolation**: Verify the mathematical extraction doesn't accidentally pair $O$ from Train 1 and $D$ from Train 2.

## 10. Rejected Candidates & Overlap Reasoning
- **Candidate A: Edge O-D Bounding Persistence (Terminal Dispersion)**
  - *Why useful*: Shows what major cities an edge connects.
  - *Overlap*: Formally equivalent to Phase 41 (Edge Route Terminal Dispersion). Rejected.
- **Candidate B: Train Cyclomatic Index**
  - *Why useful*: Identifies complex non-linear trains.
  - *Overlap*: Subsumed by Phase 26 (Train Topology Loop Analytics). Rejected.
- **Candidate C: Station Pair Absolute Articulation Points**
  - *Why useful*: Identifies critical transfer failure points.
  - *Overlap*: Identical to Phase 22 (Station O-D Bridges). Rejected.
- **Candidate D: Train Route Edge Exclusivity Profiling**
  - *Why useful*: Identifies monopolistic edge utilization by a specific train.
  - *Overlap*: Fully implemented in Phase 40 (Route Edge Structural Exclusivity). Rejected.

**END OF DISCOVERY**
*Implementation of this phase is strictly NOT approved yet.*
