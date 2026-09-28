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
**Train Route Structural Subsumption** evaluates whether an entire scheduled train route operates strictly as a redundant sub-corridor within the exact topological footprint of another longer-distance train. 

### 4. Problem / Question Answered
*Structurally, does this train operate entirely as a strict sub-corridor of another active train, providing purely supplementary local capacity within an identical topological footprint?*

### 5. Explicit Overlap Audit against Phases 1-36
- **vs. Phase 13 (Train Route Similarity)**: Phase 13 calculates the Jaccard similarity index (intersection over union) between two known trains. It evaluates bidirectional overlap. Subsumption evaluates asymmetric, contiguous topological subsetting ($A \subset B$). A train that shares 50% of its route with another train has a high similarity score, but 0 subsumption. 
- **vs. Phase 3 (Continuous Services)**: Phase 3 verifies if a single train connects a specific $A$ and $B$. It does not evaluate sequence subsetting.
- **vs. Reachability / Bounded Metrics**: Subsumption bounds itself entirely to the specific stop sequence of the target train, avoiding graph recursion.

### 6. Why the Selected Capability is Distinct
This metric introduces **Timetable Corridor Redundancy** as a new dimension. Instead of identifying where a train goes, it identifies if a train's entire spatial sequence is already perfectly replicated by another longer service. It isolates dedicated local shuttles and supplementary corridor capacities from structurally unique services.

## 7. Exact Semantics
For a target train $T$, let $seq(T) = (S_1, S_2, ..., S_k)$ be its topologically ordered sequence of station stops.
A train $T$ is **structurally subsumed** by a candidate train $T'$ if and only if:
1. $T \neq T'$
2. $T$ and $T'$ both exist within the same active timetable snapshot.
3. The exact sequence $seq(T)$ exists as a contiguous topological sub-sequence within $seq(T')$.

## 8. Mathematical Definition
Given $T$:
$seq(T) = (S_{1}, S_{2}, ..., S_{k})$

Let $V$ be the set of all active trains in the network.
$SubsumingTrains(T) = \{ T' \in V \mid T' \neq T \land seq(T) \text{ is a sub-sequence of } seq(T') \}$

**Train Subsumption Count** = $|SubsumingTrains(T)|$

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
4. **Sequence Verification**: For the heavily reduced candidate pool, apply `STRING_AGG(station_id ORDER BY stop_sequence)` and verify the subset using a `LIKE '%target_sequence%'` pattern match.

## 15. Complexity Analysis
- Target Extraction: $O(K \log K)$ where $K$ is the number of stops on the target train (typically < 100).
- Candidate Filtering: $O(E)$ bounded index scan, where $E$ is the number of trains serving the boundary stations.
- Sub-sequence Matching: String matching on a highly restricted candidate set (typically < 100 trains).

## 16. Worst-Case Behavior
The worst-case occurs if a train starts at a massive hub (e.g., NDLS) and ends at another massive hub (e.g., CNB), generating a large candidate pool of trains that visit both. However, string aggregation for ~500 trains is still computationally trivial in PostgreSQL.

## 17. Performance Analysis (Real Snapshot 2 via EXPLAIN ANALYZE)
Testing Train `58202` (a 15-stop local train):
- **Planning Time**: 1.065 ms
- **Execution Time**: 6.137 ms
- **Indexes Leveraged**: `ix_train_stops_snapshot_station` heavily prunes the candidate set during the boundary anchoring phase, avoiding sequential scans.

## 18. Real Snapshot 2 Validation
Validation confirms the metric's utility in isolating highly subsumed local trains from unique services:
- **Train 58202**: 49 STRICT subsuming trains (Execution: ~6ms)
- **Train 51145**: 13 STRICT subsuming trains (Execution: ~3ms)
- **Train 55512**: 4 STRICT subsuming trains (Execution: ~2ms)
- **Train 51916**: 1 STRICT subsuming trains (Execution: ~2ms)

## 19. Boundary Cases
- **Non-Subsumed Express Trains**: Long-distance express trains crossing multiple zones will have 0 subsuming trains, acting as the structural supersets themselves.
- **Directionality**: A candidate train traveling the reverse route does not subsume the target train due to strict `stop_sequence` ordering in string aggregation.
- **Identical Clones**: If $T'$ has the exact same sequence as $T$, it counts as a subsumption (they structurally subsume each other, representing parallel redundant capacity).

## 20. Non-Goals
- Does not measure operational passenger capacity or real passenger demand.
- Does not evaluate partial route overlap (handled by Phase 13).
- Does not compute physical track infrastructure.

## 21. ₹0 Constraints
- Met completely. Relies entirely on native PostgreSQL string aggregation (`STRING_AGG`) and subset matching (`LIKE`). No external graph databases or infrastructure are required.

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
