# RailGati V2.0 — Phase 61 Discovery

## Objective
Identify and formally define a mathematically novel historical timetable analytics capability that occupies genuinely unexplored analytical space, strictly adheres to the ₹0 budget and historical data constraints, and cannot be derived from existing Phase 1–60 endpoints.

## Phases 45–60 Capability / Overlap Map

To identify unoccupied analytical space, we first map the existing capabilities:

- **Phase 45 (Route Diversity):** Analyzes Station Pair paths; captures diverse operational corridors; does not capture cross-traffic.
- **Phase 46 (Intermediate Flow Concentration):** Analyzes Station Pairs; captures hub utilization between O-D.
- **Phase 47 (Route-Boundary Confinement):** Analyzes Station Pairs; captures topological containment within O-D bounds.
- **Phase 49 (Route Extension):** Analyzes Station Pairs; captures trains extending beyond the O-D pair.
- **Phase 50 (Temporal Order Inversions):** Analyzes Station Pairs; captures sequence inversions (A->B and B->A).
- **Phase 51 (Intermediate Halt Stratification):** Analyzes Station Pairs; captures train type distributions at intermediate stops.
- **Phase 52 (Published Return-Service Adherence):** Analyzes Station Pairs; captures symmetry of return trains.
- **Phase 53 (Simultaneous Presence):** Analyzes Stations; captures temporal overlap of trains.
- **Phase 54 (Stop Temporal Skew):** Analyzes Stations; captures arrival/departure time skew.
- **Phase 55 (Sequence Subgraph Density):** Analyzes Trains; captures structural density internal to a train's route.
- **Phase 56 (Topological Transition Continuity):** Analyzes 3-Station Sequences; captures preservation of exact A->S->B sequences.
- **Phase 57 (Disjoint Sub-Path Reconvergences):** Analyzes Trains; captures multiple trains diverging and reconverging (|V(U) ∩ V(T)| ≥ 2 with disjoint sub-paths).
- **Phase 58 (Topological Degree Extremes):** Analyzes Trains; captures max/min station degrees along a route.
- **Phase 59 (Neighborhood Subsumption):** Analyzes Station/Neighbor Pairs; captures subset relationships of 1-hop neighborhoods.
- **Phase 60 (Strict Local Bridge Pairs):** Analyzes Station Neighborhoods; captures neighbor pairs lacking alternative 2-hop paths.

## Candidate Generation and Derivability Analysis

### Candidate A: Train Route Topological Dilation (Detour Coefficient)
- **Concept:** For a train sequence, measure the ratio of its actual sequence length versus the shortest structural graph distance between its origin and destination.
- **Entity:** Train.
- **Derivability Test: YES.** A client can fetch the train's profile to get its route length, call the existing `find_network_paths` (Phase 45+) to get the shortest topological depth, and divide the two. No additional raw timetable data is needed.
- **Status:** REJECTED.

### Candidate B: Station Outbound Hub Domination
- **Concept:** For a station $S$, what percentage of its total outbound traffic is directed to a specific neighbor $N$?
- **Entity:** Station.
- **Derivability Test: YES.** A client can call the network edges endpoint to retrieve all outbound edge volumes for $S$, then locally sum and calculate the percentage distribution.
- **Status:** REJECTED.

### Candidate C: Station Neighborhood Sequential Triadic Bridging
- **Concept:** The proportion of structural triangles $\{S, A, B\}$ around station $S$ that are continuously bridged by a single train sequence $A \to S \to B$.
- **Entity:** Station.
- **Derivability Test: NO.** (Requires a combinatorial number of requests to Phase 56).
- **Status:** REJECTED. (Violates Rule 5: It is essentially an aggregated wrapper around Phase 56 Transition Continuity and Phase 33 Triadic Closure, adding no fundamentally new mathematical dimension).

### Candidate D: Train Route Single-Station Intersection Analytics
- **Concept:** For a target train sequence, evaluate all other trains to find those that share exactly one distinct station identity with the target train, and aggregate these counts at each station on the target train's route.
- **Entity:** Train.
- **Phase 15/43 Derivability Audit:**
  - **Phase 15 (Train Similarity):** Exposes `overlap_station_count` (which equals 1 for qualifying trains). However, Phase 15 permanently discards the spatial identity (`station_code`) of the overlap, making it impossible to reconstruct the per-station intersection distribution along the target route.
  - **Phase 43 (Max Shared Sub-Route):** Identifies contiguous overlaps and exposes `start_station_code` / `end_station_code`, but truncates responses to the longest overlaps (typically >1). Trains sharing exactly one station are intrinsically filtered out or buried below practical pagination limits. Furthermore, a shared contiguous length of 1 does not mathematically guarantee the absolute intersection size $|V(T) \cap V(U)| = 1$.
  - **Phase 57 (Disjoint Reconvergences):** Explicitly filters for $|V(T) \cap V(U)| \ge 2$, meaning single-station intersections are entirely excluded.
- **Derivability Test: NOT DERIVABLE.** The existing endpoint responses mathematically expose the existence of single-station overlaps (via Phase 15), but they permanently destroy the station-level spatial distribution required for this capability.
- **Status:** SELECTED.

---

## Selected Phase 61 Capability: Train Route Single-Station Intersection Analytics

### Formal Mathematical Definition
Let $G$ be the timetable graph for the active snapshot.
For a target train $T$ and a candidate train $U$:

Let $V(T)$ = distinct station identities visited by $T$
Let $V(U)$ = distinct station identities visited by $U$

The structural intersection is:
$$ I(T,U) = V(T) \cap V(U) $$

Train $U$ qualifies iff:
$$ |I(T,U)| = 1 $$

The result aggregates the count of qualifying candidate trains $U$ for each station identity in $V(T)$.

### Candidate Scope and Occurrence Semantics
- **Candidate Scope:** Candidate $U \neq T$.
- **Snapshot Semantics:** Both $T$ and $U$ must exist in the same active timetable snapshot.
- **Distinct Identities:** Operations are strictly on sets of unique station identities.
- **Duplicate/Cyclic Handling:** Repeated station visits by either $T$ or $U$ mathematically collapse to a single distinct station identity in $V(T)$ and $V(U)$. Cyclic routes therefore do not generate duplicate intersection counts.
- **Ignored Dimensions:** Direction, visit order, and timing are completely ignored.
- **Return Trains:** `return_train_number` relationships are ignored; all distinct train identities are evaluated symmetrically.

### Proposed Endpoint
`GET /api/v1/network/trains/{train_number}/single-station-intersections`

### Proposed Response Schema
```json
{
  "train_number": "12345",
  "timetable_snapshot_id": 2,
  "total_intersecting_trains": 14,
  "sequence_stops": [
    {
      "station_code": "STN_A",
      "stop_sequence": 1,
      "single_station_intersection_count": 2
    },
    {
      "station_code": "STN_B",
      "stop_sequence": 2,
      "single_station_intersection_count": 12
    }
  ]
}
```

### SQL / Query Strategy
The mathematical definition translates to an elegant, highly performant set-based SQL execution:
1. **CTE 1 (`target_train_stations`):** Select all unique `station_id`s for target train $T$.
2. **CTE 2 (`intersecting_trains`):** Select all `(train_id, station_id)` pairs for any train $U \neq T$ that stops at a station in `target_train_stations`.
3. **CTE 3 (`qualifying_trains`):** Group `intersecting_trains` by `train_id`. Filter using `HAVING COUNT(DISTINCT station_id) = 1`. Select the `train_id` and the `MIN(station_id)` (the single intersection point).
4. **Main Query:** Select the stop sequence of $T$, join the stations table, and `LEFT JOIN` a grouped count of `qualifying_trains` on `station_id`. Order by stop sequence.

### Complexity and Performance
- **Computational Complexity:** $O(|V_{snapshot}|)$ localized. The query utilizes single-pass Hash Joins and Hash Aggregations.
- **Performance Considerations:** Expected to execute in under 50ms. No $N+1$ loops. The database executes the logic purely via `ix_train_stops_snapshot_station` and `train_stop_observations_pkey` indexes.

### Real-Data Validation Plan
- Will validate against a known train on Snapshot 2.
- Ensure a stop at a major topological hub displays a high single-station intersection count, while a stop on a linear sub-branch displays 0.

### Explicit Non-Claims
- This metric represents the number/proportion of other train route identities sharing exactly one station identity with the target route.
- It makes NO claims about temporal feasibility of transfers (trains may arrive hours apart).
- It makes NO claims about physical track infrastructure or grade separation.
- It makes NO claims about passenger demand, traffic, or boarding patterns.

### Exact Relationship to Phases 1–60
- **Phase 15 (Train Similarity):** Calculates $|V(T) \cap V(U)|$ but discards the spatial identity of the intersection.
- **Phase 43 (Max Shared Sub-Route):** Retains spatial identities but explicitly biases/truncates toward maximum contiguous sequences, discarding or hiding single-station overlaps.
- **Phase 57 (Disjoint Reconvergences):** Captures trains where $|V(U) \cap V(T)| \ge 2$, acting as the mathematical complement for higher-order shared paths.

### Implementation Acceptance Criteria
- Exact adherence to $|I(T,U)| = 1$.
- No $N+1$ database queries.
- Must be executed entirely in SQL.
- Must preserve Phase 40 legacy behavior.

*Note: Implementation of this capability is NOT part of this discovery phase.*
