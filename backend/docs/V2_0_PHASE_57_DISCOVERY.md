# V2.0 Phase 57 Discovery: Train Sequence Disjoint Sub-Path Reconvergences

## 1. Proposed Capability
**Name:** Train Sequence Disjoint Sub-Path Reconvergences  
**Endpoint:** `GET /api/v1/network/trains/{train_number}/disjoint-subpath-reconvergences`  

## 2. Problem and Motivation
Timetable network routes often feature parallel services that share anchor stations but take different routes between them. However, identifying true structural redundancy requires finding "split-and-remerge" topologies where two trains diverge at station A and reconverge at station B while maintaining completely disjoint intermediate paths. 

Identifying these disjoint reconvergences exposes macro-level network redundancy and independent topological corridors spanning the same anchors, distinct from services that merely weave in and out of the same stations.

**Precise Question:**
For a target train's sequence, do there exist any station pairs $(A, B)$ such that another train in the timetable also visits $A$ then $B$, but shares *zero* intermediate stations with the target train between those two anchors?

## 3. Exact Semantics
- **Target train identity**: Defined by `train_number`, resolved to `train_id` in the active snapshot. Let its sequence be $S_1, S_2, \dots, S_n$.
- **Anchor Pair**: Any two stations $A, B$ in the target sequence where $seq_B > seq_A + 1$. 
- **Target Intermediate Path**: The set of stations $P_T = \{S_k \mid seq_A < k < seq_B\}$.
- **Candidate Train ($U$)**: Any other distinct train that visits $A$ at $seq_U(A)$ and $B$ at $seq_U(B)$ where $seq_U(B) > seq_U(A) + 1$.
- **Candidate Intermediate Path**: The set of stations $P_U = \{U_k \mid seq_U(A) < k < seq_U(B)\}$.
- **Disjoint Reconvergence Condition**: The intermediate paths must be strictly disjoint, i.e., $|P_T \cap P_U| = 0$.
- **Metrics**:
  - A list of valid reconvergences detailing:
    - `from_station_code` ($A$)
    - `to_station_code` ($B$)
    - `divergent_train_number` ($U$)
    - `target_intermediate_stops` ($|P_T|$)
    - `divergent_intermediate_stops` ($|P_U|$)

## 4. Mathematical Definition
Given target train $T$ with ordered stations $S^{(T)}$.
For every pair $(S^{(T)}_i, S^{(T)}_j)$ where $j > i + 1$:
Let $P_T = \{S^{(T)}_k \mid i < k < j\}$.

Find all trains $U \in \mathcal{O}$ such that:
$\exists u, v$ where $S^{(U)}_u = S^{(T)}_i$ and $S^{(U)}_v = S^{(T)}_j$ and $v > u + 1$.
Let $P_U = \{S^{(U)}_k \mid u < k < v\}$.

The pair $(T, U)$ across anchors $(S^{(T)}_i, S^{(T)}_j)$ is a Disjoint Reconvergence iff:
$P_T \cap P_U = \emptyset$.

## 5. Novelty Proof & Overlap Audit
This metric evaluates strict intermediate node disjointness across dynamically discovered sequence anchors.
- **vs Phase 45 (Station-Pair Route Diversity)**: Phase 45 returns the count of distinct spatial paths between a queried (A,B) pair. It does not scan a train's entire route to discover candidate pairs, nor does it guarantee that the diverse paths are mathematically disjoint. Two diverse paths in Phase 45 might share an intermediate station (e.g., A-X-B and A-X-Y-B are diverse but not disjoint). Phase 57 strictly enforces $|P_T \cap P_U| = 0$.
- **vs Phase 38 (Topological Bypasses)**: Phase 38 strictly evaluates a 1-hop edge $A \rightarrow B$ bypassing a 2-hop sequence $A \rightarrow X \rightarrow B$. Phase 57 discovers multi-hop vs multi-hop disjoint paths (e.g., 3-hop vs 4-hop).
- **vs Phase 16 (Station Service Similarity)**: Phase 16 evaluates global unordered station set intersection. It has no mechanism to bound intersections between specific sequence anchors or evaluate sub-path disjointness.

### Counterexample
**Timetable:**
- Target $T$: A - B - C - D
- Train $U$: A - B - X - D
- Train $V$: A - Y - Z - D

**Phase 45 Analysis for (A, D)**:
Reports 3 distinct paths (A-B-C-D, A-B-X-D, A-Y-Z-D). It does not isolate which ones are structurally independent of $T$.

**Phase 57 Analysis**:
- For anchors (A, D):
  - $T$'s intermediate path: {B, C}
  - $U$'s intermediate path: {B, X}. Intersection with $T$ is {B} $\neq \emptyset$. (Rejected).
  - $V$'s intermediate path: {Y, Z}. Intersection with $T$ is $\emptyset$. (Accepted!).
Phase 57 mathematically isolates Train $V$ as the true disjoint alternative, exposing structural information completely invisible to Phase 45 or Phase 16.

## 6. Data Model Mapping
- `trains`: Resolves the target `train_number`.
- `dataset_snapshots`: Resolves the active snapshot.
- `train_stop_observations`: Provides `snapshot_id`, `train_id`, `station_id`, and `stop_sequence` to bound intermediate paths and evaluate intersections.

## 7. Schema and Index Changes
None required. The existing composite index `ix_train_stops_snapshot_station` on `train_stop_observations` supports the required lookups efficiently.

## 8. Query Strategy
1. `target_pairs`: Generate all valid $(A, B)$ pairs from `target_stops` where $seq_B > seq_A + 1$.
2. `candidate_trains`: Join `train_stop_observations` twice to find other trains visiting $A$ and $B$ in correct temporal order ($seq_B > seq_A + 1$).
3. `disjoint_filter`: Apply a `WHERE NOT EXISTS` clause to ensure no intermediate station of the candidate train (bounded by its $seq_A$ and $seq_B$) exists in the target train's intermediate stations (bounded by the target's $seq_A$ and $seq_B$).

## 9. Complexity and Performance Mitigation
- **Target pairs**: For a 50-stop train, $\approx 1250$ pairs.
- **Candidate lookup**: Only evaluating trains that co-traverse the specific anchor pair. This is a highly selective join.
- **Intersection check**: `NOT EXISTS` executes almost instantaneously on the small bounded integer ranges of `stop_sequence`.
- **Performance Mitigation**: No global $O(N^2)$ cross-products. Execution is bounded by $O(n^2 \cdot K)$, where $n$ is target stations and $K$ is the number of co-traversing trains per pair, executing efficiently in PostgreSQL.

## 10. Non-Goals
- Does not imply trains run simultaneously (no departure time constraint).
- Does not represent physical track exclusivity or passenger routing choices.

## 11. Real-Data Validation Plan
Validation against Snapshot 2:
1. **Train 12628**: Evaluate a long-distance route to find regional disjoint bypasses (e.g., trains taking alternative alignments between major junctions).
2. **Train 04853**: Evaluate a short route to verify empty lists if no disjoint alternatives exist.
3. Validate sequence bounds correctly handle cyclic train routes without falsely identifying overlapping segments.

## 12. Response Schema
```json
{
  "train_number": "string",
  "total_disjoint_reconvergences": "integer",
  "reconvergences": [
    {
      "from_station_code": "string",
      "to_station_code": "string",
      "divergent_train_number": "string",
      "target_intermediate_stops": "integer",
      "divergent_intermediate_stops": "integer"
    }
  ]
}
```

## 13. Acceptance Criteria
- Endpoint returns correctly formatted schema.
- Reconvergence intermediate paths must mathematically share zero stations.
- Bounding logic strictly obeys `stop_sequence` without being affected by stations visited outside the anchor bounds.
- 0 disjoint reconvergences returns an empty list `[]` and `0` total count gracefully.
