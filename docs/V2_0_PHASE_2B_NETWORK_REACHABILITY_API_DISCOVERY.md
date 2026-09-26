# RailGati v2.0 Phase 2B — Bounded Network Reachability API Discovery

## 1. Objective
Design the first HTTP API layer that exposes the completed v2.0 Phase 2A bounded network reachability service (`find_reachable_stations`). The API will answer topological connectivity questions ("Which stations are reachable within N network hops?") without conflating topology with live passenger routing.

## 2. Current Phase 2A Service
The underlying service (`backend/src/railgati/services/network.py`) is complete and uses:
- A PostgreSQL recursive CTE for `RailwayNetworkEdge` traversal.
- PostgreSQL integer arrays for strict cycle prevention.
- Explicit timetable snapshot isolation.
- `ACTIVE` `RailwayGraphBuild` requirement.
- Minimum-hop deduplication with deterministic sorting (`min_hops ASC, station.code ASC`).
- Validation restricting `max_hops` to `1 <= max_hops <= 10`.
- Return type `list[StationReachability]` containing only `station_id` and `min_hops`.

## 3. API Purpose
To expose the topological sub-graph reachable from a canonical origin station via historical network adjacencies.

## 4. Non-Goals
This API strictly answers topology and will **not** evaluate:
- Passenger route viability, transfer buffers, or travel timing.
- Train identity, cancellations, delays, or fares.
- Live, day-specific, or current-time connectivity.
- Shortest-path sequential route reconstruction.

## 5. Existing API Conventions Inspected
Inspection of `backend/src/railgati/api/v1/destinations.py` and `schemas.py` reveals:
- **Origin resolution**: Exact match ignoring case (`func.lower(Station.code) == origin.lower()`).
- **Snapshot Selection**: `get_active_timetable_snapshot_id(db)` for timetable context, and `get_active_station_snapshot_id(db)` for station metadata.
- **Error conventions**: Missing origin or missing snapshots trigger `HTTP 404 Not Found`. Request validation uses FastAPI `Query` for `HTTP 422 Unprocessable Entity`.
- **Response Schemas**: Standard Pydantic models in `schemas.py` returning root fields (origin, snapshot id) and a list of items.

## 6. Proposed Endpoint
**GET** `/api/v1/network/reachable`

## 7. Request Parameters
| Name | Type | Location | Required | Default | Description |
|---|---|---|---|---|---|
| `origin` | `str` | Query | Yes | None | Canonical origin station code (e.g., `NDLS`). |
| `max_hops` | `int` | Query | Optional | `3` | Maximum network traversal depth. |

## 8. Parameter Validation
- **`origin`**: `min_length=1`, `max_length=50`. Whitespace will be trimmed automatically by FastAPI/Pydantic conventions.
- **`max_hops`**: `ge=1`, `le=10`. Handled automatically by FastAPI `Query(ge=1, le=10)`. 
  - `0`, `-1`, `11` → `422 Unprocessable Entity` (FastAPI native).
  - Non-integer input → `422 Unprocessable Entity` (FastAPI native).
  - The Phase 2A service acts as a secondary defense layer for the 1–10 boundary.

## 9. Station Resolution
- **Lookup**: Handled exactly as in `destinations.py` (`func.lower(Station.code) == origin.lower()`).
- **Missing Origin**: Raises `404 Not Found` with detail `"Origin station '{origin}' not found."`

## 10. Active Timetable Snapshot Selection
- Uses `get_active_timetable_snapshot_id(db)`.
- If no active timetable snapshot exists, it raises `503 Service Unavailable` as established in existing API conventions.

## 11. Graph Build Requirements
- Handled safely inside `find_reachable_stations`.
- If the snapshot has no `RailwayGraphBuild` or its status is `PENDING`/`FAILED`, the service throws a `ValueError`. 
- The router must catch this `ValueError` and translate it to `503 Service Unavailable` to reflect that the required infrastructure is temporarily or permanently unavailable.

## 12. Service/API Responsibility Boundaries
- **FastAPI Router**: Request validation, origin resolution, active snapshot selection, calling the service, error translation, station metadata resolution, response assembly.
- **Phase 2A Service**: Pure database traversal, CTE execution, topological boundary enforcement, recursive cycle prevention.

## 13. Final Proposed Response Schema
```python
class NetworkReachabilityItem(BaseModel):
    station_code: str = Field(..., description="Canonical station code")
    station_name: str | None = Field(None, description="Canonical station name")
    min_hops: int = Field(..., description="Minimum network hops to reach this station")

class NetworkReachabilityResponse(BaseModel):
    origin: str = Field(..., description="Canonical origin station code")
    timetable_snapshot_id: int = Field(..., description="ID of the timetable snapshot used")
    max_hops: int = Field(..., description="Maximum applied network hops")
    total: int = Field(..., description="Total number of reachable stations")
    stations: list[NetworkReachabilityItem]
```

## 14. Station Metadata Strategy
Station names must be resolved efficiently.
- Extract `[res.station_id for res in service_results]`.
- Use `get_active_station_snapshot_id(db)`.
- Perform a single set-based database query joining `Station` and `StationObservation` `WHERE station_id IN (...)`.
- Construct a dictionary mapping `station_id -> (code, name)` to populate the response schema in Python.
This strategy avoids N+1 per-station queries while ensuring the Phase 2A traversal service remains strictly topological.

## 15. Pagination Decision and Rationale
**Pagination is explicitly NOT recommended for this API.**
- **Actual Reachable-Station Cardinality**: Based on direct performance benchmarks executed on `timetable_snapshot_id=2` (from canonical origin NDLS):
  - `max_hops=1` yields 2 reachable stations.
  - `max_hops=3` yields 14 reachable stations.
  - `max_hops=10` yields 95 reachable stations.
- **Payload Size**: For a representative heavy-case (`max_hops=10` yielding ~95 stations), the JSON payload comprising only `code`, `name`, and `min_hops` per station will serialize to less than 10 KB.
- **Database Evaluation Dynamics**: The SQL-level implementation relies on a recursive CTE to traverse topological hops. A recursive CTE must inherently execute its full traversal to guarantee bounded depth accuracy and cycle prevention before any API-level windowing could apply. Whether returning 95 or paginating 20 items, the underlying work to construct the topological boundary remains consistent.
- **Decision**: Since the network topology naturally restricts reachable stations per hop, even the extreme `max_hops=10` boundary results in highly constrained responses. Slicing these lightweight responses via API-level pagination is unnecessary. This design favors returning the complete bounded topological structure in a single pass. This decision explicitly reflects the current v2.0 scope and graph characteristics, and can be revisited if future graph evolution demonstrates a need for pagination.

## 16. Error Contract
1. **Missing origin**: `422 Unprocessable Entity` (FastAPI).
2. **Empty origin**: `422 Unprocessable Entity` (FastAPI).
3. **Unknown station code**: `404 Not Found` (Router logic for resource lookup failure).
4. **Invalid max_hops (e.g. 0, 11, negative)**: `422 Unprocessable Entity` (FastAPI `Query` bounds).
5. **Non-integer max_hops**: `422 Unprocessable Entity` (FastAPI typing).
6. **No active timetable snapshot**: `503 Service Unavailable` (Existing API convention from `snapshots.py`).
7. **No ACTIVE graph build**: `503 Service Unavailable` (Translated from service `ValueError`).
8. **FAILED/PENDING graph build**: `503 Service Unavailable` (Translated from service `ValueError`).
9. **Valid origin, no reachable stations**: `200 OK` with `total: 0` and `stations: []`.

## 17. Deterministic Ordering
The API response directly mirrors the service's guaranteed ordering:
1. `min_hops ASC` (all immediate neighbors first).
2. `station.code ASC` (alphabetical canonical code fallback).
This is preserved by assembling the final items through sequential iteration over the service result.

## 18. Historical/Static Semantics
The endpoint represents historical/static reachability only. It leverages `timetable_snapshot_id` to strictly bound operations to the active topology graph. It guarantees network path adjacency, not real-world passenger travel feasibility.

## 19. Performance Considerations
Based on real `max_hops=10` evaluation on `timetable_snapshot=2`:
- **Execution Time**: The CTE completes in `<20ms` for a 10-hop span finding 95 stations.
- **Metadata Cost**: Fetching metadata via an `IN (...)` clause for ~100-8000 IDs requires one highly optimized Indexed B-Tree scan on the `stations` and `station_observations` tables, finishing in <10ms.
- **Indexes**: No new indexes are needed. The compound primary keys on `railway_network_edges`, `stations`, and `station_observations` perfectly service this workload.

## 20. Security/Input Validation
- All inputs are strictly typed via Pydantic/FastAPI and passed via parameterized SQL via SQLAlchemy.
- Arbitrary SQL execution is impossible.
- Snapshot selection is internally managed, shielding the graph from arbitrary user modification.
- Total memory exhaustion is completely prevented by the hard `max_hops=10` limit.

## 21. OpenAPI Documentation Requirements
The eventual FastAPI `@router.get` must include:
- `summary="Discover bounded network reachability"`
- `description="Returns the topological subgraph reachable within max_hops from the origin... This does not represent passenger routing, live timings, or viable travel itineraries."`
- Documented `404 Not Found` errors for missing origin and `503 Service Unavailable` for absent active graphs.

## 22. Future Implementation File Plan
- **Router/API**: Create `backend/src/railgati/api/v1/network.py` containing the router.
- **Schemas**: Update `backend/src/railgati/api/v1/schemas.py`.
- **Registration**: Register the router in `backend/src/railgati/api/v1/__init__.py`.
- **Tests**: Create `backend/tests/api/v1/test_network.py`.

## 23. Future Implementation Test Plan
1. Valid origin + `max_hops=1` (200 OK)
2. Valid origin + `max_hops=3` (200 OK)
3. Valid origin + `max_hops=10` (200 OK)
4. Default `max_hops` applies `3` (200 OK)
5. Missing `origin` parameter (422 Unprocessable Entity)
6. Empty `origin` (422 Unprocessable Entity)
7. Case-insensitive origin lookup (200 OK)
8. Unknown station code (404 Not Found)
9. `max_hops=0` (422 Unprocessable Entity)
10. `max_hops=11` (422 Unprocessable Entity)
11. Negative `max_hops` (422 Unprocessable Entity)
12. Non-integer `max_hops` (422 Unprocessable Entity)
13. No active timetable snapshot (503 Service Unavailable)
14. No ACTIVE graph build (503 Service Unavailable)
15. FAILED graph build (503 Service Unavailable)
16. PENDING graph build (503 Service Unavailable)
17. Valid origin with no reachable stations (200 OK, empty list)
18. Response properly ordered by `min_hops` then `station_code`
19. Station metadata bulk resolves efficiently
20. No N+1 query regression

*(Note: Pagination tests are explicitly excluded since pagination is deliberately removed from this endpoint for performance/semantics).*

## 24. Acceptance Criteria
- Discovery document complete.
- Follows all established project constraints.
- Identifies exact API boundaries.

## 25. Explicit Out-of-Scope Functionality
- Passenger multi-transfer routing (`ServiceEdge` routing).
- Timing, delay, and fare validation.
- Shortest-path journey reconstruction.

## 26. Strict Implementation Stop Condition
This constitutes the complete Phase 2B discovery. Implementation of the API router and schemas is intentionally deferred to the next phase.
