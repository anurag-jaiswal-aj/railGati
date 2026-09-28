# Phase 48 Discovery

## Status
DISCOVERY — NOT APPROVED

## Selected Capability
Network Train Route Terminal Incidence Analytics

## Analytical Question
"For a given train's route, what proportion of its distinct topological stop occurrences intersect with a station identity that acts as an absolute 'Origin' or absolute 'Destination' (a Terminal) for at least one train in the active network snapshot?"

## Candidate Alternatives Rejected
- **Train Route Subsumption Coverage:** Identifies how many other trains' routes are exact subsets of the target train's route. Rejected because it is merely a trivial directional swap of Phase 37 (Train Route Structural Subsumption), testing if `t2` is subsumed by `t1` instead of if `t1` is subsumed by `t2`.
- **Station Pair Network-Wide Directional Symmetry:** Calculates the ratio of all direct trains traveling from O to D versus D to O. Rejected because it is too closely related to Phase 31 (Paired-Service Edge Symmetry) and Phase 32 (Neighborhood Directional Symmetry), differing only by expanding the topological distance from 1 hop to N hops.
- **Station Pair Maximal Intermediate Hub Alignment:** Finds the intermediate station with the highest network-wide global flow. Rejected because Phase 46 already isolates the intermediate hub with the highest O->D concentration, and this is a trivial variant substituting global flow for local flow.

## Formal Definition
Given a network snapshot $S$ and a target train $T$, define the global set of **Network Terminals** $N_T$ as the set of all unique station identities that correspond to the absolute minimum or absolute maximum `stop_sequence` for ANY train $T_i$ operating in snapshot $S$.

For the target train $T$, let its ordered sequence of stop occurrences be $O_T = [(s_1, k_1), (s_2, k_2), \dots, (s_n, k_n)]$ where $s_i$ is the station ID and $k_i$ is the stop sequence.

The **Train Route Terminal Incidence** calculates:
1. `route_stop_occurrence_count`: The total number of valid sequence observations $n$ for $T$.
2. `distinct_route_station_count`: The distinct number of unique station identities $s_i$ across all $O_T$.
3. `terminal_occurrence_count`: The count of observations $(s_i, k_i) \in O_T$ where $s_i \in N_T$.
4. `distinct_terminal_station_count`: The distinct number of unique station identities $s_i$ across all occurrences where $s_i \in N_T$.
5. `incidence_ratio`: `terminal_occurrence_count / route_stop_occurrence_count`.

## Traversal / Occurrence Semantics
- **Identity:** The analytical unit is the `(train_id, stop_sequence)` tuple (an occurrence). 
- **Station Semantics:** A single station identity acts as a Network Terminal if it serves as the terminal sequence boundary for *any* train, including self-terminating trains.
- **Repeated Occurrences:** If a cyclic train visits the same terminal station $X$ at two different sequence indices $k_1$ and $k_2$, both stops are counted independently towards `terminal_occurrence_count`. This preserves the structural topology of the route, as the physical train touches a terminal state twice during its journey. The `distinct_terminal_station_count` explicitly tracks the unique station dimension to disambiguate loops.

## Snapshot Semantics
The definition of a "Network Terminal" is strictly scoped to the active `snapshot_id`. A station is a terminal only if it caps a train's occurrence sequence within the exact snapshot evaluated.

## Closest Existing Phases
1. **Phase 41 (Edge Route Terminal Dispersion)**
   - **What Phase 41 mathematically measures:** edge-conditioned terminal diversity.
   - **What Phase 48 mathematically measures:** train-route incidence with the network-wide set of station identities that occur as timetable origin or destination positions for at least one train occurrence in the active snapshot.
   - **Distinction:** Phase 41 groups all traffic that shares an edge to find where it came from. Phase 48 profiles the structural behavior of a specific train route by assessing its topological intersection with global network terminals. Phase 48 cannot be trivially derived from Phase 41 because Phase 41 discards the train identities and intermediate topology to focus purely on the endpoints of trains sharing an edge. They evaluate completely orthogonal entities against the "Terminal" property.

2. **Phase 21 (Train Route Profile)**
   - **What Phase 21 mathematically measures:** Profiles a train's timetable-derived kinematic profile (distance, duration, average speed).
   - **What Phase 48 mathematically measures:** Profiles a train's topological structural incidence.
   - **Distinction:** Phase 21 evaluates scalar physical properties; Phase 48 evaluates boolean network-graph properties.

3. **Phase 30 (Station Outbound Dominance)**
   - **What Phase 30 mathematically measures:** The fraction of a station's outbound occurrences going to its most popular adjacent edge.
   - **What Phase 48 mathematically measures:** The incidence of a train's route with terminal stations.
   - **Distinction:** Completely separate domains (Station-to-Edge flow versus Train-to-Station global property).

## Real Snapshot 2 Validation
Queries evaluated on historical Snapshot 2 using actual IDs:
- **Train 12951 (Large Trunk Route):**
  - `route_stop_occurrence_count`: 202
  - `distinct_route_station_count`: 202
  - `terminal_occurrence_count`: 31
  - `distinct_terminal_station_count`: 31
  - `incidence_ratio`: 0.153
- **Train 12952 (Reverse Large Trunk Route):**
  - `route_stop_occurrence_count`: 202
  - `distinct_route_station_count`: 202
  - `terminal_occurrence_count`: 31
  - `distinct_terminal_station_count`: 31
  - `incidence_ratio`: 0.153
- **Train 04853 (Cyclic Route, DNA -> MTD):**
  - `route_stop_occurrence_count`: 12
  - `distinct_route_station_count`: 6
  - `terminal_occurrence_count`: 4
  - `distinct_terminal_station_count`: 2
  - `incidence_ratio`: 0.333
  - *Explanation of repeated occurrences:* The cyclic route visits only 6 unique stations across 12 stops. It hits 2 distinct terminal stations, but passes through them a combined 4 times.
- **Train 12001 (Short Route, NDLS -> DDN):**
  - `route_stop_occurrence_count`: 87
  - `distinct_route_station_count`: 87
  - `terminal_occurrence_count`: 13
  - `distinct_terminal_station_count`: 13
  - `incidence_ratio`: 0.149
- **Train 99999 (Missing):**
  - Result: 404 Not Found.

## Edge Cases
- **Cyclic Routes:** Both occurrences are strictly counted in `terminal_occurrence_count`, accurately reflecting the structural topology of the cyclic route interacting with a terminal.
- **Self-Terminals:** A valid multi-stop train occurrence has a minimum `stop_sequence` position and a maximum `stop_sequence` position. The station identities at those positions belong to the network-terminal set because the target train itself contributes those extrema. Thus, structurally, `terminal_occurrence_count` $\ge 2$. (Empirically, in Snapshot 2, there are no valid trains with $< 2$ stops to violate this bound. However, `distinct_terminal_station_count` may be 1 for a purely degenerate circular route starting/ending at the exact same station identity).
- **Missing Train:** Defined as a 404 Not Found error.
- **Empty Snapshot:** Defined as a 404 Not Found error.

## Performance
Execution plan against Snapshot 2 for Train 12951:
- **Planning Time:** 1.792 ms
- **Execution Time:** 138.895 ms
- **Major Operators:** Aggregate (Hashed), Hash Join, Sort, CTE Scan.
- **Relevant Indexes:** `train_stop_observations_pkey`, `ix_trains_number`.
- **Sequential Scans:** The global terminal set is computed across the active timetable snapshot, and PostgreSQL selected a Parallel Seq Scan for the global bounds computation in the measured plan. This is an observed execution-plan choice, not a claim of optimality. It strictly avoids catastrophic correlated subqueries, maintaining performance.

## API Proposal
Endpoint: `GET /api/v1/network/trains/{train_number}/terminal-incidence`

Response Structure:
```json
{
  "train_number": "string",
  "route_stop_occurrence_count": 0,
  "distinct_route_station_count": 0,
  "terminal_occurrence_count": 0,
  "distinct_terminal_station_count": 0,
  "incidence_ratio": 0.0
}
```
*Note: Empty routes and missing trains return 404. Output is deterministic.*

## Implementation Considerations
- The `global_terminals` CTE must compute `MIN` and `MAX` by `train_id` independently from the target train.
- Due to the size of the timetable, ensuring PostgreSQL opts for a HashAggregate over the `train_stop_observations` table is critical.

## Non-Goals / Interpretation Limits
- Does NOT infer passenger demand for major hubs.
- Does NOT define a "terminal" via physical station size, platform count, or real-world classification, but strictly via historical timetable schedule bounds.
- Does NOT infer that the target train actually terminates at intermediate incident stations.
- Does NOT infer physical railway infrastructure topology, operational constraints, or live railway state.

## Discovery Conclusion
The Train Route Terminal Incidence metric provides a deterministic, novel structural classification of train routes using existing timetable data. It avoids duplication of existing phases like Phase 41 by profiling an orthogonal entity (train vs edge) and maintains stable execution.
