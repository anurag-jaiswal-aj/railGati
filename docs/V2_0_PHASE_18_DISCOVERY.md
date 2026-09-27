# RailGati V2.0 Phase 18 Discovery

## 1. Objective
Discover and define the next coherent Network Analytics capability for RailGati V2.0. The capability must provide a fundamentally distinct analytical dimension, leverage existing static historical timetable data without requiring graph/infrastructure changes, and strictly adhere to the ₹0 constraints.

## 2. Existing-System Context
The existing V2.0 analytics surface covers:
- **Topological & Component Analytics**: Reachability, Bounded Paths, Path Continuous Services, Network Corridors, Termini, Hub Centrality, Edge Asymmetry.
- **Volume & Flow Analytics**: Edge Volume, O-D Flow Analytics.
- **Duration & Timing Analytics**: Station Dwell Analytics (transit wait times), O-D Travel-Time Analytics.
- **Structural Analysis**: Station Route Complexity, Station Temporal Concentration.
- **Similarity Analytics**: Train Route Similarity, Station Service Similarity.

## 3. Candidates Considered
We evaluated three primary candidates for Phase 18:

**Candidate 1: Network O-D Route Diversity Analytics**
- *User/Problem*: Helps network planners determine whether historical train volume between Station A and Station B is single-path dependent or distributed across multiple topological sub-paths.
- *Overlap*: `/corridors` (Phase 7) discovers topological connectivity, but does not aggregate train occurrences by their specific distinct topological sub-paths.

**Candidate 2: Network Station Paired-Service Analytics**
- *User/Problem*: Links historically paired train schedules that terminate and originate at the same station using the `return_train_number` relationship.
- *Overlap*: Phase 11 (Station Dwell Analytics) calculates transit wait times but explicitly excludes terminal occurrences (sequence 1 and max sequence). This candidate specifically evaluates termini and links paired dataset services.

**Candidate 3: Network Concurrent Station Occupancy (Platform Utilization Proxy)**
- *User/Problem*: Identifies stations with the maximum number of simultaneously scheduled trains (overlapping arrival-departure intervals).
- *Overlap*: Phase 13 (Temporal Concentration) groups by calendar hour but does not evaluate continuous interval overlaps.

## 4. Selected Capability
**Network Station Paired-Service Analytics**

## 5. Why It Is Distinct
Unlike Station Dwells (which strictly measure scheduled transit wait time on a *single* train's continuous route), Paired-Service Analytics evaluates the scheduled clock gap between *two distinct but linked trains* at a terminal point. It utilizes a previously unused schema field (`train_observations.return_train_number`) to bridge disparate train identities, revealing the scheduled cyclic offset between paired directional services.

## 6. Exact Unit of Analysis
A terminal arrival occurrence for train A paired through `A.return_train_number` with the origin departure occurrence of train B, at the same station and within the same timetable snapshot.

## 7. Pairing Semantics
- **Arriving Service (Train A)**: A train where the target station is its final scheduled stop.
- **Departing Service (Train B)**: A train where the target station is its first scheduled stop.
- **Valid Pairing**: The arriving service's `return_train_number` exactly equals the departing service's canonical `number`.
- **Meaning of `return_train_number`**: It is a dataset-provided paired service identifier. It establishes a historical timetable pairing relationship between two scheduled trains.
- **Explicit Exclusions**: This pairing does NOT prove that the same physical trainset/rake operated both services, nor does it prove crew continuity, operational coupling, or actual turnaround behavior.

## 8. Repeated Occurrence Semantics
- Terminal occurrence is explicitly defined as `stop_sequence = MAX(stop_sequence)` for a train.
- Origin occurrence is explicitly defined as `stop_sequence = MIN(stop_sequence)` for its paired train.
- Pairing explicitly requires:
  1. The same timetable snapshot ID.
  2. The same station ID.
  3. `A.return_train_number = B.train.number`.
- Train occurrences are NOT silently deduplicated. Each train ID's unique `MAX`/`MIN` occurrence in the snapshot is preserved and linked explicitly.

## 9. Clock-Gap Semantics
Because the `source_day` field is relative to each individual train's own schedule, Train A's timeline cannot be directly compared to Train B's timeline.
We expose a **Scheduled Clock Gap** metric:
- The cyclic difference between the arriving train's clock time and the paired train's departure clock time.
- Modulo-1440 (24-hour) arithmetic is used to derive this gap.
- An exact equal clock time (0-minute gap) is preserved as exactly `0` minutes, because an equal clock time cannot legitimately be converted to 1440 minutes without an additional absolute calendar assumption.
- Ambiguities regarding whether an equal or smaller clock time implies a same-day or next-day departure are intentionally left unresolved. The metric represents purely a cyclic 24-hour clock difference.

## 10. Explicitly Unsupported Elapsed-Turnaround Semantics
This capability explicitly does **NOT** derive or report actual elapsed turnaround duration. The dataset lacks the global calendar anchoring required to resolve the absolute elapsed time between the arrival of Train A and the departure of Train B. Modulo clock arithmetic cannot establish the actual elapsed turnaround interval.

## 11. Explicitly Unsupported Physical-Rake Semantics
This capability explicitly does **NOT** claim to measure physical rolling-stock turnaround, rake utilization, or operational efficiency. The metadata connection (`return_train_number`) does not guarantee that the same physical equipment operated both services.

## 12. Snapshot Semantics
- Evaluates purely against the active timetable snapshot ID.
- Both Train A and Train B must exist within the identical active timetable snapshot.
- The station name is resolved using the active station snapshot.

## 13. Query Design
```sql
WITH termini AS (
    SELECT
        snapshot_id, train_id, station_id,
        MAX(stop_sequence) OVER (PARTITION BY snapshot_id, train_id) as max_seq,
        MIN(stop_sequence) OVER (PARTITION BY snapshot_id, train_id) as min_seq,
        stop_sequence, arrival_time, departure_time, source_day
    FROM train_stop_observations
    WHERE snapshot_id = :snapshot_id AND station_id = :station_id
),
arrivals AS (
    SELECT t.snapshot_id, t.train_id, t.station_id, t.arrival_time, t.source_day, tr.number as train_number, obs.return_train_number
    FROM termini t
    JOIN train_observations obs ON t.train_id = obs.train_id AND t.snapshot_id = obs.snapshot_id
    JOIN trains tr ON t.train_id = tr.id
    WHERE t.stop_sequence = t.max_seq AND t.arrival_time IS NOT NULL AND obs.return_train_number IS NOT NULL
),
departures AS (
    SELECT t.snapshot_id, t.train_id, t.station_id, t.departure_time, t.source_day, tr.number as train_number
    FROM termini t
    JOIN trains tr ON t.train_id = tr.id
    WHERE t.stop_sequence = t.min_seq AND t.departure_time IS NOT NULL
)
SELECT
    a.train_number as arriving_train,
    a.return_train_number as departing_train,
    a.arrival_time,
    d.departure_time,
    MOD(CAST((EXTRACT(EPOCH FROM d.departure_time::time)/60 - EXTRACT(EPOCH FROM a.arrival_time::time)/60 + 1440) AS integer), 1440) as clock_gap_mins
FROM arrivals a
JOIN departures d
  ON a.station_id = d.station_id
 AND a.return_train_number = d.train_number
 AND a.snapshot_id = d.snapshot_id
ORDER BY clock_gap_mins ASC
```

## 14. API Proposal
**Endpoint**: `GET /api/v1/network/stations/{station_code}/paired-services`

**Parameters**:
- `station_code` (Path): Canonical station code (e.g., "NDLS").

**Behavior**:
- 200 OK: Returns the paired-service analytics for the station.
- 400 Bad Request: General query failure.
- 404 Not Found: If the station code does not exist.
- 422 Unprocessable Entity: Handled by FastAPI for empty/invalid strings.
- 503 Service Unavailable: If no active timetable snapshot exists.

## 15. Response Schema
```json
{
  "station_code": "NDLS",
  "station_name": "New Delhi",
  "timetable_snapshot_id": 2,
  "paired_service_count": 138,
  "avg_clock_gap_minutes": 551.4,
  "paired_services": [
    {
      "arriving_train_number": "19023",
      "departing_train_number": "19024",
      "arrival_time": "12:45:00",
      "departure_time": "13:05:00",
      "clock_gap_minutes": 20
    }
  ]
}
```

## 16. Validation/Error Behavior
- Missing/invalid station formats trigger 422.
- A valid station with zero matched paired services returns a 200 OK with `paired_service_count: 0`, `avg_clock_gap_minutes: null`, and `paired_services: []`.

## 17. Real-Data Validation
Running the exact discovery query on active Snapshot 2 for Station `NDLS` (New Delhi):
- **Number of terminal arrival occurrences**: 149
- **Number of paired-service matches**: 138
- **Number of distinct arriving trains**: 138
- **Number of distinct paired departure trains**: 138
- **Sample Pairs**:
  - `19023` -> `19024` (Arrival: `12:45:00`, Departure: `13:05:00`, Clock Gap: `20` mins, Arr Day: `2`, Dep Day: `1`)
  - `14682` -> `14681` (Arrival: `12:50:00`, Departure: `14:50:00`, Clock Gap: `120` mins, Arr Day: `1`, Dep Day: `1`)
  - `12486` -> `12485` (Arrival: `23:20:00`, Departure: `01:40:00`, Clock Gap: `140` mins, Arr Day: `1`, Dep Day: `3`)

The relative `source_day` values show extreme divergence (e.g. Day 1 -> Day 3), proving that `source_day` timelines are independently anchored. This verifies that attempting to calculate absolute turnaround time using `source_day` is mathematically invalid without an external calendar mapping.

## 18. EXPLAIN ANALYZE Results
Execution against local PostgreSQL for Station `NDLS`:
- **Planning Time**: 0.464 ms
- **Execution Time**: 3.001 ms
- **Actual Row Counts**: 138 valid pairs.
- **Index Scans**: Exclusively uses `Index Scan using ix_train_stops_snapshot_station` efficiently narrowing rows from millions down to `233` rows.
- **Sequential Scans**: 0
- **Joins**: Uses `Nested Loop` with `Index Scans` bridging the metadata.
- **Window Functions**: Evaluated on `233` rows cleanly via QuickSort (Memory: 38kB).
- **Sort Operators**: QuickSort utilized for final order (`Memory: 34kB`).

## 19. Index Investigation
The existing `ix_train_stops_snapshot_station` explicitly triggers early filtering (`Index Cond: ((snapshot_id = 2) AND (station_id = $0))`). This prevents sequential scanning of the millions of timetable rows. The `OVER (PARTITION BY ...)` is processed entirely in-memory using mere kilobytes. No new indexes are justified.

## 20. Test Plan
- `test_api_network_paired_services_success`: Verifies standard response parsing and calculations.
- `test_api_network_paired_services_next_day`: Validates cyclic arithmetic calculation across midnight boundaries.
- `test_api_network_paired_services_exact_match`: Verifies a 0-minute calculated difference is preserved strictly as `0`.
- `test_api_network_paired_services_empty`: Ensures 200 OK with `[]` for valid stations with zero pairs.
- `test_api_network_paired_services_invalid_station`: Verifies 404 behavior.
- `test_service_network_paired_services_isolation`: Validates the logic correctly ignores matches from inactive snapshot versions.

## 21. Risks and Unresolved Questions
- **Metadata Quality**: Relies strictly on `return_train_number`. If the dataset has broken pairings, the endpoint will safely omit them, reducing volume but preserving mathematical validity.
- **Ambiguous Cycles**: A 0-minute clock gap could theoretically be a 24-hour wait or an immediate flip. The metric strictly exposes the *clock gap*, punting operational interpretation to the user.

## 22. Historical/Static Limitations
As emphasized throughout this document, this capability **cannot and does not** infer true elapsed rake turnaround times, rolling-stock equipment matching, passenger transfer viability, or operational delay propagation.
