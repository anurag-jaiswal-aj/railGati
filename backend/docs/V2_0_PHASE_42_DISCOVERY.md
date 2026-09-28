# V2.0 Phase 42 Discovery

## 1. Objective
Discover and define exactly ONE strong, non-trivial Network Analytics capability for RailGati V2.0 Phase 42 that adds genuinely new analytical value without duplicating or trivially varying any Phase 1–41 capability. This phase is restricted strictly to discovery; no implementation is authorized.

## 2. Existing Phase 1–41 Capability Inventory
The RailGati network analytics suite currently provides comprehensive primitives across 41 phases, with particular focus on structural relationships. Relevant recent structural endpoints include:
- **Phase 22**: Station O-D Bridges
- **Phase 25**: Paired-Service Temporal Symmetry
- **Phase 31**: Paired-Service Edge Symmetry
- **Phase 34**: Station Transit Articulation (In -> Out routing through a station)
- **Phase 36**: Station Transfer-Free Reachability (Total count of reachable stations)
- **Phase 37**: Train Route Structural Subsumption (Is Route A a strict sub-sequence of Route B?)
- **Phase 38**: Train Route Topological Bypass (Does a specific train bypass segments served locally by others?)
- **Phase 39**: Edge Traversal Dispersion (Immediate predecessor/successor divergence around an edge A->B)
- **Phase 40**: Train Route Edge Structural Exclusivity
- **Phase 41**: Edge Route Terminal Dispersion (Ultimate origin/destination of trains on A->B)

## 3. Detailed Overlap Audit
Any new capability analyzing edge relationships must actively avoid reproducing:
- **Immediate Adjacency Constraints**: Phase 34 and Phase 39 already map the *immediate* inbound/outbound structure around stations and edges.
- **Terminal Constraints**: Phase 16, 22, and 41 already map the ultimate structural bounds (Origins/Destinations).
- **Train Similarity Constraints**: Phase 21 already measures full route similarity (Jaccard) between pairs of specific trains.

## 4. Candidate Analytics Considered
During discovery, multiple analytical candidates were explored using Snapshot 2 data:
1. **Network Station Route Co-occurrence Affinity**: Identifying which stations are most frequently co-visited by trains serving a target station (regardless of order).
2. **Network Edge Route Topological Alternation**: For a given station pair (A, B), counting how many trains traverse them consecutively vs with intermediate stops.
3. **Network Edge Route Co-Traversal Affinity Analytics**: For a given directed edge A->B, identifying which *other* directed edges in the entire network are most frequently co-traversed by the exact same set of train identities.

## 5. Rejected Candidates and Reasons
- **Network Station Route Co-occurrence Affinity**: Rejected as it acts as a trivial variant of Phase 20 (Station Similarity) which already computes station-to-station overlap using Jaccard similarity.
- **Network Edge Route Topological Alternation**: While structurally interesting, this is essentially Phase 38 (Train Route Topological Bypass) computed from the inverse perspective (evaluating the edge instead of evaluating the train).
- **Network Edge Route Terminal Affinity**: Rejected as it is merely Phase 41 (Terminal Dispersion) presented with explicit OD-pair frequencies instead of distinct counts, mirroring the logic of Phase 22.

## 6. Selected Phase 42 Capability
**Network Edge Route Co-Traversal Affinity Analytics**

## 7. Analytical Question
*For a requested directed edge A -> B, what other specific directed edges in the network have the highest co-traversal frequency by the exact same set of train identities?*

## 8. Formal Definition
- **Input Entity**: A directed edge `E_target = A -> B` (where A and B are adjacent in at least one active train route).
- **T(E_target)**: The set of distinct train identities traversing `A -> B` consecutively in the active timetable snapshot.
- For all other directed consecutive edges `C -> D` (where `C != A` or `D != B`), let `T(C->D)` be the set of distinct train identities traversing `C -> D` consecutively.
- **co_traversed_train_count(C->D)**: The cardinality of the intersection `|T(E_target) ∩ T(C->D)|`.
- **Ordering**: The output must be deterministically sorted by `co_traversed_train_count` DESC, then `C.code` ASC, then `D.code` ASC.

## 9. Data and Schema Mapping
This capability exclusively utilizes existing RailGati relational structures:
- `Station` (`code`, `id`)
- `TrainStopObservation` (`snapshot_id`, `train_id`, `station_id`, `stop_sequence`)

## 10. Snapshot Semantics
- The metric must strictly isolate queries to the globally resolved **active timetable snapshot**.
- Station resolution must use the **active station snapshot** to map requested codes to IDs.

## 11. Deduplication / Repeated-Occurrence Semantics
- If a Train Identity traverses `A -> B` multiple times (e.g., a looping topology), it is counted exactly **once** in `T(E_target)`.
- If that same Train Identity traverses `C -> D` multiple times, it contributes exactly **once** to the intersection `co_traversed_train_count(C->D)`.
- The sets `T(E_target)` and `T(C->D)` are strict sets of distinct Train IDs.

## 12. Proposed API Contract
**Endpoint:**
`GET /api/v1/network/edges/{from_station_code}/{to_station_code}/route-co-traversal-affinity`

**Path Parameters:**
- `from_station_code`: String
- `to_station_code`: String

**Query Parameters:**
- `limit`: Integer (default=50, max=100) - To bound the response size.

**Response Schema:**
```json
{
  "from_station_code": "SBB",
  "to_station_code": "GZB",
  "traversing_train_count": 143,
  "co_traversals": [
    {
      "co_traversed_from": "ANVT",
      "co_traversed_to": "CNJ",
      "co_traversed_train_count": 83
    },
    ...
  ]
}
```

## 13. Error and Boundary Semantics
- `404 Not Found` if either station does not exist in the active station snapshot.
- `404 Not Found` if `traversing_train_count == 0` (the edge A->B does not exist consecutively in the active timetable).
- The target edge `A->B` MUST be excluded from the `co_traversals` list.

## 14. Semantic Guardrails
- **IS**: A purely structural measurement of route segment contingency based on the static historical timetable.
- **IS NOT**: A measure of passenger demand, transfer volumes, track capacity, or real-time train movements. It measures timetable coupling (e.g. if A->B closes, C->D loses exactly N trains).

## 15. Real Snapshot 2 Validation
The prototype SQL was executed against the actual Snapshot 2 database.

**High-Volume Example:** `SBB -> GZB` (Sahibabad to Ghaziabad)
- `traversing_train_count`: 143
- Top Co-Traversals:
  1. `ANVT -> CNJ`: 83 trains
  2. `CNJ -> SBB`: 77 trains
  3. `ANVR -> ANVT`: 67 trains
  4. `AJR -> DKDE`: 64 trains
  5. `ALJN -> DAQ`: 64 trains
*(Note: Identifies both the immediate predecessor `CNJ->SBB` and entirely distant, highly correlated segments like `AJR->DKDE`)*

**Ordinary Example:** `MSB -> MSF` (Chennai Beach to Chennai Fort)
- `traversing_train_count`: 132
- Top Co-Traversals:
  1. `MSF -> MPKT`: 125 trains
  2. `GWYR -> KTPM`: 70 trains
  3. `INDR -> TYMR`: 70 trains
  4. `KTBR -> INDR`: 70 trains
  5. `KTPM -> KTBR`: 70 trains
*(Note: Correctly identifies the MRTS line branch contingency down to Velachery via stations like `KTPM`)*

**Small/Boundary Example:** `AAV -> AGCI`
- `traversing_train_count`: 2
- Top Co-Traversals:
  1. `AGCI -> SVL`: 2 trains
  2. `ANND -> SNA`: 2 trains
  3. `BAJ -> OD`: 2 trains

## 16. SQL / Relational Query Strategy
```sql
WITH target_trains AS (
    SELECT DISTINCT t1.train_id
    FROM train_stop_observations t1
    JOIN train_stop_observations t2 
      ON t1.train_id = t2.train_id AND t1.snapshot_id = t2.snapshot_id
    WHERE t1.snapshot_id = :snapshot_id
      AND t1.station_id = :from_id
      AND t2.station_id = :to_id
      AND t2.stop_sequence = t1.stop_sequence + 1
),
other_edges AS (
    SELECT 
        t1.station_id as o,
        t2.station_id as d,
        COUNT(DISTINCT t1.train_id) as shared_trains
    FROM train_stop_observations t1
    JOIN train_stop_observations t2 
      ON t1.train_id = t2.train_id AND t1.snapshot_id = t2.snapshot_id
    JOIN target_trains tt ON tt.train_id = t1.train_id
    WHERE t1.snapshot_id = :snapshot_id
      AND t2.stop_sequence = t1.stop_sequence + 1
      AND NOT (t1.station_id = :from_id AND t2.station_id = :to_id)
    GROUP BY t1.station_id, t2.station_id
)
SELECT s1.code as o, s2.code as d, oe.shared_trains
FROM other_edges oe
JOIN stations s1 ON s1.id = oe.o
JOIN stations s2 ON s2.id = oe.d
ORDER BY oe.shared_trains DESC, s1.code ASC, s2.code ASC
LIMIT :limit;
```

## 17. EXPLAIN / Performance Findings
EXPLAIN ANALYZE was executed for `SBB -> GZB`:
- **Planning Time**: 1.921 ms
- **Execution Time**: 36.940 ms
- **Path**: Nested Loop over `target_trains` using the primary key to fetch consecutive stops, aggregating via `GroupAggregate`, joining to `stations` for codes, and sorting via `top-N heapsort`.

## 18. Existing Index Usage
The query relies heavily on existing indexes:
- `ix_train_stops_snapshot_station`: Resolves `target_trains` rapidly.
- `train_stop_observations_pkey`: (`snapshot_id`, `train_id`, `stop_sequence`) Used repeatedly in Nested Loops to verify `seq + 1` conditions without sequential scans.
- `stations_pkey`: Used to look up station codes efficiently during the final projection.

## 19. Scalability / Complexity Considerations
- **Space**: Output is bounded by the `LIMIT` clause.
- **Time**: The query isolates only the subset of trains traversing `A->B`. The maximum number of trains on any single edge in the snapshot is ~150. Scanning all stops for 150 trains requires a bounded number of primary key lookups, guaranteeing sub-100ms response times globally.
- **Risk**: None. No new indexes are required.

## 20. Future Implementation Test Strategy
- **Service Tests**: Isolate with a mock snapshot. Create 3 trains traversing `A->B`. Have 2 of them traverse `C->D`, 1 traverse `X->Y`, and 0 traverse `E->F`. Verify deterministic ordering and correct intersections.
- **API Tests**: Verify 404 mapping for missing stations/edges. Assert JSON schema structure matches the contract.
- **Repeated Edge Test**: Ensure a train visiting `A->B`, entering a loop, and visiting `A->B` again only counts as 1.

## 21. Implementation Boundary
Phase 42 is strictly bounded to the Edge Route Co-Traversal Affinity endpoint. It MUST NOT interfere with the unrelated Phase 40 failure `test_api_edge_exclusivity_success` or modify any existing Phase 1-41 logic.

## 22. Final Discovery Decision
**Network Edge Route Co-Traversal Affinity Analytics** is selected for V2.0 Phase 42. It provides genuinely novel insights into the structural contingency and bottleneck dependencies of network segments without duplicating any prior traversal or terminal metrics.
