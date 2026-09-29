# V2.0 Phase 53 Discovery: Network Station Peak Simultaneous Presence Analytics

## Objective
Discover a genuinely new, non-derivative railway-network analytics capability using the existing historical Datameet timetable dataset. This metric must evaluate relationships distinct from all 52 prior phases while adhering to strict zero-budget, PostgreSQL-only constraints.

## Proposed Capability
**Network Station Peak Simultaneous Presence Analytics**

This capability analyzes the maximum number of trains concurrently occupying a specific station at any given moment in the timetable schedule. By synthesizing `source_day`, `arrival_time`, and `departure_time` into a unified absolute timeline, this metric maps all station dwells as overlapping intervals and computes the absolute peak scheduled contention (simultaneous presence) required by the static timetable.

## Endpoint
`GET /api/v1/network/stations/{station_code}/simultaneous-presence`

## Exact Semantics

### Mathematical & Operational Definition
For a given station $S$ in the active snapshot, let $O$ be the set of all train stop observations at $S$.
For each observation $o \in O$, we define an absolute arrival minute and departure minute relative to the train's origin:
1. $arr_{raw} = \text{COALESCE}(o.arrival\_time, o.departure\_time)$
2. $dep_{raw} = \text{COALESCE}(o.departure\_time, o.arrival\_time)$
3. $arr_{min} = (o.source\_day \times 1440) + \text{minutes}(arr_{raw})$
4. $dep_{min} = (o.source\_day \times 1440) + \text{minutes}(dep_{raw}) + (1440 \text{ if } dep_{raw} < arr_{raw} \text{ else } 0)$

We expand each observation into two events:
- Arrival event: $(Time = arr_{min}, Weight = +1, TrainID = o.train\_id)$
- Departure event: $(Time = dep_{min}, Weight = -1, TrainID = o.train\_id)$

The events are strictly sorted by $Time$ ASC, then $Weight$ DESC (to ensure instantaneous +1/-1 arrivals at terminals are counted sequentially without zeroing out prematurely), and finally by $TrainID$ ASC for determinism.
The `peak_simultaneous_trains` is the mathematical `MAX` of the cumulative sum of $Weight$ across the sorted event stream.

### Row/Occurrence Identity
- Identity is established strictly per `train_id` per `station_id` within the boundaries of the active `snapshot_id` inside `train_stop_observations`.

### Edge Cases & Behaviors
- **Missing Resource:** HTTP 404 if the station code does not exist.
- **Terminal Stations:** Trains originating or terminating at $S$ have missing arrival or departure times. The `COALESCE` logic safely bounds them into instantaneous (0-minute) dwells, successfully registering a $+1$ concurrent presence during that exact minute without breaking the interval math.
- **Zero Traversals:** If the station exists but has no scheduled trains, returns HTTP 200 with counts = 0.
- **Snapshot Isolation:** Events are exclusively sourced from the active dataset snapshot ID.
- **Cross-Midnight Dwells:** Correctly managed by adding $1440$ minutes to the departure time if $dep_{raw} < arr_{raw}$.

## Distinction from Prior Phases
This metric is fundamentally novel because it measures **temporal convergence/overlap**, which is absent from prior analytics:
1. **vs. Phase 32 (Station Temporal Gaps):** Phase 32 calculates the time elapsed *between* consecutive departures. It does not measure the continuous overlap or concurrent accumulation of trains.
2. **vs. Phase 18 (Station Dwell Analytics):** Phase 18 aggregates the duration of individual dwells (e.g. average dwell time). It treats trains independently and ignores whether their dwells intersect on the clock.
3. **vs. Phase 46 (Intermediate Flow Concentration):** Phase 46 measures topological bottlenecking (total volume of trains passing through). It is entirely decoupled from the time domain and overlaps.

## Database Sources
- `train_stop_observations` (`snapshot_id`, `station_id`, `train_id`, `source_day`, `arrival_time`, `departure_time`)
- `stations` (`id`, `code`)
- **Timing data IS required** (`source_day`, `arrival_time`, `departure_time`) to compute the absolute temporal intervals.

## Snapshot 2 Observations (Real Database Execution)

| Station | Type | Total Scheduled Trains | Peak Simultaneous Trains |
|---------|------|------------------------|--------------------------|
| PUNE    | Normal/Hub | 181 | 11 |
| CNB     | Major Hub | 298 | 10 |
| NDLS    | Major Hub | 233 | 7 |
| LTT     | Terminal | 183 | 6 |
| BCT     | Terminal | 46 | 2 |

## Performance Assessment
A fresh `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` run against the live Snapshot 2 dataset for station `CNB` (Kanpur Central) yielded:
- **Planning Time:** 1.285 ms
- **Execution Time:** 3.181 ms
- **Total Cost:** 11.64
- **Major Strategy:** Dual CTE Scan appending into a `WindowAgg` running an ordered `SUM(change) OVER (...)`. Highly performant in-memory quicksort execution without disk-based temp files.

## Semantic Limitations (Strict Constraints)
- **NOT Physical Infrastructure:** A peak presence of 11 trains at PUNE does *not* mean PUNE has 11 physical platforms. It strictly means the published timetable schedules 11 trains to intersect at that minute.
- **NOT Congestion:** Does not account for real-world delays, signal failures, or physical operational congestion.

## Proposed Response Schema
```json
{
  "station_code": "str",
  "timetable_snapshot_id": "int",
  "total_qualifying_trains": "int",
  "peak_simultaneous_trains": "int"
}
```

## Implementation Recommendation
**APPROVE DISCOVERY**. The metric successfully models overlapping scheduled intervals natively in Postgres via CTE window functions, running in under 5ms. It introduces a vital, novel capacity-planning dimension (peak concurrent timetable pressure) without duplicating topological flow or gap metrics.
