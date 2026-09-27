# V2.0 Phase 21 Discovery

## Objective
Identify the next meaningful, distinct, and technically defensible network/station/train analytics capability that can be implemented safely using the existing historical/static railway timetable data, adhering strictly to the established ₹0 constraint.

## Existing Capability Coverage
V2.0 Analytics currently covers:
- **Topology**: Reachability (1), Bounded Paths (2), Termini (9)
- **Path Behavior**: Network Service/Path Attribution (3, 4), Continuous Services (5), Corridors (6), Hub Centrality (7)
- **Volume & Flow**: Edge Volume (8), O-D Flow (10), Edge Asymmetry (14)
- **Temporal Station/Network Metrics**: Station Dwells (11), Temporal Concentration (13), O-D Travel-Time (17), Edge Transit Durations (20)
- **Structural Analysis**: Station Route Complexity (12), Route Similarity (15), Station Similarity (16), Paired Services (18), Station Reversals (19)

**Remaining Capability Gap**: RailGati heavily profiles the network through nodes (stations), edges (segments), and global routes (O-D bounds). However, it currently lacks a unified profile for **individual train identities**. While Phase 11 calculates average wait times across a station, and Phase 20 calculates average travel times across an edge, there is no analytic that measures the aggregate end-to-end topological scale and temporal efficiency of a single train's entire path.

## Candidate Analytics

### Candidate 1: Network Train Route Profile Analytics
- **Product Question**: What is a specific train's total topological length (stop count), end-to-end scheduled duration, and what percentage of its journey is spent actively moving versus stationary (dwelling) at intermediate stations?
- **Concept**: Computes the absolute breadth (time and space) of a train's path and derives a "dwell ratio" representing its temporal efficiency.
- **Feasibility**: High. Computable entirely within PostgreSQL using targeted index scans and CTEs.

### Candidate 2: Network Station Route Diversity Analytics
- **Product Question**: How many unique destination termini can be reached directly from this station?
- **Concept**: Measures the breadth of global access a station provides by counting unique final destination stations among trains that pass through it.
- **Feasibility**: Moderate. Conceptually overlaps with Phase 1 (Reachability) and Phase 9 (Termini).

### Candidate 3: Network Train Stop Gap Analytics
- **Product Question**: For a specific train, what is the longest single uninterrupted transit leg (by scheduled duration) on its journey?
- **Concept**: Finds the temporal bottleneck or largest infrastructure gap on a train's path.
- **Feasibility**: Moderate. Heavily overlaps with the individual edge metrics exposed in Phase 20, just scoped to a single train rather than aggregated at a station.

## Candidate Feasibility Analysis
- **Candidate 3 (Stop Gaps)** evaluates edges, which is functionally derivative of the adjacent-edge analytics from Phase 20.
- **Candidate 2 (Route Diversity)** leverages termini data but overlaps conceptually with existing Hub Centrality and Reachability metrics.
- **Candidate 1 (Train Route Profile)** is conceptually novel. It shifts the analytical lens from the station/edge to the *complete Train entity*, extracting a canonical temporal efficiency metric (Dwell Percentage) that explicitly distinguishes rapid express routes from slow passenger routes across their entire lifespan.

## Selected Phase 21 Capability
**Network Train Route Profile Analytics**

## Exact Semantics
- **Unit of Analysis**: A single active historical train identity.
- **Total Stops**: The absolute count of valid recorded stops in the snapshot.
- **Total Duration**: The scheduled temporal span from the departure at the first recorded stop (`min_seq`) to the arrival at the final recorded stop (`max_seq`), correctly adjusting for `source_day` transitions.
- **Total Dwell**: The sum of all wait times (`departure_time - arrival_time`) exclusively at *intermediate* stations. Midnight cross-overs for individual dwells are handled via `+ 1440` minutes when departure < arrival.
- **Dwell Percentage**: `(Total Dwell / Total Duration) * 100`. Defines the proportion of the train's lifespan spent stationary.
- Relies solely on static timetable data with no claims about physical speed, live delays, or actual distance.

## Data Sources and Tables
- `train_stop_observations`: Provides `stop_sequence`, `departure_time`, `arrival_time`, and `source_day`.
- `trains`: Resolves the `train_number`.
- `stations`: Resolves origin and destination station codes.

## Computation
The analytic is computed using a single 5-stage targeted PostgreSQL CTE:
1. `train_stops`: Isolates all stops for the target train using `ix_train_stops_snapshot_station` (or equivalent train ID index).
2. `termini`: Identifies `min_seq`, `max_seq`, and `total_stops` using Window Functions/Grouping.
3. `span_bounds`: Joins `termini` back to `train_stops` to extract exact origin departure and destination arrival times.
4. `span_calc`: Computes total end-to-end duration explicitly using `source_day` differences.
5. `dwells`: Aggregates the intermediate dwell times, accounting for standard timetable midnight-crosses.
The final select calculates the ratio.

## Proposed API Contract
**Endpoint**: `GET /api/v1/network/trains/{train_number}/profile`

**Response Schema**:
```json
{
  "train_number": "12301",
  "timetable_snapshot_id": 2,
  "origin_station_code": "HWH",
  "destination_station_code": "NDLS",
  "total_stops": 218,
  "total_duration_minutes": 1020.0,
  "total_dwell_minutes": 30.0,
  "dwell_percentage": 2.9
}
```

## Performance Validation
The proposed query was executed against the local PostgreSQL active snapshot for Train `12301`:
- **Execution Time**: ~0.872 ms
- **Planning Time**: ~1.610 ms
- **Mechanics**: The execution avoids all sequential scans. It leverages `train_stop_observations_pkey` (which inherently clusters by snapshot and train_id) to retrieve the train's entire path in under 0.1 ms, allowing fast in-memory Hash Aggregation (consuming <25kB memory).

## Edge Cases
- **Missing Boundaries**: If a train lacks arrival/departure timings at its absolute termini, duration calculation gracefully falls back or returns nulls.
- **Trains with < 3 Stops**: Automatically yield 0 intermediate dwell minutes.
- **0-Minute Total Duration**: Mathematical division by zero is prevented via `NULLIF(duration, 0)`.
- **Anomalous Dataset Timings**: Retained purely as mathematical evaluations of the source data, preserving the ₹0 / source-purity constraint.

## Limitations and Non-Claims
- Does not infer passenger travel behavior or ticketable routes.
- Does not predict actual physical train velocity or live punctuality.
- Dwell calculations assume standard timetable day-crossings and do not infer long-term layovers (>24h) for a single station stop unless structurally supported by the raw timings.

## ₹0 Compliance
This metric relies exclusively on PostgreSQL set-based aggregates natively derived from the ingested historical timetable snapshot, requiring zero external maps, LLMs, or paid infrastructure.

## Implementation Scope for Next Step
- No database migrations or schema updates are required.
- Add Pydantic response models in `schemas.py`.
- Add a service method `calculate_train_profile` in `services/network.py`.
- Register the `/trains/{train_number}/profile` route in `api/v1/network.py`.
- Write comprehensive API and service tests to validate the `source_day` arithmetic, missing timing behaviors, and short-train logic.

## Discovery Conclusion
Network Train Route Profile Analytics successfully provides a distinct and hyper-performant capability, closing the Train-level analytical gap in the RailGati V2.0 Network Analytics suite. Discovery is complete; implementation is intentionally deferred.
