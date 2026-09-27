# RailGati V2.0 Phase 33: Network Station Neighborhood Triadic Closure Analytics

## 1. Objective
Discover and rigorously specify the 33rd foundational railway analytics capability for RailGati V2.0. The objective is to identify a distinct analytical dimension that is mathematically deterministic, relies solely on historical/static active timetable data, requires no new infrastructure or migrations, and strictly honors the ₹0 budget.

## 2. Repository and Data-State Inspection
An inspection of the current RailGati repository and PostgreSQL database was conducted:
- **Timetable Snapshot:** Dataset Snapshot 2 is ACTIVE.
- **Graph Topology:** The network graph is constructed via sequence offsets (`stop_sequence` and `stop_sequence + 1`) from `train_stop_observations`.
- **Existing Analytics (Phases 1-32):** Includes metrics measuring degrees, volume, symmetry, loop topology, structural halts, slowness, outward dominance, and directional neighborhood overlap (Phase 32).

## 3. Existing Phase 1–32 Capability Map
- **Phase 7, 8, 10:** Node degrees and edge/O-D volumes.
- **Phase 11, 23, 27, 29:** Station time, dwells, gaps, and structural halts.
- **Phase 14, 30:** Imbalance on specific directed edges and outbound volume dominance.
- **Phase 15, 16:** Topological Jaccard similarities between distinct trains or stations.
- **Phase 18, 25, 31:** Paired-service layovers, temporal symmetry, and edge symmetry.
- **Phase 26:** Train-level topological loops.
- **Phase 32:** Station Neighborhood Directional Symmetry (Overlap of outbound vs inbound sets).

## 4. Candidate Analytics
Eight candidates were systematically generated and evaluated against the timetable structure:

1. **Network Station Route Terminal Diversity Analytics**
   - *Question:* For a given station S, what is the ratio of DISTINCT final terminating stations among all trains visiting S, relative to total trains visiting S?
   - *Unit:* A single station.
2. **Network Station Neighborhood Triadic Closure Analytics**
   - *Question:* For a given station S, among all unique unordered pairs of its distinct outbound scheduled neighbors {A, B}, what proportion have a scheduled timetable edge connecting A and B in either direction?
   - *Unit:* A single station's outbound neighbor set.
3. **Network Station Subsequent Hop Fan-Out Analytics (Neighborhood Expansion)**
   - *Question:* For a given station S, what is the average absolute outbound degree of its immediate scheduled outbound neighbors?
   - *Unit:* A single station.
4. **Network Edge Station Degree Assortativity**
   - *Question:* For a directed edge A->B, what is the ratio of |N_out(A)| to |N_in(B)|?
   - *Unit:* A single directed edge.
5. **Network Edge Route Persistence Analytics**
   - *Question:* For a directed edge A->B, among all trains traversing it, what proportion also share the identical subsequent edge B->C (most common)?
   - *Unit:* A single directed edge.
6. **Network Station Inbound-Origin Diversity Analytics**
   - *Question:* What is the ratio of distinct originating stations among all trains passing through S, relative to total trains?
   - *Unit:* A single station.
7. **Network Edge Dedicated Service Proportion Analytics**
   - *Question:* For an edge A->B, what proportion of scheduled train occurrences traversing A->B originate at A and terminate at B?
   - *Unit:* A single directed edge.
8. **Network Train Outbound Dominance Defiance Analytics**
   - *Question:* For a train identity, what proportion of the edges it traverses are NOT the dominant outbound edge (from Phase 30) of the originating station?
   - *Unit:* A single train identity.

## 5. Candidate-by-Candidate Analysis & Rejections
- **Candidate 1 (Terminal Diversity):** Overlaps significantly with Phase 9 (Terminus Analytics). Rejected.
- **Candidate 3 (Fan-Out):** Computes degree of neighbors, which is a trivial aggregation of Phase 7 (Hub Centrality). Rejected.
- **Candidate 4 (Assortativity):** Trivial mathematical division of Phase 7 results. Rejected.
- **Candidate 5 (Route Persistence):** Overlaps with Phase 12 (Route Complexity) and Phase 20 (Outbound Edge Transit). Rejected.
- **Candidate 6 (Origin Diversity):** Structurally identical to Terminal Diversity, overlapping Phase 9. Rejected.
- **Candidate 7 (Dedicated Service):** Rejected because the numerator (distinct trains originating at A, terminating at B, and traversing edge A->B) mathematically equates to non-stop trains covering O-D pair (A,B). This is a trivial intersection of Phase 10 (O-D flow) and Phase 8 (edge volume). It does not introduce a structurally new dimension.
- **Candidate 8 (Dominance Defiance):** A direct mathematical inverse of Phase 30 (Outbound Dominance). Rejected.

## 6. Selected Candidate
**Candidate 2: Network Station Neighborhood Triadic Closure Analytics**

## 7. Why Selected
Triadic Closure evaluates a timetable-derived local neighbor-pair closure ratio. It is mathematically distinct from all existing dimensions, depends strictly on timetable-derived scheduled occurrences, respects the ₹0 constraint, and can be efficiently executed using standard CTE aggregations on existing PostgreSQL indexes.

## 8. Why This Is Not Phase 1–32 Duplication
The metric must be strictly differentiated from Phases 7, 26, and 32:
- **Phase 7 (Hub Centrality):** Measures station-level degree/adjacency volume characteristics. It does not evaluate connectivity *between* the station's neighbors.
- **Phase 26 (Train Topology Loops):** Identifies non-consecutive repeated station visits within ONE train's ordered timetable route. Triadic Closure evaluates distinct edges independent of any single train's routing.
- **Phase 32 (Neighborhood Directional Symmetry):** Compares $N_{out}(S)$ against $N_{in}(S)$ using Jaccard overlap. Triadic Closure examines relationships BETWEEN MEMBERS OF $N_{out}(S)$. It evaluates second-order relationships among the queried station's outbound timetable neighbors, rather than comparing N_out to N_in.

## 9. Exact Semantics
- **Unit of Analysis:** A valid `Station` in the active snapshot.
- **Outbound Neighbors ($N_{out}$):** The distinct set of stations appearing as the immediately following scheduled stop after $S$ in the active timetable snapshot.
- **Possible Pairs:** $|N_{out}| \times (|N_{out}| - 1) / 2$. This represents the number of unique unordered pairs $\{A, B\}$ where $A, B \in N_{out}$ and $A \neq B$.
- **Pair Canonicalization:** Unordered pairs are canonicalized mathematically (e.g., $A < B$) to ensure that edges $A \rightarrow B$ and $B \rightarrow A$ both count identically toward closing the single unordered pair $\{A, B\}$.
- **Closed Pairs:** The number of unordered neighbor pairs $\{A, B\}$ for which at least one adjacent timetable edge exists between $A$ and $B$.
- **Closure Ratio:** $\frac{\text{Closed Pairs}}{\text{Possible Pairs}}$. The denominator is valid only when $|N_{out}| \ge 2$.

## 10. API Contract
**GET /api/v1/network/stations/{station_code}/neighborhood-triadic-closure**

**Response Fields:**
- `station_code` (str)
- `station_name` (str)
- `timetable_snapshot_id` (int)
- `outbound_degree` (int)
- `possible_neighbor_pairs` (int)
- `closed_neighbor_pairs` (int)
- `triadic_closure_ratio` (float)

**HTTP Behaviors:**
- **200 OK:** Successful calculation ($|N_{out}| \ge 2$).
- **400 Bad Request:** Outbound degree < 2.
- **404 Not Found:** Station not found.
- **503 Service Unavailable:** No active snapshot.

## 11. Analytical Unit
The unit of analysis is the distinct unordered topological pair within the outbound neighbor set of a queried station.

## 12. Active Snapshot Semantics
The endpoint strictly utilizes `get_active_timetable_snapshot_id(db)`. The calculation filters strictly by this snapshot.

## 13. Mathematical Definitions
For station $S$, let $N = N_{out}(S)$.
$$ \text{outbound\_degree} = |N| $$
$$ \text{possible\_neighbor\_pairs} = \frac{|N|(|N| - 1)}{2} $$
Let $E$ be the set of all active scheduled edges. For any canonical pair $\{A, B\} \in N$ where $A < B$:
$$ \text{closed\_neighbor\_pairs} = \sum_{A < B \in N} \mathbb{I}((A, B) \in E \lor (B, A) \in E) $$
$$ \text{triadic\_closure\_ratio} = \frac{\text{closed\_neighbor\_pairs}}{\text{possible\_neighbor\_pairs}} \quad \text{(Undefined if } |N| < 2) $$

## 14. Repeated-Occurrence Semantics
Handled explicitly via `DISTINCT` bounding and canonicalization `LEAST(a, b), GREATEST(a, b)`. $A \rightarrow B$ and $B \rightarrow A$ close the unordered pair $\{A, B\}$ exactly once. Repeated occurrences of $A \rightarrow B$ across 50 trains do not multiply the closure count, fulfilling the mathematical set definition of distinct presence.

## 15. Missing-Data Semantics
Edges missing from the snapshot dataset logically do not exist in the active timetable graph and do not contribute to closure.

## 16. source_day/timing Semantics
This metric relies exclusively on structural adjacency (`stop_sequence`). Arrival time, departure time, and `source_day` are mathematically irrelevant and explicitly excluded.

## 17. SQL/Query Strategy
1. **CTE `outbound_neighbors`**: Selects `DISTINCT tso2.station_id` originating from $S$. (DISTINCT guarantees true set membership for $N_{out}$).
2. **CTE `possible_pairs`**: Cross-joins `outbound a` and `outbound b` filtering `a.station_id < b.station_id` to generate unique unordered pairs.
3. **CTE `actual_edges`**: Selects `DISTINCT LEAST(tso1.station_id, tso2.station_id) AS n1, GREATEST(tso1.station_id, tso2.station_id) AS n2` joining on the primary sequence, filtered such that both endpoints exist within `outbound_neighbors`. (DISTINCT and LEAST/GREATEST safely canonicalizes bidirectional and repeated occurrences into singular unordered topological closures).
4. Returns the subquery counts of `possible_pairs` and `actual_edges`.

## 18. EXPLAIN ANALYZE
Tested for MGS on Snapshot 2.
- **Planning Time:** 1.90 ms
- **Execution Time:** 13.47 ms
- **Strategy:** PostgreSQL leveraged index scans (`ix_train_stops_snapshot_station` and `train_stop_observations_pkey`) for the initial localized graph traversal, evaluating neighbor interconnectivity through Hash Semi Joins against the index-scanned target set.
- **Sequential Scan:** No sequential scans were present in the generated query plan on the Snapshot 2 dataset.
- **Parallelism:** Processed natively without distributing to parallel workers.

## 19. Real Snapshot 2 Validation
The SQL was validated against actual Snapshot 2 data:
- **MGS (Mughal Sarai Junction):** Outbound degree 8. Possible unique pairs 28. Actual closed pairs 6. Ratio: 6/28 $\approx 0.214$.
- **BYS (Barsali):** Outbound degree 3. Possible unique pairs 3. Actual closed pairs 1. Ratio: 1/3 $\approx 0.333$. (Valid station, partial closure, HTTP 200).
- **XX-BECE (Bhilai East Cabin):** Outbound degree 1. Ratio undefined. (Triggers HTTP 400).

## 20. Independent Validation
An independent Python script successfully reproduced the exact metric for MGS.
- Constructed $N_{out}$ using a Python `set` comprehension: yielding 8 items.
- Generated all unique unordered pairs in Python: yielding 28 distinct elements.
- Iterated all raw topological snapshot edges, applying canonicalization `(min(a, b), max(a, b))` and testing membership against the 28 targets.
- Discovered exactly 6 canonical pairs mathematically closed by real adjacent edge data.
- $6 \le 28$. $0 \le 0.214 \le 1$. Ratio confirmed manually as $6/28$.

## 21. Edge Cases
- **Degree 0 or 1:** The denominator is zero. Triggers HTTP 400.
- **Valid Degree $\ge 2$:** e.g., BYS (degree 3). Ratio safely returns 0.333 with HTTP 200.
- **Symmetric Edges:** A bidirectional pair $(A \rightarrow B$ and $B \rightarrow A)$ closes the unordered pair exactly once.
- **Unknown Station Code:** Returns HTTP 404.
- **Station S as an Endpoint:** By definition, an edge between two members of $N_{out}(S)$ cannot involve $S$ unless $S$ is itself a member of its own $N_{out}(S)$ (a self-loop), which is exceptionally rare in the timetable. Even if it did, canonicalization handles it securely.

## 22. Error Semantics
- **404 Not Found:** Queried station is absent from the active dataset.
- **400 Bad Request:** Outbound degree $< 2$. Follows the RailGati convention established in prior phases (e.g., Phase 32 isolated stations, Phase 31 zero-forward train bounds) where an undefined mathematical denominator resulting from an absence of qualifying network bounds gracefully triggers HTTP 400 instead of returning falsified `0.0` or generic `null` topologies.
- **503 Service Unavailable:** Active timetable snapshot is missing.

## 23. ₹0 Compliance
Validates natively in PostgreSQL without supplemental indexing, relying strictly on existing relational tables.

## 24. Explicit Non-Goals
This metric evaluates a timetable-derived local neighbor-pair closure ratio. It does NOT establish:
- a passenger network
- an operational pattern
- a physical route structure
- physical track connectivity
- geographic proximity
- dispatcher intent

## 25. Implementation Boundaries
Only schemas, service logic, API route, and tests for Triadic Closure Analytics will be implemented in the active backend source tree.

## 26. Approval Gate
This Phase 33 discovery document has been finalized and audited. No application code has been modified. Phase 33 awaits implementation approval.
