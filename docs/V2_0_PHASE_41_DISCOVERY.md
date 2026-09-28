# V2.0 Phase 41 Discovery: Network Edge Route Terminal Dispersion Analytics

## 1. Objective
Discover and define a new, genuinely distinct historical timetable analytics capability for RailGati (V2.0 Phase 41). The capability must not overlap with Phase 1–40, must rely purely on historical PostgreSQL schedule data without external APIs, and must have rigid dataset-derived semantics.

## 2. Phase 1–40 Overlap Audit
Before selecting the new capability, an explicit audit of existing structurally related metrics was performed:
- **Phase 39 (Edge Traversal Dispersion)**: Evaluates immediate 1-hop upstream and downstream adjacency for an edge (converging/bifurcating immediately prior/subsequent stations). It does *not* consider the ultimate terminals of the routes traversing the edge.
- **Phase 40 (Train Route Edge Structural Exclusivity)**: Classifies whether edges are strictly dedicated to a specific train's sequence. It does not quantify terminal diversity for a generic edge.
- **Phase 8 (Network O-D Bridges)**: Finds edges that act as structural bottlenecks for a *given* Origin-Destination pair. It does not take a generic edge and evaluate its global Origin-Destination diversity.
- **Phase 4 (Network Flows)**: Counts total scheduled train volumes strictly between requested O-D pairs, independent of intermediate path traversal.
- **Phase 3 (Network Termini)**: Identifies stations that act as terminals anywhere in the graph, without linking them to specific edge traversals.

The selected metric (Edge Terminal Dispersion) is strictly orthogonal to all existing metrics: it evaluates the macroscopic Origin-Destination diversity of any specified intermediate edge, distinguishing "global mixing trunks" from "dedicated local corridors."

## 3. Candidates Considered

### Candidate A: Network Edge Route Terminal Dispersion Analytics (Selected)
- **Concept**: Given a directed edge A -> B, evaluate all scheduled trains traversing that edge and count the number of *distinct absolute origins* and *distinct absolute destinations* for those trains.
- **Rationale**: Structurally classifies the macro-role of a timetable edge (e.g., heavily shared long-distance trunk vs. isolated high-volume shuttle corridor).

### Candidate B: Network Station Triadic Alternation (Rejected)
- **Concept**: Identifying if stations participate heavily in A -> B -> A cycles.
- **Reason for Rejection**: Phase 28 (Topology Loops) already provides mature structural loop and cyclic pattern detection.

### Candidate C: Network Train Route Topological Redundancy (Rejected)
- **Concept**: Finding alternate multi-edge paths between nodes on a single train's route provided by other services.
- **Reason for Rejection**: High overlap with Phase 38 (Topological Bypasses), which already structurally isolates path short-circuits.

### Candidate D: Network Station Structural O-D Reachability (Rejected)
- **Concept**: From station S, how many distinct Termini are reachable globally?
- **Reason for Rejection**: Redundant overlap with Phase 31 (Transfer-Free Reach) and Phase 35 (Station Similarity).

---

## 4. Selected Phase 41 Capability: Network Edge Route Terminal Dispersion Analytics

### 4.1 Exact Semantics & Constraints
- Evaluates a specific directed station edge E = (A, B) within the active historical timetable snapshot.
- Identifies the set `T` of all canonical train occurrences traversing A -> B consecutively.
- For each train `t` in `T`, determines its absolute Origin (the station with `min(stop_sequence)`) and absolute Destination (the station with `max(stop_sequence)`).
- Calculates the count of distinct Origin stations and distinct Destination stations represented by `T`.
- A valid edge returns exact traversal and terminal diversity counts.
- An edge not traversed by any train gracefully returns a 404 Edge Not Found.

### 4.2 Semantic Guardrails
- **DO NOT** claim this represents physical passenger ticketing demand, passenger origin-destination matrices, or actual human travel patterns.
- **DO NOT** imply live operations or real-time track capacity.
- **DO NOT** conflate this with immediate upstream/downstream adjacency (Phase 39). This strictly identifies absolute endpoints of scheduled route graphs.

### 4.3 Real Snapshot 2 Validation
The metric was manually validated against raw Snapshot 2 dataset tables.

**Edge: SBB (Sahibabad) -> GZB (Ghaziabad)** [Major Arterial Trunk]
- **Traversing Trains**: 143
- **Distinct Origins**: 32
- **Distinct Destinations**: 64
- *Validation*: Structurally represents a massive global mixing trunk. Despite only 143 trains, they scatter to 64 disparate destinations.

**Edge: MSB (Chennai Beach) -> MSF (Chennai Fort)** [Local High-Volume Corridor]
- **Traversing Trains**: 132
- **Distinct Origins**: 11
- **Distinct Destinations**: 12
- *Validation*: Structurally represents a tightly constrained local corridor. Volume is massive (132 trains), but they only shuttle between 11/12 specific terminals.

**Edge: AAV (Ambivli) -> AGCI (Angadippuram)** [Edge-Case / Anomaly]
- **Traversing Trains**: 2
- **Distinct Origins**: 1
- **Distinct Destinations**: 1
- *Validation*: A dedicated structural relationship with absolutely no dispersion.

### 4.4 API Contract
**Method/Endpoint:**
`GET /api/v1/network/edges/{from_station_code}/{to_station_code}/route-terminal-dispersion`

**Path Parameters:**
- `from_station_code` (string)
- `to_station_code` (string)

**Response:**
```json
{
  "from_station_code": "SBB",
  "to_station_code": "GZB",
  "timetable_snapshot_id": 2,
  "traversing_train_count": 143,
  "distinct_origin_count": 32,
  "distinct_destination_count": 64
}
```

### 4.5 Query Strategy
```sql
WITH edge_trains AS (
    SELECT 
        t1.train_id
    FROM train_stop_observations t1
    JOIN train_stop_observations t2 
      ON t1.train_id = t2.train_id
     AND t1.snapshot_id = t2.snapshot_id
     AND t2.stop_sequence = t1.stop_sequence + 1
    JOIN stations s1 ON s1.id = t1.station_id
    JOIN stations s2 ON s2.id = t2.station_id
    WHERE t1.snapshot_id = :snapshot_id
      AND s1.code = :from_code
      AND s2.code = :to_code
),
train_bounds AS (
    SELECT 
        tso.train_id,
        MIN(tso.stop_sequence) as min_seq,
        MAX(tso.stop_sequence) as max_seq
    FROM train_stop_observations tso
    JOIN edge_trains et ON tso.train_id = et.train_id
    WHERE tso.snapshot_id = :snapshot_id
    GROUP BY tso.train_id
),
train_terminals AS (
    SELECT 
        tb.train_id,
        orig_tso.station_id as origin_id,
        dest_tso.station_id as dest_id
    FROM train_bounds tb
    JOIN train_stop_observations orig_tso 
      ON orig_tso.train_id = tb.train_id 
     AND orig_tso.stop_sequence = tb.min_seq
     AND orig_tso.snapshot_id = :snapshot_id
    JOIN train_stop_observations dest_tso 
      ON dest_tso.train_id = tb.train_id 
     AND dest_tso.stop_sequence = tb.max_seq
     AND dest_tso.snapshot_id = :snapshot_id
)
SELECT 
    COUNT(train_id) as traversing_train_count,
    COUNT(DISTINCT origin_id) as distinct_origin_count,
    COUNT(DISTINCT dest_id) as distinct_destination_count
FROM train_terminals;
```

### 4.6 Performance Measurement (EXPLAIN ANALYZE)
Tested against the heavily loaded SBB -> GZB edge (143 traversing trains):
- **Planning Time**: ~1.975 ms
- **Execution Time**: ~18.384 ms
- **Scan Behavior**: Employs `Index Scan` utilizing `ix_train_stops_snapshot_station` to find the initial edge constraints rapidly. It utilizes `train_stop_observations_pkey` (Snapshot ID, Train ID, Stop Sequence) perfectly to locate `min(stop_sequence)` and `max(stop_sequence)` bounding rows instantaneously for all 143 traversing trains. There are zero sequential scans, ensuring robust scalability regardless of global snapshot size.

### 4.7 Edge Cases
- Unknown `from_code` or `to_code`: standard 404 Not Found.
- Edge exists logically but not traversed consecutively in the active snapshot: standard 404 Edge Not Found.
- Start or end of train (where A is Origin or B is Destination): Safe; minimum/maximum sequence boundary inclusive.

### 4.8 Future Implementation Boundary
This capability requires a single new API route in `api/v1/network.py` and a corresponding service function in `services/network.py`. No database migrations, index adjustments, or dependency additions are necessary.
