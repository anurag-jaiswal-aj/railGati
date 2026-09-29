# V2.0 Phase 58 Discovery

## 1. Current Phase 1–57 Analytical Inventory
A rigorous audit of the existing analytical capabilities (Phases 1–57) reveals a comprehensive coverage of:
- **Global Topologies:** Network hub centrality, corridors, O-D bridges, transit articulation, topology loops.
- **Route Structures:** Train route profiles, structural subsumption, topological bypasses, maximum shared sub-routes, route exclusivity, intermediate flow concentration, boundary confinement, sequence subgraph density.
- **Route Comparisons:** Train service similarity, station service similarity, co-traversal affinity.
- **Micro-Transitions:** Topological transition continuity (Phases 56), disjoint sub-path reconvergences (Phase 57).
- **Temporal Metrics:** Bunching, gaps, dwell skew, relative slowness, temporal order inversions.

**Identified Gap:**
While absolute global degrees (Phase 7) and aggregate route subgraph density (Phase 55) are measured, there is no metric that analyzes the **discrete local-extrema analysis of station degree along the ordered train sequence**. Rail networks are not topologically flat; trains navigate a structural "terrain" of high-degree hubs and low-degree spokes. Identifying the strict local maxima and minima of this terrain relative to a specific route reveals profound insights about the structural role of a train's intermediate stops.

## 2. Train Sequence Topological Degree Extremes (RECOMMENDED)
**Endpoint:** `GET /api/v1/network/trains/{train_number}/topological-degree-extremes`

**Definition:** 
Evaluates the sequential progression of global topological station degrees along a target train's ordered stop sequence to identify strict local extrema.

1. **Global Degree Formulation:** Let $D(S)$ be the global undirected topological degree of station $S$. This is precisely defined as the number of distinct adjacent station identities connected to station $S$ by the existing timetable network within the same snapshot. Directional timetable edges ($A \to B$ and $B \to A$) are normalized into an undirected station-neighbor relation ($A \leftrightarrow B$) before aggregation.
2. **Sequential Mapping:** For a target train with an ordered stop sequence $S_1, S_2, \ldots, S_n$, map the global degrees: $D_1, \ldots, D_n$.
3. **Strict Classification:** For interior occurrences $i$ (where $1 < i < n$):
   - **LOCAL_MAXIMUM:** $D_i > D_{i-1}$ AND $D_i > D_{i+1}$. The train climbs to a local structural peak and immediately descends.
   - **LOCAL_MINIMUM:** $D_i < D_{i-1}$ AND $D_i < D_{i+1}$. The train dips into a structural valley between two higher-connected stations.
   - **TRANSIT:** Any other condition. This strictly includes equal-degree plateaus and monotonic sequences.
   - **TERMINAL:** Applied exclusively to the first ($S_1$) and last ($S_n$) stops of the sequence.

### Explicit Plateau Behavior
The classification relies on strict inequalities. Plateaus are classified entirely as TRANSIT.
- `2 -> 5 -> 5 -> 2`: Both `5` occurrences are classified as `TRANSIT`.
- `2 -> 5 -> 5 -> 5 -> 2`: All three `5` occurrences are classified as `TRANSIT`.
The metric does not attempt to designate one plateau occurrence as a peak.

### Terminals Clarification
Terminals are not eligible for local-extrema classification because they do not have both a preceding and succeeding route neighbor.
- **1 stop route:** The single occurrence is a `TERMINAL`.
- **2 stop route:** Both occurrences are `TERMINAL`.
- **>= 3 stop route:** The first and last occurrences are `TERMINAL`; all interior occurrences are independently evaluated as `LOCAL_MAXIMUM`, `LOCAL_MINIMUM`, or `TRANSIT`.

### Occurrence vs Station Identity
The metric distinguishes station identity (used for global degree) from stop occurrence (the chronological visit within a train's journey).
- **Example A:** A train travels `A -> B -> C -> B -> D`. The two `B` visits are separate stop occurrences. They share the same global degree $D(B)$ but are evaluated independently against their respective sequence neighbors (`A/C` and `C/D`).
- **Example B (Cyclic):** A train travels `A -> B -> A -> C`. The occurrence identity is rigorously preserved using the composite identity `(snapshot_id, train_id, stop_sequence)`. The occurrences are not collapsed before applying neighbor evaluation (`LAG`/`LEAD`).

## 3. Rejected Alternatives
- **Train Sequence Temporal Halt Isolation:** Risked overlap with "Scheduled Stop Temporal Skew" (Phase 54) and "Temporal Bunching" (Phase 37).
- **Train Sequence Degree Assortativity:** While novel, Pearson correlation is mathematically brittle (failing on zero variance) and less intuitive than discrete topological mapping.

## 4. Novelty / Overlap Matrix

| Phase | Metric | Distinction |
|-------|--------|-------------|
| **Phase 7** | Network Hub Centrality | Measures network-level station degree. Our Phase 58 metric projects this station-level global degree onto the ordered occurrences of a specific train. |
| **Phase 16** | Station Service Similarity | Measures set-based Jaccard similarity between station schedules, unconnected to ordered route topologies. |
| **Phase 46** | Intermediate Flow Concentration | Identifies aggregated hub presence for stations along an O-D path. Phase 58 analyzes sequential derivatives of degree for a single train. |
| **Phase 55** | Sequence Subgraph Density | Analyzes the aggregate density of edges between all nodes in a route. Phase 58 evaluates a 1-dimensional discrete profile of local degree transitions. |
| **Phase 56** | Topological Transition Continuity | Measures the fractional continuation of outbound paths on specific edges. Phase 58 evaluates undirected global station degrees. |
| **Phase 57** | Disjoint Sub-Path Reconvergences | Identifies alternative trains navigating disjoint segments. Phase 58 maps the degree terrain of one target train. |

The Phase 58 metric is not merely a returned-field aggregation of an existing endpoint; it computes an entirely new relational structure representing the discrete sequence profile of topological extremas for a specific train entity.

## 5. Non-Claims
This metric explicitly **DOES NOT** measure:
- Graph-theoretic articulation points (cut vertices).
- Passenger demand, ticketing, or commercial performance.
- Station importance in terms of passenger volume.
- Operational criticality or scheduling reliability.
- Physical railway infrastructure criticality.
- Congestion or actual train traffic execution.

It is strictly a historical timetable-derived topological degree profile.

## 6. Implementation Constraints
The analytical calculation **MUST** be set-based and performed by the database in a single primary query execution, with no application-level N+1 query pattern.

**Required Set-Based Strategy:**
- **CTE 1:** Construct the snapshot-scoped undirected station-neighbor relation from `train_stop_observations`.
- **CTE 2:** Compute distinct global station degree `D(S)` for the snapshot.
- **CTE 3:** Obtain the target train's ordered stop occurrences from `train_stop_observations` and join the global degrees computed in CTE 2.
- **CTE 4:** Apply `LAG()` and `LEAD()` window functions partitioned by the target train and ordered by `stop_sequence`.
- **Final Projection:** Apply the strict classification `CASE` logic to resolve `LOCAL_MAXIMUM`, `LOCAL_MINIMUM`, `TRANSIT`, or `TERMINAL`.

This query strategy is universally compatible with PostgreSQL and SQLite, fulfilling all performance constraints.

## 7. Concrete Example
**Global Undirected Degrees (Snapshot context):**
`X` (deg 1), `A` (deg 2), `B` (deg 8), `C` (deg 3), `D` (deg 10), `Y` (deg 1)

**Target Train Sequence:** `X -> A -> B -> C -> D -> Y`
- `X` (Seq 1): `TERMINAL` (deg 1)
- `A` (Seq 2): `TRANSIT` (deg 2, preceding 1, succeeding 8)
- `B` (Seq 3): `LOCAL_MAXIMUM` (deg 8, preceding 2, succeeding 3)
- `C` (Seq 4): `LOCAL_MINIMUM` (deg 3, preceding 8, succeeding 10)
- `D` (Seq 5): `LOCAL_MAXIMUM` (deg 10, preceding 3, succeeding 1)
- `Y` (Seq 6): `TERMINAL` (deg 1)

**Interpretation:**
`B` and `D` are local topological degree peaks along this train's route.

**Output Payload Fields:**
- `train_number` (string)
- `timetable_snapshot_id` (integer)
- `total_stops` (integer)
- `local_maxima_count`: 2
- `local_minima_count`: 1
- `transit_count`: 1
- `sequence_classification` (array of detailed objects with `stop_sequence`, `station_code`, `global_degree`, and `classification_type`)

## 8. Final Verdict

Recommendation:
PROCEED TO IMPLEMENTATION
