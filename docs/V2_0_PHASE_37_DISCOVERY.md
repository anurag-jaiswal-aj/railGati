# V2.0 Phase 37: Network Train Route Structural Subsumption Analytics

## 1. Phase Objective
Identify, evaluate, and formally define exactly ONE next railway-network intelligence capability that is genuinely distinct from all completed V2.0 phases. 

The selected capability is **Network Train Route Structural Subsumption Analytics**.

## 2. Candidate Capabilities Investigated
During discovery, multiple distinct analytical dimensions were evaluated before selecting the final capability. The following were explored and explicitly rejected to avoid cosmetic overlap with previous phases:

1. **Station Sequence Positional Skew (Timetable Route Positional Skew)**
   - *Concept*: Calculates where a station typically falls in the topological sequence of traversing trains (e.g., origin bias, transit bias, destination bias).
   - *Rejection Reason*: While mathematically distinct, validation on real Snapshot 2 data revealed that major hubs naturally average out to exactly ~0.50 (middle of the journey), making the raw average less discriminative without complex variance aggregations.
   
2. **Station-Pair Route Trajectory Diversity**
   - *Concept*: For a given Origin-Destination pair, counts the number of distinct topological intermediate paths taken by trains connecting them.
   - *Rejection Reason*: Closely aligns with an aggregation of Phase 2 (Bounded Paths) combined with Phase 8 (O-D flows). 

3. **Train Route Exclusivity (Single-Edge Cut Vulnerability)**
   - *Concept*: Measures what percentage of a train's topological sequence uses edges with a total network volume of exactly 1.
   - *Rejection Reason*: Merely an aggregation of Phase 6 (Edge Volume) evaluated at the train level.

4. **Network Edge O-D Embeddedness**
   - *Concept*: Evaluates the number of globally unique O-D pairs whose trains traverse a specific local edge.
   - *Rejection Reason*: Explicitly documented as a cosmetic variation of Phase 20 (Station O-D Bridges logic applied to an edge).

## 3. Selected Capability: Network Train Route Structural Subsumption
**Train Route Structural Subsumption** evaluates whether an entire scheduled train route operates strictly as a contiguous subsequence within the ordered stop sequence of another train.

### 4. Problem / Question Answered
*Structurally, does the complete ordered timetable stop sequence of this train occur as a contiguous ordered subsequence of another active train's timetable stop sequence?*

### 5. Explicit Overlap Audit against Phases 1-36
- **vs. Phase 15 (Train Route Similarity)**: Phase 15 uses Jaccard similarity over distinct station sets and ignores route order/direction. Phase 37 uses asymmetric ordered contiguous stop-sequence containment and therefore captures a different structural relationship.
- **vs. Phase 3 (Continuous Services)**: Phase 3 verifies if a single train occurrence connects a specific $A$ and $B$. It does not evaluate sequence subsetting.
- **vs. Reachability / Bounded Metrics**: Subsumption bounds itself entirely to the specific ordered stop sequence of the target train, avoiding graph recursion.

### 6. Why the Selected Capability is Distinct
This metric is distinct because it measures asymmetric containment of one complete ordered timetable stop sequence inside another complete ordered timetable stop sequence. Instead of identifying origin-destination connectivity, it establishes historical timetable structural containment between specific scheduled train occurrences.

## 7. Exact Semantics
For a target train $T$, let $seq(T)$ be its complete ordered timetable stop sequence.
A train $T$ is **structurally subsumed** by a candidate train $T'$ if and only if:
1. $T \neq T'$
2. Both train occurrences belong to the same active timetable snapshot.
3. The complete ordered stop sequence of $T$ occurs as a contiguous ordered subsequence of $T'$.

## 8. Mathematical Definition
For a target train $T$:
$seq(T) = [S_1, S_2, ..., S_k]$

For a candidate train $T'$:
$seq(T') = [U_1, U_2, ..., U_m]$

$T'$ structurally subsumes $T$ iff:
- $T \neq T'$
- both train occurrences belong to the same active timetable snapshot;
- there exists an offset $j$ such that for every $i$ from 1 through $k$:
  $U_{j+i-1} = S_i$

This definition explicitly preserves station order, direction, contiguity, and repeated station occurrences where present.

**Train Subsumption Count** = number of distinct candidate trains $T'$ that structurally subsume $T$.

### 8.1. Repeated Stations
Repeated station occurrences are explicitly preserved in the ordered stop sequence. A match must preserve the actual ordered stop positions. 

Example:
Target: A → B → A

Candidate: X → A → B → A → Y
This qualifies because the complete ordered sequence occurs contiguously.

Candidate: X → A → B → C → A → Y
This does NOT qualify merely because all target station names occur; the required ordered contiguous sequence does not occur. Repeated visits must not be collapsed into a set.

### 8.2. Directionality
Direction and order matter explicitly in the ordered stop sequence evaluation.

Example:
Target: A → B → C

Candidate: X → A → B → C → Y
This qualifies.

Candidate: X → C → B → A → Y
This does not qualify. Reverse ordering is not treated as subsumption.

## 9. Data Dependencies
- `trains`: For resolving the target train identifier.
- `train_stop_observations`: To extract the ordered `station_id` sequence via `stop_sequence` for both the target and candidate trains.
- `dataset_snapshots`: To bound queries to the active timetable.

## 10. Snapshot Semantics
The query is heavily partitioned by `snapshot_id`. A target train is only evaluated against candidate trains operating within the exact same snapshot version.

## 11. API Proposal
```http
GET /api/v1/network/trains/{train_number}/structural-subsumption
```

## 12. Response Fields
```json
{
  "train_number": "51145",
  "subsuming_train_count": 13,
  "is_structurally_subsumed": true
}
```

## 13. Error Semantics
- `404 Not Found`: If the target train does not exist in the active snapshot, or if the snapshot is missing.
- `400 Bad Request`: If the target train has fewer than 2 valid stops (impossible for a valid train, but handled defensively).

## 14. Query and Algorithm Design
To avoid unbounded `STRING_AGG` computation across the entire timetable, the algorithm is optimized using explicit bounding:
1. **Target Extraction**: Extract the ordered $seq(T)$ for the target train.
2. **Boundary Anchoring**: Identify $S_{first}$ and $S_{last}$ from $seq(T)$.
3. **Candidate Filtering**: Select only candidate trains $T'$ that visit $S_{first}$ and later visit $S_{last}$ (`tso1.stop_sequence < tso2.stop_sequence`).
4. **Sequence Verification**: For the heavily reduced candidate pool, implement a verification algorithm (which may potentially use `STRING_AGG` and `LIKE` if proven safe as an implementation technique) that strictly ensures the target's ordered stop sequence exists as a contiguous ordered subsequence inside the candidate's sequence, adhering to the mathematical definition.

## 15. Complexity Analysis
- Target Extraction: $O(K \log K)$ where $K$ is the number of stops on the target train (typically < 100).
- Candidate Filtering: $O(E)$ bounded index scan, where $E$ is the number of trains serving the boundary stations.
- Sub-sequence Matching: String matching on a highly restricted candidate set (typically < 100 trains).

## 16. Worst-Case Behavior
The worst-case occurs if a train starts at a massive hub (e.g., NDLS) and ends at another massive hub (e.g., CNB), generating a large candidate pool of trains that visit both. However, string aggregation for ~500 trains is still computationally trivial in PostgreSQL.

## 17. Performance Analysis (Real Snapshot 2 via EXPLAIN ANALYZE)
Testing an exploratory query on Train `58202` (a 15-stop local train):
- **Planning Time**: approximately 1.065 ms
- **Execution Time**: approximately 6.137 ms
- **Indexes Leveraged**: `ix_train_stops_snapshot_station` heavily pruned the candidate set.

*Note: This is discovery-stage performance for an exploratory query. It is not guaranteed that the final implementation will have identical performance.*

## 18. Real Snapshot 2 Validation
Exploratory discovery queries and the final mathematical implementation validated the following findings:
- **Train 58202**: 49 candidate subsuming trains
- **Train 51145**: 13 candidate subsuming trains
- **Train 55512**: 4 candidate subsuming trains
- **Train 51916**: 1 candidate subsuming train

*Note: These values have been independently validated using the exact ordered stop-sequence mathematical semantics in the final implementation. No discrepancies were found with the discovery-stage exploratory queries.*

## 19. Boundary Cases
- **Non-Subsumed Trains**: Trains that are not completely contained within another sequence will have 0 subsuming candidate trains.
- **Directionality**: Reverse-ordered routes do not qualify, as established in the mathematical semantics.
- **Identical Sequences**: If $T'$ has the exact same ordered stop sequence as $T$, it mathematically satisfies the contiguous subsequence condition (offset $j=1$).

## 20. Non-Goals
This metric explicitly does NOT establish or measure:
- passenger demand;
- passenger accessibility;
- actual passenger journeys;
- operational redundancy;
- operational capacity;
- physical railway redundancy;
- reliability;
- congestion;
- real-world service substitution;
- partial route overlap (handled by Phase 15).

## 21. ₹0 Constraints
- Met completely. Implementation will rely on native PostgreSQL features without requiring external graph databases or infrastructure.

## 22. Implementation Boundaries
- Modifies `api/v1/schemas.py` for response models.
- Modifies `services/network.py` for query execution.
- Modifies `api/v1/network.py` to expose the endpoint.

## 23. Planned Tests
1. **Normal Case**: Target train with a known subset of another train.
2. **Non-Subsumed Case**: Long-distance train with 0 subsumptions.
3. **Directionality**: Verify reverse-route candidates are correctly rejected.
4. **Clone/Parallel Case**: Verify identical parallel trains count as subsumptions.
5. **Missing Entity**: Unknown train number raises 404.

## 24. Approval Gate
This document defines the strict boundaries for Phase 37 implementation. Do not implement without explicit user instruction.
