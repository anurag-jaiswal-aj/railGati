# RailGati v1.3 — Destination Discovery Discovery

## 1. Executive Summary
RailGati v1.3 focuses on "Destination Discovery" ("Where Can I Go?"). This feature will allow users to query reachable destinations from a given origin station based on the historical Datameet timetable. The analysis confirms this can be built relationally on PostgreSQL without external routing APIs, graph databases, or breaking the strict ₹0 budget constraints. It maintains historical, static semantics.

## 2. Current Repository/Data-State Findings
**FACT**: RailGati v1.2 has a complete relational schema mapping stations, trains, and temporal stop observations (`TrainStopObservation`).
**FACT**: The v1.2 journey API efficiently discovers point-to-point routes (direct and 1-transfer) via algorithmic deduplication and strict temporal rule enforcement (arrival/departure sequences).
**FACT**: Station and Train datasets are stable, versioned under a Snapshot (DatasetSnapshot) architecture.
**FACT**: No existing graph databases or caching systems (Redis) are currently deployed, and the architecture relies heavily on PostgreSQL's relational capabilities and `B-tree` indexes.

## 3. Problem Definition
Currently, users can check trains passing through a station, or compare historical journeys between a specific origin and destination. However, users cannot ask open-ended questions like "Which stations can I reach directly from here?" This limits exploratory planning. v1.3 solves this by providing a destination discovery interface.

## 4. Terminology and Definitions
- **Reachable Destination**: A canonical station that can be traveled to from the origin station following historical schedule constraints.
- **Direct Destination**: A station reachable via at least one direct train without transfers.
- **One-Transfer Destination**: A station reachable via exactly one valid historical transfer connection.
- **Journey Path**: A sequence of trains enabling travel from origin to destination.

## 5. Candidate Scope Analysis
- **A. Direct destinations only**: Simple query (origin `stop_sequence` < dest `stop_sequence`), highly performant. High product value.
- **B. Direct + one-transfer destinations**: Exponentially more complex candidate generation. Requires evaluating all possible transfers. May cause severe N+1 or Cartesian product performance issues if queried universally without constraints.
- **C. Destination discovery with travel-time filtering**: High value, allows answering "Where can I go in under 5 hours?". Requires robust duration parsing.
- **D. Destination discovery with transfer-count filtering**: Allows users to explicitly limit query scale (e.g. `max_transfers=0`).
- **E. Destination discovery with ranking**: Requires defining "best" destinations (by travel time, frequency, or alphabetical).

## 6. Proposed V1.3 Scope
**PROPOSAL**: v1.3 should implement Destination Discovery supporting:
1. Direct destinations (origin -> downstream stations).
2. Travel-time filtering (when temporal data allows duration calculation).
3. Transfer-count filtering strictly bounded to `max_transfers=0` initially (direct-only) to guarantee performance while providing immediate exploratory value. One-transfer destination discovery should be deferred or introduced with strict API bounds (e.g., maximum travel time) due to Cartesian explosion.

## 7. Explicit Non-Goals
**DEFERRED**: 
- Multi-transfer destination discovery (>1 transfer).
- Unbounded one-transfer destination discovery (if performance proves unacceptable).
- Graph databases or in-memory routing engines (e.g., NetworkX).

**OUT OF SCOPE**:
- Date-specific planning.
- Live fares, seat availability, or current delay statuses.
- Scraping or paid APIs.
- Recommendations based on live popularity or ML models.

## 8. Reachability Semantics
**PROPOSAL**: A destination is "reachable" if there is at least one structurally valid historical journey (direct, or bounded transfer) from the origin to that destination in the active snapshot. Missing temporal data (`MISSING_DATA` confidence) implies structural reachability but disqualifies the destination from duration-based filters.

## 9. Direct Destination Semantics
**FACT**: A direct destination requires a `TrainStopObservation` for the origin and a `TrainStopObservation` for the destination on the same `train_id`, where origin `stop_sequence` < destination `stop_sequence`.
**PROPOSAL**: The query should `SELECT DISTINCT destination_station_id` from such pairs. Return trains (same physical route, opposite direction) are treated purely by their respective historical schedules, not inferred.

## 10. One-Transfer Destination Semantics
**PROPOSAL**: Deferred for the initial v1.3 implementation, OR implemented only with mandatory strict travel-time bounds. A one-transfer destination is any station where the earliest combined historical journey duration (origin -> transfer -> destination) fits the user's constraints.
**OPEN QUESTION**: Does providing 1-transfer destinations universally (e.g. from NDLS to all of India) overload PostgreSQL? Benchmarking is required.

## 11. Timing and Source-Day Semantics
**FACT**: `source_day` is 1-indexed. Relative duration is calculated via `(dest_day - orig_day) * 24h + (dest_time - orig_time)`.
**PROPOSAL**: For travel-time filtering (e.g., "reachable in < X hours"), destinations reached by journeys with missing timing data are explicitly excluded, as the travel time cannot be verified against the filter.

## 12. Destination Identity and Deduplication
**PROPOSAL**: A destination is represented by its unique canonical Station. Even if 50 trains go from NDLS to MAS, MAS is returned exactly once in the destination list. The API may aggregate metadata (e.g., `fastest_duration`, `direct_trains_count`) for that destination.

## 13. Ranking and Sorting
**PROPOSAL**: Destinations should be deterministically sortable by:
1. `fastest_duration_minutes` (ASC, nulls last).
2. Alphabetical by canonical `station_name`.

## 14. Filtering
**PROPOSAL**: Support filtering by:
- `max_duration_minutes`: Excludes destinations requiring longer travel times.
- `max_transfers`: `0` (Direct only).

## 15. Data Source Assessment
**FACT**: Existing Datameet historical dataset is sufficient.
**PROPOSAL**: No new data sources required. Adheres to ₹0 budget constraint.

## 16. Query/Architecture Design
**PROPOSAL**: 
- Reusing `compare_journeys` iteratively over all stations would cause an N+1 query disaster.
- A dedicated service-level query `find_reachable_destinations(origin_station_id)` is required.
- The query relies on self-joining `TrainStopObservation` for direct destinations and grouping by destination.

## 17. PostgreSQL vs Graph Evaluation
**FACT**: PostgreSQL is currently sufficient for direct queries via standard joins.
**PROPOSAL**: No graph database (Neo4j) or memory graph (NetworkX) is required for v1.3. Direct downstream connectivity scales well in RDBMS via `B-tree` indexes.

## 18. Performance and Indexing Strategy
**FACT**: Existing B-tree on `(snapshot_id, train_id, stop_sequence)` supports rapid sequential scan per train.
**OPEN QUESTION**: A new composite index on `(snapshot_id, station_id, train_id)` might be required to rapidly find all trains leaving the origin station.
**PROPOSAL**: Implement without new indexes first. Benchmark against real Datameet volume. Apply indexes only if query exceeds acceptable thresholds (e.g., >500ms).

## 19. API Contract Proposal
**PROPOSAL**: 
`GET /api/v1/destinations`
**Query Parameters**:
- `origin`: string (canonical station code, required)
- `max_transfers`: int (default 0, constrained to 0)
- `max_duration_minutes`: int (optional, default None)
- `page`: int (default 1)
- `size`: int (default 50)

## 20. Response Contract Proposal
**PROPOSAL**:
```json
{
  "origin": "NDLS",
  "timetable_snapshot_id": 2,
  "max_transfers": 0,
  "total": 150,
  "page": 1,
  "size": 50,
  "destinations": [
    {
      "station_code": "MAS",
      "station_name": "CHENNAI CENTRAL",
      "fastest_duration_minutes": 1830,
      "direct_trains_count": 12,
      "timing_confidence": "HIGH"
    }
  ]
}
```

## 21. Error/Validation Contract
- **404 Not Found**: If `origin` station code does not exist.
- **422 Unprocessable Content**: If `max_transfers` > 0 (if 1-transfer is deferred), or `max_duration_minutes` < 0.

## 22. Snapshot and Provenance Semantics
**PROPOSAL**: The endpoint resolves the `ACTIVE` timetable snapshot exactly as the `stations` and `journeys` APIs do. Result sets strictly isolate to the matched `snapshot_id`.

## 23. Test Strategy
**PROPOSAL**:
- Unit tests: verify `fastest_duration_minutes` aggregates correctly across multiple direct trains.
- Unit tests: verify destinations with `stop_sequence` <= origin `stop_sequence` are NOT returned (no backwards time travel).
- API tests: validation bounds (`max_duration_minutes < 0`).
- Integrity tests: snapshot isolation.

## 24. Risks and Edge Cases
- **Looping Trains**: Trains visiting a station twice (e.g. circular trains) must not break `stop_sequence` logic. Handled correctly by selecting the *first* downstream occurrence.
- **Pagination Performance**: `LIMIT/OFFSET` on grouped destination aggregates might require full materialization.

## 25. Open Questions
- Should 1-transfer destination discovery be attempted relationally, or does it definitively mandate v2.0 graph capabilities?

## 26. V1.3 Acceptance Criteria
- [ ] Discovery API handles valid origin queries.
- [ ] Returns valid direct destinations.
- [ ] Correctly aggregates shortest travel time per destination.
- [ ] Properly paginates.
- [ ] Deterministic sorting behavior.
- [ ] Historical semantics explicitly stated in API docs.

## 27. Implementation Readiness
This specification can be safely implemented using the current data models without modifying schema or external infrastructure.

## 28. Deferred V1.4+ Ideas
- Map-based visualization of reachable destinations.
- Multi-transfer arbitrary routing.
- Graph database integration.
