# V2.0 Phase 60 Discovery (Revised)

## 1. Phase 60 Objective
Identify and propose exactly one mathematically precise, genuinely distinct analytical capability for the RailGati V2.0 network analytics suite. The metric must rely strictly on historical static timetable topology (Snapshot-scoped), avoid redundancy with Phases 1–59, and execute efficiently without requiring real-time data or passenger assumptions.

### Addressed Revision Constraints
The previously considered "Station Pair Strict Path Bottlenecks" was correctly rejected because its outputs (the intersection of intermediate stops across all direct routes) can be trivially derived in memory from the exact station sequences exposed by **Phase 45 (Route Diversity)**. A core constraint of Phase 60 is that the capability must be strictly non-derivable from existing endpoints.

## 2. New Candidate Proposals

### Candidate A: Station Service Global Orthogonality
- **Entity:** Station.
- **Formal Definition:** For a target station $S$, evaluate all unique pairs of trains $(T_1, T_2)$ that both stop at $S$. Identify the proportion of these pairs that intersect *exactly once globally* (i.e., $|Stops(T_1) \cap Stops(T_2)| = 1$, and that intersection is $S$).
- **Inputs:** `station_code`.
- **Output Fields:** `total_train_pairs`, `orthogonal_train_pairs_count`, `orthogonality_ratio`.
- **Closest Existing Phases:** Phase 39 (Similarity) compares two explicitly provided trains. Phase 57 (Disjoint Reconvergences) requires trains to intersect at $\ge 2$ stops.
- **Exact Difference:** Aggregates pure 1-point topological route orthogonality across the entire cohort of trains visiting a single hub.
- **Derivability Test:** *Could this be reconstructed?* NO. It requires evaluating the global route intersection of every single pair of trains visiting $S$. No existing endpoint exposes the global routes for all trains at a station simultaneously.

### Candidate B: Station Neighborhood Strict Local Bridge Pairs
- **Entity:** Station.
- **Formal Definition:** For a target station $S$, evaluate every unique pair of its immediate neighbors $\{A, B\}$. Determine if $S$ acts as the absolute exclusive 2-hop topological bridge between $A$ and $B$, meaning there is no direct connection between $A$ and $B$, and no other alternative intermediate station $X$ connecting them.
- **Inputs:** `station_code`.
- **Output Fields:** Comprehensive list of neighbor pairs with their direct and alternative bridging properties.
- **Closest Existing Phases:** Phase 33 (Triadic Closure).
- **Exact Difference:** Phase 33 only evaluates 1-hop closure between neighbors. This metric introduces a strict topological search for alternative 2-hop global bridges ($X$).
- **Derivability Test:** *Could this be reconstructed?* NO. (See Derivability Section below).

### Candidate C: Train Sequence Forward Cohort Decay
- **Entity:** Train Sequence.
- **Formal Definition:** For target train $T$, evaluate the cohort of trains $C$ that share its initial edge $S_1 \to S_2$. For each subsequent stop $S_k$, calculate the exact subset of $C$ that has continuously shared every edge from $S_1$ up to $S_k$ with $T$.
- **Inputs:** `train_number`.
- **Output Fields:** `initial_cohort_size`, `decay_profile`.
- **Closest Existing Phases:** Phase 40 (Route Edge Exclusivity).
- **Exact Difference:** Phase 40 is memoryless; it counts raw volume per edge. Cohort Decay strictly intersects the *identities* of the trains.
- **Derivability Test:** *Could this be reconstructed?* NO. Deriving this requires the exact `train_id`s on every edge and performing a rolling identity set intersection, which is not exposed.

## 3. Rejected Candidates
- **Candidate A (Global Orthogonality):** Rejected. At major mega-hubs (e.g., `NDLS` with 300+ trains), evaluating $(300 \times 299)/2 = 44,850$ pairs and globally intersecting their routes poses a massive $O(N^2)$ cross-join performance risk in SQL.
- **Candidate C (Cohort Decay):** Rejected. The API semantics are awkward (defining which segment the cohort starts from), and rolling recursive identity intersections are notoriously difficult to write performantly across database dialects.

## 4. Selected Metric: Station Neighborhood Strict Local Bridge Pairs (Candidate B)

**Why this is the strongest candidate:**
- **Mathematical Precision:** Identifies absolute topological dependency and irreplaceable routing micro-hubs.
- **Analytical Novelty:** Completely survives the derivability test. It exposes hidden chokepoints that hold absolute monopoly power over specific neighbor pairs.
- **SQL Feasibility & Performance:** Highly constrained. By restricting the candidate pool strictly to the pairs of $N(S)$, the search space is drastically bounded. Performance will be exceptionally fast and predictable.

## 5. Formal Definition and Graph Semantics

1. **Neighbor Definition:**
   - A station $A$ is a neighbor of $S$ ($A \in N(S)$) if and only if there is at least one train in the active snapshot where $A$ is immediately followed by $S$ (or vice-versa). 
   - Adjacency is treated as an **undirected** structural edge derived from the timetable.

2. **Candidate Pair:**
   - A candidate pair $\{A, B\}$ must satisfy: $A \in N(S)$, $B \in N(S)$, and $A \neq B$. 
   - The pair is strictly **unordered** ($\{A, B\}$ is equivalent to $\{B, A\}$).

3. **Direct Closure:**
   - $A$ and $B$ have a "direct timetable adjacency" if there is an undirected edge between $A$ and $B$ in the active snapshot.

4. **Alternative 2-Hop Bridge:**
   - Another station $X$ provides an alternative bridge $A - X - B$ if and only if $X \neq S$, $X \neq A$, $X \neq B$, and undirected edges $\{A, X\}$ and $\{X, B\}$ both exist in the active timetable.

5. **Strict Local Bridge Predicate:**
   - $IsStrictLocalBridge(S, A, B) = \text{True}$ iff ALL of the following hold:
     1. $A \in N(S) \land B \in N(S)$
     2. **NO Direct Edge:** Direct adjacency $\{A, B\}$ does NOT exist.
     3. **NO Alternative X:** The count of alternative 2-hop bridges $X$ is exactly 0.

6. **Explicit Decisions:**
   - If $\{A, B\}$ has a direct edge, $IsStrictLocalBridge$ **fails** (evaluates False).
   - If another $X$ provides $A - X - B$, $IsStrictLocalBridge$ **fails**.
   - If multiple alternative $X$ values exist, it **fails**.
   - If $S$ is the only 2-hop intermediate, but $A-B$ is directly adjacent, it **fails**. They do not strictly depend on $S$ because they have a direct path.
   - If there is a longer path $A - X - Y - B$, it **does NOT matter**. The metric explicitly and strictly measures absolute 2-hop local isolation. A 3-hop or 10-hop detour is analytically distinct from a local 2-hop bridge.
   - Repeated train visits do not create duplicate station identities.
   - High or low train occurrence counts do not affect the boolean topological structure.

7. **Concrete Graph Examples:**
   Let $S$ be adjacent to $A$ and $B$.
   - **Case 1:** $A-S-B$ exists. No $A-X-B$ exists ($X \neq S$). No $A-B$ exists.
     **Result:** Qualifies (True). $S$ is the strict 2-hop bridge.
   - **Case 2:** $A-S-B$ exists. $A-X-B$ also exists. No $A-B$ exists.
     **Result:** Fails (False). $X$ is an alternative.
   - **Case 3:** $A-S-B$ exists. $A-B$ exists.
     **Result:** Fails (False). They have a direct edge.
   - **Case 4:** $A-S-B$ exists. $A-X-Y-B$ exists. No $A-X-B$ exists. No $A-B$ exists.
     **Result:** Qualifies (True). Longer paths do not violate the 2-hop exclusivity.

## 6. Precise Comparison Against Existing Phases
- **Phase 33 (Neighborhood Triadic Closure):** Phase 33 only calculates the ratio of direct edges $\{A, B\}$. It is entirely blind to the existence of $X$ outside $N(S)$.
- **Phase 34 (Transit Articulation):** Transit Articulation calculates if removing $S$ fractures the *entire global component*. Strict Local Bridges calculates localized 2-hop dependency. Removing $S$ might not disconnect the graph globally (Case 4), but it breaks the strict local bridge.
- **Phase 35 (2-Hop Reachability Expansion):** Phase 35 measures the raw count of distinct stations located exactly 2 hops from $S$. It does not evaluate the cross-connectivity of $N(S)$ via $X$.
- **Phase 32 (Neighborhood Directional Symmetry):** Phase 32 evaluates if $A \to S$ implies $S \to A$. Totally unrelated to $A-B$ cross-connectivity.
- **Phase 59 (Neighborhood Subsumption):** Phase 59 evaluates if $N(A) \setminus \{S\} \subset N(S) \setminus \{A\}$. It compares absolute subset hierarchies, not localized pairwise 2-hop exclusions.

## 7. Derivability Test Re-run
**Could this be reconstructed from an existing Phase 1–59 endpoint?**
**Answer: NO.**
While Phase 33 exposes whether $\{A, B\}$ has a direct edge (Condition 2), you cannot satisfy Condition 3 (Alternative Bridges). To know if an alternative bridge $X$ exists between $A$ and $B$, you must know if $N(A) \cap N(B) \setminus \{S\} \neq \emptyset$. Phase 33 only describes edges strictly *within* $N(S)$. Phase 35 lists nodes 2 hops away, but does not provide the explicit graph structure indicating which node in $N(S)$ connects to which node 2 hops away, nor does it map shared intersections. Without querying the database for $A \leftrightarrow X \leftrightarrow B$, it is impossible to derive the alternative bridge count.

## 8. Occurrence Identity and Deduplication
The timetable graph is evaluated purely topologically. Consecutive stops generate undirected edges $\{U, V\}$. 
- Multiple trains stopping consecutively at $U$ and $V$ collapse to a single unweighted edge.
- Cyclic trains or reciprocal directional trains ($U \to V$ and $V \to U$) collapse to a single distinct undirected adjacency representation. 

## 9. Edge Cases Handled
- **Degree 0 / Isolated Station:** Returns an empty array (0 neighbor pairs).
- **Degree 1:** Returns an empty array (0 neighbor pairs).
- **Degree 2:** Evaluates exactly 1 unordered pair.
- **Multiple Alternative X nodes:** Returns `alternative_bridge_count` > 0 and evaluates False.
- **Cyclic Routes:** Adjacency is collapsed; self-loops are ignored.

## 10. API Proposal and Output Fields
**Endpoint:** `GET /api/v1/network/stations/{station_code}/strict-local-bridges`

**Response Schema (`StationStrictLocalBridgesResponse`):**
- `station_code` (str)
- `timetable_snapshot_id` (int)
- `total_neighbor_pairs` (int): Total unique combinations of $N(S)$.
- `evaluated_pairs` (list of `NeighborPairEvaluation`):
  - `neighbor_a` (str)
  - `neighbor_b` (str)
  - `has_direct_adjacency` (bool): True if $A-B$ exists.
  - `alternative_bridge_count` (int): The exact number of alternative stations $X$ bridging $A$ and $B$.
  - `is_strict_local_bridge` (bool): True iff `has_direct_adjacency` is False and `alternative_bridge_count` is 0.

## 11. SQL/Query Strategy & Complexity
1. **CTE `target_neighbors`:** Fetch all distinct $A \in N(S)$.
2. **CTE `neighbor_pairs`:** Cross join `target_neighbors` to itself where $A < B$ (for undirected unique pairs).
3. **CTE `direct_adj`:** Join `neighbor_pairs` against the global edge table to determine if $\{A, B\}$ exists.
4. **CTE `alt_bridges`:** Join `neighbor_pairs` against global edges twice ($A \leftrightarrow X$ and $X \leftrightarrow B$) where $X \neq S$. Group by $A, B$ to count distinct $X$.
5. Select the pairs, left join the flags, and compute the final boolean.
- **Complexity:** $O(N(S)^2 \times \text{MaxDegree})$. Extremely performant due to the localized bounds of $N(S)$.

## 12. Implementation Acceptance Criteria
- Must execute as a single primary `db.execute` query.
- Must correctly populate all boolean flags and counts.
- Must not use application-level N+1 loops.
- Must be covered by focused API and service tests verifying the concrete graph cases.
- Must leave the legacy Phase 40 test failure untouched.

**Phase 60 implementation is NOT part of this discovery.**
