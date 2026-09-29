# V2.0 Phase 59 Discovery

## 1. Current Phase 1–58 Analytical Inventory
The RailGati network API currently exposes a comprehensive suite of analytical dimensions covering historical timetable structures:
- **Station/Train Basics:** Hub centrality (Phase 7), terminus classification, similarity.
- **Paths & Routes:** O-D paths, path attribution, continuous services, route profile, maximum shared sub-routes.
- **Edge Properties:** Edge volume, asymmetry, temporal bunching, relative slowness, exclusivity, dispersion.
- **Sequence Structure:** Topology loops, structural halts, bypasses (Phase 38), train route structural subsumption (Phase 37), topological transition continuity (Phase 56), disjoint reconvergences (Phase 57), topological degree extremes (Phase 58).
- **Temporal Analysis:** Concentration, gaps, paired-service symmetry, order inversions.

While sequence-level analytics and path-level analytics are highly mature, pure topological hierarchy at the station level (specifically, structural timetable containment) remains unexplored beyond simple degree counts and triadic ratios.

## 2. Candidate A: Station Neighborhood Topological Subsumption
- **Proposed Endpoint:** `GET /api/v1/network/stations/{station_code}/neighborhood-subsumption`
- **Definition:** For a target station $S$ and its undirected snapshot-scoped immediate timetable neighborhood $N(S)$, find all adjacent stations $H \in N(S)$ such that the reduced neighborhood of $S$ is a strictly proper subset of the reduced neighborhood of $H$. 

Mathematically: 
$N(S) \setminus \{H\} \subset N(H) \setminus \{S\}$

Operationally, $H$ strictly subsumes $S$ iff BOTH conditions hold:
1. Every neighbor of $S$ other than $H$ is also a neighbor of $H$ other than $S$.
($N(S) \setminus \{H\} \subseteq N(H) \setminus \{S\}$)
2. $H$ has at least one additional neighbor that $S$ does not have.
($N(H) \setminus \{S\} \setminus N(S) \neq \emptyset$)

- **Output Meaning:** Identifies adjacent stations that topologically "dominate" or strictly subsume the target station. If $S$ is subsumed by $H$, $H$ has a strictly larger immediate timetable neighborhood that contains all of $S$'s other immediate timetable neighbors. $S$ is structurally redundant to $H$ in the timetable topology.
- **Complexity:** $O(\text{Degree}(S) \times \text{MaxDegree})$, highly performant.

## 3. Candidate B: Train Sequence External Detour Availability
- **Proposed Endpoint:** `GET /api/v1/network/trains/{train_number}/external-detours`
- **Definition:** For each consecutive edge $A \to B$ in a train's sequence, determine if there exists a station $X$ *not* present in the train's sequence such that global edges $A \to X$ and $X \to B$ both exist in the active timetable.
- **Output Meaning:** Identifies edges along a train's route that have a 1-stop topological bypass via an external station.
- **Complexity:** $O(\text{Stops} \times \text{MaxDegree})$, highly performant.

## 4. Candidate C: Station Pair Strict Path Bottlenecks
- **Proposed Endpoint:** `GET /api/v1/network/stations/{from_code}/to/{to_code}/path-bottlenecks`
- **Definition:** For all trains traversing from station $A$ to station $B$, identify intermediate stations $X$ that appear on the sequence of *every single train* serving the $A \to B$ relation.
- **Output Meaning:** $X$ is a strict topological bottleneck for O-D travel between $A$ and $B$.
- **Complexity:** $O(\text{Trains}_{A \to B} \times \text{Stops})$, highly performant.

## 5. Rejected Candidates and Reasons
- **Station Hub-Spoke Oscillation:** Categorizing neighbors into Core/Periphery based on a threshold. *Reason:* Relies on arbitrary subjective degree thresholds.
- **Train Route Edge Centrality Profile:** Profiling the edge volume along a route. *Reason:* Too similar to Phase 58 (degree extremes) and Phase 26 (route profile), merely swapping station for edge.
- **Station Sequence Predecessor/Successor Overlap:** Comparing incoming vs outgoing trains. *Reason:* Redundant with Phase 32 (Neighborhood Directional Symmetry).

## 6. Novelty / Overlap Matrix

| Candidate | Closest Existing Phase(s) | Precise Distinction |
| :--- | :--- | :--- |
| **A. Neighborhood Subsumption** | P32, P33, P34, P35, P37, P58 | P32 calculates directional inbound/outbound Jaccard symmetry. P33 calculates closure among pairs of outbound neighbors. P34 calculates local bounded transit-articulation dependency. P35 calculates 2-hop expansion. P37 calculates strict ordered contiguous train-route subsumption. P58 calculates degree local extrema along a train sequence. Phase 59 introduces proper set-containment between reduced one-hop neighborhoods of adjacent station identities. |
| **B. External Detours** | P56 (Transition Continuity), P38 (Bypasses) | P56 checks if a 2-hop internal sequence has a 1-hop external shortcut. This checks if a 1-hop internal sequence has a 2-hop external detour. |
| **C. Path Bottlenecks** | P46 (Intermediate Hubs), P45 (Route Diversity) | P46 merely identifies high-degree intermediate stops. P45 counts distinct routes. This requires a strict intersection of intermediate stop lists across all matching trains. |

## 7. Recommended Phase 59 Capability
**Select: Candidate A (Station Neighborhood Topological Subsumption)**

**Reasoning:**
- **Semantic Novelty:** Introduces the concept of *strict hierarchical topological subordination* at the station level.
- **Usefulness:** Finding strict subsumption reveals exact structural subordination between stations in the timetable graph, highlighting stations that offer NO unique topological adjacency over their dominating neighbor.
- **Mathematical Precision:** Relies on absolute proper set-containment ($A \subset B$), preventing symmetric false subsumption and avoiding subjective thresholds.
- **Performance Feasibility:** Requires joining only the immediate neighbors of the target station and evaluating their neighborhoods, cleanly executable in set-based SQL.
- **₹0 Compliance:** Uses existing static timetable data.

## 8. Proposed Contract

- **Endpoint:** `GET /api/v1/network/stations/{station_code}/neighborhood-subsumption`
- **Parameters:**
  - `station_code` (str): The target station code.
- **Response Fields:**
  - `station_code` (str): The requested station.
  - `total_neighbors` (int): Total distinct topological neighbors of the target station.
  - `subsuming_neighbors` (list): Array of adjacent stations that structurally subsume the target station under the STRICT proper-subset relation.
    - `station_code` (str): Code of the subsuming neighbor.
    - `neighbor_degree` (int): The global degree of the subsuming neighbor.
- **Validation & Error Behavior:** 404 if the station does not exist or has no observations in the active snapshot. 503 if no active snapshot exists.
- **Empty/Null Behavior:** If the station is not subsumed by any neighbor, `subsuming_neighbors` is returned as an empty list `[]`.
- **Snapshot Semantics:** Evaluates strictly against the undirected topological edges present in the active timetable snapshot.
- **Occurrence Identity:** This endpoint is station-identity based, not timetable-occurrence based. Repeated timetable edges are deduplicated. The analytical entities are the target station identity $S$, the candidate adjacent station identity $H$, and distinct station identities in their snapshot-scoped immediate neighborhoods.

## 9. Concrete Examples

**Example 1: Proper Subset Subsumption**
- `SUBURB` connects to `JUNCTION` and `LOCAL_STOP`. 
- $N(\text{SUBURB}) = \{\text{JUNCTION}, \text{LOCAL_STOP}\}$.
- `JUNCTION` connects to `SUBURB`, `LOCAL_STOP`, `CITY_CENTER`, `NORTH_HUB`.
- $N(\text{JUNCTION}) = \{\text{SUBURB}, \text{LOCAL_STOP}, \text{CITY_CENTER}, \text{NORTH_HUB}\}$.

**Calculation:**
- Evaluate `JUNCTION` as a candidate subsumer for `SUBURB`.
- $N(\text{SUBURB}) \setminus \{\text{JUNCTION}\} = \{\text{LOCAL_STOP}\}$
- $N(\text{JUNCTION}) \setminus \{\text{SUBURB}\} = \{\text{LOCAL_STOP}, \text{CITY_CENTER}, \text{NORTH_HUB}\}$
- $\{\text{LOCAL_STOP}\}$ is a proper subset of $\{\text{LOCAL_STOP}, \text{CITY_CENTER}, \text{NORTH_HUB}\}$.
- Result: `JUNCTION` strictly subsumes `SUBURB`. `JUNCTION` has a strictly larger immediate timetable neighborhood that contains all of `SUBURB`'s other immediate timetable neighbors.

**Example 2: Leaf Station Behavior**
- A linear segment: `A — B`
- $N(A) \setminus \{B\} = \emptyset$
- $N(B) \setminus \{A\} = \emptyset$
- While $\emptyset \subseteq \emptyset$ is true, $\emptyset \subset \emptyset$ is false. $B$ does not have any additional neighbor.
- Result: Neither station strictly subsumes the other under the strict definition.

- A connected segment: `A — B — C`
- $N(A) \setminus \{B\} = \emptyset$
- $N(B) \setminus \{A\} = \{C\}$
- $\emptyset \subset \{C\}$ is true. $B$ strictly subsumes $A$.

**Example 3: Preventing Symmetric False Subsumption**
- $N(A) = \{B, C\}$
- $N(B) = \{A, C\}$
- $N(A) \setminus \{B\} = \{C\}$
- $N(B) \setminus \{A\} = \{C\}$
- Neither $\{C\} \subset \{C\}$ nor $\{C\} \subset \{C\}$ is true. The strict definition correctly prevents two adjacent stations with identical reduced neighborhoods from subsuming each other.

## 10. Implementation Constraints
- **SQL Strategy:** 
  1. CTE `edge_pairs` and `undirected_edges`: build the distinct snapshot-scoped neighborhood graph.
  2. CTE `target_neighbors`: Select immediate neighbors $v$ of the target $u=S$.
  3. CTE `candidate_neighbors`: Select edges $u, v$ for all candidate $H$.
  4. Final `SELECT`: Filter candidates $H$ by enforcing BOTH proper subset conditions:
     - A. No neighbor of $S$ (other than $H$) is missing from $H$'s neighborhood. (`NOT EXISTS`)
     - B. At least one neighbor exists in $H$'s reduced neighborhood that is absent from $S$'s reduced neighborhood. (`EXISTS`)
- **No-N+1 Requirement:** Must execute as a single `db.execute()` query.
- **Dialect:** Must remain set-based and compatible with both PostgreSQL (production) and SQLite (tests).

## 11. Non-Claims
This metric is exclusively a historical timetable-topology set-containment metric. It must NOT be interpreted as measuring or implying:
- physical infrastructure ownership or geography
- physical distance or geographic reachability
- passenger dependency, travel convenience, or accessibility
- operational dependency or priority
- service frequency advantage, actual train movement, congestion, or reliability

## 12. Final Verdict
Recommendation: PROCEED TO IMPLEMENTATION
