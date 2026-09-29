# Phase 49 Discovery

## Status
DISCOVERY — NOT APPROVED

## Selected Capability
Network Station Pair Route Extension Analytics

## Analytical Question
For the specific set of trains directly connecting a given Origin and Destination station, how vast is the feeder network supplying the Origin, and how vast is the distributor network radiating from the Destination?

## Candidate Alternatives Rejected
- **Train Route Hub Articulation**: Merely applying the Phase 48 calculation to a differently filtered set of stations (Hubs instead of Terminals). Rejected as superficial re-aggregation.
- **Station Pair Sub-Route Overlap**: Largely redundant with Phase 37 and Phase 43 train-level subsumption metrics applied to segments.
- **Station Pair Intermediate Transfer Opportunity**: Functionally identical to Phase 46 (Station Pair Intermediate Flow Concentration), which already maps traffic crossing the intermediate segments.

## Formal Definition
**Entities**: Active Timetable Snapshot, Station Pair (O, D), Train Stop Observations.

For a target station pair (O, D) where O != D:
1. **Valid Traversals**: Any train occurrence in the active snapshot where the train visits O at sequence $s_o$ and D at sequence $s_d$, such that $s_o < s_d$.
2. **Pre-Origin Stations**: The set of distinct station identities visited by the serving trains at sequence $s_x < s_o$ for their respective valid traversal.
3. **Post-Destination Stations**: The set of distinct station identities visited by the serving trains at sequence $s_y > s_d$ for their respective valid traversal.
4. **Total Extension Stations**: The set of distinct station identities present in either the Pre-Origin or Post-Destination sets.

**Metrics Calculated**:
- `traversal_occurrence_count`: The number of valid traversals between O and D.
- `pre_origin_station_count`: Size of the Pre-Origin Stations set.
- `post_destination_station_count`: Size of the Post-Destination Stations set.
- `total_extension_station_count`: Size of the Total Extension Stations set.

## Traversal / Occurrence Semantics
- **Train Identity**: Evaluated per occurrence via `stop_sequence`.
- **Cyclic/Repeated Traversals**: If a train traverses O -> D multiple times, each valid pair $(s_o, s_d)$ acts as an independent anchor for evaluating $s_x$ and $s_y$. The pre/post stations from all valid traversals are aggregated globally for the metric.
- **Deduplication**: Station identities are deduplicated within the pre-origin, post-destination, and total extension sets.

## Snapshot Semantics
Strictly bounded to the active timetable snapshot. Station occurrences and traversals are cross-joined heavily relying on `snapshot_id`.

## Closest Existing Phases
1. **Phase 47 (Station Pair Route-Boundary Confinement)**
   - *Existing Measures*: The count of *trains* bounded strictly by O or D.
   - *Phase 49 Measures*: The geographical/structural *stations* lying outside O and D.
   - *Distinction*: Phase 47 measures train identity bounding status; Phase 49 measures the topological footprint (station count) of the feeder/distributor segments.
2. **Phase 46 (Station Pair Intermediate Flow Concentration)**
   - *Existing Measures*: Trains overlapping the *intermediate* segment (between O and D).
   - *Phase 49 Measures*: The network footprint attached to the *external* segments (before O, after D).
   - *Distinction*: Completely different spatial domains (internal vs. external) and output dimensions (train count vs. station count).
3. **Phase 36 (Transfer-Free Reachability)**
   - *Existing Measures*: Global 1-hop reachability for a *single* station.
   - *Phase 49 Measures*: Upstream/downstream extension isolated strictly to the traffic servicing a dual-station O-D flow.

## Real Snapshot 2 Validation
Values queried directly against Snapshot 2 database:

- **Large / High-Volume (NDLS -> CNB)**
  - traversal_occurrence_count: 38
  - pre_origin_station_count: 28
  - post_destination_station_count: 1044
  - total_extension_station_count: 1072
- **Mirror Large / High-Volume (CNB -> NDLS)**
  - traversal_occurrence_count: 39
  - pre_origin_station_count: 1038
  - post_destination_station_count: 76
  - total_extension_station_count: 1114
- **Medium Volume (GKP -> LKO)**
  - traversal_occurrence_count: 24
  - pre_origin_station_count: 499
  - post_destination_station_count: 886
  - total_extension_station_count: 1385
- **Suburban / Small Pre-Origin (BCT -> BVI)**
  - traversal_occurrence_count: 23
  - pre_origin_station_count: 0
  - post_destination_station_count: 477
  - total_extension_station_count: 477
- **Missing Station / Empty (INVALID -> CNB)**
  - "One or both stations not found." (Handled via 404 in API).

## Edge Cases
- **Missing Train/Station**: Returns `404 Not Found`.
- **Zero Traversals**: If O and D exist but no direct path connects them, returns `404 Not Found` (Standard O-D pair convention).
- **Origin = Destination**: Mathematical impossibility under $s_o < s_d$ for adjacent sequences, but logically rejected as `400 Bad Request`.
- **No active snapshot**: Returns `503 Service Unavailable`.

## Performance
An `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` execution for the massive `CNB -> NDLS` flow generated:
- **Planning Time**: ~1.182 ms
- **Execution Time**: ~7.023 ms
- **Major Operators**: `CTE Scan`, `Hash Join`, `Append`, and `HashAggregate`. The query relies on highly effective materialization and in-memory hash hashing to intersect traversal sets and extension footprint. Performance is observed to be exceptionally well-handled by PostgreSQL's native engine. No external complexity bounds were assumed.

## API Proposal
`GET /api/v1/network/station-pairs/{origin_code}/{destination_code}/route-extension`

**Response Fields**:
```json
{
    "origin_station": "CNB",
    "destination_station": "NDLS",
    "traversal_occurrence_count": 39,
    "pre_origin_station_count": 1038,
    "post_destination_station_count": 76,
    "total_extension_station_count": 1114
}
```

## Implementation Considerations
A precise 4-CTE SQL query is required to calculate `valid_traversals` accurately via $s_o < s_d$, followed by independent `pre_origin_stops` and `post_dest_stops` CTEs joining on the valid anchor sequences. `total_extension_station_count` safely merges these using a `UNION` for distinct identities.

## Non-Goals / Interpretation Limits
This metric measures the historical structural size of the feeder and distributor topologies associated with specific dual-station paths. It explicitly does not gauge passenger throughput, load factors, seating capacity, or real-world ticket sales. 

## Discovery Conclusion
Phase 49 offers a computationally elegant and deeply revealing capability that clearly bifurcates and quantifies the structural funneling capabilities (pre-origin vs. post-destination) of railway paths. It sits conceptually apart from previous boundary and hub analytics.
