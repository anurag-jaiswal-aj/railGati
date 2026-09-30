# Phase 68 — Implementation Report

## Formal Definition
The Edge Topological Quadrangle Support measures the number of distinct chordless 4-cycles containing a given canonical undirected edge $e = (u, v)$ within the active graph build. 
A 4-cycle $u - a - b - v - u$ is chordless if and only if both potential chords $(u, b)$ and $(v, a)$ do not exist in the graph. This metric strictly counts the number of distinct parallel corridors forming a 3-hop detour grid around the edge, bypassing simple triangulation.

## Chordless-Cycle Semantics
An edge $e = (u,v)$ participates in a chordless 4-cycle if there is an edge $(x,y)$ such that $x \in N_{ex}(u)$ and $y \in N_{ex}(v)$, where:
- $N_{ex}(u) = N(u) \setminus N(v) \setminus \{v\}$
- $N_{ex}(v) = N(v) \setminus N(u) \setminus \{u\}$

Any such edge $(x,y)$ contributes exactly one distinct chordless 4-cycle. Diagonals (chords) are perfectly excluded because the vertex sets are strictly exclusive.

## Algorithm
1. Extract the full active canonical graph and build undirected adjacency sets in memory.
2. Iterate through all canonical edges $(u, v)$.
3. Compute exclusive neighborhoods $N_{ex}(u)$ and $N_{ex}(v)$ using set difference.
4. Iterate over the smaller of the two exclusive neighborhoods, counting connections into the larger exclusive neighborhood using $O(1)$ set intersection length.
5. Materialize the computed count into a bulk insertion table.

## Complexity
Graph extraction is $O(E)$.
Adjacency set operations take $O(d(u) + d(v))$.
Counting takes $O(|N_{ex}(u)|) \cdot O(1)$ intersection operations, bounded strictly by $O(d_{max})$.
Total complexity per edge is bounded by $O(d_{max})$, making the global complexity $O(E \cdot d_{max})$. Since $d_{max}$ is small in a sparse graph, it effectively acts as $O(E)$.

## Database/Materialization Design
Table: `railway_network_edge_topological_quadrangle_support`
Fields: `id`, `graph_build_id`, `timetable_snapshot_id`, `station_a_id`, `station_b_id`, `quadrangle_support`.
Constraints: `station_a_id < station_b_id`, unique compound index on `(graph_build_id, station_a_id, station_b_id)`.
Rebuilding the graph idempotently deletes old materialized rows to prevent duplicates.

## Endpoint
`GET /api/v1/network/edges/{from_station_code}/{to_station_code}/topological-quadrangle-support`

## Test Coverage
Created `test_network_edge_topological_quadrangle_support.py` in both `tests/api/` and `tests/services/`. Test coverage checks:
- Simple Paths (Support 0)
- Triangles (Support 0)
- Chordless Squares (Support 1)
- K4 Complete Graphs (Support 0, correctly identifying chords)
- Self-loops (rejected via HTTP 400/ValueError)
- Unknown stations and non-existent topological edges (HTTP 404/None)

## Oracle Validation
An explicit permutation-based Oracle (`oracle_quad.py`) was implemented checking all $\binom{V-2}{2}$ candidate pairs to find true chordless 4-cycles. The $O(E \cdot d_{max})$ exclusive-neighborhood production algorithm perfectly matched the Oracle mathematically. 

## Snapshot 2 Validation
The materialization process was executed on the exact PostgreSQL Snapshot 2 database.
- Canonical Graph Edges: 10,195
- Materialized Phase 68 Rows: 10,195
- Missing / Duplicate / Null Rows: 0
- Self-loops / Invalid Orientations: 0

## Actual Support Distribution
- Support 0: 9,505 edges
- Support 1: 604 edges
- Support 2: 71 edges
- Support 3: 14 edges
- Support 4: 1 edge

Total edges with support $\ge 1$: 690 edges.

## Performance Measurements
- Overall Graph extraction took standard time ($\approx 30$ seconds, though caching bypassed it in the tests).
- Phase 68 Quadrangle calculation purely on $10,195$ edges took strictly $<0.01s$.
- Idempotent Database insertion of 10,195 integer records took $\approx 0.15$s.
- The lookup API performs exactly 1 indexed SQL read on the materialized table, resulting in $O(1)$ response time.

## Regression Results
- **Phase 68 Tests**: Passed.
- **Phase 65 Regression**: Passed.
- **Phase 66 Regression**: Passed.
- **Phase 67 Regression**: Passed.
- **Full Pytest Suite**: 697 passed. 
- **Known Failure**: 1 known HTTP 404 failure strictly confined to `test_api_edge_exclusivity_success` (Phase 40). No other regressions occurred.
