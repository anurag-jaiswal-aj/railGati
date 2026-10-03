# ADR-001: Network Topology and Graph Analytics

## Context
During the V2.0 and V2.2 discovery and implementation phases, several graph algorithms were introduced to evaluate the topological connectivity of the historical train schedule data. A clear distinction was needed between strict passenger journey planning (V1.3) and structural/topological analysis (V2.x). This document preserves the durable architectural, product, and algorithmic constraints established during those phases.

## Decisions

### 1. Separation of Concerns: Topology vs. Passenger Itineraries (V2.2 vs V1.3)
- **Problem**: Mixing topology with itinerary planning creates confusing user expectations.
- **Decision**: V2.2 features measure pure topological reachability over `RailwayNetworkEdge`, whereas V1.3 measures 0-transfer passenger reachability using exact `TrainStopObservation` timing.
- **Semantics/Constraints**:
  - A "network hop" (V2) traverses a single historical network edge between adjacent stations. It does NOT imply a single passenger transfer or continuous service.
  - V2 features must explicitly exclude exact travel times, durations, availability, delays, and current operational substitutions. 
  - V2 UI features must carry historical/topological disclaimers.

### 2. Algorithmic Complexity and Precomputation for Max-Flow
- **Problem**: Computing topological edge connectivity between arbitrary station pairs (Bridge Bipartition Size).
- **Decision**: Rely on per-request execution of the Edmonds-Karp Max-Flow algorithm rather than blocking precomputation (e.g., Gomory-Hu tree).
- **Semantics/Constraints**:
  - A Gomory-Hu precomputation would require ~95 seconds of blocking work.
  - Edmonds-Karp is $O(V \cdot E^2)$, which is sufficiently fast (10-40ms) due to the sparse, low-connectivity nature of the `RailwayNetworkEdge` graph topology.
  - All max-flow execution must happen dynamically per HTTP request.

### 3. Historical Snapshot Isolation
- **Problem**: Railway schedules evolve. Combining data from different eras creates invalid graph topologies.
- **Decision**: All V2 topological algorithms must explicitly restrict execution to a single `timetable_snapshot_id`.
- **Semantics/Constraints**:
  - Network edges and train observations must be filtered strictly by `timetable_snapshot_id`. Graph traversals may never cross snapshot boundaries.

### 4. Recursive Traversal Safety
- **Problem**: Bounded reachability exploration risks infinite loops in cyclic network topologies.
- **Decision**: Prevent cycles in recursive CTE implementations explicitly.
- **Semantics/Constraints**:
  - Traversal tracks the visited path array (`p.visited_ids || e.to_station_id`) and explicitly filters subsequent edges (`NOT (e.to_station_id = ANY(p.visited_ids))`).
  - Strict maximum bounds (e.g. `max_hops = 5`) must be enforced at the API layer.
