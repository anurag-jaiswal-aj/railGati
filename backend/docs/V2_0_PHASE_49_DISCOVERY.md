# Phase 49 Discovery

## Status
DISCOVERY — NOT APPROVED

## Selected Capability
Network Station Pair Route Extension Analytics

## Analytical Question
For the specific set of trains directly connecting a given Origin and Destination station, how vast is the external route-extension station set supplying the Origin, and how vast is the timetable-derived station extension radiating from the Destination?

## Candidate Alternatives Rejected
- **Train Route Hub Articulation**: Merely applying the Phase 48 calculation to a differently filtered set of stations (Hubs instead of Terminals). Rejected as superficial re-aggregation.
- **Station Pair Sub-Route Overlap**: Largely redundant with Phase 37 and Phase 43 train-level subsumption metrics applied to segments.
- **Station Pair Intermediate Transfer Opportunity**: Functionally identical to Phase 46 (Station Pair Intermediate Flow Concentration), which already maps traffic crossing the intermediate segments.

## Formal Definition
**Entities**: Active Timetable Snapshot, Station Pair (O, D), Train Stop Observations.

For an ordered target station pair (O, D):
1. Find all valid traversal instances:
       (train occurrence, o_seq, d_seq)
       where O occurs at o_seq,
       D occurs at d_seq,
       and o_seq < d_seq.

2. For every traversal instance (O,D,T,o_seq,d_seq):
       Pre = distinct station identities at sequence positions < o_seq
       Post = distinct station identities at sequence positions > d_seq

3. Aggregate globally:
       pre_origin_station_set = UNION of all Pre sets across all valid traversal instances
       post_destination_station_set = UNION of all Post sets across all valid traversal instances

4. Report:
       traversal_occurrence_count
       pre_origin_station_count
       post_destination_station_count
       total_extension_station_count (Size of pre_origin_station_set UNION post_destination_station_set)

where all three station counts evaluate DISTINCT station identities.

The metric is:
- historical
- timetable-derived
- snapshot-scoped
- ordered O→D
- traversal-instance based
- station-identity aggregated

## Traversal / Occurrence Semantics & Train Identity
The metric does NOT count serving trains as the unit of the extension station counts. A single train may contribute multiple valid O→D traversal instances.
The extension station counts are based strictly on DISTINCT STATION IDENTITIES after aggregating the extension sets from all valid traversal instances.

`traversal_occurrence_count` represents the number of distinct valid traversal instances (not the number of distinct serving trains).

## Cyclic / Repeated Occurrences
Multiple O→D sequence pairs form independent traversal instances.
For example, given a train route:
    O(1) ... D(3) ... O(6) ... D(8)

The valid traversal instances (where origin_sequence < destination_sequence) are:
    (O1, D1) i.e. sequences 1 and 3
    (O1, D2) i.e. sequences 1 and 8
    (O2, D2) i.e. sequences 6 and 8

It does NOT include (O2, D1) i.e. sequences 6 and 3, because O occurs after D in that pair.

For each of these three valid traversal instances, its own Pre and Post station sets are calculated based on those precise sequence bounds. Only after that calculation are the station identities unioned globally across all instances.

## Snapshot Semantics
Strictly bounded to the active timetable snapshot. Station occurrences and traversals are cross-joined heavily relying on `snapshot_id`.

## Closest Existing Phases
1. **Phase 22 (Station O-D Bridges)**
   - *Existing Measures*: Target-station-centric metric identifying train-level origin/destination boundaries associated with a single station.
   - *Phase 49 Measures*: Ordered O→D station-pair-centric metric extracting the station identities lying outside the pair's traversal boundaries.
   - *Distinction*: Phase 49 extracts actual intermediate/external station structures linked to an O→D flow, which cannot be obtained merely by filtering Phase 22's terminal-centric output.

2. **Phase 47 (Station Pair Route-Boundary Confinement)**
   - *Existing Measures*: Boundary classification of traversal instances (counting traversal instances bounded strictly by O or D).
   - *Phase 49 Measures*: External station-set extraction from traversal instances.
   - *Distinction*: Phase 47 classifies the boundary status of the traversals; Phase 49 isolates the timetable-derived station extension structures lying outside O and D. It is not merely another boundary ratio.

3. **Phase 46 (Station Pair Intermediate Flow Concentration)**
   - *Existing Measures*: Identifies stations strictly BETWEEN O and D and counts traversal-instance participation and station occurrence counts.
   - *Phase 49 Measures*: Identifies stations strictly OUTSIDE the O→D boundaries (before O, after D) and aggregates DISTINCT station identities.
   - *Distinction*: Phase 49 explicitly does not measure intermediate stations.

## Real Snapshot 2 Validation
Values queried directly against Snapshot 2 database (using exactly the Formal Definition logic):

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

## Edge Cases
- **Missing Train/Station**: Returns `404 Not Found` (Standard project convention for missing inputs).
- **Zero Traversals**: If O and D exist but no direct path connects them, returns `404 Not Found` (Consistent with existing station-pair analytics API conventions where no direct relation implies a 404).
- **Origin = Destination**: Returns `400 Bad Request` (Consistent with existing station-pair API conventions preventing identical inputs).
- **No active snapshot**: Returns `503 Service Unavailable`.

## Performance
An `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` execution for the `CNB -> NDLS` flow generated:
- **Planning Time**: ~1.182 ms
- **Execution Time**: ~7.023 ms
- **Major Operators**: The measured plan used `Hash Join`, `CTE Scan`, and `HashAggregate`/`Append` operators and completed in approximately 7 ms.

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
This metric measures timetable-derived station sets associated with specific dual-station paths. It explicitly does not gauge passenger throughput, load factors, seating capacity, or real-world ticket sales. It does not measure geographic distance, geographic area, physical railway extent, track coverage, or infrastructure reach.

## Discovery Conclusion
Phase 49 offers a computationally solid capability that clearly bifurcates and quantifies the structural (pre-origin vs. post-destination) extensions of railway paths.
