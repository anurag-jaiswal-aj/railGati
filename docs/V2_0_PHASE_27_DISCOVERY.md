# V2.0 Phase 27 Discovery: Network Train Structural Halt Analytics

## 1. Objective
Discover and define a new, genuinely distinct historical timetable analytics capability for RailGati (V2.0 Phase 27). The capability must not overlap with Phase 1–26, must rely purely on historical PostgreSQL schedule data without external APIs, and must have rigid dataset-derived semantics.

## 2. Capabilities Inspected & V2.0 Coverage Matrix
- **Phase 11 (Station Dwell)**: Computes global average dwells at a specific station across *all* transiting trains.
- **Phase 21 (Route Profile)**: Computes a train's total route duration and *total* aggregate dwell.
- **Phase 14, 15, 17, 18, 19, 20, 22, 23, 24, 25, 26**: All validated to ensure no overlap regarding train-specific scheduled internal structural stops.

## 3. Candidates Considered

### Candidate A: Network Train Structural Halt Analytics (Selected)
- **Concept**: Analyzes a single train's scheduled route to identify and rank the intermediate stations where the train has the longest scheduled dwell times.
- **Usefulness**: Structurally isolates scheduled structural/timetable dwell nodes for a specific train route.
- **Unit**: Train.

### Candidate B: Network Train Scheduled Day-Boundary Analytics (Rejected)
- **Concept**: Groups a train's progression by `source_day` to find the exact first and last station reached per scheduled day.
- **Reason for Rejection**: Real Snapshot 2 validation reveals that intermediate non-passenger/non-passenger observations frequently omit `source_day` (e.g. `source_day IS NULL` for 102 stops on Vivek Express 15905). This breaks contiguous day-boundary aggregations, making the metric unreliable without heavy data imputation, which violates strict historical dataset rules.

### Candidate C: Network Train Topological Convergence Analytics (Rejected)
- **Concept**: Finds the exact sequence of overlapping stations (first shared, last shared) between two specific train services.
- **Reason for Rejection**: Conceptually overlaps with Phase 15 (Route Similarity), which already measures topological intersection via the Jaccard index. Furthermore, querying exact topological sub-paths is fragile against minor non-passenger-stop deviations.

### Candidate D: Station Express Bypass Analytics (Rejected)
- **Concept**: Identifies trains that travel from station A to station C without stopping at an intermediate station B (where B is topologically between A and C on other services).
- **Reason for Rejection**: The timetable is a logical scheduled-service graph, not a physical geometric graph. Bypassing B logically does not guarantee physical tracking through B, making "bypass" claims geometrically unprovable from timetable data alone.

---

## 4. Selected Phase 27 Capability: Network Train Structural Halt Analytics

### 4.1 Exact Semantics & Constraints
- Evaluates a single canonical train within the active timetable snapshot.
- Considers ONLY intermediate stops (strictly excludes the structural origin and destination, as terminus dwells are inherently infinite/undefined).
- Requires `arrival_time` and `departure_time` to be present.
- Safely calculates cross-midnight intermediate halts using `+ 86400 seconds` where `departure_time < arrival_time`, adhering exactly to Phase 11 proven semantics.
- Ranks the stations by dwell time descending.
- A valid train with no qualifying intermediate stops (e.g., a direct non-stop service with only 2 stations) gracefully returns an empty list.

### 4.2 Semantic Guardrails
- **DO NOT** claim these are guaranteed physical stops on the current live railway.
- **DO NOT** claim these are locations where passengers board/alight.
- **DO NOT** claim any operational reason for a dwell. It is simply a "scheduled structural/timetable dwell".

### 4.3 Real Snapshot 2 Validation
Querying the raw Snapshot 2 dataset for long-distance trains proves the capability:

**Vivek Express (15905)**:
- Durgapur (DGR): 40 mins
- Vijayawada (BZA): 20 mins
- New Jalpaiguri (NJP): 15 mins
- Guwahati (GHY): 15 mins
These perfectly map the scheduled structural halts on this 4-day route.

**Shatabdi Express (12004)**:
- Kanpur (CNB): 5 mins
- Etawah (ETW): 2 mins
This perfectly maps the short 2–5 minute halts typical of premium express routes.

### 4.4 API Contract
**Method/Endpoint:**
`GET /api/v1/network/trains/{train_number}/structural-halts`

**Path Parameters:**
- `train_number` (string)

**Query Parameters:**
- `limit` (int, default=10, max=50)

**Response:**
```json
{
  "train_number": "15905",
  "timetable_snapshot_id": 2,
  "halts": [
    {
      "station_code": "DGR",
      "dwell_minutes": 40.0
    },
    {
      "station_code": "BZA",
      "dwell_minutes": 20.0
    }
  ]
}
```

### 4.5 Query Strategy
```sql
SELECT s.code as station_code, 
       (EXTRACT(EPOCH FROM tso.departure_time::time) - EXTRACT(EPOCH FROM tso.arrival_time::time) +
        CASE WHEN EXTRACT(EPOCH FROM tso.departure_time::time) < EXTRACT(EPOCH FROM tso.arrival_time::time)
             THEN 86400 ELSE 0 END)/60 as dwell_minutes
FROM train_stop_observations tso
JOIN stations s ON s.id = tso.station_id
WHERE tso.snapshot_id = :snapshot_id 
  AND tso.train_id = :train_id
  AND tso.arrival_time IS NOT NULL AND tso.departure_time IS NOT NULL
  AND tso.stop_sequence > :min_sequence
  AND tso.stop_sequence < :max_sequence
ORDER BY dwell_minutes DESC, s.code ASC
LIMIT :limit;
```
*(Note: `min_sequence` and `max_sequence` are extracted first for the train).*

### 4.6 Performance Measurement (EXPLAIN ANALYZE)
Tested exact proposed query for Train 15905:
- **Planning Time**: 1.947 ms
- **Execution Time**: 2.506 ms
- **Scan Behavior**: Utilizes ultra-fast `Index Only Scan` (forward and backward) on `train_stop_observations_pkey` to extract min/max sequence bounds instantaneously. Followed by a targeted `Index Scan` on `train_stop_observations_pkey` and `stations_pkey`. No global sequential scans occur. Existing indexes are perfectly sufficient.

### 4.7 Migration/Infrastructure Impact
- **Migration required**: No.
- **Schema changes**: None.

### 4.8 Acceptance Criteria
- Endpoint and service `calculate_train_structural_halts` implemented.
- Correctly skips origin and destination sequence numbers.
- Handles midnight-crossing dwells safely via `+86400`.
- Returns empty array for a 2-stop train.
- Throws standard 404 for unknown trains or trains outside the snapshot.
- Fully tested without regression in existing suites.
