# V2.0 Phase 30 Discovery

## Objective
Perform a rigorous discovery for the next genuinely distinct V2.0 network/timetable analytical capability. The capability must provide a useful, deterministic railway intelligence metric that adds a new analytical dimension without semantic overlap. It must rely strictly on existing historical timetable data, remain within the ₹0 budget, and demonstrate concrete performance and viability using real Snapshot 2 data.

## Existing Phase Overlap Review
A rigorous review of V2.0 (Phases 1–29) was conducted to ensure strict non-overlap. The current matrix covers:
- **Topological Volume**: Corridors (Phase 6), Hub Centrality (Phase 7), Edge Volume (Phase 8), Termini (Phase 9), O-D Flows (Phase 10).
- **Time / Delay**: Station Dwell (Phase 11), Edge Asymmetry (Phase 13), O-D Travel Time (Phase 17).
- **Structural Shape**: Route Complexity (Phase 12), Temporal Concentration (Phase 13), Outbound-Edge Transit (Phase 19), Edge Bunching (Phase 24), Paired Symmetry (Phase 25), Topological Loops (Phase 26).
- **Relative Comparisons**: Relative Edge Slowness (Phase 28), Relative Station Dwell (Phase 29).

None of the existing metrics explicitly quantify the **Scheduled Outbound Service Concentration** of a station's scheduled outbound timetable occurrences.

To clarify the distinction from existing phases:

**Phase 7 Hub Centrality:**
- measures station-level degree/occurrence relationships in the network.
- does not compute the concentration of outbound occurrences among a station's adjacent destinations.

**Phase 19 Outbound Edge Transit:**
- measures scheduled traversal duration for individual outbound adjacent edges.
- does not measure how outbound occurrences are distributed across destinations.

**Phase 8 Edge Volume:**
- reports volume for individual edges.
- this Phase 30 metric aggregates those outbound edge occurrences into a station-level concentration ratio.

**Phase 10 O-D Flow:**
- concerns terminal origin-destination occurrence pairs.
- Phase 30 concerns only the immediate next station from the queried station.

**Phase 13 Edge Asymmetry:**
- compares reciprocal edge volumes or durations.
- Phase 30 does not require a reciprocal edge and does not compare directions.

## Candidate Analytics

1. **Network Station Outbound Dominance Analytics (Station Level)**
   - **Formula**: `MAX(adjacent_destination_occurrences) / SUM(all_outbound_occurrences)`
   - **What it measures**: The concentration of scheduled outbound adjacent-edge timetable occurrences. A dominance of 1.0 indicates all scheduled outbound timetable occurrences from the station use the same immediately adjacent destination; a low dominance (<0.3) indicates greater dispersion of scheduled outbound service occurrences across multiple adjacent destinations.

2. **Network Edge Travel Time Spread Analytics (Edge Level)**
   - **Formula**: `MAX(edge_duration) - MIN(edge_duration)` across all trains traversing an identical adjacent pair.
   - **What it measures**: The heterogeneity of transit speeds on a physical edge.

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
| **Outbound Dominance** | Phase 7 (Hubs) | Phase 7 measures total absolute occurrences. This measures relative occurrence distribution. | None. Highly efficient topological aggregation. |
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

This candidate provides an entirely new analytical dimension: **Scheduled Outbound Service Concentration**.
It deterministically calculates the distribution of scheduled outbound timetable occurrences from a station.
- Do 100% of scheduled outbound timetable occurrences from the station use the same immediately adjacent destination? (Dominance = `1.0`).
- Does the station have a greater dispersion of scheduled outbound service occurrences across multiple adjacent destinations? (Dominance e.g. `0.18`).
This is distinct from Phase 7 (Hub Centrality) which only counts total occurrences, failing to distinguish a single-path node from a node with highly dispersed occurrences.

## Exact Semantics

For station S:

For every train-stop occurrence where:
- snapshot_id = active timetable snapshot
- current station = S
- a consecutive next stop exists
- next stop has stop_sequence = current stop_sequence + 1

group occurrences by exact adjacent destination station D.

Let:
`edge_occurrences(S,D)` = number of qualifying scheduled timetable occurrences from S directly to D.

Then:

`total_outbound_occurrences(S)`
    = SUM over all D of `edge_occurrences(S,D)`

`max_outbound_occurrences(S)`
    = MAX over D of `edge_occurrences(S,D)`

`outbound_dominance_ratio(S)`
    = `max_outbound_occurrences(S)` / `total_outbound_occurrences(S)`

The ratio is therefore in the range (0, 1] for stations with at least one qualifying outbound occurrence.

**Explicit Non-Goals (What it DOES NOT measure)**:
It does NOT measure:
- passenger demand
- passenger flow
- physical track capacity
- congestion
- train frequency in the real world
- actual train movements
- operational routing
- geographic direction
- railway junction capacity
- network importance
- passenger connectivity
- commercial importance

It measures only the concentration of scheduled outbound adjacent-edge timetable occurrences in the selected historical snapshot.

**Explicit Note on "Outbound"**:
"Outbound" strictly means the next station in the timetable `stop_sequence`.
It does NOT mean:
- geographic north/south/east/west
- physical railway direction
- train movement direction inferred from geography.

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
Preserve every qualifying timetable occurrence.
If the same train visits the same station multiple times and each visit has a valid consecutive next stop, each occurrence counts independently, preserving each qualifying scheduled timetable occurrence independently.
Do NOT collapse to distinct trains unless the metric definition explicitly changes.
Do NOT claim that repeated occurrences represent physical train traffic.

## Time Semantics
This metric is purely **topological**. It requires absolutely no time-math, no `source_day` logic, and no cross-midnight arithmetic. It evaluates pure structural sequence (`stop_sequence + 1`). This makes it highly resilient to data anomalies.

## Edge Cases
- **Terminus Station**: A station where every arriving train ends its route (no `tso2` exists). `total_outbound_occurrences` = 0. The API will safely return `dominance_ratio = 0.0` and counts = 0, avoiding ZeroDivisionError.
- **Single Path Station**: All outbound occurrences go to one adjacent station. Returns `dominance_ratio = 1.0`.
- **Missing Departure Record**: Because this evaluates pure `stop_sequence`, missing timestamps do not break the topology. We intentionally do NOT filter by `departure_time IS NOT NULL` because sequence structure is preserved regardless of timestamp availability.

## Performance Plan
The query targets a single station, completely eliminating global sequential scans.
- **Indexes utilized**: 
  - `ix_stations_code` for the target resolution.
  - `ix_train_stops_snapshot_station` to instantly retrieve the anchor outbound edges.
  - `train_stop_observations_pkey` (snapshot_id, train_id, stop_sequence) to instantly retrieve the `tso2` destination node.
- **Cost**: Planning ~1.6ms, Execution ~9.9ms. Extremely performant for real-time API.

## Test Plan
- **Basic Node**: A station with 3 occurrences to adjacent station A and 1 occurrence to adjacent station B. Ratio = 0.75.
- **Pure Linear Node**: A station with 5 occurrences all to adjacent station A. Ratio = 1.0.
- **Pure Terminus**: A station with 0 outbound occurrences. Ratio = 0.0.
- **Repeated Visit Loop**: Train visits station A, departs to B; later visits station A, departs to B again. Occurrences = 2.
- **Unknown Station**: Returns 404.

## Real Snapshot 2 Validation
Exploratory SQL was executed against Snapshot 2.
- **MGS**: 
  - `total_outbound_occurrences`: 245
  - `max_outbound_occurrences`: 46
  - `dominance_ratio`: ≈ 0.1877
- **PBE**: 
  - `total_outbound_occurrences`: 31
  - `max_outbound_occurrences`: 6
  - `dominance_ratio`: ≈ 0.1935
- **BTI**: 
  - `total_outbound_occurrences`: 57
  - `max_outbound_occurrences`: 13
  - `dominance_ratio`: ≈ 0.2280

These are scheduled timetable occurrence counts from Snapshot 2.

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
