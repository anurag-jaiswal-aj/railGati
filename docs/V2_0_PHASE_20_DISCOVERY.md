# V2.0 Phase 20 Discovery

## Objective
Study the existing RailGati architecture and completed V2.0 phases to identify the next meaningful, distinct network/station/train analytics capability. The capability must be implemented safely using the existing historical/static timetable data, adhering strictly to the ₹0 constraints, and avoiding assumptions about live operations.

## Existing Capability Coverage
The V2.0 analytics surface already comprehensively covers:
- **Topology & Paths**: Reachability (1), Bounded Paths (2), Termini (9), Corridors (6), Hubs (7), Continuous Services (5)
- **Volume & Flow**: Edge Volume (8), O-D Flow (10), Temporal Concentration (13), Edge Asymmetry (14)
- **Duration & Timing**: Station Dwells (11), O-D Travel-Time (17), Paired-Service Scheduled Layovers (18)
- **Structural Analysis**: Route Complexity (12), Train Route Similarity (15), Station Service Similarity (16), Station Directional Reversals (19)

## Candidate Analytics

### Candidate 1: Network Station Outbound Edge Transit Analytics
- **Question**: For trains departing a given station, what is the scheduled transit duration (minimum, maximum, and average minutes) across its immediate outbound track segments?
- **Concept**: Analyzes the pure moving transit time between two adjacent stations, isolating the track traversal time from station layovers or end-to-end multi-segment journeys.
- **Feasibility**: High. Uses a simple self-join on `stop_sequence = src_seq + 1`.

### Candidate 2: Network Train Span Analytics
- **Question**: What is the total topological length (stop count) and temporal duration for a specific train from its absolute origin to its final destination?
- **Concept**: Evaluates the end-to-end breadth of an individual train identity across the network.
- **Feasibility**: High. Uses `MIN(stop_sequence)` and `MAX(stop_sequence)` to extract boundaries.

### Candidate 3: Network Train Dwell Profiling Analytics
- **Question**: Which trains spend the highest percentage of their total journey time sitting at stations?
- **Concept**: Calculates the ratio of total stationary dwell time to total moving transit time across a train's entire path.
- **Feasibility**: Moderate. Requires aggregating all dwells and dividing by the total span duration.

## Candidate Feasibility Analysis
- **Candidate 3 (Dwell Profiling)** is useful but overlaps significantly with Phase 11 (Station Dwells) and Candidate 2 (Train Span). It is a derived metric.
- **Candidate 2 (Train Span)** is straightforward but primarily serves as a train metadata profile rather than a deep structural network analytic.
- **Candidate 1 (Outbound Edge Transit Analytics)** fills a critical gap in the existing duration analytics. Phase 11 measures stationary wait times, and Phase 17 measures multi-hop O-D durations, but no existing phase measures the *pure transit speed/duration* along a specific track segment. This is crucial for discovering timetable slack, track speed limits, and dataset anomalies (e.g., trains crossing midnight improperly).

## Selected Phase 20 Capability
**Network Station Outbound Edge Transit Analytics**

## Exact Semantics
- Evaluates the scheduled travel duration across a single directed topological edge originating at the target station.
- **Transit Duration**: Defined as the time difference between the departure at the target station (`stop n`) and the arrival at the immediate next station (`stop n+1`) for the same train.
- Must account for cross-day travel accurately by computing `(dst_day - src_day) * 1440 + dst_arrival - src_departure`.
- Mathematically exposes dataset anomalies: if the raw timetable improperly increments `source_day` for a short transit, the analytic will accurately report the resulting anomalous large duration (e.g., 1447 minutes) without inventing arbitrary filters.

## Data Sources and Tables
- `train_stop_observations`: Provides `station_id`, `stop_sequence`, `departure_time`, `arrival_time`, and `source_day`.
- `stations`: Provides canonical station metadata.
- Evaluated entirely within the boundaries of the active dataset snapshot.

## Computation
A two-stage CTE strategy is employed to guarantee performance:
1. `target_trains`: Select all `train_id`, `stop_sequence`, `departure_time`, and `source_day` for trains visiting the target station where `departure_time` is not null.
2. `next_stops`: Join `train_stop_observations` for the identical `train_id` where `stop_sequence = target.src_seq + 1` and `arrival_time` is not null.
3. Compute the `duration_mins` using the cross-day logic.
4. Group by the destination station to aggregate `count`, `min`, `max`, and `avg`.

## Proposed API Contract
**Endpoint**: `GET /api/v1/network/stations/{station_code}/outbound-edges/transit`

**Response Schema**:
```json
{
  "station_code": "NDLS",
  "station_name": "New Delhi",
  "timetable_snapshot_id": 2,
  "outbound_edges": [
    {
      "next_station_code": "CSB",
      "next_station_name": "Shivaji Bridge",
      "train_volume": 100,
      "min_duration_minutes": 1,
      "max_duration_minutes": 6,
      "avg_duration_minutes": 2.0
    }
  ]
}
```

## Performance Validation
Executing the selected query for Station `NDLS` against the active local PostgreSQL database yielded exceptional performance:
- **Planning Time**: 3.388 ms
- **Execution Time**: 6.009 ms
- **Mechanics**: Instead of a full-timetable Window Scan, the query leverages `ix_train_stops_snapshot_station` to instantly isolate the target trains (149 rows), then joins the exact next sequence using the `train_stop_observations_pkey`.
- **Sequential Scans**: 0. Memory operations were restricted to a lightweight Hash Join (16kB) and QuickSort (33kB).

## Edge Cases
- **Anomalous Cross-Day Increments**: Found real-data cases (e.g., NDLS to DSB) where `source_day` increments incorrectly in the raw timetable for a 00:10 departure and 00:17 arrival, resulting in a dataset-accurate calculation of 1447 minutes. The analytic preserves and exposes this faithfully.
- **Terminal Stops**: Trains terminating at the target station have no `next_stop` (no arrival time or sequence n+1) and are seamlessly excluded.

## Limitations and Non-Claims
- Does not infer physical distance (km) or true train velocity (km/h).
- Does not predict actual live running times, delays, or congestion.
- Reflects only the scheduled cyclic clock gap specified by the timetable.

## ₹0 Compliance
The capability is fully computable via PostgreSQL set-based operations using only the locally ingested historical timetable, demanding zero external APIs, LLMs, or paid infrastructure.

## Implementation Scope for Next Step
- No database schema migrations required.
- Requires new Pydantic models in `schemas.py`.
- Requires a new service method `calculate_station_outbound_transit` in `services/network.py`.
- Requires the API route registration.
- Requires comprehensive semantic testing focusing on cross-day arithmetic and anomalous dataset exposure.

## Discovery Conclusion
Network Station Outbound Edge Transit Analytics successfully provides a distinct, highly performant, and structurally insightful layer to the V2.0 Network Analytics suite, safely extending our temporal analysis from nodes (dwells) and global paths (O-D times) to specific localized network track segments.
