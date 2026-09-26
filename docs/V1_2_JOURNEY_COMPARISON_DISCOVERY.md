# RailGati v1.2 — Journey Comparison Discovery

## 1. Executive Summary
RailGati v1.2 aims to provide historical journey comparison between an origin and destination station. Analysis of the existing historical Datameet timetable (v1.1) reveals that we can algorithmically deduce **direct journeys** and simple **one-transfer journeys** using deterministic rules without relying on external mapping or paid routing APIs. However, because the data is strictly historical, all comparisons must be treated as structural routing guidance rather than live, date-specific operational schedules. Multi-transfer journey routing is deferred to avoid algorithmic complexities in PostgreSQL.

## 2. Current Data Capability
The existing foundation (`DatasetSnapshot`, `Station`, `Train`, `TrainStopObservation`, `TrainObservation`) provides:
- **VERIFIED Station Sequence**: `stop_sequence` orders stops per train.
- **VERIFIED Timing**: `arrival_time` and `departure_time` strings (`HH:MM:SS` format).
- **VERIFIED Temporal Offset**: `source_day` indicates the relative day of the journey (1-indexed).
- **VERIFIED Return Linking**: `return_train_number` optionally identifies reverse directional trains as metadata (not a prerequisite for discovering reverse journeys).

From this we can calculate:
- **DERIVED Relative Journey Duration**: `((dest_day - orig_day) * 24h) + (dest_time - orig_time)`.
- **DERIVED Number of Stops**: `dest.stop_sequence - orig.stop_sequence`.
- **DERIVED Direct Journeys**: By self-joining `TrainStopObservation` on the same train where origin `stop_sequence` < destination `stop_sequence`.
- **DERIVED One-Transfer Possibilities**: By joining two trains intersecting at a common station, checking that Train A arrives before Train B departs.

## 3. Supported vs Unsupported Features

**SUPPORTED** (Can be implemented using currently verified data and deterministic algorithms. Does not imply operational validity or guaranteed connections):
- Direct trains (Origin -> Dest on same train).
- One-transfer journeys (Origin -> Transfer -> Dest).
- Journeys crossing `source_day` boundaries.
- Same-station transfers.
- Calculating relative duration and transfer waiting times (when time/day data is present).

**DERIVABLE**:
- Return journeys (by swapping origin/destination or referring to `return_train_number` where paired directional services are identified).

**UNAVAILABLE** (Requires data that RailGati does not currently possess):
- Date-specific routing ("Trains running on 2026-10-15").
- Different-station transfers in the same city (requires geographic/metro linkage).
- Real-world transfer feasibility (requires platform data and minimum connection times).
- Live availability, fares, seat maps.

**OUT OF SCOPE**:
- Multi-transfer journeys (>1 transfer).

## 4. Time Semantics
Time must strictly be treated as *relative durations*. 
- **VERIFIED Parsing**: Parse `HH:MM:SS` strings.
- **ASSUMPTION Source Day**: `source_day` is preserved directly from the source. The implementation must not invent absolute calendar dates.
- **Duration Preconditions**: Duration calculations are valid only when the relevant `source_day` and time fields provide sufficient information. Source day behavior must be validated against representative real records.
- **Missing Data**: Null or inconsistent temporal data must produce unavailable timing rather than fabricated timing. A structurally valid route is not necessarily a temporally comparable route.

## 5. Direct Journey Algorithm
A direct journey exists if:
1. `T_orig` matches `origin_code` and `T_dest` matches `destination_code`.
2. Both share the same `train_id` and `snapshot_id`.
3. `T_orig.stop_sequence < T_dest.stop_sequence`.

**ASSUMPTION Handling Duplicates**: If a train visits a station multiple times (e.g., circular routes), take the earliest `T_orig` and the first `T_dest` that occurs *after* `T_orig`.

## 6. One-Transfer Algorithm
**STATUS: IMPLEMENTED**
The query foundation for historical one-transfer journeys is now implemented.
A one-transfer journey exists if:
1. Train A connects `Origin` -> `Transfer`.
2. Train B connects `Transfer` -> `Destination`.
3. Train A != Train B.
4. **Different-Station Transfers**: Unsupported. Train A and Train B must transfer at the exact same canonical station.
5. **Temporal Ordering**: `Train B departure at Transfer` > `Train A arrival at Transfer`.
6. **Transfer Occurrence Identity**: A distinct one-transfer path is strictly identified by `(train_a.id, train_a.transfer_stop_sequence, transfer_station.id, train_b.id, train_b.transfer_stop_sequence)`. If a train visits the same transfer station multiple times, each valid occurrence combination is preserved as a distinct journey option.
7. **Missing Temporal Information**: If any required temporal field (`arrival_time`, `departure_time`, or `source_day`) at the transfer station is missing, the connection cannot be temporally validated and is explicitly excluded.
8. **ASSUMPTION Transfer Buffer**: The minimum transfer time is an algorithmic configurable assumption (default 120 minutes), not an Indian Railways operational guarantee. Real-world connections are not guaranteed operationally.
9. **ASSUMPTION Maximum Layover**: The maximum layover is an algorithmic pruning/business rule (default 1440 minutes) to avoid presenting extremely long waits as useful comparisons. It is not an operational railway rule.
10. **Multi-Transfer Routing**: Remains strictly OUT OF SCOPE.

## 7. Multi-Transfer Decision
**Decision: OUT OF SCOPE for v1.2.**
Multi-transfer routing substantially increases algorithmic complexity. It requires path search/state management, stronger temporal/path constraints, and increases candidate-path explosion as transfer depth grows. It is better handled as a dedicated graph/routing milestone in the future (e.g., v2.0).

## 8. Graph Architecture Decision
**Decision: NO GRAPH DATABASE REQUIRED.**
PostgreSQL remains the source of truth. Direct and one-transfer queries can be implemented relationally without severe overhead. Application-level routing abstractions are acceptable at this stage. A later graph/routing layer can be introduced when multi-transfer routing actually requires it.

## 9. Journey Comparison Model
Output fields for a Journey (Direct or Transfer):
- `journey_id`: Algorithmic hash for UI keys.
- `type`: `DIRECT` or `ONE_TRANSFER`.
- `legs`: Array of train segments.
- `total_duration_minutes`: Sum of leg durations + transfer times (if calculable).
- `timing_confidence`: Enum (`HIGH`, `MISSING_DATA`).

**Duration Semantics**: 
- For a direct journey, duration is calculable only when the relevant origin departure and destination arrival timing information is available and temporally interpretable.
- For a transfer journey, total duration requires: first-leg departure, transfer arrival, second-leg departure, final destination arrival.
- If required temporal information is missing or ambiguous, do not fabricate duration. Preserve structural journey information where possible and mark calculated timing unavailable (`MISSING_DATA`).

## 10. Sorting/Comparison Dimensions
**STATUS: IMPLEMENTED**
The combined comparison service combines direct and one-transfer journeys (when `max_transfers=1`) and sorts them deterministically. No arbitrary pruning or result truncation is applied; all valid structural candidates are returned.

No single journey is "best." The backend returns all valid journeys deterministically sorted, letting the frontend resort if necessary. Missing durations are handled explicitly and do not crash sorting.

**Deterministic Combined Sort**:
1. `total_duration_minutes` (ASC, nulls last).
2. `departure_time` (ASC, nulls last).
3. `type` (`DIRECT` before `ONE_TRANSFER`).
4. `train_a_number`, `train_b_number`, `journey_id` (ASC) as a deterministic tie-breaker.

**ASSUMPTION**: This default ordering is merely a product/API convention to guarantee stable results across identical requests. It is not a claim that a specific journey is universally preferable, nor is it a recommendation or "best journey" ranking. Missing data explicitly sinks to the bottom of duration sorts but remains available. Every distinct journey occurrence retains its unique `journey_id`.

## 11. Proposed API Contract
**STATUS: IMPLEMENTED**
`GET /api/v1/journeys/compare`
**Parameters**:
- `source`: string (canonical station code, required)
- `destination`: string (canonical station code, required)
- `max_transfers`: int (default 0, constrained to 0 or 1 in v1.2)
- `min_transfer_minutes`: int (default 120, >= 0)
- `max_layover_minutes`: int (default 1440, >= 0, >= min_transfer_minutes)

**Response Shape**: Returns a JSON object with `source`, `destination`, `timetable_snapshot_id`, `max_transfers`, and an array of `journeys` (each representing a `JourneyOption` schema). Validations map to explicit HTTP 400, 404, or 422 errors.

*Note: `date` is intentionally unsupported because the current dataset does not provide sufficient verified calendar validity. The endpoint exposes historical structural journey options and does NOT answer "which train runs today?". No live running status, date-specific guarantees, or fare/seat information is provided.*

## 12. Edge Cases
- **Origin == Destination**: Return 400 Bad Request.
- **Null Arrival/Departure/Day**: Calculate route structurally, set `duration=null`, `timing_confidence=MISSING_DATA`.
- **Transfer at Origin/Dest**: Filtered out (Leg A or B must have > 0 stops).

## 13. Performance Analysis
- ~5,207 trains, ~417,070 stops.
- **TARGET Direct Search**: Benchmark direct journey queries against the real local dataset. Record actual latency.
- **TARGET One-Transfer Search**: Benchmark one-transfer queries against the real local dataset. Record actual latency. Use the results to determine whether additional indexes or pruning are necessary.

## 14. Index Requirements
**TARGET**: Determine index optimizations based on query benchmarks. Possible composite indexes:
- `ix_train_stops_snapshot_station` on `(snapshot_id, station_id)`
- `ix_train_stops_snapshot_train_seq` on `(snapshot_id, train_id, stop_sequence)`

## 15. Data Source Requirements
v1.2 can be implemented entirely using the existing Datameet historical dataset.
**UNAVAILABLE**: Date-specific scheduling, live status, fares, seat availability.

## 16. ₹0 Compliance
All logic runs purely in Python/PostgreSQL. No paid external APIs are required.

## 17. Version Boundary
- **v1.2**: Direct and 1-transfer historical journey comparison (PostgreSQL).
- **v2.0**: Broader railway graph/routing (Multi-transfer routing).

## 18. Implementation Plan
- **Step 1**: Create v1.2 Pydantic models.
- **Step 2**: Implement `DirectJourneyQuery` service logic and benchmark.
- **Step 3**: Implement `OneTransferJourneyQuery` service logic (with configurable buffers) and benchmark.
- **Step 4**: Apply required indexes and pruning based on benchmark results.
- **Step 5**: Implement `GET /api/v1/journeys/compare` endpoint.

## 19. Risks / Open Questions
- **One-Transfer Volume**: One-transfer candidate volume must be measured against the real dataset. The implementation must prevent uncontrolled result explosion. Deterministic pruning/pagination may be introduced if benchmark results justify it, and any pruning policy must be documented and deterministic.
- **Data Quality**: If Datameet `source_day` is heavily flawed, transfer calculations will degrade to `MISSING_DATA`.

## 20. Final Scope Recommendation
Proceed with v1.2:
- direct historical journey comparison
- one-transfer historical journey comparison
- relative timing where sufficiently supported
- explicit missing-data handling
- deterministic comparison
- PostgreSQL-based implementation
- ₹0 compliant

Not v1.2:
- live status
- current-date timetable validity
- live cancellations
- live fares
- live seat availability
- guaranteed connections
- multi-transfer routing
- subjective recommendation engine
- ML prediction
