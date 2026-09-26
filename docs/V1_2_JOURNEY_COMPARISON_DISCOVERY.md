# RailGati v1.2 — Journey Comparison Discovery

## 1. Executive Summary
RailGati v1.2 aims to provide historical journey comparison between an origin and destination station. Analysis of the existing historical Datameet timetable (v1.1) reveals that we can algorithmically deduce **direct journeys** and simple **one-transfer journeys** using deterministic rules without relying on external mapping or paid routing APIs. However, because the data is strictly historical, all comparisons must be treated as structural routing guidance rather than live, date-specific operational schedules. Multi-transfer journey routing is deferred to avoid graph traversal complexities in PostgreSQL.

## 2. Current Data Capability
The existing foundation (`DatasetSnapshot`, `Station`, `Train`, `TrainStopObservation`, `TrainObservation`) provides:
- **Station Sequence**: `stop_sequence` orders stops per train.
- **Timing**: `arrival_time` and `departure_time` strings (`HH:MM:SS` format).
- **Temporal Offset**: `source_day` indicates the relative day of the journey (1-indexed).
- **Return Linking**: `return_train_number` optionally identifies reverse directional trains.

From this we can calculate:
- **Relative Journey Duration**: `((dest_day - orig_day) * 24h) + (dest_time - orig_time)`.
- **Number of Stops**: `dest.stop_sequence - orig.stop_sequence`.
- **Direct Journeys**: By self-joining `TrainStopObservation` on the same train where origin `stop_sequence` < destination `stop_sequence`.
- **One-Transfer Possibilities**: By joining two trains intersecting at a common station, checking that Train A arrives before Train B departs.

We *cannot* reliably calculate:
- **Absolute Datetime**: Because there is no calendar mapping (e.g., "Does it run on Tuesdays?").
- **Real-time delays** or **cancellations**.

## 3. Supported vs Unsupported Features

**SUPPORTED**:
- Direct trains (Origin -> Dest on same train).
- One-transfer journeys (Origin -> Transfer -> Dest).
- Journeys crossing `source_day` boundaries.
- Same-station transfers.
- Calculating relative duration and transfer waiting times (when time/day data is present).

**DERIVABLE**:
- Return journeys (by swapping origin/destination or using `return_train_number`).

**REQUIRES MORE DATA**:
- Date-specific routing ("Trains running on 2026-10-15").
- Different-station transfers in the same city (requires geographic/metro linkage).
- Real-world transfer feasibility (requires platform data and minimum connection times).

**OUT OF SCOPE**:
- Multi-transfer journeys (>1 transfer).
- Live availability, fares, seat maps.

## 4. Time Semantics
Time must strictly be treated as *relative durations*. 
- **Time parsing**: Parse `HH:MM:SS` strings and `source_day` into a normalized minutes-from-origin-departure offset.
- **Duration Formula**: `(DayB - DayA) * 1440 + (MinuteB - MinuteA)`. 
- **Missing Data**: If `arrival_time`, `departure_time`, or `source_day` is null, the duration cannot be calculated. The journey is still returned, but `duration` is marked `null` and sorted last.
- **Midnight Crossings**: Handled intrinsically if `source_day` is properly populated (e.g., Day 1 23:30 to Day 2 01:30). If `source_day` is missing but times imply an overnight crossing, we must *not* infer it blindly; fallback to `null` duration to prevent silent errors.

## 5. Direct Journey Algorithm
A direct journey exists if:
1. `T_orig` matches `origin_code` and `T_dest` matches `destination_code`.
2. Both share the same `train_id` and `snapshot_id`.
3. `T_orig.stop_sequence < T_dest.stop_sequence`.

**Handling Duplicates**: If a train visits a station multiple times (e.g., circular routes), take the earliest `T_orig` and the first `T_dest` that occurs *after* `T_orig`.

## 6. One-Transfer Algorithm
A one-transfer journey exists if:
1. Train A connects `Origin` -> `Transfer`.
2. Train B connects `Transfer` -> `Destination`.
3. Train A != Train B.
4. **Temporal Ordering**: `Train B departure at Transfer` > `Train A arrival at Transfer`.
5. **Transfer Buffer**: To prevent impossible 1-minute connections, a configurable conservative buffer (e.g., `minimum_transfer_minutes=120`) is applied algorithmically. `(Train B dep - Train A arr) >= 120`. 
6. **Maximum Layover**: Filter out layovers exceeding 24 hours to prune noise.

## 7. Multi-Transfer Decision
**Decision: OUT OF SCOPE for v1.2.**
Multi-transfer (2+) introduces exponential path explosion. In a relational database, this requires recursive CTEs or a dedicated graph database, causing severe performance degradation for a historical dataset. It should be deferred to a later graph-based version (e.g., v2.0).

## 8. Graph Architecture Decision
**Decision: NO GRAPH DATABASE REQUIRED.**
For 0-transfer and 1-transfer lookups, PostgreSQL handles standard relational joins efficiently. Introducing Neo4j/RedisGraph violates the architectural constraint (simplicity, ₹0, modular-monolith) without providing necessary value for v1.2. Graph structures will remain purely an application-level abstraction in Python.

## 9. Journey Comparison Model
Output fields for a Journey (Direct or Transfer):
- `journey_id`: Algorithmic hash for UI keys.
- `type`: `DIRECT` or `ONE_TRANSFER`.
- `legs`: Array of train segments.
  - `train_number`, `train_name`, `train_type`.
  - `origin_station`, `destination_station`.
  - `departure_time`, `arrival_time`, `source_day_offset`.
  - `duration_minutes` (if calculable).
- `total_duration_minutes`: Sum of leg durations + transfer times.
- `transfers`: Array of `station_code` and `layover_minutes`.
- `timing_confidence`: Enum (`HIGH`, `MISSING_DATA`).

## 10. Sorting/Comparison Dimensions
No single journey is "best." The API will return all valid journeys and let the frontend sort.
**Default Sort**:
1. `type` (`DIRECT` before `ONE_TRANSFER`).
2. `total_duration_minutes` (ASC, nulls last).
3. `departure_time` (ASC).

Other dimensions exposed to UI: Fewest stops, Earliest departure. Subjective labels like "Recommended" are forbidden.

## 11. Proposed API Contract
`GET /api/v1/journeys/compare`
**Parameters**:
- `source`: string (station code)
- `destination`: string (station code)
- `max_transfers`: int (default 0, max 1)
- `min_transfer_minutes`: int (default 120)
*Note: `date` is explicitly omitted because the data is historical.*

**Response**: `PaginatedResponse[JourneyOption]` containing the structure defined in Section 9.

## 12. Edge Cases
- **Origin == Destination**: Return 400 Bad Request.
- **Unknown Station**: Return 404 Not Found.
- **Null Arrival/Departure/Day**: Calculate route structurally, set `duration=null`, `timing_confidence=MISSING_DATA`.
- **Transfer at Origin/Dest**: Filtered out (Leg A or B must have > 0 stops).
- **Multiple Transfer Stations for Same Trains**: Select the one yielding the shortest layover.
- **Circular/Duplicate Stops**: Handled by strict `stop_sequence` inequality checks.

## 13. Performance Analysis
- ~5,207 trains, ~417,070 stops.
- **Direct Search**: Fast. `JOIN train_stop_observations t1, train_stop_observations t2` on `train_id`. Expected <50ms.
- **One-Transfer Search**: Slower. Requires joining `t1` (origin), `t2` (transfer), `t3` (transfer), `t4` (destination). Expected 100-300ms.
- **Optimization**: Standard B-Tree indices on PostgreSQL are sufficient. Caching/Redis is not required for this dataset size.

## 14. Index Requirements
To support fast self-joins in PostgreSQL, the following composite indexes are required in v1.2 migrations:
- `ix_train_stops_snapshot_station` on `(snapshot_id, station_id)`
- `ix_train_stops_snapshot_train_seq` on `(snapshot_id, train_id, stop_sequence)`

## 15. Data Source Requirements
v1.2 can be implemented entirely using the existing Datameet historical dataset.
**Explicitly Unavailable**: Date-specific scheduling, live status, fares, seat availability.

## 16. ₹0 Compliance
All logic runs purely in Python/PostgreSQL. No external APIs (Google Maps, IRCTC, etc.), no LLMs, and no paid DB extensions are required.

## 17. Version Boundary
- **v1.2**: Direct and 1-transfer historical journey comparison (PostgreSQL).
- **v2.0**: Multi-transfer Journey Graph (In-memory routing / GraphDB).
- **v2.X**: Live data, analytics, predictions (Deferred until open-data sources are secured).

## 18. Implementation Plan
- **Step 1**: Create v1.2 Pydantic models (`JourneyOption`, `JourneyLeg`).
- **Step 2**: Implement index migration for `TrainStopObservation`.
- **Step 3**: Implement `DirectJourneyQuery` service logic.
- **Step 4**: Implement `OneTransferJourneyQuery` service logic (with configurable buffers).
- **Step 5**: Implement `GET /api/v1/journeys/compare` endpoint.
- **Step 6**: Test cases (direct, transfer, missing times, circular).
- **Step 7**: Performance verification.

## 19. Risks / Open Questions
- **One-Transfer Volume**: A heavily connected transfer hub (e.g., NDLS) might yield thousands of technically valid but impractical one-transfer combinations. Result pruning (limiting to top 50 fastest layovers) may be required.
- **Data Quality**: If Datameet `source_day` is heavily flawed, transfer calculations will degrade to `MISSING_DATA`. 

## 20. Final Scope Recommendation
Proceed with v1.2 Journey Comparison scoped strictly to **Direct** and **One-Transfer** historical routes. Exclude date parameters. Exclude subjective ranking. Implement entirely over PostgreSQL without adding graph database infrastructure. Add API warnings that the schedule is historically illustrative, not operationally guaranteed.
