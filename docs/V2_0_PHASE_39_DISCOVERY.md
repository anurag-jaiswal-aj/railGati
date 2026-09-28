# Phase 39 Discovery: Network Edge Traversal Dispersion Analytics

## 1. Selected Phase 39 Capability
**Network Edge Traversal Dispersion Analytics** (also known as Structural Edge Routing Diversity Analytics).

## 2. Exact Analytical Question
"When trains traverse a specific scheduled directed timetable edge $A \to B$, how many distinct preceding stations did they converge from, and how many distinct immediately subsequent stations do they bifurcate to?"

This quantifies the 2nd-order topological context of an edge by revealing its local mixing structure. 

## 3. Why It Is Useful
This metric automatically classifies the structural role of every timetable edge without requiring manual geographic or physical corridor mapping. It differentiates:
- **Trunk Corridors ($1 \to 1$):** High volume edges where all trains originate from the same preceding station and continue to the same subsequent station.
- **Funnels ($N \to 1$):** Edges where multiple diverse upstream routes merge into a single downstream direction.
- **Distributors ($1 \to N$):** Edges where trains arrive from a single route but immediately scatter to diverse downstream destinations.
- **Mixers / Interchanges ($N \to M$):** Edges that act as complex routing chokepoints where diverse inbound origins cross over to diverse outbound destinations.

## 4. Distinctness from Phases 1–38
- **Phase 7 (Edge Volume):** Only counts the scalar volume of trains traversing an edge. Dispersion evaluates the upstream/downstream topological footprint *conditioned* on that edge traversal.
- **Phase 19 (Outbound Transit):** Focuses on travel duration statistics from a station, not topological dispersion.
- **Phase 30 (Outbound Dominance):** Evaluates a single station's outbound degree distribution. Dispersion evaluates an *edge*, intrinsically linking the upstream arrival to the downstream departure.
- **Phase 33 (Transit Articulation):** Measures if a *station* acts as a cut-vertex for its 2-hop neighborhood. Dispersion classifies a specific *edge* as a convergence/bifurcation point.
- **Phase 38 (Topological Bypasses):** Evaluates a target train's *entire route* for structural short-circuits. Dispersion evaluates a target *edge* for its 4-hop structural sliding window $(X \to A \to B \to Y)$.

## 5. Formal Definition
For a target scheduled edge $E = (S_A, S_B)$ in an active timetable snapshot:
1. Define the traversal set $T_E$ as all train occurrences that visit $S_A$ at some sequence $i$ and $S_B$ at $i+1$.
2. **Edge Volume ($V$):** $|T_E|$
3. **Convergence Count ($C$):** The number of distinct stations $X$ visited at sequence $i-1$ by trains in $T_E$.
4. **Originating Count ($O$):** The number of trains in $T_E$ for which $i=1$ (the train starts at $S_A$).
5. **Bifurcation Count ($B$):** The number of distinct stations $Y$ visited at sequence $i+2$ by trains in $T_E$.
6. **Terminating Count ($T$):** The number of trains in $T_E$ for which $i+1$ is the final stop (the train ends at $S_B$).

## 6. Input Data Required
- `timetable_snapshots` (Active snapshot filter)
- `train_stop_observations` (Station visits, sequence numbers)
- `stations` (Resolving station codes $A$ and $B$)

## 7. SQL/Relational Computation Approach
Uses a CTE to isolate all `train_stop_observations` pairs for $A \to B$.
Then executes four parallel scalar subqueries against that CTE:
1. `COUNT(DISTINCT train_id)` for volume.
2. `JOIN` with $seq_o - 1$ and `COUNT(DISTINCT station_id)` for Convergence.
3. `NOT EXISTS` at $seq_o - 1$ for Originating.
4. `JOIN` with $seq_d + 1$ and `COUNT(DISTINCT station_id)` for Bifurcation.
5. `NOT EXISTS` at $seq_d + 1$ for Terminating.

## 8. Handling of Duplicates
`COUNT(DISTINCT station_id)` naturally prevents duplicate identical trains from artificially inflating the structural convergence/bifurcation counts. If 50 trains follow the exact same $X \to A \to B \to Y$ path, they contribute exactly 1 to Convergence and 1 to Bifurcation.

## 9. Active Snapshot Semantics
All lookups strictly isolate data to the `active_timetable_snapshot_id`. 

## 10. Edge Cases
- **Terminating Trains:** A train ending at $B$ has no subsequent station. It correctly does not contribute to `bifurcation_count`. It is tracked in `terminating_count`.
- **Originating Trains:** A train starting at $A$ has no preceding station. It is tracked in `originating_count`.

## 11. Real Snapshot 2 Exploration Results
Executing against Snapshot 2 reveals stark structural differences among high-volume edges:

- **SBB $\to$ GZB (Mixer):** Volume 143. Convergence 6. Bifurcation 5. (Massive interchange point).
- **MSB $\to$ MSF (Pure Origin):** Volume 132. 119 trains originate directly at MSB. Convergence is only 1.
- **DI $\to$ THK (Funnel):** Volume 121. Convergence 2. Bifurcation 1.
- **THK $\to$ DI (Distributor):** Volume 120. Convergence 1. Bifurcation 3.
- **BWN $\to$ TIT (Corridor):** Volume 118. Convergence 1. Bifurcation 1. (Strict trunk line).

## 12. Complexity Analysis
The analytical space is sharply constrained by the initial edge filter.
Complexity is $O(E_{AB} \times \log V)$ where $E_{AB}$ is the volume of the target edge, rather than the size of the whole network. 

## 13. EXPLAIN ANALYZE Findings
Benchmarked on `SBB -> GZB`:
- **Execution Time:** ~7 ms.
- **Plan:** No sequential scans. Utilizes `ix_stations_code` to resolve codes, `ix_train_stops_snapshot_station` to find all trains visiting SBB, and `train_stop_observations_pkey` nested loops to check $seq+1$ (for GZB), $seq-1$, and $seq+2$.
- Extremely performant. Safe for real-time API serving.

## 14. Expected API Endpoint
`GET /api/v1/network/edges/{from_station_code}/{to_station_code}/dispersion`

## 15. Expected Response Semantics
```json
{
    "from_station_code": "SBB",
    "to_station_code": "GZB",
    "timetable_snapshot_id": 2,
    "edge_volume": 143,
    "convergence_count": 6,
    "originating_train_count": 0,
    "bifurcation_count": 5,
    "terminating_train_count": 1
}
```

## 16. Explicit Non-Goals and Semantic Limitations
- This is a purely historical timetable-derived graph metric.
- It does **NOT** represent physical railway switch/junction complexity.
- It does **NOT** represent actual passenger transfers or passenger demand.
- It does **NOT** account for operational realities like platform occupancy, congestion, or physical capacity.
- It only measures scheduled sequence connectivity as published.

## 17. Why this is worthy of Phase 39
It provides a completely new dimension for understanding the network graph. While previous phases looked at how central a node is, or how much volume traverses an edge, this metric exposes the "second-order" routing topology of the network. It allows downstream analytical systems to automatically distinguish between a high-volume branch-line corridor and a high-volume central hub crossing, purely from tabular schedule structure.
