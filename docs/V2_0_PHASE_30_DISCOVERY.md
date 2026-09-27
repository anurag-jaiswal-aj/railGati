# V2.0 Phase 30 Discovery

## Objective
Perform a rigorous discovery for the next genuinely distinct V2.0 network/timetable analytical capability. The capability must provide a useful, deterministic railway intelligence metric that adds a new analytical dimension without semantic overlap. It must rely strictly on existing historical timetable data, remain within the ₹0 budget, and demonstrate concrete performance and viability using real Snapshot 2 data.

## Existing Phase Overlap Review
A rigorous review of V2.0 (Phases 1–29) was conducted to ensure strict non-overlap. The current matrix covers:
- **Topological Volume**: Corridors (Phase 6), Hub Centrality (Phase 7), Edge Volume (Phase 8), Termini (Phase 9), O-D Flows (Phase 10).
- **Time / Delay**: Station Dwell (Phase 11), Edge Asymmetry (Phase 13), O-D Travel Time (Phase 17).
- **Structural Shape**: Route Complexity (Phase 12), Temporal Concentration (Phase 13), Outbound-Edge Transit (Phase 19), Edge Bunching (Phase 24), Paired Symmetry (Phase 25), Topological Loops (Phase 26).
- **Relative Comparisons**: Relative Edge Slowness (Phase 28), Relative Station Dwell (Phase 29).

None of the existing metrics explicitly quantify the **branching dispersal / junction behavior** of a station's outbound traffic routing.

## Candidate Analytics

1. **Network Station Outbound Dominance Analytics (Station Level)**
   - **Formula**: `MAX(adjacent_destination_occurrences) / SUM(all_outbound_occurrences)`
   - **What it measures**: The structural dispersal of traffic leaving a station. A dominance of 1.0 indicates purely linear traffic; a low dominance (<0.3) indicates a multi-directional junction.

2. **Network Edge Travel Time Spread Analytics (Edge Level)**
   - **Formula**: `MAX(edge_duration) - MIN(edge_duration)` across all trains traversing an identical adjacent pair.
   - **What it measures**: The heterogeneity of transit speeds on a physical edge (e.g. express vs freight mix).

3. **Network Station Dwell Spread Analytics (Station Level)**
   - **Formula**: `MAX(station_dwell) - MIN(station_dwell)` across all intermediate stops.
   - **What it measures**: The heterogeneity of dwell policies at a single station.

4. **Network Station Terminus Dominance Analytics (Station Level)**
   - **Formula**: `(Origin Occurrences + Destination Occurrences) / Total Occurrences`
   - **What it measures**: The relative proportion of a station's role as a dead-end/terminus versus a transit node.

5. **Network Train Stop Cadence Uniformity Analytics (Train Level)**
   - **Formula**: The variance of scheduled edge transit times for a single train.
   - **What it measures**: Evaluates whether a train's stops are rhythmically spaced.

## Candidate Comparison
| Candidate | Closest Existing Phase | Key Difference | Major Risks |
| :--- | :--- | :--- | :--- |
| **Outbound Dominance** | Phase 7 (Hubs) | Phase 7 measures total absolute volume. This measures relative routing dispersal. | None. Highly efficient topological aggregation. |
| **Edge Travel Time Spread** | Phase 13 (Asymmetry) | Measures variance of speeds in one direction, not directional bias. | High vulnerability to `source_day` clock anomalies cross-midnight, producing false 1439 min spreads. |
| **Station Dwell Spread** | Phase 11 (Dwell) | Measures variance of dwells, not the mean. | High vulnerability to clock-math anomalies. |
| **Terminus Dominance** | Phase 9 (Termini) | Evaluates relative percentage, not absolute volume. | High semantic overlap with Phase 9. |
| **Stop Cadence** | Phase 20 (Profile) | Evaluates rhythmic regularity of edge durations. | Requires complex stddev/variance math which lacks native SQLite support, breaking DB agnostic rules. |

## Rejected Candidates
- **Edge Travel Time Spread** & **Station Dwell Spread**: Explicitly rejected due to `source_day` and clock-math anomalies. Exploratory SQL on Snapshot 2 revealed anomalous 1439-minute spreads when clock logic awkwardly crosses midnights without elapsed-time provenance.
- **Terminus Dominance**: Explicitly rejected due to unacceptable semantic overlap with Phase 9.
- **Stop Cadence Uniformity**: Explicitly rejected due to cross-dialect SQLite constraints on standard deviation functions, and utilizing MAX/MIN fallback re-introduces the clock anomaly vulnerability.

## Selected Candidate
**Network Station Outbound Dominance Analytics**

This candidate provides an entirely new analytical dimension: **Routing Dispersal / Junction Architecture**.
It deterministically calculates how a station distributes its departing traffic.
- A linear station (A -> B -> C) has an Outbound Dominance of `1.0` (100% of departures go to C).
- A true multi-directional hub (like Mughalsarai / MGS) has a low dominance (e.g. `0.18`), meaning its traffic fractures across many different adjacent destinations.
This is distinct from Phase 7 (Hub Centrality) which only counts *how many* trains touch the station, failing to distinguish a massive linear bottleneck from a complex fractal junction.

## Exact Semantics
- **Analytical Unit**: A specific requested station in the active timetable snapshot.
- **Target Metric**: The proportion of all valid scheduled outbound train occurrences that are directed to the single most-frequented adjacent station.
- **Occurrences**: An occurrence is defined as any continuous topological edge (`stop_sequence` -> `stop_sequence + 1`) originating at the target station.
- **No Deduplication**: Repeated occurrences by the *same* train (e.g. in topological loops) are counted as distinct outbound occurrences. This represents true physical routing volume.
- **Values**:
  - `dominance_ratio`: Float `(0.0, 1.0]`. `1.0` means all traffic flows to one adjacent station. `0.0` is returned if there is no outbound traffic.
  - `max_outbound_occurrences`: Integer count of traffic to the most popular adjacent node.
  - `total_outbound_occurrences`: Integer total count of all outbound traffic.

## Data Model / SQL Approach
- Retrieve active `timetable_snapshot_id`.
- Use a targeted CTE anchored to the specific `station_id`.
- `JOIN train_stop_observations tso2` ON `train_id` and `stop_sequence + 1`.
- Group by `tso2.station_id` to aggregate occurrences.
- Select `MAX(occurrences)` and `SUM(occurrences)`.
- Protect against division by zero using `NULLIF` (coalesced to `0.0` in the application layer).

## API Contract
**Endpoint:** `GET /api/v1/network/stations/{station_code}/outbound-dominance`

**Response Shape:**
```json
{
  "station_code": "MGS",
  "timetable_snapshot_id": 2,
  "dominance_ratio": 0.18775,
  "max_outbound_occurrences": 46,
  "total_outbound_occurrences": 245
}
```

## Validation Rules
- `station_code` must be uppercase.
- Station must exist in the active snapshot. Returns `404 Not Found` if missing.
- `dominance_ratio` must be between `0.0` and `1.0`.
- `max_outbound_occurrences` must be `<= total_outbound_occurrences`.

## Repeated Occurrence Semantics
This is strictly **occurrence-based**. If Train 12301 departs MGS twice within its schedule (topological loop), it counts as 2 outbound occurrences. It does NOT distinct by train identity. This ensures the ratio reflects total timetable structural load.

## Time Semantics
This metric is purely **topological**. It requires absolutely no time-math, no `source_day` logic, and no cross-midnight arithmetic. It evaluates pure structural sequence (`stop_sequence + 1`). This makes it highly resilient to data anomalies.

## Edge Cases
- **Terminus Station**: A station where every arriving train ends its route (no `tso2` exists). `total_outbound_occurrences` = 0. The API will safely return `dominance_ratio = 0.0` and counts = 0, avoiding ZeroDivisionError.
- **Single Line Station**: Traffic only departs to one adjacent station. Returns `dominance_ratio = 1.0`.
- **Missing Departure Record**: Because this evaluates pure `stop_sequence`, missing timestamps do not break the topology. We intentionally do NOT filter by `departure_time IS NOT NULL` because sequence structure is preserved regardless of timestamp availability.

## Performance Plan
The query targets a single station, completely eliminating global sequential scans.
- **Indexes utilized**: 
  - `ix_stations_code` for the target resolution.
  - `ix_train_stops_snapshot_station` to instantly retrieve the anchor outbound edges.
  - `train_stop_observations_pkey` (snapshot_id, train_id, stop_sequence) to instantly retrieve the `tso2` destination node.
- **Cost**: Planning ~1.6ms, Execution ~9.9ms. Extremely performant for real-time API.

## Test Plan
- **Basic Junction**: A station with 3 departures to A and 1 departure to B. Ratio = 0.75.
- **Pure Linear**: A station with 5 departures all to A. Ratio = 1.0.
- **Pure Terminus**: A station with 0 departures. Ratio = 0.0.
- **Topology Loop**: Train departs to A, then later visits again and departs to A. Occurrences = 2.
- **Unknown Station**: Returns 404.

## Real Snapshot 2 Validation
Exploratory SQL was executed against Snapshot 2.
- **Mughalsarai (MGS)**: `max_outbound`: 46, `total_outbound`: 245. `dominance_ratio`: 0.18775. (Confirms massive multi-directional junction).
- **Philibhit (PBE)**: `max_outbound`: 6, `total_outbound`: 31. `dominance_ratio`: 0.1935.
- **Bhatinda (BTI)**: `max_outbound`: 13, `total_outbound`: 57. `dominance_ratio`: 0.228.

## Acceptance Criteria
- [ ] Implement `GET /api/v1/network/stations/{station_code}/outbound-dominance`.
- [ ] Returns correct validation behavior for unknown stations.
- [ ] Snapshot 2 test for `MGS` strictly matches ratio `0.1877...`.
- [ ] No sequential scans across `train_stop_observations` when executed for a single station.

## Implementation Boundary
- No migrations required.
- Requires appending schema `StationOutboundDominanceResponse` in `schemas.py`.
- Requires appending service `calculate_station_outbound_dominance` in `services/network.py`.
- Requires appending router `get_network_station_outbound_dominance` in `api/v1/network.py`.
