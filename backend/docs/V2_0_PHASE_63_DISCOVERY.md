# RailGati V2.0 Phase 63 Discovery
## Station Junction Through-Service Connectivity

**Status:** PROPOSED (Discovery Phase Only)  
**Author:** AI System  
**Date:** 2026-09-30  

---

### 1. Executive Summary

We propose **Station Junction Through-Service Connectivity** as the V2.0 Phase 63 analytical metric. 

This is strictly a historical timetable structural metric. It evaluates a station $S$ that acts as a structural junction (degree $\ge 2$) and determines the proportion of its topological branch pairings that are explicitly traversed by a continuous through-service sequence in the active historical timetable.

**CRITICAL SEMANTIC BOUNDARY:**
This metric proves only that the historical timetable contains at least one qualifying train occurrence with a consecutive stop sequence through $S$. 
It MUST NOT claim:
- passenger travel
- passenger demand
- actual passenger transfers
- physical track connectivity
- operational continuity on a particular real-world date
- current service availability
- traffic volume
- reliability
- congestion
- capacity
- route preference

### 2. Mathematical Definition

For a given station $S$ in an active timetable snapshot:

1. **Structural Neighborhood ($N(S)$)**: 
   Let $N(S)$ be the set of distinct adjacent canonical station identities connected to $S$ by the active timetable topology.
   Let $k = |N(S)|$.

2. **Possible Neighbor Pairs**: 
   The total number of unique, unordered neighbor pairs $\{A, B\}$ where $A \neq B$.
   $M = \frac{k(k - 1)}{2}$

3. **Served Neighbor Pairs**: 
   An unordered neighbor pair $\{A, B\}$ is a **SERVED THROUGH-SERVICE PAIR** if at least one historical train occurrence contains the consecutive three-station sequence:
   $A \to S \to B$
   OR
   $B \to S \to A$
   
   The two directions count as ONE unordered neighbor pair. The number of served neighbor pairs is the total count of unordered pairs satisfying this predicate.

4. **Primary Ratio**: 
   $$\text{through\_service\_pair\_ratio} = \frac{\text{served\_neighbor\_pairs}}{\text{possible\_neighbor\_pairs}}$$

If $k < 2$, the metric is mathematically undefined and should strictly use the project's established error semantics rather than inventing a `0.0` value.

### 3. API Contract

**Endpoint**: `GET /api/v1/network/stations/{station_code}/junction-through-service`

**Response Proposal**:
```json
{
  "station_code": "NDLS",
  "station_name": "NEW DELHI",
  "neighbor_count": 4,
  "possible_neighbor_pairs": 6,
  "served_neighbor_pairs": 4,
  "through_service_pair_ratio": 0.6667,
  "served_pairs": [
    {
      "neighbor_a": "DLI",
      "neighbor_b": "TKJ",
      "qualifying_train_count": 12
    },
    {
      "neighbor_a": "NZM",
      "neighbor_b": "SZM",
      "qualifying_train_count": 5
    }
  ],
  "unserved_pairs": [
    {
      "neighbor_a": "DLI",
      "neighbor_b": "SZM"
    }
  ]
}
```
*(Note: `neighbor_a` and `neighbor_b` should be sorted to guarantee canonical representation. `qualifying_train_count` explicitly counts distinct historical train identities/occurrences traversing the specific pair in either direction. Unserved pairs are included if justified by bounded response size since $M \le 45$ typically).*

### 4. Overlap & Derivability Audit

We have rigorously audited this metric against the closest completed Phase 1–62 capabilities:

- **vs. Phase 33 (Network Station Neighborhood Triadic Closure)**: Phase 33 asks whether pairs of outbound neighbors have a direct active timetable edge between them. Phase 63 asks whether a historical train occurrence actually traverses $A \to S \to B$ or $B \to S \to A$. Therefore, Phase 33 is an edge-to-edge topology relationship, while Phase 63 is a train-sequence service relationship through $S$.
- **vs. Phase 60 (Network Station Strict Local Bridges)**: Phase 60 asks whether a neighbor pair is structurally dependent on $S$ under its local graph rule. Phase 63 does NOT test vulnerability, dependency, alternate paths, or bridge status. Phase 63 only measures whether a historical timetable service sequence traverses through $S$ between the pair.
- **vs. Phase 32 (Neighborhood Directional Symmetry)**: Phase 32 compares inbound and outbound neighbor sets using Jaccard similarity. Phase 63 instead examines whether train stop sequences explicitly connect two neighbors through the station.
- **vs. Phases 31 / 14 / 25**: Phase 63 is not paired-service symmetry or directional edge-volume symmetry. It does not depend on `return_train_number`. It does not compare raw edge counts. It does not compare paired-service durations.

**Conclusion**: This metric isolates a novel interaction between undirected topology and strict sequence occurrence traversing a local node.

### 5. Occurrence Semantics

- **Snapshot Scope**: Analyzed exclusively within the same active timetable snapshot.
- **Occurrence Identity**: Evaluated per strictly identical train occurrence.
- **Sequence Rigidity**: Stop sequence must be strictly consecutive:
  - $\text{seq}(A) + 1 = \text{seq}(S)$ and $\text{seq}(S) + 1 = \text{seq}(B)$ for $A \to S \to B$.
- **Symmetry**: Reverse direction ($B \to S \to A$) is checked symmetrically and maps to the same unordered pair $\{A, B\}$.
- **Repetition Allowance**: Repeated station identities within the snapshot/route are permitted.
- **Cyclic Identity Preservation**: Repeated/cyclic routes must preserve stop-occurrence identity when evaluating consecutive sequences.
- **Exclusion of Non-Consecutive Visits**: A train merely visiting $A$ and $B$ somewhere on its route without the strict $A \to S \to B$ window does NOT qualify. (e.g., $A \to X \to S \to B$ fails).
- **Repetitive Deduplication**: $A \to S \to B$ occurring multiple times on one train counts only once for the unordered neighbor pair's served/unserved predicate.
- **Multiple Train Deduplication**: Multiple different trains traversing the sequence still produce only one served pair in the overall count (though they contribute to `qualifying_train_count`).
- **Irrelevance of Timing/Return**: Timing and `return_train_number` are irrelevant to the core metric.

### 6. Mathematical Examples

**Example 1: Basic Bridging**
If $S$ has neighbors $\{A, B, C, D\}$, then $k=4$:
`possible_neighbor_pairs` = $4 \times 3 / 2 = 6$.

Suppose historical timetable sequences include:
- $A \to S \to B$
- $B \to S \to A$
- $A \to S \to C$
- $D \to S \to C$

Then served unordered pairs are: $\{A, B\}, \{A, C\}, \{C, D\}$.
- `served_neighbor_pairs` = 3
- `through_service_pair_ratio` = 3 / 6 = 0.5.
*(Note: The two A/B directions count as one pair).*

**Example 2: Adjacency vs Service**
If $A$ and $B$ are both neighbors of $S$ but no historical train sequence has $A \to S \to B$ or $B \to S \to A$, then $\{A, B\}$ is an unserved pair. This holds true **even if** $A$ and $B$ share a direct edge elsewhere in the network topology. Structural adjacency alone does not qualify a pair as served.

### 7. Computational Strategy

- **Relational Aggregation**: Prefer PostgreSQL-native relational window functions (`LAG`, `LEAD`) over the `train_stop_observations` table for the specific target station $S$.
- **No Path Enumeration**: Do NOT use recursive graph traversal or enumerate arbitrary paths.
- **Scoping**: Use existing active snapshot scoping and canonical station indexing.
- **N+1 Avoidance**: Avoid N+1 queries by executing a single analytical grouped query extracting all bridging instances through $S$.
- **Oracle Validation**: The SQL implementation must be validated dynamically against a small in-memory Python oracle during test execution.
- *(Note: No performance numbers or query times are claimed until EXPLAIN ANALYZE is performed during the formal implementation phase).*

### 8. Documented Edge Cases

1. **Unknown station**: Fails safely with standard 404/Error handler.
2. **Missing active timetable snapshot**: Fails securely according to established dataset validation.
3. **k = 0**: Fails with defined mathematical error/404 handling (no neighbors).
4. **k = 1**: Fails with defined mathematical error/404 handling (division by zero, not a junction).
5. **k >= 2 with zero served pairs**: Handled correctly. Returns 0 served pairs and 0.0 ratio.
6. **One train providing multiple qualifying pairs**: A highly cyclic train could bridge $\{A, B\}$ and $\{B, C\}$ during different visits to $S$. Validated accurately via stop-occurrence indexing.
7. **Multiple trains providing the same pair**: Bounded as one distinct served pair, increments `qualifying_train_count`.
8. **Repeated visits to S by the same train**: Each independent $Prev \to S \to Next$ window is evaluated separately.
9. **$A \to S \to B$ and $B \to S \to A$ both existing**: Maps gracefully to the single unordered canonical set $\{A, B\}$.
10. **Cyclic/repeating routes**: Stop sequences are respected strictly. Cycles do not break the 3-stop window evaluation.
11. **Station appearing as a terminal**: If a train starts at $S$ or ends at $S$, it cannot form a 3-stop through sequence ($Prev \to S \to Next$). Such occurrences automatically fail the sequence condition and do not contribute to bridged pairs.
12. **Snapshot isolation**: Evaluation remains strictly confined to the currently active dataset snapshot boundary.

---

**Approval Status**: Phase 63 discovery is conditionally approved for implementation after this semantic revision. Implementation remains blocked pending manual approval.
