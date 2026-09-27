# V2.0 Phase 26 Discovery: Network Train Topological Loop Analytics

## 1. Objective
Discover and define a new, genuinely distinct historical timetable analytics capability for RailGati that can be implemented entirely from existing PostgreSQL timetable snapshot data, without external APIs or live scraping.

## 2. Existing Capabilities Checked
- Phase 19: Station Directional Reversal Analytics (checks immediate `A -> B -> A` reversals at a specific station).
- Phase 21: Train Route Profile (calculates absolute duration bounds and total stops).
- Phase 22: Station O-D Bridging Analytics.
- All other completed V2.0 analytics correctly avoid modeling intra-train sequence cycles.

## 3. Candidates Evaluated

### Candidate A: Network Train Topological Loop Analytics (Selected)
- **Concept**: Identifies macro-circular topology by finding stations a specific train visits multiple times at non-adjacent stop sequences.
- **Endpoint**: `GET /api/v1/network/trains/{train_number}/topology-loops`

### Candidate B: Network Station O-D Dominance Analytics
- **Concept**: For a specific station, calculates the percentage of train occurrences that treat it as a pure origin, pure destination, or intermediate stop.
- **Endpoint**: `GET /api/v1/network/stations/{station_code}/od-dominance`
- **Why Rejected**: Redundant conceptually with Phase 9 (Network Terminus Analytics) and Phase 7 (Hub Centrality). It is a station-level slice of existing macro-network aggregation rather than a new capability.

### Candidate C: Network Train Structural Segment Analytics
- **Concept**: Computes the duration of every adjacent `[sequence i, sequence i+1]` edge traversed by a train to identify the longest continuous uninterrupted scheduled segment.
- **Endpoint**: `GET /api/v1/network/trains/{train_number}/longest-segment`
- **Why Rejected**: While distinct from Phase 21, real-data testing reveals that the "longest segment" predominantly identifies dataset anomalies where `source_day` artificially jumps by +1 (resulting in ~1440+ minute segments between adjacent stops). The semantic rules require treating `source_day` as mathematical fact, making this metric fundamentally noisy and deceptive regarding true network topology.

---

## 4. Selected Candidate: Network Train Topological Loop Analytics

### 4.1 Concept and Value
While traditional railway networks are often modeled linearly, certain complex train services operate in topological loops (e.g., circular urban routes, or branching services that return to an anchor station). 

This metric evaluates a single scheduled train and isolates the anchor stations that define a "macro-loop"—meaning the train stops at the station, visits at least one other distinct station, and subsequently returns to the original station.

### 4.2 Exact Semantics and Guardrails
- Must only evaluate the active timetable snapshot.
- Must filter out immediate data double-logs (where a train visits a station at sequence `N` and `N+1`) by enforcing a sequence gap greater than 1.
- Does NOT measure track geometry or physical loops. It purely measures structural timetable schedule occurrences.
- Does NOT measure immediate directional reversals at a station (covered in Phase 19).

### 4.3 Mathematical Definition
For a given `train_id` in the active `snapshot_id`:
1. Group all occurrences by `station_id`.
2. Filter for groups having `COUNT(*) > 1`.
3. Filter for groups having `MAX(stop_sequence) - MIN(stop_sequence) > 1`.
4. Calculate the `loop_span` as `MAX(stop_sequence) - MIN(stop_sequence)`.
5. Aggregate the `stop_sequences` involved.

### 4.4 Real Snapshot 2 Validation
Querying the local dataset reveals definitive non-linear routes:

- **Train 58421**: Visits station `GHNH` 3 times (sequences 18, 44, 54). `loop_span` = 36.
- **Train 54292**: Visits station `BSB` 3 times at sequences spanning a massive 81 sequence gap (a massive out-and-back topology loop).

This verifies that structural loops are a mathematically robust property of the dataset.

### 4.5 API Contract

**Method/Endpoint:**
`GET /api/v1/network/trains/{train_number}/topology-loops`

**Path Parameters:**
- `train_number` (string)

**Response:**
```json
{
  "train_number": "58421",
  "timetable_snapshot_id": 2,
  "has_loops": true,
  "loop_count": 2,
  "loops": [
    {
      "station_code": "GHNH",
      "visit_count": 3,
      "max_sequence_span": 36
    }
  ]
}
```

### 4.6 Query Strategy & EXPLAIN Results
Using PostgreSQL aggregation:
```sql
SELECT s.code as station_code, 
       COUNT(*) as visit_count,
       MAX(tso.stop_sequence) - MIN(tso.stop_sequence) as max_sequence_span
FROM train_stop_observations tso
JOIN stations s ON s.id = tso.station_id
WHERE tso.snapshot_id = :snapshot_id 
  AND tso.train_id = :train_id
GROUP BY tso.station_id, s.code
HAVING COUNT(*) > 1 
   AND MAX(tso.stop_sequence) - MIN(tso.stop_sequence) > 1
ORDER BY max_sequence_span DESC, s.code ASC;
```

**EXPLAIN ANALYZE (Train 58421):**
- **Planning Time**: 2.951 ms
- **Execution Time**: 4.955 ms
- **Scan Behavior**: Utilizes `train_stop_observations_pkey` (Index Scan) efficiently filtering by `snapshot_id` and `train_id`. The dataset size permits a negligible fast sequential scan / hash join on the `stations` dimension table (8,989 rows), avoiding global scan penalties on the massive observation table. Existing indexes are perfectly sufficient.

### 4.7 Migration/Infrastructure Impact
- **Migration required**: No.
- **Schema changes**: None.
- Uses existing indexes (`ix_trains_number`, `train_stop_observations_pkey`, `stations_pkey`).

### 4.8 Acceptance Criteria
- Service method `get_train_topology_loops` exists.
- HTTP 404 for unknown trains or trains absent in the snapshot.
- Correctly returns `has_loops = False` and an empty array for linear trains.
- Correctly calculates `max_sequence_span` preventing sequence double-counting.
- Full API/Service test coverage is provided.

### 4.9 Explicit Non-Goals
- Do not compute physical track pathing.
- Do not resolve or merge loops logically.
- Do not analyze Phase 19 immediate reversals.
