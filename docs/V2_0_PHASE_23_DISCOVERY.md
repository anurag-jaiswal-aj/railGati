# V2.0 Phase 23 Discovery

## Objective
Study the existing RailGati V2.0 implementation and identify the next distinct, meaningful, and technically defensible network/station analytic capability using exclusively historical/static railway timetable data, while adhering strictly to the established ₹0 constraint.

## Existing Capability Coverage
V2.0 Analytics currently covers:
- **Topology & Nodes**: Reachability (1), Bounded Paths (2), Termini Analytics (9), O-D Bridging (22)
- **Station Metrics**: Hub Centrality (7), Station Dwells (11), Route Complexity (12), Station Similarity (16)
- **Edges & Connectivity**: Corridors (6), Edge Volume (8), Edge Asymmetry (14), Edge Transit (20)
- **Train Metrics**: Continuous Services (5), Route Similarity (15), Reversals (19), Route Profiles (21)
- **O-D Bounds**: O-D Flows (10), O-D Travel-Time (17)
- **Temporal**: Temporal Concentration (13) bins occurrences into static 4-hour chunks (Morning/Afternoon/Evening/Night).

**Remaining Capability Gap**: While Phase 13 identifies which 4-hour bucket holds the most traffic, there is no analytic evaluating the micro-temporal "rhythm" or structural "dead zones" of a station. Users cannot answer: "What is the longest continuous span of time where absolutely no trains operate from this station?"

## Candidate Analytics

### Candidate A: Network Station Topological Adjacency Analytics
- **Purpose**: Measure the direct topological branching factor of a station (node degree).
- **Exact Semantics**: Count of distinct preceding and succeeding stations across all intersecting trains.
- **Feasibility**: High. However, this is largely derivative of Phase 8 (Edge Volume) and Phase 20 (Outbound Transit), which already enumerate and evaluate adjacent outbound edges.

### Candidate B: Network Station Temporal Gap Analytics (Idle Window)
- **Purpose**: Discover the timetable "pulse" and structural "dead zones" of a station by measuring precise gaps between departures.
- **Exact Semantics**: Projects all valid departures into a single 24-hour cyclical clock, sorts them chronologically, computes the exact minute delta between consecutive departures (including the midnight wraparound gap), and isolates the maximum absolute "idle window" along with the global average interval.
- **Feasibility**: Exceptionally high. Leverages `LEAD()` window functions over the `ix_train_stops_snapshot_station` index, running in < 2ms without scanning the full timetable.

### Candidate C: Network Train Hub Intersection Analytics
- **Purpose**: Evaluate if a specific train operates as a "super-express" by measuring how many major hubs it crosses.
- **Exact Semantics**: Counts how many of the Top 50 volume-ranked stations (from Phase 7 Hub Centrality) are intersected by a single train.
- **Feasibility**: Poor. Highly derivative, requiring tight logical coupling with the Phase 7 Hub Centrality algorithm. It fails to provide a mathematically independent structural dimension.

## Candidate Feasibility Analysis
- **Candidate A** is technically sound but conceptually redundant given existing Edge-volume analytics.
- **Candidate C** is tightly coupled and derivative.
- **Candidate B** isolates a completely unaddressed dimension of timetable topology: the absolute temporal spacing of nodes. It operates with exceptional database performance (< 2ms) while avoiding `source_day` complications by explicitly collapsing operations into a 24-hour structural loop. 

## Selected Phase 23 Capability
**Network Station Temporal Gap Analytics (Idle Window)**

Explicitly supported because the timetable dataset stores precise string-encoded `departure_time` fields, enabling in-database epoch conversions and chronological window aggregations over the station's daily operational cycle.

## Exact Semantics
- **Source Snapshot**: The active timetable snapshot.
- **Station Identity**: The target station being queried.
- **Valid Departures**: All unique occurrences of a train at the target station containing a non-null `departure_time`.
- **Cyclical Clock Projection**: `source_day` is explicitly ignored. A station's operational density is evaluated on an absolute 24-hour clock cycle. (A train arriving on its own `source_day` 2 at 02:00 impacts the station's daily 02:00 rhythm identical to a train on `source_day` 1).
- **Consecutive Gap**: The difference in minutes between one departure and the chronologically next departure.
- **Midnight Wraparound Gap**: The difference between the first departure of the day (minimum time) and the last departure of the day (maximum time), calculated as `(MIN + 1440) - MAX`.
- **Maximum Idle Window**: The largest single gap identified, representing the longest continuous period without a scheduled departure.
- **Average Idle Window**: `1440.0 / NULLIF(total_departures, 0)`.
- **Repeated Visits**: If a train visits the station twice, both `departure_time` values are naturally included in the 24-hour cyclical pool.

## Data Sources and Tables
- `train_stop_observations`: Provides `snapshot_id`, `station_id`, and `departure_time`.

## Computation
The analytic uses a highly performant `LEAD` window function:
1. `departures`: Retrieves `departure_time::time` for all valid target trains via `ix_train_stops_snapshot_station`, converted to `dep_mins` (minutes from midnight).
2. `sorted_deps`: Applies `LEAD(dep_mins) OVER (ORDER BY dep_mins ASC)` to align adjacent temporal events.
3. `gaps`: Extracts `next_dep_mins - dep_mins` for all adjacent pairs, and uses a `UNION ALL` to append the midnight wrap gap: `(MIN(dep_mins) + 1440) - MAX(dep_mins)`.
4. Finally, it aggregates `MAX(gap)`.

## Proposed API Contract
**Endpoint**: `GET /api/v1/network/stations/{station_code}/temporal-gaps`

**Response Schema**:
```json
{
  "station_code": "NDLS",
  "station_name": "NEW DELHI",
  "timetable_snapshot_id": 2,
  "total_departures": 149,
  "average_idle_window_minutes": 9.7,
  "max_idle_window_minutes": 140.0
}
```

## Performance Validation
The query was validated against `NDLS` (New Delhi) and `CNB` (Kanpur Central) on active snapshot 2 in PostgreSQL:
- **Planning Time**: ~0.850 ms
- **Execution Time**: ~1.475 ms
- **Scan Types**: `ix_train_stops_snapshot_station` isolates the intersecting trains. The database performs an in-memory `WindowAgg` sort (< 50kB) across the isolated rows. No `Seq Scan` is invoked.

## Real Local Validation Results
- **NDLS**: Contains 149 valid departures. The average idle window is 9.7 minutes. The maximum idle window (structural dead zone) is exactly **140 minutes** (2 hours 20 minutes).
- **CNB**: Contains 289 valid departures. The average idle window is 5.0 minutes. The maximum idle window is exactly **40 minutes**.

## Edge Cases
- **Unknown Station**: Returns HTTP 404.
- **Isolated Station (No Trains)**: Returns HTTP 404 (no qualifying service).
- **Single Departure Station**: If a station has exactly 1 departure per 24 hours, the `max_idle_window_minutes` evaluates to exactly `1440.0` (it waits a full day for the same train).
- **Null Departures**: Terminating trains lacking a `departure_time` are explicitly excluded from the gap pool (since they do not depart).

## Limitations and Non-Claims
- This measures *structural timetable topology*. It does **not** measure live operational platform availability.
- It does **not** assert that trains actually operate on time.
- It explicitly flattens multi-day operations into a single 24-hour cyclical clock; it does not map weekly schedules.

## ₹0 Compliance
The logic relies entirely on SQL window functions running against the pre-existing, locally hosted historical timetable database, requiring zero external dependencies.

## Implementation Scope for Next Step
- No schema modifications or migrations are necessary.
- Add `TemporalGapsResponse` in `schemas.py`.
- Add `calculate_station_temporal_gaps` to `services/network.py`.
- Expose `GET /api/v1/network/stations/{station_code}/temporal-gaps` in `api/v1/network.py`.
- Write targeted API and Service tests verifying zero-division, midnight wraparound, and SQLite fallback logic.

## Discovery Conclusion
Network Station Temporal Gap Analytics (Idle Window) provides a fully distinct, highly scalable micro-temporal metric, closing the gap left by Phase 13's static macro-buckets. Discovery is complete; implementation is intentionally deferred.
