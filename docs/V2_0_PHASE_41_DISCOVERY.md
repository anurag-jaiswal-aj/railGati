# V2.0 Phase 41 Discovery: Network Edge Route Terminal Dispersion Analytics

## 1. Objective
Discover and define a new, genuinely distinct historical timetable analytics capability for RailGati (V2.0 Phase 41). The capability must not overlap with Phase 1–40, must rely purely on historical PostgreSQL schedule data without external APIs, and must have rigid dataset-derived semantics.

## 2. Phase 1–40 Overlap Audit
Before selecting the new capability, an explicit audit of existing structurally related metrics was performed:

- **Phase 10 (Network O-D Flow)**: Groups timetable train occurrences by their absolute origin and absolute destination, and measures O-D flow volume for those train route occurrences. It asks: "How many timetable train occurrences have origin O and destination D?"
  - *Phase 41 Distinction*: Phase 41 first conditions on a specific directed adjacent timetable edge A -> B, selects the distinct train identities that traverse that specific edge, and then examines the absolute origin and destination of those selected trains. It asks: "Among trains that traverse this specific edge, how diverse are their absolute timetable origins and destinations?" Therefore, Phase 41 is an edge-conditioned terminal-diversity metric, while Phase 10 is a global O-D flow aggregation that does not condition its aggregation on the traversal of a requested intermediate directed edge.
- **Phase 35 (Station 2-Hop Reachability Expansion)**: Examines reachable stations from a specific station within 2 hops.
- **Phase 36 (Station Transfer-Free Reachability)**: Evaluates global reachability from a single station without transfers.
- **Phase 37 (Train Route Structural Subsumption)**: Determines if a train's entire route is a subset of another train's route.
- **Phase 38 (Train Route Topological Bypass)**: Identifies if a train route bypasses a station on another train's route.
- **Phase 39 (Edge Traversal Dispersion)**: Evaluates immediate 1-hop upstream and downstream adjacency for an edge (converging/bifurcating immediately prior/subsequent stations). It does *not* consider the ultimate terminals of the routes traversing the edge.
- **Phase 40 (Train Route Edge Structural Exclusivity)**: Classifies whether edges are strictly dedicated to a specific train's sequence. It does not quantify terminal diversity for a generic edge.
- **Phase 22 (Station O-D Bridges)**: Finds edges that act as structural bottlenecks for a *given* Origin-Destination pair. It does not take a generic edge and evaluate its global Origin-Destination diversity.
- **Phase 23 (Station Temporal Gaps)**: Analyzes time gaps between consecutive arrivals at a station.
- **Phase 30 (Station Outbound Dominance)**: Analyzes the distribution of outbound edge volumes from a specific station.

The selected metric (Edge Terminal Dispersion) is strictly orthogonal to all existing metrics: it evaluates the macroscopic Origin-Destination diversity of the trains that traverse any specified intermediate edge.

## 3. Candidates Considered

### Candidate A: Network Edge Route Terminal Dispersion Analytics (Selected)
- **Concept**: Given a directed edge A -> B, evaluate all distinct scheduled trains traversing that edge and count the number of *distinct absolute origins* and *distinct absolute destinations* for those trains.
- **Rationale**: Structurally classifies the terminal diversity of trains sharing a specific timetable edge.

### Candidate B: Network Station Triadic Alternation (Rejected)
- **Concept**: Identifying if stations participate heavily in A -> B -> A cycles.
- **Reason for Rejection**: Phase 28 (Topology Loops) already provides mature structural loop and cyclic pattern detection.

### Candidate C: Network Train Route Topological Redundancy (Rejected)
- **Concept**: Finding alternate multi-edge paths between nodes on a single train's route provided by other services.
- **Reason for Rejection**: High overlap with Phase 38 (Train Route Topological Bypass), which already structurally isolates path short-circuits.

### Candidate D: Network Station Structural O-D Reachability (Rejected)
- **Concept**: From station S, how many distinct Termini are reachable globally?
- **Reason for Rejection**: Redundant overlap with Phase 36 (Station Transfer-Free Reachability).

---

## 4. Selected Phase 41 Capability: Network Edge Route Terminal Dispersion Analytics

### 4.1 Exact Semantics & Constraints
The metric is defined exactly as follows:
- Evaluates a specific directed station edge E = (A, B) within the active historical timetable snapshot.
- Let `T(A,B)` be the set of DISTINCT timetable train identities in the active timetable snapshot that contain at least one consecutive stop pair A -> B.
- `traversing_train_count` = `|T(A,B)|`. It must NOT count repeated traversal of the same A -> B edge by the same train identity multiple times. One train identity counts exactly once.
- For each selected train identity in `T(A,B)`:
  - origin = station at minimum stop_sequence
  - destination = station at maximum stop_sequence
- `distinct_origin_count` = number of distinct origin station identities among `T(A,B)`.
- `distinct_destination_count` = number of distinct destination station identities among `T(A,B)`.

### 4.2 Semantic Guardrails
This Phase 41 metric is strictly:
- historical
- timetable-derived
- edge-conditioned
- structural
- based on scheduled train identities

It is explicitly NOT:
- passenger O-D demand
- ticketing demand
- passenger flow
- physical track topology
- infrastructure capacity
- operational routing
- current railway service
- live traffic
- congestion
- reliability
- trunk/branch classification
- service quality

### 4.3 Error Semantics
The API defines deterministic behavior for edge and boundary cases:
- **A. unknown station code**: Standard 404 Not Found (matches existing station verification conventions).
- **B. known stations but no directed A -> B timetable edge**: Standard 404 Edge Not Found (matches existing edge verification conventions).
- **C. valid edge with exactly one distinct traversing train identity**: Validly returns `traversing_train_count = 1`, `distinct_origin_count = 1`, `distinct_destination_count = 1`.
- **D. valid edge with multiple trains sharing the same origin/destination**: Validly returns `traversing_train_count > 1`, but the distinct origin and destination counts will reflect the deduplicated terminal sets.
- **E. valid edge where the same train traverses A -> B multiple times**: The duplicate traversals are deduplicated when defining `T(A,B)`. The train identity contributes exactly 1 to `traversing_train_count` and its origin/destination contribute exactly 1 to the distinct terminal sets.

### 4.4 Real Snapshot 2 Validation
The metric was manually validated against raw Snapshot 2 dataset tables using the exact formulated SQL query.

**SBB (Sahibabad) -> GZB (Ghaziabad)** (Edge with higher terminal diversity)
- traversing_train_count = 143
- distinct_origin_count = 32
- distinct_destination_count = 64

**MSB (Chennai Beach) -> MSF (Chennai Fort)** (Edge with lower terminal diversity)
- traversing_train_count = 132
- distinct_origin_count = 11
- distinct_destination_count = 12

**AAV (Ambivli) -> AGCI (Angadippuram)** (Edge with minimum terminal diversity)
- traversing_train_count = 2
- distinct_origin_count = 1
- distinct_destination_count = 1

### 4.5 API Contract
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

### 4.6 Query Strategy
The conceptual query strategy leverages a fully relational approach using standard Common Table Expressions (CTEs) without looping or array aggregation. It explicitly enforces the distinct train identity rule by using `SELECT DISTINCT` in the initial `edge_trains` CTE.

```sql
WITH edge_trains AS (
    SELECT DISTINCT
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

### 4.7 Performance Measurement (EXPLAIN ANALYZE)
Tested exact proposed query against the SBB -> GZB edge (143 distinct traversing train identities) in Snapshot 2:
- **Planning Time**: 1.929 ms
- **Execution Time**: 14.552 ms
- **Scan Behavior**: The observed plan utilizes an `Index Scan` via `ix_train_stops_snapshot_station` to find the initial edge constraints. It then utilizes `train_stop_observations_pkey` via `Index Only Scan` to locate bounding `min(stop_sequence)` and `max(stop_sequence)` rows.
- **Sequential Scans**: Zero sequential scans were observed in the tested plan.
*(Note: This represents the plan for the tested case and should not be generalized arbitrarily).*

### 4.8 Future Implementation Boundary
This capability requires a single new API route in `api/v1/network.py` and a corresponding service function in `services/network.py`. No database migrations, index adjustments, or dependency additions are necessary.
