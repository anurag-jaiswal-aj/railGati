# V2.0 Phase 29 Discovery

## Objective
To rigorously discover and design the next genuinely distinct network/timetable analytical capability for RailGati after Phase 28, adhering to historical timetable constraints, the ₹0 budget, and strictly avoiding operational/live inference.

## Existing Phase Overlap Review
RailGati V2.0 currently evaluates the graph at three primary depths:
1. **Edge level:** edge volume, edge asymmetry, paired services, outbound edge transit, edge temporal bunching.
2. **Station level:** hub centrality, termini, station dwell (absolute), temporal concentration, service similarity, O-D bridges, station temporal gaps.
3. **Train level:** route complexity, route similarity, directional reversals, paired-service symmetry, topology loops, structural halts, relative edge slowness (Phase 28).

Phase 28 established the ability to contrast a target train's edge traversal duration against the historical network average for that exact edge. There is currently no equivalent analytic for vertices (stations). While Phase 27 returns a train's absolute structural halts, it does not compare them to the network baseline. While Phase 11 returns station absolute dwells, it does not contextualize an individual train's relative behavior.

## Candidate Analytics

### Candidate 1: Network Train Relative Station Dwell Analytics
- **Endpoint:** `GET /api/v1/network/trains/{train_number}/relative-station-dwell`
- **Unit:** Scheduled intermediate stops for a target train.
- **Formula:** `target_dwell / network_average_dwell` at the identical station (returned if ratio > 1.0).
- **Required Data:** `train_stop_observations` arrival and departure timings.

### Candidate 2: Network Station Directional Bias Analytics
- **Endpoint:** `GET /api/v1/network/stations/{station_code}/directional-bias`
- **Unit:** Outbound scheduled service distribution from a station.
- **Formula:** Proportion of departures directed toward the single most frequented adjacent destination.
- **Required Data:** Outbound edge occurrences.

### Candidate 3: Network Train Schedule Density Profile
- **Endpoint:** `GET /api/v1/network/trains/{train_number}/schedule-density`
- **Unit:** Scheduled edges along a train's route.
- **Formula:** Number of other trains scheduled on the same edge within a ±60-minute window of the target train's departure.

## Rejected Candidates
- **Candidate 2 (Directional Bias):** Overlaps significantly with hub centrality and edge asymmetry. It may also imply geographic directionality which we strictly avoid inferring.
- **Candidate 3 (Schedule Density Profile):** Highly vulnerable to implicitly measuring physical congestion, signaling capacity, and actual train overtaking, which violates the strict constraint against live/operational/capacity inference.

## Selected Candidate
**Network Train Relative Station Dwell Analytics (Candidate 1)**

It is genuinely distinct because it contextualizes a train's static vertex-behavior against the network baseline. Phase 28 isolates edge transit anomalies (moving); Phase 29 will isolate station dwell anomalies (waiting). E.g. discovering that Train 15905 is scheduled to halt for 40 minutes at Durgapur (DGR) when the network historical average at DGR is only 4 minutes (ratio ~10). 

## Exact Semantics
- Uses the **active timetable snapshot**.
- Evaluates **intermediate scheduled stops only** (requires both arrival and departure). Origin and destination termini are inherently excluded because their dwell is undefined.
- The **Network Baseline** consists of all qualifying intermediate timetable occurrences (valid arrival and departure) at the exact same station in the same snapshot.
- The **Target Train is INCLUDED** in the baseline average calculation.
- **Repeated Target Occurrences** (e.g. a train revisiting a station via a loop) remain strictly independent and are identified by `target_stop_sequence`.
- The baseline station matching uses a `DISTINCT` lookup of target station IDs to prevent artificial multiplication of the network occurrence count.
- The average is a pure arithmetic **AVG**.
- Returns only occurrences where **slowness ratio > 1.0**.
- Zero-average baselines (e.g., if all baseline occurrences mysteriously have exactly 0-minute dwells) safely exclude the ratio calculation (`NULLIF`) and omit the occurrence.
- This is a purely historical/static scheduled timetable metric. It explicitly does **NOT** measure actual live delays, physical wait times, passenger embarking/disembarking demand, or operational causes (crew changes, technical halts, overtaking, rake sharing).

## Data Model / SQL Approach
Utilizes a highly efficient, multi-CTE strategy leveraging existing indices:
1. `target_dwells`: Extract all intermediate stops for the target train with duration > 0 (clock-time math with +1440 cross-midnight wraparound).
2. `target_station_ids`: Extract `DISTINCT station_id` from `target_dwells` to form a unique baseline filter.
3. `network_dwells`: Fetch all network intermediate dwells across the exact same snapshot where `station_id` exists in `target_station_ids`.
4. `network_stats`: Group `network_dwells` by `station_id` to compute `AVG(dwell)` and `COUNT(*)`.
5. Join `target_dwells` against `network_stats`, filter `ratio > 1.0`, and output sorted by `ratio DESC, target_stop_sequence ASC`.

## API Contract

**Request:**
`GET /api/v1/network/trains/{train_number}/relative-station-dwell`

**Response:**
```json
{
  "train_number": "15905",
  "timetable_snapshot_id": 2,
  "relative_dwells": [
    {
      "target_stop_sequence": 457,
      "station_code": "DGR",
      "target_dwell_minutes": 40.0,
      "network_average_minutes": 4.03,
      "network_occurrence_count": 159,
      "slowness_ratio": 9.92
    }
  ]
}
```

## Validation Rules
- `train_number` must resolve to an existing train (ValueError / 404).
- `target_duration_minutes` must be non-negative.
- `slowness_ratio` must be strictly > 1.0.

## Edge Cases
- **Repeated Visits:** Preserved independently, distinguished by `target_stop_sequence`.
- **Termini:** Excluded automatically (missing arrival or departure).
- **Missing Timings:** Excluded cleanly (requires `arrival_time IS NOT NULL` and `departure_time IS NOT NULL`).
- **Cross-Midnight Dwells:** Correctly handled (e.g., arr 23:55, dep 00:10 -> 15 mins).
- **Zero Average:** Trapped via `NULLIF(avg_dwell, 0)`, excluding the stop from the result array.

## Performance Plan
- The query will scan the `trains` and `train_stop_observations` tables to establish `target_dwells` (`ix_trains_number`, `train_stop_observations_pkey`).
- `network_dwells` will securely use the `ix_train_stops_snapshot_station` index driven by the `target_station_ids` IN/JOIN filter.
- No global sequential scans will occur.

## Test Plan
- **Service layer:** Implement exact mock scenarios verifying target inclusions, cross-midnight, missing timing omission, zero-average omission, and strict distinct baseline aggregation over repeated loops.
- **API layer:** Mirror service tests via `httpx` to guarantee JSON schema, HTTP status codes, and HTTP 404 for unknown trains.

## Real Snapshot 2 Validation
Exploratory discovery against Snapshot 2 explicitly confirmed the feasibility of the query:
Train `15905`:
- DGR (Seq 457): Target Dwell 40.0 mins, Network Average 4.03 mins, Occurrences 159, Ratio ~9.92
- HIJ (Seq 408): Target Dwell 5.0 mins, Network Average 0.15 mins, Occurrences 113, Ratio ~33.23
Train `12004`:
- ETW (Seq 43): Target Dwell 2.0 mins, Network Average 0.56 mins, Occurrences 185, Ratio ~3.55

**EXPLAIN ANALYZE for 15905:**
- Planning Time: ~2.9 ms
- Execution Time: ~69.4 ms
- Indexing: `Index Scan using ix_train_stops_snapshot_station` strictly utilized.
- Global Sequential Scan: None.

## Acceptance Criteria
- Discovery document committed to `docs/V2_0_PHASE_29_DISCOVERY.md`.
- No implementations executed.
- The document clearly outlines the query shape, metrics, and exact semantics.

## Implementation Boundary
Implementation is strictly prohibited until Phase 29 is explicitly authorized.
