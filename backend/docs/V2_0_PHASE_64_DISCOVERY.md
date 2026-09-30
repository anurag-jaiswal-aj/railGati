# RailGati V2.0 Phase 64 Discovery
## Train Route Topological Perimeter Expansion

### 1. Objective & Candidate Selection
The goal of Phase 64 is to introduce a genuinely novel, non-derivative structural analytics capability to the RailGati V2.0 network API.

**Selected Candidate:** Train Route Topological Perimeter Expansion.
This metric elevates the concept of an undirected structural neighborhood boundary to an entire functional sub-graph (a train route). It calculates the set of distinct station identities structurally adjacent to the train route, explicitly excluding the stations the train visits.

### 2. Formal Mathematical Definition
For a target historical train $T$:
- Let $R(T)$ be the set of distinct station identities visited by target train $T$ in the active timetable snapshot.
- Let structural adjacency be strictly **UNDIRECTED**: an active `NetworkEdge` $A \to B$ or $B \to A$ establishes adjacency between $A$ and $B$.

Define the perimeter $P(T)$ as the set of distinct station identities outside $R(T)$ that are structurally adjacent to at least one station in $R(T)$:
$$P(T) = \{ X \mid X \notin R(T), \text{ and there exists } S \in R(T) \text{ such that an active network edge connects } S \text{ and } X \text{ in either direction} \}$$

**Explicit Computational Rules:**
- Route station identities in $R(T)$ are strictly deduplicated.
- Repeated/cyclic visits by train $T$ do not multiply or inflate $R(T)$.
- An external station adjacent to multiple distinct route stations appears exactly once in $P(T)$.
- Reciprocal network edges (e.g., $S \to X$ and $X \to S$) still produce exactly one perimeter station $X$.
- `return_train_number` is irrelevant.
- Temporal schedule timing is irrelevant.
- Train direction is irrelevant to the perimeter once undirected adjacency is established.
- All relationships are exclusively bounded to the active timetable snapshot.

### 3. API Contract
**Endpoint:**
`GET /api/v1/network/trains/{train_number}/topological-perimeter-expansion`

**Output Schema:**
```json
{
  "target_train_number": "string",
  "route_station_count": 0,
  "perimeter_station_count": 0,
  "perimeter_expansion_ratio": 0.0,
  "perimeter_stations": [
    {
      "station_code": "string",
      "station_name": "string"
    }
  ]
}
```
Where `perimeter_expansion_ratio` = `perimeter_station_count` / `route_station_count`.
The ratio denominator is the number of DISTINCT station identities in the target train's route.

### 4. Worked Example
**Target route ($T$):**
A $\to$ B $\to$ C $\to$ D

**Network undirected adjacency additionally contains:**
A—X
B—X
B—Y
C—Z
D—Y

**Evaluation:**
- Route stations $R(T)$ = {A, B, C, D}
- Adjacent external stations = {X (from A), X (from B), Y (from B), Z (from C), Y (from D)}
- Perimeter $P(T)$ = {X, Y, Z}

*Note that X is counted exactly once even though both A and B connect to it, and Y is counted exactly once even though both B and D connect to it.*

**Results:**
- `route_station_count` = 4
- `perimeter_station_count` = 3
- `perimeter_expansion_ratio` = 3 / 4 = 0.75

### 5. Explicit Edge Cases Evaluated
- **Unknown train:** Returns an HTTP 404 error.
- **Train absent from active snapshot:** Returns an HTTP 404 error.
- **One-stop train:** $R(T)$ = 1. $P(T)$ is simply the undirected neighborhood of that single station.
- **Two-stop train:** $R(T)$ = 2. $P(T)$ is the combined undirected neighborhood excluding the two stops.
- **Route with repeated station identities:** The station identity is counted exactly once in $R(T)$.
- **Isolated route station:** Included in $R(T)$ safely; contributes no external edges if disconnected.
- **Zero perimeter stations:** If the train visits an entirely isolated closed-loop component with zero external structural edges, $P(T) = \emptyset$, `perimeter_station_count` = 0, and ratio = 0.0.
- **Multiple route stations sharing the same external perimeter station:** Deduplicated rigorously in $P(T)$.
- **Reciprocal edges:** Deduplicated rigorously.

### 6. Overlap Audit vs. Existing Capabilities
The metric is genuinely novel and not a trivial projection of existing endpoints.

- **Phase 35 (2-Hop Expansion):** Phase 35 is *station-scoped* and exposes local 2-hop outbound expansion. It does not define the union of the 1-hop structural neighborhoods surrounding an entire train route. Phase 64 is *train-route-scoped*, constructs the complete distinct station footprint $R(T)$, computes the union of external structural neighbors of that entire footprint, excludes the footprint itself, and deduplicates the external boundary globally.
- **Phase 39 (Edge Traversal Dispersion):** Evaluates the fractional edge-routing volumes, not a node-set topological boundary.
- **Phase 55 (Sequence Subgraph Density):** Evaluates the density of active edges *strictly internal* to the sequence footprint. Phase 64 strictly defines the *external* structural neighborhood boundary of the entire footprint.
- **Phase 58 (Topological Degree Extremes):** Evaluates local degree extrema points sequentially along a train route. It does not compute the global boundary union.
- **Phase 60 (Strict Local Bridges):** Evaluates a strict local bridge predicate around a single station.
- **Phase 62 (Structural Shortest-Path Divergence):** Evaluates endpoint shortest-path divergence distances.
- **Phase 63 (Station Junction Through-Service):** Evaluates train-through-service pair connectivity routing at a specific junction.

### 7. Explicit Non-Semantics
This metric does NOT measure:
- passenger demand
- passenger catchment
- transfer availability
- transfer feasibility
- schedule connectivity
- connection quality
- service frequency
- reliability
- physical/geographic proximity
- operational importance
- congestion
- network centrality

It is strictly defined as a HISTORICAL TIMETABLE TOPOLOGY structural boundary measurement.

### 8. PostgreSQL Implementation Strategy
The algorithm will utilize a PostgreSQL-native set-based query without N+1 application loops.

The query will:
1. Identify the target train's distinct station identities in the active snapshot into a CTE.
2. Identify `NetworkEdge` endpoints adjacent to any route station (joining where the route station is either `from_station_id` or `to_station_id`).
3. Treat both `from_station_id` and `to_station_id` as valid undirected adjacent endpoints.
4. Filter out any adjacent endpoints that are already present in the target route footprint.
5. Apply `DISTINCT` to the resulting external perimeter station identities.
6. Join with `StationObservation` for canonical names.
7. Remain strictly bounded to the target train footprint rather than performing full table scans over unrelated data.
