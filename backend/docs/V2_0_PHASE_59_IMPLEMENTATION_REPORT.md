# V2.0 Phase 59 Implementation Report

## Implementation Summary
Phase 59 adds a new analytical capability to identify strict hierarchical topological dependencies at the station level: **Station Neighborhood Topological Subsumption**. The implementation calculates whether a station's immediate geographic (timetable) reachability is entirely encompassed and strictly superseded by one of its immediate neighbors.

## Endpoint Details
- **Path:** `GET /api/v1/network/stations/{station_code}/neighborhood-subsumption`
- **Method:** `GET`
- **Response Schema:** `StationNeighborhoodTopologicalSubsumptionResponse`
  - `station_code` (str): Target station code.
  - `timetable_snapshot_id` (int): ID of the active snapshot evaluated.
  - `total_neighbors` (int): Count of distinct adjacent neighbors.
  - `subsuming_neighbors` (list): Array of `StationNeighborhoodSubsumingNeighbor` objects.
    - `station_code` (str): Neighbor that strictly subsumes the target.
    - `neighbor_degree` (int): The global degree of the subsuming neighbor.

## Exact Mathematical Semantics
For the active snapshot, let $N(S)$ be the distinct adjacent neighbors of the target station $S$.
A neighbor $H \in N(S)$ strictly subsumes $S$ iff the reduced neighborhood of $S$ is a strictly proper subset of the reduced neighborhood of $H$.

Mathematically:
$N(S) \setminus \{H\} \subset N(H) \setminus \{S\}$

This requires exactly two conditions to hold:
1. $N(S) \setminus \{H\} \subseteq N(H) \setminus \{S\}$ (No distinct neighbor of $S$ is missing from $H$)
2. $N(H) \setminus \{S\} \setminus N(S) \neq \emptyset$ ($H$ has at least one distinct neighbor not present in $S$'s neighborhood)

## Edge Cases and Behaviors Handled
- **Leaf Behavior:** A simple linear segment $A - B$ evaluates to neither strictly subsuming the other because neither has an additional neighbor.
- **Equal Neighborhoods:** Two stations with identically shared reduced neighborhoods ($N(A)=\{B,C\}$, $N(B)=\{A,C\}$) do NOT subsume each other.
- **Repeated Edge occurrences:** The analysis deduplicates multiple train sequences passing through the same adjacent stations, enforcing a station-identity based graph instead of a traversal-frequency graph.
- **Empty / No Subsumers:** Returns `subsuming_neighbors: []` appropriately without erroring.
- **Snapshot Isolation:** Only evaluates occurrences belonging to the strictly active snapshot.

## SQL / Query Strategy
The logic is performed in a single, set-based database execution using an optimized CTE structure bound strictly to the target station:
1. `target_neighbors` & `target_neighbors_clean`: Derives the distinct immediate neighbors of the target $S$, excluding $S$ itself.
2. `candidate_edges`: Scans consecutive `train_stop_observations` exclusively restricted to edges originating or terminating at nodes within `target_neighbors`. This avoids materializing the snapshot-wide graph.
3. `candidate_neighbors` & `candidate_neighbors_clean`: Normalizes and deduplicates the candidate edges into an undirected graph restricted to candidates $H \in N(S)$.
4. `neighbor_degrees`: Calculates the full degree of each neighbor $H$ strictly within the required subset.
5. The final SELECT statement joins the candidate nodes and enforces the strict subsumption constraints using `NOT EXISTS` to verify no node of $S$ is missing, and an `EXISTS` to verify $H$ has an additional node.
6. The query results are cleanly converted to the output model without requiring application-level graph traversals or N+1 lookups.

## Real-Data Validation
Executed against Snapshot 2 static timetable data.
**Found Target Station:** `XX-BECE`
- **Total Neighbors:** 2
- **Subsuming Neighbors:** 
  - `BEC` (degree 3)
  - `CNA` (degree 6)

**Example No-Subsumer Stations:** `NDLS`, `DLI`, `HWH`
All processed successfully with `total_neighbors` populated but yielding empty lists for `subsuming_neighbors`. 

## Performance Validation
- A single SQL execution strictly traverses the neighborhood depth without N+1 queries.
- Initial unoptimized queries were materializing the entire snapshot graph (1-2.5 seconds, sequential scans).
- The final optimized query pushes the `:target_id` down into indexed joins, avoiding the snapshot-wide scan. `EXPLAIN ANALYZE` confirms it relies heavily on `ix_train_stops_snapshot_station` index scans.
- **Measured execution times:** ~0.009 seconds for low-degree stations (`XX-BECE`) and ~0.041 seconds for high-degree stations (`NDLS`), operating with peak efficiency and dynamic boundary constraints.
- Python memory remains trivial since we fetch only the final `subsuming_neighbors`.

## Non-Claims / Limitations
This capability strictly measures historical timetable topology set-containment. It **does not claim or measure**:
- Physical track infrastructure ownership.
- Passenger distance, travel time, dependency, or accessibility.
- Operational priority or true movement tracking.
- Service reliability, congestion, or true hub dependency.
