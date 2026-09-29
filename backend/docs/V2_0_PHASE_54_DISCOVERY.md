# V2.0 Phase 54 Discovery: Train Scheduled Stop Temporal Skew

## Objective
Discover and define exactly ONE genuinely novel railway-network analytics capability using the existing RailGati historical timetable dataset, adding a materially different analytical dimension from Phases 1–53.

## Candidate: Train Scheduled Stop Temporal Skew
**Exact Name:** Train Scheduled Stop Temporal Skew (or Train Temporal Skew)
**Exact Endpoint:** `GET /api/v1/network/trains/{train_number}/stop-temporal-skew`

### Analytical Question
Within a specific train's complete scheduled journey, are its intermediate stops distributed evenly across its total travel duration, or are they disproportionately clustered near the origin (front-loaded) or near the destination (back-loaded)? This reveals if a service functions structurally as a "local-then-express" or "express-then-local" service.

### Novelty Justification
This metric is materially distinct from existing phases:
1. **Phase 24 (Temporal Bunching) / Phase 25 (Temporal Concentration):** These evaluate departures at a single *station* across all trains. Phase 54 evaluates the internal geometry of a single *train* across all its stations.
2. **Phase 41 (Train Profile):** Evaluates macro totals (total duration, total dwell, percentage dwell) but inherently treats time as a flat sum. Phase 54 explicitly evaluates the *distribution* of time, identifying structural skew within the same total duration.
3. **Phase 50 (Temporal Order Inversions):** Evaluates if Train A passes Train B between two stations. Phase 54 evaluates a single train's structural schedule independently of others.
4. **Phase 51 (Intermediate Halt Stratification):** Evaluates the variance in the *number* of stops between two stations. Phase 54 evaluates the *time* at which stops occur across an entire route.

### Exact Semantics & Mathematical Definition
1. Identify the absolute origin stop (minimum `stop_sequence`) and extract its `departure_time` ($T_{start}$).
2. Identify the absolute terminal stop (maximum `stop_sequence`) and extract its `arrival_time` ($T_{end}$).
3. Calculate total journey duration: $T_{total} = T_{end} - T_{start}$ (safely accounting for midnight crossovers).
4. For every *intermediate* stop, determine its midpoint time $T_{inter}$: average of arrival and departure (or whichever is available if one is NULL).
5. For each intermediate stop, calculate its fractional temporal offset: $F_i = (T_{inter} - T_{start}) / T_{total}$.
6. Calculate the mean of all $F_i$.
7. **Temporal Skew** $= \text{Mean}(F_i) - 0.5$.

**Interpretation:**
- **< -0.05**: `FRONT_LOADED` (Stops occur disproportionately early in the journey).
- **> +0.05**: `BACK_LOADED` (Stops occur disproportionately late).
- **Between -0.05 and +0.05**: `BALANCED`.

### Identity & Grouping
- **Occurrence Identity:** An analyzed occurrence is the entire scheduled path of a specific `train_number` within a specific `snapshot_id`.
- **Grouping:** All valid intermediate `TrainStopObservation` rows belonging to that train.

### Database Sources & Requirements
- **Required Tables:** `trains`, `train_stop_observations`.
- **Timing Fields:** Mandatory. Requires `departure_time` and `source_day` at origin; `arrival_time` and `source_day` at terminal; and at least one timing field at intermediate stops.
- **Snapshot Scoping:** Bound strictly to a single `snapshot_id`.

### Edge Cases & Handling
1. **Missing/NULL Endpoints:** If origin lacks departure or terminal lacks arrival, $T_{total}$ cannot be established. Return `null` for skew.
2. **Zero/Undefined Denominator:** If $T_{total} \le 0$ (e.g., data anomaly where arrival $\le$ departure at endpoints without valid crossover), return `null` for skew.
3. **Sparse Case (0 Intermediate Stops):** If a train is non-stop (only 2 stops total), mean fraction is undefined. Return `null` for skew.
4. **Cyclic/Slip Routes:** Accurately evaluated by sequence order, treating the entire loop as a linear temporal progression from min sequence to max sequence.

### HTTP Semantics
- **Missing Train:** `404 Not Found`.
- **Sparse Case (0 intermediate stops):** `200 OK` with `temporal_skew = null`, `skew_classification = null`.
- **Invalid Data/Zero Denominator:** `200 OK` with `temporal_skew = null`.
- **Success:** `200 OK` with calculated schema.

### Proposed Response Schema
```json
{
  "train_number": "string",
  "total_intermediate_stops": "integer",
  "temporal_skew": "float | null",
  "skew_classification": "string | null"
}
```

---

## Snapshot 2 Real Data Discovery Results

Real queries against the historical PostgreSQL Snapshot 2 yielded the following cases:

1. **Normal Case (`12345` Saraighat Exp):**
   - Intermediate Stops: `130`
   - Temporal Skew: `-0.1587`
   - Classification: `FRONT_LOADED` (Spends more time stopping early in the journey).

2. **Major Case (`12516`):**
   - Intermediate Stops: `591`
   - Temporal Skew: `+0.0051`
   - Classification: `BALANCED` (Stops are evenly distributed).

3. **Unusual/Cyclic Case (`16688-Slip`):**
   - Intermediate Stops: `456`
   - Temporal Skew: `+0.0010`
   - Classification: `BALANCED`

4. **Sparse Case (`11449`):**
   - Intermediate Stops: `0` (or undefined due to lack of valid endpoints).
   - Temporal Skew: `None`
   - Classification: `None`

---

## Performance Assessment
A fresh `EXPLAIN (ANALYZE, BUFFERS)` on the final CTE logic for a single train (`12345`) in Snapshot 2:

- **Planning Time:** `2.754 ms`
- **Execution Time:** `248.144 ms`
- **Major Operators:** `Merge Join`, `GroupAggregate`, `Sort` (Memory: 25kB), `Nested Loop`, `Index Scan`.
- **Relevant Indexes Used:** `train_stop_observations_pkey`, `ix_trains_number`.
- **Sequential Scans:** 0 on main tables.
- **Temp Disk Usage:** 0 blocks read/written.

---

## Semantic Limitations
This is a purely historical timetable-derived metric. It explicitly does **NOT** measure:
- Passenger behavior, boarding distribution, or demand.
- Physical infrastructure, actual operations, or reliability.
- Congestion or platform capacity.
- The actual movement or physical speed of the train in the real world.
It measures purely the structural intent of the published schedule.

---

## Implementation Recommendation
**APPROVE DISCOVERY**. The capability is mathematically robust, handles edge cases gracefully, introduces a genuinely novel analytical dimension (internal temporal geometry), and strictly respects all data limitations and semantics.
