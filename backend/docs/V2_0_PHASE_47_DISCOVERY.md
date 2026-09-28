# Phase 47 Discovery

## Status
DISCOVERY — NOT APPROVED

## Selected Capability
**Station Pair Route-Boundary Confinement Analytics**

## Problem / Analytical Question
For an arbitrary sequence of two stations ($O$ and $D$) historically traversed by multiple trains, how does that specific traversal segment topologically align with the absolute sequence boundaries of the trains traversing it? 
Is the $O \to D$ segment the entire recorded historical route for those trains, or is it structurally embedded as a sub-segment within longer transit routes?

## Formal Definition
Given an origin station code $O$, a destination station code $D$, and a historical timetable snapshot.

A valid **traversal instance** is formally defined as the mathematically `DISTINCT` tuple $(train\_id, o\_seq, d\_seq)$ where:
1. Train $train\_id$ stops at $O$ at sequence $o\_seq$
2. Train $train\_id$ stops at $D$ at sequence $d\_seq$
3. $o\_seq < d\_seq$
4. Both observations occur strictly within the same `snapshot_id`.

For each train $train\_id$, its absolute topological boundaries in the dataset are defined as:
- $t_{min} = \min(stop\_sequence)$ for train $train\_id$
- $t_{max} = \max(stop\_sequence)$ for train $train\_id$

Every `DISTINCT` valid traversal instance $(train\_id, o\_seq, d\_seq)$ is strictly classified into exactly one of four topological boundary states:
1. **`STRICTLY_BOUNDED`**: $o\_seq = t_{min}$ AND $d\_seq = t_{max}$. 
   *(The $O \to D$ traversal perfectly bounds the train's entire recorded historical sequence).*
2. **`ORIGIN_BOUNDED`**: $o\_seq = t_{min}$ AND $d\_seq < t_{max}$. 
   *(The train originates exactly at $O$ but terminates strictly after $D$).*
3. **`DESTINATION_BOUNDED`**: $o\_seq > t_{min}$ AND $d\_seq = t_{max}$. 
   *(The train's recorded sequence begins strictly before $O$ but terminates exactly at $D$).*
4. **`UNBOUNDED_EMBEDDED`**: $o\_seq > t_{min}$ AND $d\_seq < t_{max}$. 
   *(The $O \to D$ traversal is entirely embedded within a longer recorded train sequence).*

## Input / Output
**Input**: 
- `origin_station_code` (e.g., "NDLS")
- `destination_station_code` (e.g., "HWH")
- Contextual `snapshot_id`

**Output**:
- Total volume of traversals
- A dictionary mapping each of the 4 topological boundary states to:
  - The count of traversals in that state
  - The ordered array of traversing `train_id`s

## Data Semantics
- Strictly evaluates `train_stop_observations` grouped by `train_id`.
- The evaluation compares local sequence coordinates against the global bounding limits of the train's dataset scope.

## Repeated-Occurrence Semantics
If a train structurally loops or visits $O$ or $D$ multiple times, all valid tuples $(o\_seq, d\_seq)$ where $o\_seq < d\_seq$ are generated as `DISTINCT` independent traversal instances. Each instance tuple is independently classified against the train's absolute $t_{min}$ and $t_{max}$. 

## Snapshot Semantics
All evaluation, including both local sequence indexing and absolute terminal limits ($t_{min}, t_{max}$), is performed strictly scoped to the exact active timetable `snapshot_id`. Boundaries are evaluated solely within that timetable snapshot and are not mixed with station snapshot semantics or leaked across independent timetable datasets.

## Closest Existing Phases
1. **Phase 41 (Edge Route Terminal Dispersion)**: Phase 41 queries a 1-hop *Edge* and aggregates the string names of the ultimate terminal stations to measure geographic dispersion. Phase 47 queries an arbitrary *Station Pair* (N-hop) and evaluates the structural *confinement* states (the boolean boundary intersections) locally at $O$ and $D$.
2. **Phase 44 (Train Route O-D Structural Exclusivity)**: Phase 44 starts with a specific *Train*, identifies its absolute O and D, and counts how many other trains share those exact endpoints. Phase 47 takes a user-supplied *Station Pair* and categorizes traversing trains based on how their absolute boundaries relate to the queried pair.
3. **Phase 46 (Station Pair Intermediate Flow Concentration)**: Phase 46 identifies intermediate topological stations *between* the station pair. Phase 47 evaluates the route boundaries *outside/at* the station pair.

## Candidate Alternatives Rejected
- **Station Pair Terminal Reach**: Rejected. Overlaps strongly with Phase 41, just generalizing from a 1-hop edge to an N-hop pair.
- **Train Route Prefix Divergence**: Rejected. Enforcing an "identical sequence from absolute origin" creates brittle prefix-cohort comparisons that behave inconsistently when real-world datasets drop minor stations.
- **Station Pair Bypassed Stations**: Rejected. Overlaps heavily with Phase 38 (Topological Bypasses) combined with standard pair traversal logic.

## Real Snapshot 2 Validation
The formal query was successfully validated against Snapshot 2.

**`NDLS` $\to$ `HWH`**
- `STRICTLY_BOUNDED`: 6 (Sample trains: 466, 529, 530, 532, 540)
- Total Traversals: 6
*(100% of these services exactly match the absolute boundaries)*

**`LTT` $\to$ `PUNE`**
- `DESTINATION_BOUNDED`: 6
- `ORIGIN_BOUNDED`: 4
- `UNBOUNDED_EMBEDDED`: 17 (Sample trains: 11, 12, 14, 18, 19)
- Total Traversals: 27
*(Dominated by embedded transit segments)*

**`NDLS` $\to$ `CNB`**
- `ORIGIN_BOUNDED`: 35 (Sample trains: 286, 463, 466, 494, 502)
- `STRICTLY_BOUNDED`: 2
- `UNBOUNDED_EMBEDDED`: 1
- Total Traversals: 38
*(Massively dominated by outbound origin-bounded segments)*

## Edge Cases
**`VDR` $\to$ `CDG`** (Unconnected Valid Stations)
- Total Traversals: 0
- Handled gracefully with zeroed/empty classifications.

**`MMCT` $\to$ `NDLS`** (Missing Station Code)
- Total Traversals: 0
- Standard pre-flight validation guarantees a 404 Not Found before analytical processing.

## Performance
An optimized EXPLAIN query utilizing a CTE to pre-filter bounding trains was executed for `LTT` $\to$ `PUNE`.
- **Planning Time**: 0.556 ms
- **Execution Time**: 2.379 ms
- **Major Operators**: CTE Scan, Hash Join, Index Only Scan.
- **Index usage**: Heavy leverage of `ix_stations_code`, `ix_train_stops_snapshot_station`, and `train_stop_observations_pkey`.
- **Sequential Scans**: 0. The pre-filtering ensures bounds are only calculated for trains traversing the segment, eliminating any full-table sweeps.

## API Proposal
`GET /api/v1/network/station-pairs/{origin_station_code}/to/{destination_station_code}/route-boundary-confinement`
Returns the `StationPairRouteBoundaryConfinementResponse` containing total counts and the four classification objects.

## Implementation Considerations
Must utilize a two-pass CTE or pre-filter subquery to evaluate $t_{min}$ and $t_{max}$ exclusively for the `target_traversals` cohort. Computing boundaries for the entire snapshot dynamically induces a heavy Sequential Scan and must be avoided.

## Non-Goals / Explicit Interpretation Limits
- Does NOT infer physical passenger capacity.
- Does NOT infer physical track segments.
- Does NOT claim operational demand.
- Merely models historical sequence indices and boundaries in the structural dataset.

## Discovery Conclusion
The metric robustly classifies network topology boundaries using purely existing historical sequence semantics. It provides an immediate structural distinction between dedicated short-haul and embedded long-haul segments. It runs extremely fast (2-3ms) and avoids overlap with existing pair-based or edge-based analytics.
