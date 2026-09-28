# RailGati V2.0 – Phase 46 Discovery: Station Pair Intermediate Flow Concentration

**STATUS**: DISCOVERY (NOT IMPLEMENTED)

## 1. Objective
Discover and formalize exactly one new, mathematically justified V2.0 network analytics capability that provides novel timetable structural intelligence, independent of physical geospatial/track infrastructure, using the historical active timetable snapshot.

## 2. Selected Capability: Station Pair Intermediate Flow Concentration Analytics
### Proposed Endpoint
`GET /api/v1/network/stations/{from_station_code}/{to_station_code}/intermediate-flow-concentration`

### Problem Statement
When travelling from an origin $O$ to a destination $D$ via scheduled direct services, the actual intermediate stops visited vary significantly based on timetable configurations. While Phase 45 provides complete exact topological paths, it does not directly aggregate station incidence properties. This proposed metric answers: *For a given $(O, D)$ pair, what is the exact historical timetable-derived station concentration of each intermediate station evaluated across all qualifying $O \to D$ timetable traversal instances?*

### Formal Metric Definition
- Let $\mathbb{T}$ be the set of all active trains in the given timetable snapshot.
- For a requested $(O, D)$ pair, define a **valid traversal instance** as a tuple $(T, x, y)$ where train $T \in \mathbb{T}$ stops at $O$ at sequence index $x$, stops at $D$ at sequence index $y$, and $x < y$. All observations must belong strictly to the active timetable snapshot.
- For every valid traversal instance $(T, x, y)$, evaluate all intermediate stations $S$ occurring strictly between $x$ and $y$ (i.e. at index $i$ such that $x < i < y$).
- Evaluate two distinct metrics for each intermediate station $S$:
  - **`traversal_instance_count(S)`**: The total number of DISTINCT $(T, x, y)$ traversal instances containing $S$ at least once strictly between $x$ and $y$.
  - **`occurrence_count(S)`**: The total absolute number of stop occurrences of $S$ appearing strictly between $x$ and $y$ across all valid traversal instances.

*Critical Distinction Example*:
If a station occurs twice strictly between the selected origin and destination during a single traversal instance (e.g. $O \to B \to X \to B \to D$), then for this single traversal instance $(T, x_{O}, y_{D})$:
- $B$ traversal_instance_count contribution = 1
- $B$ occurrence_count contribution = 2

## 3. Semantics
- **Inputs**: `from_station_code`, `to_station_code`.
- **Outputs**: 
  - `timetable_snapshot_id` (int)
  - `total_traversal_instances` (int, total number of qualifying traversal instances evaluated)
  - `intermediate_hubs`: Array of objects containing `station_code`, `occurrence_count`, `traversal_instance_count`.
- **Sorting/Tie-Breaking**: Sorted deterministically by `traversal_instance_count` (DESC), then `occurrence_count` (DESC), then `station_code` (ASC).
- **Invalid Inputs**: Returns HTTP 404 Not Found if either station does not exist in the active global station definitions.
- **Zero-Result Behavior**: If $O$ and $D$ have zero qualifying traversal instances, or if they are purely adjacent with no intermediate stops, the endpoint correctly returns an empty `intermediate_hubs` array and `total_traversal_instances = 0`.

### Repeated Origin/Destination Semantics
Every valid $x < y$ occurrence pair constitutes a strictly distinct traversal instance. Do not silently deduplicate by train identity.
*Example*: For $A \to D \to A \to D$, computing for the pair $A \to D$ yields three valid occurrence pairs:
1. $A_1 \to D_1$
2. $A_1 \to D_2$
3. $A_2 \to D_2$
Therefore, the traversal universe contains exactly 3 traversal instances. For every such traversal instance, intermediate stations are evaluated independently.

### Snapshot Semantics
- The active timetable snapshot is resolved once per request.
- All train-stop observations are enforced strictly to that snapshot.
- Origin and destination occurrences are paired only within the exact same train identity AND exact same snapshot.
- No observations from previous, inactive, or adjacent snapshots participate.

## 4. Relationship & Overlap with Existing Phases
### Distinctness from Phase 45 (Station Pair Route Diversity)
- Phase 45 groups complete exact ordered $O \to D$ station sequences and treats the path identity as the entire ordered array.
- Phase 46 completely ignores complete path identity, projecting qualifying $O \to D$ traversal instances onto individual intermediate stations instead, measuring station incidence independently across traversal bounds.

*Concrete Example*:
- Traversal 1: $O \to A \to B \to D$
- Traversal 2: $O \to A \to C \to D$
- Phase 45 evaluation: Identifies 2 completely distinct paths.
- Phase 46 evaluation: Evaluates $A$ as appearing in 2 traversal instances; $B$ in 1; $C$ in 1.

### Distinctness from Phase 22 (Station O-D Bridges)
- Phase 22 strictly detects mandatory structural cut-vertices (stations appearing in 100% of traversals).
- Phase 46 yields continuous incidence probability across the entirety of qualifying traversals, reporting fractional timetable incidence rates (e.g. present in 1 out of 27 traversals).

## 5. Non-Claims & Strict Limitations
This metric represents purely *O-D-conditioned timetable traversal incidence*. 
It does **NOT** measure, estimate, or imply:
- passenger demand or volume
- ticket sales or passenger preference
- train capacity
- physical track utilization
- infrastructure bottlenecks or physical bottlenecks
- traffic bottlenecks or operational bottlenecks
- primary geographic trunks or geographic detours
- single points of failure
- operational dependency, service reliability, or congestion
- geographic centrality or current/live service availability
- real-world structural redundancy

If a station features a 100% traversal instance rate, it is strictly an artifact of historical timetable incidence rules, NOT an operational "bottleneck" or "single point of failure".

## 6. Real-Data Discovery (Snapshot 2 Validation)
Executed against local PostgreSQL Snapshot 2 datasets.

### `NDLS` $\to$ `HWH`
- **Qualifying traversal-instance count**: 6
- **Distinct intermediate station count**: 320 (Note: Earlier discovery documentation contained incorrect manually recorded counts; independent relational verification established the authoritative values. The scratch SQL query utilized `LIMIT 15` and never executed a `COUNT(*)` over distinct stations. The independent formal bounded count is exactly 320.)
- **Top stations by traversal_instance_count**:
  - `AAP` (Occurrence count: 6, Traversal instance count: 6)
  - `AJR` (Occurrence count: 6, Traversal instance count: 6)
  - `ALD` (Occurrence count: 6, Traversal instance count: 6)
  - `ALJN` (Occurrence count: 6, Traversal instance count: 6)
  - `ANVR` (Occurrence count: 6, Traversal instance count: 6)
  *(Array maintains strict deterministic ordering: `traversal DESC`, `occurrence DESC`, `station_code ASC`)*

### `LTT` $\to$ `PUNE`
- **Qualifying traversal-instance count**: 27
- **Distinct intermediate station count**: 48 (Note: Earlier discovery documentation contained incorrect manually recorded counts; independent relational verification established the authoritative values. The formal limit is exactly 48.)
- **Stations occurring in all qualifying traversal instances (27/27)**: `ABH`, `AKRD`, `BGW`, `BND`, `BUD`, `BVS`, `CCH`, `DAPD`, `DEHR`, `DI`, `DIVA`, `GC`, `GRWD`, `KAD`, `KJMG`, `KJT`, `KK`, `KMST`, `KNHE`, `KOPR`, `KSWD`, `KYN`, `LNL`, `MLND`, `MVL`, `NHU`, `NRL`, `PDI`, `PMP`, `SHLU`, `SVJR`, `TGN`, `THK`, `TNA`, `ULNR`, `VDN`, `VGI`, `VK`, `VLDI`, `VVH`. (Note: Earlier discovery documentation contained incorrect manually recorded counts; independent relational verification established the authoritative values. The formal distinct bound is 40 stations.)
- **Stations occurring in only one qualifying traversal instance (1/27)**: `BGWI`, `MHLC`, `NAGC`, `NNCN`, `SLRW`, `TKW`.

### `VDR` $\to$ `CDG` (Zero Hub Case)
- **Qualifying traversal-instance count**: 0
- **Distinct intermediate station count**: 0
- Return payload returns correctly empty intermediate array.

## 7. Performance (EXPLAIN ANALYZE)
Executing the core bounded extraction on `NDLS` $\to$ `HWH`:
- **Planning Time**: ~2.524 ms
- **Execution Time**: ~9.156 ms
- **Major Operators**: Leverages an highly efficient `Hash Join` across filtered bounds utilizing the `ix_train_stops_snapshot_station` index to perfectly isolate bounding $O$ and $D$ intervals ($x < y$). Then deploys a `Nested Loop` scanning only the subset of `train_stop_observations` constrained by $x < stop\_sequence < y$.
- **Index usage**: Exclusively relies on existing primary and snapshot/station B-Tree indices. No sequential scans were performed. Total memory utilized during `Sort` aggregation capped at ~124kB.

## 8. Implementation Feasibility
- Fully implementable natively via PostgreSQL utilizing existing `train_stop_observations` indexing.
- Requires no python-side path string hashing (unlike Phase 45) since `COUNT(DISTINCT)` handles mathematically correct traversal deduplication directly at the aggregation step. No database schema modifications or migrations are required.

## 9. Rejected Candidates & Overlap Reasoning
- **Candidate A: Edge O-D Bounding Persistence (Terminal Dispersion)**
  - *Why useful:* Showcased extreme termini pairings driving traffic through a specific physical edge.
  - *Overlap:* Formally equivalent to Phase 41 (Edge Route Terminal Dispersion) which outputs origin/destination distributions for an edge. Rejected.
- **Candidate B: Train Cyclomatic Index**
  - *Why useful:* Graded trains on non-linear topological looping complexity.
  - *Overlap:* Perfectly subsumed by Phase 26 (Train Topology Loop Analytics) which natively calculates loops and duplicate station visits per-train. Rejected.
- **Candidate C: Station Pair Absolute Articulation Points**
  - *Why useful:* Isolated 100% dependency stations for O-D pairs.
  - *Overlap:* Identical to Phase 22 (Station O-D Bridges) which explicitly yields 100% dependency nodes bounding an O-D pair. Rejected.
- **Candidate D: Train Route Edge Exclusivity Profiling**
  - *Why useful:* Identified monopolistic edge utilization by a specific train.
  - *Overlap:* Fully implemented and addressed in Phase 40 (Route Edge Structural Exclusivity). Rejected.

**END OF DISCOVERY**
*Implementation of this phase is strictly NOT approved yet.*
