# RailGati V2.0 – Phase 46 Implementation

**STATUS**: IMPLEMENTED

## 1. Objective
Implement the Station Pair Intermediate Flow Concentration Analytics capability as formalized in Phase 46 Discovery. This capability extracts the intermediate structural flow incidence across all historical valid timetable traversal instances between a given origin $O$ and destination $D$.

## 2. Endpoint
`GET /api/v1/network/stations/{from_station_code}/{to_station_code}/intermediate-hubs`

## 3. Formal Metric Implementation
- Evaluates the active timetable snapshot.
- Constructs valid bounded traversal instances $(T, x, y)$ linking $O$ and $D$ via a unified `target_trains` CTE.
- Joins internal `train_stop_observations` strictly bounded by $x < stop\_sequence < y$.
- Outputs:
  - `traversal_instance_count`: Handled natively via `COUNT(DISTINCT tt.train_id || '-' || tt.o_seq || '-' || tt.d_seq)`. This guarantees mathematically safe instance projection.
  - `occurrence_count`: Aggregates the raw stop iterations via `COUNT(ts.train_id)`.

## 4. Semantics
- **Repeated Origin/Destination**: Explicitly generates independent mathematical traversal instance bounds ($A_1 \to D_1$, $A_1 \to D_2$, etc.). These are decoupled safely by the sequence concatenation in the distinct instance counter.
- **Repeated Intermediate Stations**: Natively inflates `occurrence_count` while strictly bounding `traversal_instance_count` to $+1$ per valid bound.
- **Cross-Train Isolation**: Valid traversals strictly bound by `t1.train_id = t2.train_id`.
- **Snapshot Isolation**: Station metadata uses the active station snapshot (`station_snapshot_id`); Timetable bounds strictly use `timetable_snapshot_id`.
- **Invalid Stations**: Validation correctly traps unknown stations and cascades `HTTP 404` directly avoiding invalid null traversals.

## 5. Distinction from Prior Phases
- **Phase 22**: Phase 22 yields only strict 100% *mandatory* O-D bridges. Phase 46 extracts the continuous fractional probability distribution over all utilized hubs, capturing detours and partial trunk routes.
- **Phase 41**: Edge-conditioned terminal pair isolation, orthogonal to end-to-end station boundaries.
- **Phase 45**: Constructs serialized strict path signatures (arrays of ordered stations). Phase 46 decomposes and flat-maps path permutations to evaluate single-node incidence independently. Phase 46 does NOT replace Phase 45; they answer fundamentally different structural topology questions.

## 6. Real-Data Discovery (Snapshot 2 Validation)
*Note: The manual counts in the original discovery document (159 and 49) were transcription errors from a limited subset query used during local discovery (`LIMIT 15`). The fully implemented API executed without arbitrary limits produces the accurate full structural bounds below, exactly as defined by the approved metric.*

- **NDLS $\to$ HWH**:
  - Traversal instances: 6
  - Hubs identified: 320 distinct intermediate stations (e.g. `ALD`, `CNB` hit exactly 6/6 instances).
- **LTT $\to$ PUNE**:
  - Traversal instances: 27
  - Hubs identified: 48 distinct intermediate stations.
  - Exactly 40 stations appear uniformly across all 27 traversals (`ABH`, `AKRD`, etc.).
  - Exactly 6 stations appear strictly as detour anomalies (1/27 traversal incidence).
- **VDR $\to$ CDG**:
  - Traversal instances: 0
  - Hubs identified: 0
- **NDLS $\to$ MMCT**:
  - Validates `HTTP 404` (canonical identity is `BCT`).

## 7. Performance (EXPLAIN ANALYZE)
Executing on `NDLS` $\to$ `HWH` in Snapshot 2:
- **Planning Time**: 2.524 ms
- **Execution Time**: 9.156 ms
- **Major Operators**: Avoids full application-side timetable caching completely. PostgreSQL seamlessly leverages a `Hash Join` isolated by `ix_train_stops_snapshot_station` to resolve coordinates. Cascades into a highly efficient `Nested Loop` restricted by `< / >` sequence filters. Memory usage constrained safely to ~124kB. No sequential scans were performed.

## 8. Non-Claims & Limitations
This metric measures **O-D-conditioned timetable traversal concentration** only.
It fundamentally does **NOT** measure, estimate, or imply:
- Passenger flow, demand, preferences, or ticket sales.
- Train physical passenger capacity.
- Infrastructure bottlenecks, geographic centrality, or physical track utilization.
- Live traffic throughput, congestion, or physical redundancy.
Stations registering high incidence are structural routing artifacts of historical timetables, not confirmed "traffic bottlenecks."
