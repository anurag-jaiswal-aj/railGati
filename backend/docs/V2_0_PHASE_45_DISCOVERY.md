# RailGati V2.0 – Phase 45 Discovery: Station Pair Route Diversity Analytics

## 1. Objective
Discover exactly ONE genuinely new Network Analytics capability for Phase 45 that is materially distinct from all previous phases, derives strictly from historical timetable data, and can be evaluated relationally under a ₹0 architecture.

## 2. Phase 1–44 Overlap Audit
This capability must be sharply distinguished from existing phase metrics:
- **Phase 17 (Network O-D Travel Time):** Analyzes the temporal duration between two stations, but does not extract or group by the structural intermediate paths taken.
- **Phase 22 (Station O-D Bridges):** Identifies all reachable destinations from a single station, but does not identify the specific paths or diversity of routes to a specific destination.
- **Phase 36 (Transfer-Free Reachability):** Measures the volume of reachable stations, not the topological paths taken to reach them.
- **Phase 39 (Edge Traversal Dispersion) & Phase 41:** Focus on terminal destinations of trains crossing a specific edge, rather than the entire intermediate route between two arbitrary stations.
- **Phase 43 (Train Maximum Shared Sub-Route):** Focuses on the longest shared contiguous sequence between two specific trains.
- **Phase 44 (Train Route O-D Structural Exclusivity):** Focuses on a single train and identifies O-D pairs that ONLY that train connects. It explicitly strips out intermediate sequence data to focus purely on the endpoints.

**Conclusion:** No existing endpoint extracts and groups the complete ordered sub-sequences (paths) connecting two specific stations to reveal how many structurally distinct ways trains navigate between them.

## 3. Candidates Considered
- **Network Station Triadic Closure for Transfers:** For a station, what ratio of incoming/outgoing direct routes bypass the station?
- **Train Sub-Route Edge Utilization:** For a given train, what is the average number of other trains sharing its edges?
- **Station Pair Route Diversity Analytics:** Given an Origin and Destination station, what are the distinct contiguous topological routes traversed by trains connecting them, and how are trains distributed across these routes?

## 4. Rejected Candidates and Reasons
- **Network Station Triadic Closure for Transfers:** Rejected because it overlaps directly with Phase 34 (Transit Articulation) and Phase 33 (Neighborhood Triadic Closure).
- **Train Sub-Route Edge Utilization:** Rejected because it is essentially an aggregate inversion of Phase 40 (Edge Structural Exclusivity) and Phase 28 (Relative Edge Slowness). It does not offer a genuinely new structural view.

## 5. Selected Phase 45 Capability
**Station Pair Route Diversity Analytics**
Given an Origin station $O$ and Destination station $D$, how many distinct structural paths (exact ordered station sequences) exist in the timetable connecting $O$ to $D$, and how many trains traverse each distinct path?

This metric reveals the structural diversity of the network between two points. For instance, it answers whether all 10 trains connecting New Delhi and Mumbai take the exact same physical route, or if they are distributed across 3 distinct topological corridors.

## 6. Formal Mathematical Definition
- Let $O$ and $D$ be the target origin and destination station identities.
- Let $\mathbb{T}$ be the set of all active trains in the timetable snapshot.
- For each train $t \in \mathbb{T}$, identify all pairs of sequence indices $(x, y)$ such that the train visits $O$ at stop sequence $x$, and visits $D$ at stop sequence $y$, where $x < y$.
- A single traversal instance is defined by the train $t$ and the valid sequence pair $(x, y)$.
- The structural route (path) of this traversal is the ordered sequence of station identities $P_{t,x,y} = [S_x, S_{x+1}, \dots, S_y]$.
- The metric groups all traversal instances across all trains by their exact structural route sequence $P$.
- For each unique structural route $P$, the metric calculates:
  - `path_length`: The number of stops in $P$ (which is $y - x + 1$).
  - `train_count`: The number of traversal instances that perfectly match route $P$.
- The output is the set of distinct structural routes, ordered by `train_count` descending, then `path_length` ascending.

## 7. Exact Data Semantics
The query isolates trains that visit both $O$ and $D$ in the correct order. It then extracts the complete ordered sequence of stations between those two sequence indices for each train, aggregates them into a string signature, and groups by that signature.

## 8. Snapshot Semantics
Target station validation, train filtering, and intermediate stop extraction are strictly isolated to the specified active `timetable_snapshot_id`.

## 9. Repeated-Occurrence Semantics
If a single train connects $O$ and $D$ multiple times (e.g., visits $O$, then $D$, then $O$ again, then $D$ again), each distinct $(x < y)$ topological pairing is evaluated as an independent traversal instance for that train. This correctly reflects that the train physically offers multiple distinct connection instances between the two stations, potentially via different intermediate paths.

## 10. Tie/Edge-Case Semantics
- **No Connecting Trains:** If no trains connect $O$ to $D$, returns an empty array.
- **Direct Adjacency:** If $O$ and $D$ are adjacent, the `path_length` is 2, and the signature is exactly `O -> D`.
- **Unknown Stations:** Returns HTTP 404.

## 11. Semantic Guardrails
- **Timetable-Structural Metric:** Quantifies historical timetable path diversity.
- **Does NOT infer:** Real-time train routing choices, physical track layouts, passenger preference for one route over another, or dynamic rerouting capabilities.

## 12. API Contract
**Endpoint:** `GET /api/v1/network/stations/{origin_station_code}/paths/{destination_station_code}`

**Response Schema:**
```json
{
  "origin_station_code": "LTT",
  "destination_station_code": "PUNE",
  "timetable_snapshot_id": 2,
  "distinct_path_count": 2,
  "paths": [
    {
      "path_signature": "LTT -> VVH -> GC -> VK -> KJMG -> BND -> NHU -> MLND -> TNA -> KLVA -> MBQ -> DIVA -> KOPR -> DI -> THK -> ABH -> KYN -> VLDI -> ULNR -> ABH -> BUD -> VGI -> NRL -> BVS -> KJT -> PDI -> MHC -> LNL -> MVL -> KMST -> VDN -> TGN -> BGWI -> DEHR -> PMP -> KSWD -> DAPD -> KK -> SVJR -> PUNE",
      "path_length": 40,
      "train_count": 26
    }
  ]
}
```

## 13. Query Strategy
1. **target_trains:** Identify trains hitting $O$ at $o\_seq$ and $D$ at $d\_seq$ ($o\_seq < d\_seq$).
2. **paths:** Join `target_trains` back to `train_stop_observations` to extract all stops $ts$ where $ts.stop\_sequence$ is between $o\_seq$ and $d\_seq$.
3. **signature generation:** Use `STRING_AGG(station_code, ' -> ' ORDER BY stop_sequence)` to build a deterministic path signature for each traversal instance.
4. **aggregation:** Group the results by `path_signature` and `path_length`, counting the distinct `train_id`s (traversal instances).
5. **Ordering:** Sort deterministically by `train_count DESC`, then `path_length ASC`.

## 14. Snapshot 2 Validation
Exploration against PostgreSQL Snapshot 2 confirmed the metric works natively:
- **NDLS -> MMCT:** Yields exactly **0 distinct paths**.
- **LTT -> PUNE:** Yields exactly **2 distinct paths** (one path taken by 26 trains, another longer path taken by 1 train).
- **BBS -> HWH:** Yields exactly **6 distinct paths** across 28 trains, showcasing diverse structural routing choices (e.g., via different bypasses).
- **NDLS -> HWH:** Yields exactly **3 distinct paths** across 6 trains.

## 15. EXPLAIN ANALYZE Findings
Testing the heavy traversal case (BBS -> HWH):
- **Planning Time:** 1.799 ms
- **Execution Time:** ~10.170 ms
- **Strategy Highlights:** The query efficiently leverages the `ix_train_stops_snapshot_station` index to quickly find candidates in `target_trains`, followed by an `Incremental Sort` and `Merge Join` against `train_stop_observations_pkey` to extract the intermediate stops. The `STRING_AGG` grouping is highly performant. The maximum memory used for sorting was only ~44kB. No sequential scans were performed on the observations table. This guarantees a safe $O(K \cdot L)$ scaling, where $K$ is the number of connecting trains and $L$ is the path length.

## 16. Implementation Boundary
This is Phase 45 discovery. No API logic, schema adjustments, or test implementations are permitted.

## 17. Explicit STOP Condition
Stop immediately after saving and committing this discovery document.
