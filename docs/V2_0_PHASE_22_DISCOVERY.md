# V2.0 Phase 22 Discovery

## Objective
Study the existing RailGati V2.0 implementation and identify the next distinct, meaningful, and technically defensible network/station analytic capability using exclusively historical/static railway timetable data, while adhering strictly to the established ₹0 constraint.

## Existing Capability Coverage
V2.0 Analytics currently covers:
- **Topology & Nodes**: Reachability (1), Bounded Paths (2), Termini Analytics (9)
- **Station Metrics**: Hub Centrality (7), Station Dwells (11), Route Complexity (12), Station Similarity (16)
- **Edges & Connectivity**: Corridors (6), Edge Volume (8), Edge Asymmetry (14), Edge Transit (20)
- **Train Metrics**: Continuous Services (5), Route Similarity (15), Reversals (19), Route Profiles (21)
- **O-D Bounds**: O-D Flows (10), O-D Travel-Time (17)

**Remaining Capability Gap**: While Phase 10 (O-D Flows) ranks global origin-destination bounds, and Phase 7 (Hub Centrality) identifies massive structural station funnels, there is no analytic that explicitly links a specific intermediate station to the broader *macro-topological termini* it bridges. Users cannot currently ask: "What are the ultimate start and end points of the traffic flowing through this station?"

## Candidate Analytics

### Candidate 1: Network Station O-D Bridging Analytics
- **Product Question**: What are the ultimate origins and destinations of all trains traversing a specific station, and what are the most frequent O-D terminal bounds bridged by this node?
- **Exact Semantics**: Computes the diversity of absolute termini accessible via trains crossing a specific node, returning the distinct count of unique origins, destinations, terminal pairs, and a ranked list of the top volumetric terminal O-D bounds bridged.
- **Feasibility**: High. Computable entirely within PostgreSQL using correlated subqueries leveraging `train_stop_observations_pkey`.

### Candidate 2: Network Station Connectivity Asymmetry Analytics
- **Product Question**: Is a station more heavily weighted as a "source" (more outward connections than inward) or a "sink" (more inward than outward)?
- **Exact Semantics**: Compares the sum of trains terminating at a station vs originating at a station.
- **Feasibility**: Moderate. Strongly overlaps with Phase 9 (Termini) and Phase 14 (Edge Asymmetry). Derivative in nature.

### Candidate 3: Network Train Progression Skew Analytics
- **Product Question**: For a specific train, is its scheduled duration heavily skewed toward the beginning of its route or the end?
- **Exact Semantics**: Calculates the median chronological point of a train route compared to its topological midpoint to identify "fast" and "slow" halves.
- **Feasibility**: Moderate. Complex to compute safely in pure SQL without iterative window framing, risking poor performance.

## Candidate Feasibility Analysis
- **Candidate 2** operates using existing Phase 9 and Phase 14 components. It provides only a minor derivative insight.
- **Candidate 3** evaluates train-level time density, but the SQL constraints are complex and borderline unscalable without full denormalization.
- **Candidate 1** bridges the analytical space between "Hub Centrality" (the node) and "O-D Flows" (the network bounds). It introduces a completely novel topological measure (Bridging Capacity/Diversity) that scales perfectly within the existing indexing schema using less than 15ms of execution time on major hubs like New Delhi (NDLS).

## Selected Phase 22 Capability
**Network Station O-D Bridging Analytics**

Explicitly supported because the timetable dataset stores absolute train paths, allowing a specific intermediate node to efficiently look up the `min_seq` and `max_seq` (the termini) of every train intersecting it.

## Exact Semantics
- **Source Snapshot**: The active timetable snapshot.
- **Station Identity**: The target intermediate station being queried.
- **Target Trains**: The distinct set of active trains that possess a valid `train_stop_observation` at the target station.
- **Origin**: The station at the absolute minimum `stop_sequence` for a given target train.
- **Destination**: The station at the absolute maximum `stop_sequence` for a given target train.
- **Bridged Pair**: The directional tuple `(Origin, Destination)` for a target train.
- **Occurrence Semantics**: Every valid train occurrence intersecting the station contributes exactly one Bridged Pair.
- **Repeated Visits**: If a train visits the target station multiple times (e.g. cyclic routes), it is counted distinctly as one single target train (unique train identity) bridging its absolute `min_seq` and `max_seq`.
- **Top OD Pairs**: The highest volumetric subset of bridged pairs, sorted by volume descending, then alphabetically by origin code and destination code for determinism.

## Data Sources and Tables
- `train_stop_observations`: Provides `snapshot_id`, `train_id`, `station_id`, and `stop_sequence`.
- `stations`: Resolves station codes and names for the origin and destination termini.

## Computation
The analytic uses a highly performant correlated-subquery CTE structure:
1. `target_trains`: Aggregates the distinct `train_id`s stopping at the target station using `ix_train_stops_snapshot_station`.
2. `train_bounds`: Maps each target `train_id` to its ultimate origin and destination by extracting the `station_id` at `ORDER BY stop_sequence ASC LIMIT 1` and `ORDER BY stop_sequence DESC LIMIT 1`. This exploits the primary key perfectly.
3. Finally, the query aggregates the unique counts (`COUNT(DISTINCT)`) and performs a volumetric `GROUP BY` to extract the Top N bridged pairs.

## Proposed API Contract
**Endpoint**: `GET /api/v1/network/stations/{station_code}/od-bridges`

**Response Schema**:
```json
{
  "station_code": "NDLS",
  "station_name": "NEW DELHI",
  "timetable_snapshot_id": 2,
  "unique_origins_count": 77,
  "unique_destinations_count": 81,
  "unique_od_pairs_count": 160,
  "top_od_pairs": [
    {
      "origin_station_code": "HWH",
      "origin_station_name": "HOWRAH JN",
      "destination_station_code": "NDLS",
      "destination_station_name": "NEW DELHI",
      "train_volume": 6
    }
  ]
}
```
*(Note: If the target station happens to be the terminus for a train, it is explicitly preserved in the O-D pair, validating that the station bridges traffic directly to/from itself).*

## Performance Validation
The query was validated against `NDLS` on active snapshot 2 in PostgreSQL:
- **Planning Time**: ~1.422 ms
- **Execution Time**: ~12.833 ms
- **Scan Types**: `ix_train_stops_snapshot_station` isolates the intersecting trains. `train_stop_observations_pkey` is then utilized via `Index Scan` and `Index Scan Backward` with `LIMIT 1` to instantly retrieve the absolute termini.
- **Full Table Scans**: 0. Memory usage relies entirely on lightweight Hash Joins (<1MB).

## Edge Cases
- **Unknown Station**: Returns HTTP 404.
- **Isolated Station (No Trains)**: Returns 0 for counts and an empty array for `top_od_pairs`.
- **Short Routes (Origin = Destination)**: Timetables theoretically shouldn't contain 1-stop trains, but if they do, the Origin and Destination correctly evaluate to the same station safely.
- **Missing Termini Timings**: Stop timings (`arrival_time` / `departure_time`) are completely irrelevant to this structural analytic, bypassing missing-data errors.

## Limitations and Non-Claims
- This measures *structural timetable O-D bounds*. It does **not** reflect actual passenger travel volumes, ticketing O-D demand, or geographic layout.
- Two distinct stations might have identical O-D bounds, which does not imply they share the same physical tracks.

## ₹0 Compliance
The logic relies entirely on SQL aggregations running against the pre-existing, locally hosted historical timetable database, requiring zero external dependencies, maps, or paid APIs.

## Implementation Scope for Next Step
- No schema modifications or migrations are necessary.
- Add `ODBridgesResponse` and related item models in `schemas.py`.
- Add `calculate_station_od_bridges` to `services/network.py`.
- Expose `GET /api/v1/network/stations/{station_code}/od-bridges` in `api/v1/network.py`.
- Write targeted API and Service tests verifying zero-division, isolation bounds, and determinism.

## Discovery Conclusion
Network Station O-D Bridging Analytics provides a fully distinct, highly scalable macroscopic topology metric, successfully closing the gap between localized Hub Centrality and global O-D Flows. Discovery is complete; implementation is intentionally deferred.
