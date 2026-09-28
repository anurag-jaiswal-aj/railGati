# Phase 48 Discovery

## Status
DISCOVERY — NOT APPROVED

## Selected Capability
Network Train Route Terminal Incidence Analytics

## Analytical Question
"For a given train's route, what proportion of its distinct topological stops serve as an absolute 'Origin' or absolute 'Destination' (a Terminal) for at least one train in the active network snapshot?"

## Candidate Alternatives Rejected
- **Train Route Subsumption Coverage:** Identifies how many other trains' routes are exact subsets of the target train's route. Rejected because it is merely a trivial directional swap of Phase 37 (Train Route Structural Subsumption), testing if `t2` is subsumed by `t1` instead of if `t1` is subsumed by `t2`.
- **Station Pair Network-Wide Directional Symmetry:** Calculates the ratio of all direct trains traveling from O to D versus D to O. Rejected because it is too closely related to Phase 31 (Paired-Service Edge Symmetry) and Phase 32 (Neighborhood Directional Symmetry), differing only by expanding the topological distance from 1 hop to N hops.
- **Station Pair Maximal Intermediate Hub Alignment:** Finds the intermediate station with the highest network-wide global flow. Rejected because Phase 46 already isolates the intermediate hub with the highest O->D concentration, and this is a trivial variant substituting global flow for local flow.

## Formal Definition
Given a network snapshot $S$ and a target train $T$, define the global set of **Network Terminals** $N_T$ as the set of all stations that correspond to the absolute minimum or absolute maximum `stop_sequence` for ANY train $T_i$ operating in snapshot $S$.

For the target train $T$, let its ordered sequence of stops be $O_T = [(s_1, k_1), (s_2, k_2), \dots, (s_n, k_n)]$ where $s_i$ is the station ID and $k_i$ is the stop sequence.

The **Train Route Terminal Incidence** is calculated as:
1. `total_stops`: The total number of valid sequence observations $n$ for $T$.
2. `terminal_incident_stops`: The count of observations $(s_i, k_i) \in O_T$ where $s_i \in N_T$.
3. `incidence_ratio`: `terminal_incident_stops / total_stops`.

Empty behaviour: If train $T$ is not found in $S$, the metric is undefined (returning a 404 error). If $T$ has 0 stops in $S$, returns 0s.

## Traversal / Occurrence Semantics
- **Identity:** The analytical unit is the `(train_id, stop_sequence)` tuple (an occurrence). 
- **Station Semantics:** A single physical station acts as a Network Terminal if it is the terminal for *any* train, including self-terminating trains.
- **Repeated Occurrences:** If a cyclic train visits the same terminal station $X$ at two different sequence indices $k_1$ and $k_2$, both stops are counted independently towards `terminal_incident_stops`. This preserves structural occurrence counting.

## Snapshot Semantics
The definition of a "Network Terminal" is strictly scoped to the active `snapshot_id`. A station is a terminal only if it caps a train's sequence within the exact snapshot evaluated.

## Closest Existing Phases
1. **Phase 41 (Edge Route Terminal Dispersion)**
   - **What Phase 41 does:** For a specific *Edge* (Station Pair), identifies the distinct Terminals of all trains passing through that physical track.
   - **What Phase 48 does:** For a specific *Train*, calculates the proportion of its topological stops that act as Terminals network-wide.
   - **Distinction:** Phase 41 aggregates global endpoints based on localized edge intersection. Phase 48 profiles an entire train route's structural behavior based on its incidence with globally defined terminals. They operate on mathematically orthogonal entity-groupings.

2. **Phase 21 (Train Route Profile)**
   - **What Phase 21 does:** Profiles a train's physical properties (distance, duration, average speed).
   - **What Phase 48 does:** Profiles a train's topological properties.
   - **Distinction:** Phase 21 is kinematic and temporal; Phase 48 is purely topological.

3. **Phase 16 (Station Service Similarity)**
   - **What Phase 16 does:** Compares the set of trains visiting station A with station B.
   - **What Phase 48 does:** Evaluates a single train against a global boolean property (Terminal Status) of stations.
   - **Distinction:** Phase 16 operates on train-set intersection. Phase 48 operates on station-set membership.

## Real Snapshot 2 Validation
Queries evaluated on historical Snapshot 2 using actual IDs:
- **Train 12951 (Large Trunk Route):**
  - `total_stops`: 202
  - `terminal_incident_stops`: 31
  - `incidence_ratio`: 0.153
- **Train 12952 (Reverse Large Trunk Route):**
  - `total_stops`: 202
  - `terminal_incident_stops`: 31
  - `incidence_ratio`: 0.153
- **Train 04853 (Cyclic Route, DNA -> MTD):**
  - `total_stops`: 12
  - `terminal_incident_stops`: 4
  - `incidence_ratio`: 0.333
- **Train 00000 (Undefined):**
  - Result: 404 Not Found.

## Edge Cases
- **Cyclic Routes:** A train that loops back to a terminal station will have both sequence indices counted as incident stops.
- **Self-Terminals:** The origin and destination of the target train $T$ itself automatically qualify as Network Terminals. Thus, `terminal_incident_stops` is strictly $\ge 2$ for any valid train with length $\ge 2$.
- **Missing Train:** Defined as a 404 Not Found error.
- **Empty Snapshot:** Defined as a 404 Not Found error.

## Performance
Execution plan against Snapshot 2 for Train 12951:
- **Planning Time:** ~1.3 ms
- **Execution Time:** ~86.8 ms
- **Major Operators:** Hash Join, HashAggregate, Parallel Seq Scan, CTE Scan.
- **Indexes Utilized:** `train_stop_observations_pkey`, `ix_trains_number`.
- **Behavior:** The query efficiently extracts the global bounds (`MIN`/`MAX` stop sequence) across the network using a parallel scan and hash aggregation, creating an in-memory hash table of Network Terminals, which is then probed by the target train's 202 stops.

## API Proposal
Endpoint: `GET /api/v1/network/trains/{train_number}/terminal-incidence`

Response Structure:
```json
{
  "train_number": "string",
  "total_stops": 0,
  "terminal_incident_stops": 0,
  "incidence_ratio": 0.0
}
```

## Implementation Considerations
- The `global_terminals` CTE must compute `MIN` and `MAX` by `train_id` independently from the target train.
- Due to the size of the timetable, ensuring PostgreSQL opts for a HashAggregate over the `train_stop_observations` table is critical for keeping execution under 100ms. Avoid correlated subqueries in the global bound calculation.

## Non-Goals / Interpretation Limits
- Does NOT infer passenger demand for major hubs.
- Does NOT define a "terminal" via physical station size, platform count, or real-world classification, but strictly via historical timetable schedule bounds.
- Does NOT infer that the target train actually terminates at intermediate incident stations.

## Discovery Conclusion
The Train Route Terminal Incidence metric provides a deterministic, novel structural classification of train routes using existing timetable data. It avoids trivial duplication of existing Phases and maintains stable execution characteristics.
