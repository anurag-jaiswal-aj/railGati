# Phase 40 Discovery: Network Train Route Edge Structural Exclusivity Analytics

## 1. Candidate Capabilities Explored

During discovery, several structural network capabilities were evaluated:

1. **Network Station-Pair Route Sequence Diversity:** For a given Origin-Destination pair, count the number of structurally distinct intermediate sequences used by trains.
   *Status:* Rejected. It overlaps too heavily with Phase 5 (Corridor Analytics), which already discovers and delineates distinct physical/structural paths between two stations.
2. **Network Edge Structural Dependency (Cut-Edge Vulnerability):** Identifies edges whose removal would structurally disconnect certain station pairs in the timetable.
   *Status:* Rejected. Computing all-pairs reachability components or exact articulation bridges for every edge requires $O(V+E)$ recursive graph traversals or full graph materialization, violating the strict PostgreSQL performance constraints.
3. **Train Route Edge Structural Exclusivity Analytics:** Evaluates a target train's entire route to determine which of its traversed edges are structurally exclusive to its exact service pattern.
   *Status:* Selected.

## 2. Selected Phase 40 Capability
**Network Train Route Edge Structural Exclusivity Analytics**

## 3. Exact Analytical Question
"For a specific target train's route, how many of its scheduled adjacent timetable edges are structurally exclusive to its exact routing pattern?"

An edge is "exclusive" if every single train traversing it shares the exact same full ordered station sequence as the target train. If an edge is traversed by even one train with a different structural sequence, it is considered "shared."

## 4. Why It Is Useful
This metric quantifies the structural uniqueness of a service's footprint. It automatically classifies the nature of a train's routing:
- **Dedicated / Branch-Line Services:** High exclusivity count. These trains operate on segments of the network where no other structurally diverse services run. 
- **Pure Core / Trunk-Line Services:** Zero exclusivity count. Every edge of their route is shared with other diverse overlapping trains. 

## 5. Detailed Distinction from Phases 1–39
- **Phase 7 (Edge Volume):** Merely counts trains on a single edge. Exclusivity evaluates the full structural sequence equality of all traversing trains across a full route.
- **Phase 37 (Train Route Structural Subsumption):** Asks if the target train's *entire route* is subsumed by *another* train's route. Exclusivity asks if the target train has *individual edges* that no structurally diverse train traverses.
- **Phase 38 (Topological Bypasses):** Looks for short-circuits *within* the train's own route. Exclusivity compares the train against all *other* trains overlapping its path.
- **Phase 39 (Edge Traversal Dispersion):** Looks at a single edge and counts immediately preceding/following stations (1-hop footprint). Exclusivity evaluates a train's entire route and enforces full sequence equality for exclusivity.

## 6. Formal Mathematical/Relational Definition
For a target train $T$ traversing a sequence of stations $seq(T) = [S_1, S_2, \ldots, S_k]$ in the active timetable snapshot:
1. Identify all $k-1$ adjacent directed edges $E_i = (S_i, S_{i+1})$.
2. For each edge $E_i$, define the traversing set $R(E_i)$ as all train occurrences traversing $(S_i, S_{i+1})$.
3. An edge $E_i$ is **exclusive** if $\forall T' \in R(E_i), seq(T') = seq(T)$.
4. An edge $E_i$ is **shared** if $\exists T' \in R(E_i)$ such that $seq(T') \neq seq(T)$.
5. Calculate `route_edge_count` = $k-1$.
6. Calculate `exclusive_edge_count` = $| \{ E_i \mid E_i \text{ is exclusive} \} |$.

## 7. Required Data
- `timetable_snapshots` (Active snapshot scoping)
- `trains` (Target train resolution)
- `train_stop_observations` (Sequence extraction and edge traversals)

## 8. SQL/Computation Approach
1. Isolate the target train and its $O(K)$ edges using a CTE.
2. Compute the exact full string-aggregated sequence of the target train `STRING_AGG(station_id ORDER BY stop_sequence)`.
3. Self-join `train_stop_observations` to find all distinct train IDs traversing each target edge.
4. For each distinct traversing train, use a `NOT EXISTS` subquery to check if its `STRING_AGG` sequence differs from the target train's sequence.
5. Aggregate the total edges and the boolean exclusivity flags.

## 9. Duplicate and Repeated-Station Handling
- **Daily Frequencies/Duplicates:** If a route is operated by 7 daily trains with identical stop sequences, the edge remains "exclusive" to that service pattern. Sequence equality handles this perfectly.
- **Repeated Stations:** `STRING_AGG` with precise order mathematically preserves repeated station topologies (e.g., A -> B -> A). 

## 10. Active Snapshot Semantics
All stop observations, target train edges, traversing trains, and sequence aggregations strictly filter on the active timetable snapshot. 

## 11. Edge Cases
- **1-Stop Trains:** Handled naturally (0 edges, 0 exclusive).
- **Non-existent Train:** Follows standard 404 API error semantics.

## 12. Real Snapshot 2 Findings
Executing against Snapshot 2 reveals stark structural service classifications:
- **Train 41053:** 16 edges total. 14 edges are exclusive. (A dedicated branch-line/local service).
- **Train 55759:** 2 edges total. 2 edges are exclusive. (An isolated shuttle).
- **Train 58865:** 20 edges total. 2 edges are exclusive. (A mixed route that branches off a shared trunk).
- **Train 12106:** 132 edges total. 0 edges are exclusive. (A massive trunk-line express where every edge is shared with diverse services).

## 13. Complexity Analysis
The algorithmic complexity is bounded by $O(K \times V_E \times L_{avg})$, where $K$ is the target train route length, $V_E$ is the volume of traversing trains per edge, and $L_{avg}$ is the average sequence length of those traversing trains.

## 14. EXPLAIN ANALYZE Findings
Benchmarked on heavy trunk Train 12106 (132 edges) and local Train 41053 (16 edges):
- **Train 41053 (Short/Branch):** ~18 ms execution.
- **Train 12106 (Heavy/Trunk):** ~479 ms execution.
The query successfully utilizes `ix_train_stops_snapshot_station` to find edge traversals and `train_stop_observations_pkey` for sequence extraction. It requires no full table sequential scans and scales cleanly under 500ms, satisfying API real-time constraints. No new indexes are required.

## 15. Proposed API Endpoint
`GET /api/v1/network/trains/{train_number}/route-edge-exclusivity`

## 16. Proposed Response Semantics
```json
{
    "train_number": "41053",
    "timetable_snapshot_id": 2,
    "route_edge_count": 16,
    "exclusive_edge_count": 14,
    "shared_edge_count": 2,
    "has_exclusive_edges": true
}
```

## 17. Explicit Non-Goals
- This is purely a historical timetable-derived structural metric.
- It does **NOT** represent physical railway tracks (two structurally distinct trains might share the same physical track).
- It does **NOT** measure geographic isolation.
- It does **NOT** represent passenger load, ticketing exclusivity, or operational track ownership.

## 18. Why this deserves Phase 40
It introduces the concept of **Service Footprint Exclusivity**. Rather than measuring if an edge is busy (Phase 7), or if a train is a sub-segment of another (Phase 37), this metric measures how much of a train's topological existence is entirely dedicated to its specific structural pattern. It allows downstream analytical systems to computationally distinguish trunk corridors from structural capillaries.
