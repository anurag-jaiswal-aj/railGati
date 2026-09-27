# v2.0 Phase 9 Discovery: Network Terminus Analytics

**STATUS:** DISCOVERY ONLY.
**IMPLEMENTATION:** DEFERRED.

## 1. Problem Statement
RailGati currently possesses macroscopic network graph capabilities including Corridor Analytics (Phase 6), Node Hub Centrality (Phase 7), and Segment Edge Volume (Phase 8). Phase 7 Hub Centrality successfully identifies the busiest transit hubs by summing *all* adjacent service occurrences (both passing through and stopping). However, this fails to distinguish between heavy intermediate transit hubs and true structural **termini**—stations where historical train occurrences absolutely originate or terminate in the timetable. Analytical systems need to identify the network's structural endpoints without conflating them with mere high-throughput intermediate nodes.

## 2. User / Product Purpose
To expose the historical stations that act as the primary generating sources and sinks of the active railway timetable snapshot. This provides intelligence on network generation and consumption points, isolating actual journey boundaries from simple transit topology.

## 3. Terminology: Terminus vs Network Source/Sink
This capability identifies the first and final observed timetable stops of historical train occurrences. It is strictly "Network Terminus Analytics". It does NOT prove a graph-theoretic source or sink, an operational physical terminal, or a station where a train currently originates/terminates. These are strictly historical timetable occurrence boundaries.

## 4. Explicit Scope
- Create a new endpoint `GET /api/v1/network/termini` to return stations ranked by their historical terminus occurrence volume.
- Compute the absolute starting and ending stops for all train occurrences within exactly one active timetable snapshot.
- Restrict logic strictly to the active `DatasetSnapshot`.
- Ensure strict ₹0 compatibility using pure PostgreSQL execution.

## 5. Explicit Non-Goals
- **Live Operations:** Does not track current train schedules, cancellations, delays, or dynamic platform assignments.
- **Passenger Demand:** Terminus occurrences do not equate to passenger counts, boarding volume, or alighting volume.
- **Physical Capacity:** Does not infer the number of physical platforms, yard lines, or physical track capacity.
- **Distinct Trains:** The metric tracks historical *occurrences*, not unique physical train sets.
- **Current Operational Frequency:** Does not claim live train frequency.

## 6. Existing Models Reused
- `TrainStopObservation`
- `Station`
- `StationObservation`
- `DatasetSnapshot`

*(Note: `RailwayGraphBuild` and `RailwayNetworkEdge` are NOT required. This analytics derives purely from timetable boundary data, not recursive graph topology).*

## 7. Hardened Snapshot Semantics
The query MUST operate against exactly one active timetable snapshot.
For a given timetable snapshot `S`:
- The first stop of train `T` is the `MIN(stop_sequence)` among `TrainStopObservation` rows where `snapshot_id = S` and `train_id = T`.
- The last stop of train `T` is the `MAX(stop_sequence)` among `TrainStopObservation` rows where `snapshot_id = S` and `train_id = T`.

**CRITICAL RULE:** All terminus calculations MUST remain inside the same timetable snapshot. The canonical `Train` identity spans snapshots, but `TrainStopObservation` is snapshot-bound. Allowing cross-snapshot aggregation would dangerously corrupt the bounds. The derivation query MUST explicitly filter `WHERE snapshot_id = :active_timetable_snapshot_id`.

## 8. Exact Occurrence Semantics
- **Originating Count (`originating_count`)**: The number of train timetable occurrences whose first observed stop in the selected timetable snapshot is this station.
- **Terminating Count (`terminating_count`)**: The number of train timetable occurrences whose last observed stop in the selected timetable snapshot is this station.
- **Total Terminus Volume (`total_terminus_volume`)**: `originating_count + terminating_count`.

These are historical timetable occurrence-boundary counts. A single train occurrence may contribute exactly one originating count and one terminating count, meaning `total_terminus_volume` counts both ends of the same historical train occurrence.

## 9. Repeated Stations & Return Train Semantics
- **Repeated Stations / Loops:** A train may visit the same canonical station multiple times. The first occurrence is determined *exclusively* by the absolute minimum `stop_sequence`. The final occurrence is determined *exclusively* by the absolute maximum `stop_sequence`. The implementation MUST NOT group merely by station code, collapse repeated station visits, or assume an intermediate visit constitutes an origin/terminus.
- **Return Train Semantics:** `return_train_number` is ignored for counting purposes. Each train observation is counted independently. The implementation MUST explicitly avoid merging paired directional trains. This preserves existing RailGati occurrence semantics where each bound direction is a distinct historical occurrence.

## 10. Graph-Build Dependency Decision
**DECISION:** `RailwayGraphBuild` dependency is **REMOVED**.
*Justification:* The proposed terminus metrics derive fundamentally from `TrainStopObservation` boundaries and `Station` metadata. They do not require `RailwayNetworkEdge` or graph traversal. Terminus analytics is timetable-derived, not graph-derived. Requiring an `ACTIVE` graph build would create an unnecessary blocking dependency; therefore, the API will NOT return a 503 merely because a graph build is missing or `INACTIVE`, provided the timetable snapshot exists.

## 11. Active Station Metadata
Station metadata is resolved using the active station snapshot. The canonical `Station` identity remains separate from `StationObservation`.
- No metadata leakage from older snapshots is permitted.
- If a station has no metadata in the active station snapshot, the standard project INNER JOIN behavior applies: the station is safely excluded from the response.

## 12. Proposed API
**Endpoint:** `GET /api/v1/network/termini`
**Method:** GET

**Query Parameters:**
- `limit` (integer, default 50, min 1, max 500). *Note: LIMIT is an output bound pushed to PostgreSQL; it does not limit the intermediate grouping/derivation work.*

**Sort Semantics (Deterministic):**
- `total_terminus_volume DESC`
- `originating_count DESC`
- `terminating_count DESC`
- `station_code ASC`

**Response Structure:**
```json
{
  "timetable_snapshot_id": 2,
  "termini": [
    {
      "station_code": "HWH",
      "station_name": "Howrah Junction",
      "originating_count": 136,
      "terminating_count": 127,
      "total_terminus_volume": 263
    }
  ]
}
```

## 13. Query Strategy
The database strategy ensures safety and efficiency without precomputing across all snapshots or N+1 fetching:
1. Resolve the active timetable snapshot and active station snapshot.
2. Derive per-(snapshot, train_id) `MIN` and `MAX` `stop_sequence` directly in SQL filtering strictly by the active timetable snapshot.
3. Map those boundary stop occurrences to `station_id`.
4. Aggregate `originating_count` and `terminating_count` by station.
5. `INNER JOIN` to active `station_observations` to resolve canonical metadata.
6. Apply deterministic `ORDER BY` and `LIMIT` within PostgreSQL.

## 14. Performance Discovery Methodology
The implementation must eventually benchmark the actual active dataset. Performance conclusions will be stated strictly as measured observations on the current dataset.
Require `EXPLAIN ANALYZE` measuring:
- Planning time and Execution time.
- `TrainStopObservation` scan behavior.
- `GROUP BY` and join strategy.
- Sort strategy and memory usage.
- Rows processed vs rows returned.
- Index usage.

*(Note: Prior exploratory queries indicating ~16ms execution via Top-N heapsort merely prove current-dataset feasibility, not universal infinite scalability).*

## 15. Test Discovery
Focused tests must be implemented covering the following cases:

**SERVICE TESTS:**
1. Normal origin/terminus counts correctly derived.
2. Origin is not counted as terminus unless it is also the final stop.
3. Transit station is not counted as origin/terminus.
4. Repeated station visits do not artificially inflate terminus bounds.
5. Minimum `stop_sequence` determines origin.
6. Maximum `stop_sequence` determines terminus.
7. Snapshot isolation (inactive snapshot data cannot bleed).
8. Reverse-direction/paired train behavior (treated as independent).
9. Empty timetable yields empty results.
10. Deterministic ordering correctly applies tie-breakers.
11. Limit behavior safely restricts output.
12. Missing/incomplete stop data behavior (trains with <2 stops).

**API TESTS:**
1. Default limit respects 50.
2. Explicit limits are respected.
3. Limit 0 yields HTTP 422.
4. Limit 501 yields HTTP 422.
5. Empty result returns HTTP 200 with an empty list.
6. Active station metadata isolation.
7. Snapshot isolation verified.
8. Deterministic ordering verified.

*(Unknown/invalid station behavior is excluded as the endpoint does not accept station filters).*

## 16. Limitations & Future Extensions
- **Limitations:** Only measures static, historical timetable schedules. Terminus volume does not correlate with live operational frequency.
- **Future Extensions:** Time-bounded terminus analytics.

*(End of Discovery)*
