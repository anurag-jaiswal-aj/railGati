# V2.0 Phase 56 Discovery

## Problem / Motivation
An overlap audit determined that calculating 1-hop edge alignment (e.g., $F(A \rightarrow B) / F_{out}(A)$) across a route merely aggregates edge-level statistics (derivable from Phase 30 Outbound Dominance and Phase 39 Traversal Dispersion). Because unweighted aggregations treat routes as unordered sets of edges, two trains executing the same edges in reverse order would erroneously receive the same score, proving the lack of sequence-structural novelty.

To extract genuinely new structural information, we must evaluate topological features that span across sequence boundaries. We propose evaluating **2-hop path continuity**. By measuring the preservation of historical timetable occurrences across consecutive edge pairs, we analyze whether a train's transitions are structurally continuous or highly fractured relative to the surrounding network flow.

## Proposed Capability
**Train Sequence Topological Transition Continuity**

For a target train traversing a sequence of stations $S_1, S_2, \dots, S_n$, the metric evaluates every sequential 3-station triplet $(S_{i-1}, S_i, S_{i+1})$. It calculates the "Transition Preservation Ratio": the proportion of timetable occurrences that traverse the first edge ($S_{i-1} \rightarrow S_i$) that *continue* uninterrupted to complete the exact 2-hop path ($S_{i-1} \rightarrow S_i \rightarrow S_{i+1}$).

This extracts multi-edge topological path dependency. Because 2-hop path volumes are mathematically underivable from independent 1-hop edge volumes (a network can have heavy traffic on $A \rightarrow B$ and $B \rightarrow C$, yet zero traffic doing $A \rightarrow B \rightarrow C$), this metric introduces strictly novel, non-derivable structural information.

## Exact Semantics & Mathematical Definition
- **Input Entities**: Target train $T$, active timetable snapshot.
- **Sequence Semantics**: The ordered sequence of $n$ occurrences $S_1, S_2, \dots, S_n$.
- **Triplets**: $n-2$ consecutive chronological station triplets $Tr_i = (S_i, S_{i+1}, S_{i+2})$ for $1 \le i \le n-2$.
- **Edge Inflow ($N_{in}$)**: The count of distinct active trains traversing $S_i \rightarrow S_{i+1}$ directly.
- **Path Continuation ($N_{path}$)**: The count of distinct active trains traversing $S_i \rightarrow S_{i+1} \rightarrow S_{i+2}$ directly.
- **Transition Continuity ($C_i$)**: $C_i = \frac{N_{path}}{N_{in}}$.
  - Because $T$ itself performs this exact 2-hop sequence, $N_{path} \ge 1$ and $N_{in} \ge 1$.
  - Thus, $0.0 < C_i \le 1.0$.
- **Route Aggregation**: 
  - $\bar{C} = \frac{1}{n-2} \sum_{i=1}^{n-2} C_i$ (Average structural continuity).
  - $C_{min} = \min(C_i)$ (The single most structurally fractured transition on the route).
- **Handling of Repeated Stations / Cyclic Routes**: Chronological triplets correctly capture cycles (e.g., $A \rightarrow B \rightarrow A$).
- **Undefined Cases**: If $n < 3$, the metric cannot evaluate a 2-hop transition. Returns HTTP 422 or appropriate empty state.

## Data Model Mapping
- No schema changes required.
- Requires correlated 2-hop and 3-hop self-joins on `train_stop_observations` matching `stop_sequence + 1 = stop_sequence` mapped exclusively to the train's $n-2$ specific chronological triplets.

## Endpoint Proposal
`GET /api/v1/network/trains/{train_number}/topological-transition-continuity`

## Response Schema Proposal
```json
{
  "train_number": "12951",
  "timetable_snapshot_id": 2,
  "route_triplet_count": 200,
  "average_transition_continuity": 0.852,
  "minimum_transition_continuity": 0.125,
  "maximum_transition_continuity": 1.0,
  "minimum_continuity_triplet": {
    "station_1_code": "STN_A",
    "station_2_code": "STN_B",
    "station_3_code": "STN_C",
    "continuity_factor": 0.125
  }
}
```

## Example Scenarios
- **Scenario A (Path Preservation)**: A train follows a major corridor $A \rightarrow B \rightarrow C$. 50 trains travel $A \rightarrow B$. 48 of those continue $B \rightarrow C$. $C_i = 48/50 = 0.96$. (Requires implementation-time verification).
- **Scenario B (Fractured Transit)**: A train takes an unusual diversion. 20 trains travel $X \rightarrow Y$. Only 2 (including the target) continue to the obscure branch $Y \rightarrow Z$. $C_i = 2/20 = 0.10$. (Requires implementation-time verification).

## Performance Analysis & Complexity
- **Expected SQL Strategy**: 
  1. CTE `target_triads` extracts the $n-2$ physical station triplets specifically for train $T$ (~50 rows).
  2. Use a `LATERAL` join or correlated subqueries to calculate $N_{in}$ (2-table self-join) and $N_{path}$ (3-table self-join) independently for each of the ~50 target rows, strictly filtered by `snapshot_id`.
- **Complexity**: $O(n_{triplets} \times \text{IndexScan})$. By avoiding a global materialization of all possible 3-hop paths (which would cause a massive $O(V^3)$ combinatorial explosion), the query remains perfectly bounded to the train's specific route length. Expected execution $\sim 100-300\text{ms}$.

## Duplicate/Overlap Audit
- **Phase 39 (Edge Traversal Dispersion) & Phase 30 (Outbound Dominance)**: These assess 1-hop edge volumes. 2-hop path volumes cannot be derived from 1-hop margins.
- **Phase 42 (Co-Traversal Affinity)**: Evaluates sharing on a single edge, not across a multi-edge path.
- **Phase 17 (Path Continuous Services)**: Phase 17 calculates raw flow for an arbitrary path array. Phase 56 dynamically extracts a train's topological triplets, divides 2-hop by 1-hop flows to define structural preservation constraints, and aggregates these constraints into a definitive sequence-bound metric.
- **Phase 55 (Sequence Subgraph Density)**: Evaluates non-consecutive chords ($j > i+1$). Phase 56 strictly evaluates consecutive paths ($i, i+1, i+2$).
- **Verdict**: Genuinely new sequence-dependent information.

## Non-Goals
- Does not measure operational delays, passenger flow, or physical capacity.
- Purely measures the historical timetable 2-hop structural continuation mapping.

## Acceptance Criteria
- Must independently evaluate each chronological triplet to support cyclic routes.
- Must accurately compute $N_{in}$ and $N_{path}$ using distinct train occurrence counts to prevent duplicate multiplication.
- Must execute efficiently without globally materializing all 3-hop paths in the timetable.
