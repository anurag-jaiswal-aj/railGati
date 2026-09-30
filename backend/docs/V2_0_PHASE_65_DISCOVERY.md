# RailGati V2.0 Phase 65 Discovery
## Edge Topological Resilience Detour

### 1. Objective & Candidate Selection
The objective of Phase 65 is to introduce a genuinely novel network/timetable analytical capability, avoiding trivial aggregations or projections of Phase 1–64.

**Rejected Candidates:**
- **Train Route Global Topological Chords:** Rejected because identifying un-traversed edges within a train's sequence footprint is structurally equivalent to calculating the explicit complement of Phase 55 (Sequence Subgraph Density).
- **Station Neighborhood Component Fragmentation:** Rejected as it overlaps with Phase 60 (Strict Local Bridges) and Phase 34 (Transit Articulation) without providing an independent, distinct routing concept.
- **Station Neighborhood Average Degree:** Rejected as a trivial arithmetic aggregation of Phase 7 (Hub Centrality).

**Selected Capability:** 
Edge Topological Resilience Detour

**Endpoint:**
`GET /api/v1/network/edges/{from_station_code}/{to_station_code}/topological-resilience-detour`

### 2. Formal Mathematical Definition
Let $G = (V,E)$ be the active undirected timetable topology graph, where:
- $V$ = station identities in the active snapshot.
- $E$ = distinct UNDIRECTED structural adjacencies induced by active `RailwayNetworkEdge` rows.

An undirected structural adjacency $\{A,B\}$ exists if at least one active NetworkEdge exists ($A \to B$ OR $B \to A$).

For target edge $e=\{A,B\} \in E$:
$G-e$ is the graph after removing $e$. Removing $e$ means removing the ENTIRE undirected structural adjacency between A and B from the search graph (i.e. if only $A \to B$ exists, remove it; if only $B \to A$ exists, remove it; if both exist, BOTH are excluded).

Then:
$$detour\_distance(e) = dist_{G-e}(A,B)$$
where $dist$ is the minimum number of undirected structural edges in a path from $A$ to $B$.

**Metrics:**
If $A$ and $B$ remain connected in $G-e$:
- `detour_distance` = $D(A,B)$
- `detour_exists` = true

If $A$ and $B$ are disconnected in $G-e$:
- `detour_distance` = null
- `detour_exists` = false

**Definitions:**
- direct structural edge distance before removal = 1
- triangle bypass A-C-B = detour_distance 2
- longer bypass = corresponding hop count
- no bypass = null

### 3. Terminology & Clarification of "Bridge"
If no alternative path exists between A and B after removing the target undirected structural adjacency ($detour\_distance$ is null), the target structural edge is a **graph-theoretic bridge of the active UNDIRECTED timetable topology**.

This explicitly does **NOT** imply:
- a physical railway track bridge
- actual passenger vulnerability or impact
- guaranteed service disruption
- real-world operational disruption or vulnerability

It is only a graph-theoretic property of the historical timetable topology. 
The analysis is restricted to "alternative structural path" evaluation.

### 4. Worked Example
**Graph:**
Target edge: A—B
Other topology: A—C, C—D, D—B, A—X, X—B

**Target Edge Removal:**
After removing the target undirected structural adjacency A—B, the remaining graph contains two paths:
- A—X—B = 2 hops
- A—C—D—B = 3 hops

**Result:**
- `detour_distance` = 2
- `detour_exists` = true
- `is_structural_bridge` = false

**Bridge Example:**
If the graph only contained A—B and A—C, removing A—B leaves no A-to-B path.
- `detour_distance` = null
- `detour_exists` = false
- `is_structural_bridge` = true

### 5. Output Schema
```json
{
  "from_station_code": "string",
  "from_station_name": "string",
  "to_station_code": "string",
  "to_station_name": "string",
  "detour_exists": boolean,
  "detour_distance": integer | null,
  "is_structural_bridge": boolean
}
```
*Note: `is_structural_bridge` is strictly evaluated as (`detour_distance` is null).*

### 6. Edge Validation & Semantics
- **Unknown station:** Returns standard 404 behavior.
- **Target structural adjacency does not exist in the active snapshot:** Returns standard 404 / not-found behavior.
- **Only one direction exists (A $\to$ B):** Treated as a valid, singular structural edge.
- **Both directions exist (A $\to$ B and B $\to$ A):** Treated as a single structural edge (reciprocal NetworkEdges do not represent two independent edges for this metric).
- **Self-edge (A $\to$ A):** Should not be treated as a valid A-B structural connection for this metric; validates via standard 400 error.

### 7. Overlap Audit
This metric computes the exact alternative path length for an edge, differentiating it mathematically from existing phases:
- **Phase 60 (Strict Local Bridges):** Asks a LOCAL neighbor-pair question around ONE station and only checks whether a 2-hop alternative exists through an allowed intermediate station. It cannot reconstruct exact detour distances greater than 2.
- **Phase 62 (Shortest-Path Divergence):** Asks the shortest structural distance between the endpoints of an ENTIRE TRAIN ROUTE and compares it with that train's actual route length.
- **Phase 65 (Edge Topological Resilience Detour):** Targets ONE EXISTING STRUCTURAL EDGE and computes the shortest alternative path between that edge's endpoints strictly after removing that exact edge.

### 8. Edge Cases
The implementation will natively handle:
- direct triangle bypass (distance 2)
- longer bypass (distance $> 2$)
- reciprocal target edge (both directions excluded)
- one-direction-only target edge
- structural bridge with no alternative (null)
- multiple alternative paths (evaluates the minimum)
- cycles (traversal deduplication)
- self-edge (rejected via validation)
- nonexistent structural edge (404)
- unknown station (404)
- snapshot isolation (only processes active snapshot edges)

### 9. Computational Strategy & Implementation Safety
The algorithm leverages a PostgreSQL-native recursive CTE / BFS:
1. Operate securely within the active snapshot.
2. Construct the undirected adjacency logically from both `NetworkEdge` directions.
3. Explicitly exclude the target undirected edge (A-B) from the traversal.
4. Search from A toward B, computing minimum depth.
5. Terminate efficiently when the destination B is reached or all reachable states are exhausted.

**Mathematical Bound vs. Operational Safeguards:**
The exact mathematical metric inherently caps at a safe theoretical maximum path length of $|V| - 1$, where $|V|$ is the number of distinct station vertices in the relevant active graph (because a simple shortest path cannot contain repeated vertices). The mathematical definition relies on this exhaustive search and does not impose arbitrary fixed depth limits (like $< 15$) that would silently alter the result. 

Practical execution safeguards (such as query timeouts, statement limits, or memory boundaries) are strictly operational safeguards. They must never be presented as part of the metric semantics, nor should they silently convert an expensive query into an "unknown" or "bridge" result.
