# RailGati V2.0 Phase 52 Discovery

**Status:** DISCOVERY

## Objective
Identify a genuinely new, structurally significant railway-network analytic that strictly adheres to RailGati constraints (historical timetable schema, ₹0 budget, no external data, purely structural), avoids overlapping with the Route Diversity (Phase 45) or Halt Stratification (Phase 51) metrics, and passes a strict distinctness test against all prior phases.

## Candidate Analysis & Strict Rejection Test

During the second discovery round, five distinct candidate concepts were evaluated against the strict rejection criteria:

1. **Network Station-Pair Administrative State Transition Analytics**
   - *Question:* How many jurisdictional state boundaries does a traversal cross between O and D?
   - *Closest Phase:* Phase 51 Intermediate Halt Stratification.
   - *Rejection Rationale:* REJECTED. Evaluates the categorical `state` field of intermediate stops to measure administrative fragmentation, but ultimately functions as a trivial variation/aggregation of Phase 51 halt counts masked by metadata.

2. **Network Train Route Intra-Zonal Terminal Consistency Analytics**
   - *Question:* Does a train's absolute origin and absolute destination belong to the same railway zone?
   - *Closest Phase:* Phase 48 Terminal Dispersion / OD Flow.
   - *Rejection Rationale:* REJECTED. Evaluates categorical terminal attributes, making it another OD flow/terminal metric.

3. **Network Station Categorical Multi-Zone Hub Analytics**
   - *Question:* For a specific station, how many distinct railway zones are represented by the immediate next stops of all departing trains?
   - *Closest Phase:* Station Degree / Hub Centrality.
   - *Rejection Rationale:* REJECTED. It is explicitly another station degree/hub measure.

4. **Network Station-Pair Multi-Day Traversal Span Analytics**
   - *Question:* For a station pair O -> D, what is the distribution of the calendar `source_day` shift?
   - *Closest Phase:* Travel Time Analytics, Temporal Gaps.
   - *Rejection Rationale:* REJECTED. Falls under the banned "temporal concentration/gap/duration" umbrella.

5. **Network Station-Pair Published Return-Service Adherence Analytics**
   - *Question:* For an O->D corridor, do the explicitly published "return trains" of forward services actually perform the mirrored D->O traversal?
   - *Closest Phase:* Phase 45 OD Flow, Phase 50 Temporal Inversion.
   - *Selection Rationale:* **ACCEPTED**. It utilizes the entirely untapped `return_train_number` metadata to structurally validate paired services against the topological graph. It is neither a reachability metric, a temporal metric, nor a simple aggregation of route diversity.

## Selected Concept: Network Station-Pair Published Return-Service Adherence Analytics

### 1. Analytic Name
Network Station-Pair Published Return-Service Adherence Analytics

### 2. Problem Statement
The dataset provides a `return_train_number` string field for many train observations, ostensibly indicating that the railway operates a mirrored service in the opposite direction. However, this is merely a metadata claim. Does the physical timetable actually fulfill this claim for a specific Origin-Destination corridor? Do the designated return trains structurally visit the Destination and subsequently return to the Origin?

### 3. Why It Is Not Already Answered
Previous phases measure total OD flow, directional volume (Edge Asymmetry), and topological paths (Phase 45 Route Diversity). None of them evaluate explicit structural pairings. OD Flow might show 10 trains O->D and 10 trains D->O, but Return-Service Adherence identifies whether those 10 return trains are actually the *designated operational pairs* of the forward trains, or if the corridor is serviced by structurally disjoint rolling stock loops.

### 4. Exact Relational Semantics
- **Entities:** Valid forward traversals between Origin (O) and Destination (D).
- **Forward Traversal:** Train `T1` visits O at sequence $S_1$ and D at sequence $S_2$ where $S_1 < S_2$.
- **Return Metadata:** `T1`'s observation in `train_observations` contains `return_train_number`.
- **Validation:** Attempt to locate Train `T2` matching `return_train_number` within the same snapshot. If `T2` exists, verify it visits D at sequence $S_3$ and O at sequence $S_4$ where $S_3 < S_4$.
- **Adherence States:**
  - `unpaired`: `return_train_number` is null or empty.
  - `adherent`: `T2` exists and correctly traverses D -> O.
  - `non_adherent`: `T2` does not exist in the snapshot, or it exists but fails to complete the D -> O structural traversal.

### 5. Mathematical Definition
Let $F_{O \to D}$ be the set of valid forward traversals.
For each $f \in F_{O \to D}$, let $R(f)$ be its designated return train number.
If $R(f) = \emptyset$, status is `unpaired`.
If $R(f) \neq \emptyset$, let $T_{R(f)}$ be the set of sequences for that train.
If $\exists (seq_D, seq_O) \in T_{R(f)}$ such that $seq_D < seq_O$, status is `adherent`.
Else, status is `non_adherent`.

### 6. Exact Endpoint Proposal
`GET /api/v1/network/station-pairs/{origin_code}/{destination_code}/return-service-adherence`

### 7. Complete Response Contract
```json
{
  "origin_station_code": "str",
  "destination_station_code": "str",
  "timetable_snapshot_id": "int",
  "total_forward_traversals": "int (Count of valid O->D traversals)",
  "unpaired_traversal_count": "int (Count where return_train_number is absent)",
  "adherent_return_traversal_count": "int (Count where return train correctly traverses D->O)",
  "non_adherent_return_traversal_count": "int (Count where return train is missing or fails to traverse D->O)"
}
```

### 8. Repeated/Cyclic Route Semantics
Strictly handled. If the designated return train visits D and O multiple times, it is considered adherent as long as *at least one* valid occurrence of D -> O (where D's sequence < O's sequence) exists in its itinerary.

### 9. Snapshot Semantics
Fully isolated. The designated return train is evaluated strictly against its `train_stop_observations` within the same `timetable_snapshot_id` as the forward traversal.

### 10. Deduplication Semantics
The metric operates on traversals (train occurrences). If multiple trains share the same `return_train_number` (rare but possible in schedule anomalies), each forward traversal independently evaluates its adherence status.

### 11. Missing-Data Behavior
If the Origin or Destination is not found, returns HTTP 404. If the forward traversals are zero, it returns zeroes across all counters. If the `return_train_number` cannot be resolved to a valid `train_id`, it is gracefully binned as `non_adherent`.

### 12. Real Snapshot 2 Examples
Derived directly from the historical database:
- **CNB -> NDLS:** 39 total | 0 unpaired | 38 adherent | 1 non-adherent
- **LTT -> PUNE:** 27 total | 0 unpaired | 26 adherent | 1 non-adherent
- **HWH -> PNBE:** 11 total | 0 unpaired | 11 adherent | 0 non-adherent
- **BCT -> BVI:** 23 total | 3 unpaired | 20 adherent | 0 non-adherent

### 13. EXPLAIN ANALYZE (Representative Query: CNB -> NDLS)
- **Planning Time:** 0.900 ms
- **Execution Time:** 1.729 ms

### 14. Relevant Indexes & Sequential-Scan Assessment
- **Query Strategy:** The query planner utilizes `Nested Loop Left Join` heavily over primary and composite indexes.
- **Relevant Indexes utilized:** `ix_stations_code`, `ix_train_stops_snapshot_station`, `train_observations_pkey`, `ix_trains_number`, `train_stop_observations_pkey`.
- **Sequential Scans:** None. The query perfectly leverages indexing for every single join constraint.

### 15. Complexity Assessment
Moderate join depth but exceptionally low computational overhead. Because the initial bounding set (forward traversals) is small and highly indexed, subsequent outer joins to validate the return train's stops execute in sub-millisecond ranges.

### 16. Data Limitations
The metric evaluates structural schedule adherence, not physical execution. It determines if the *timetable* successfully mirrors the published return service. It cannot verify if the return service ran on time, ran with the same physical rake, or was cancelled on a specific day.

### 17. ₹0 Compliance
Fully compliant. Operates exclusively on the existing static PostgreSQL relational schema using standard SQL features, requiring zero external APIs, plugins, or paid datasets.
