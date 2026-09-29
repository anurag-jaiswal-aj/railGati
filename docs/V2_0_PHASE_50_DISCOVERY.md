# RailGati V2.0 - Phase 50 Discovery
## Network Station Triplet Sequential Traversal Analytics

**Status:** `DISCOVERY — NOT APPROVED`

### 1. Rationale and Capability Definition

In previous phases, RailGati has heavily focused on analyzing the structural and network properties of independent station pairs (O-D pairs). However, real-world railway network corridors often span multiple key intermediate nodes, creating a demand for multi-segment sequential reachability analysis. 

Phase 50 introduces **Network Station Triplet Sequential Traversal Analytics**. This capability answers a critical structural question: *Given an ordered triplet of stations (A, B, C), how many distinct trains traverse this entire corridor sequentially without requiring a transfer?*

This metric determines if a station acts as a structural terminus/divergence point or a pass-through node for a given corridor, directly evaluating the timetable-derived structural continuity of multi-segment passenger journeys.

### 2. Mathematical and Relational Model

For any given timetable snapshot $\mathcal{S}$ and an ordered triplet of stations $(A, B, C)$, we define a valid **Sequential Triplet Traversal** if there exists a train $T$ such that:

1. $T$ stops at station $A$ at sequence $s_A$
2. $T$ stops at station $B$ at sequence $s_B$
3. $T$ stops at station $C$ at sequence $s_C$
4. $s_A < s_B < s_C$

The analytics output computes:
- $\text{traversal\_occurrence\_count}$: The total number of valid sequential traversals $(t, s_A, s_B, s_C)$ satisfying the above conditions.
- $\text{distinct\_train\_count}$: The number of unique trains providing this service. (This is distinct from occurrence count when trains have topological loops, though rare for triplets).

### 3. Snapshot 2 Validation

Exploratory queries on the actual historical Datameet Snapshot 2 database yield the following highly distinct results, proving the metric's capacity to discriminate between continuous corridors and disjointed segments:

* **CNB -> NDLS -> UMB (Kanpur -> New Delhi -> Ambala)**
  * `traversal_occurrence_count`: 0
  * `distinct_train_count`: 0
  * *Insight: Although Kanpur to New Delhi is a massive corridor, and New Delhi to Ambala is another, no trains run this exact sequential corridor (trains from Kanpur terminate at NDLS or bypass it).*

* **NDLS -> UMB -> CDG (New Delhi -> Ambala -> Chandigarh)**
  * `traversal_occurrence_count`: 5
  * `distinct_train_count`: 5
  * *Insight: Defines a robust continuous corridor (e.g., Shatabdi services).*

* **BCT -> BVI -> ST (Mumbai Central -> Borivali -> Surat)**
  * `traversal_occurrence_count`: 22
  * `distinct_train_count`: 22

* **GKP -> LKO -> CNB (Gorakhpur -> Lucknow -> Kanpur Central)**
  * `traversal_occurrence_count`: 8
  * `distinct_train_count`: 7
  * *Insight: Shows that 7 distinct trains provide this continuous transit, with one train executing the corridor twice.*

### 4. Database Performance Analysis

A PostgreSQL `EXPLAIN (ANALYZE, FORMAT JSON)` audit was run on the Triplet Sequential CTE query. 

**Execution Plan for BCT -> BVI -> ST:**
- **Join Strategy**: `Merge Join` between sequences $A \to B$, and a `Bitmap Heap Scan` for sequence $C$.
- **Index Utilization**: Heavily utilizes `ix_train_stops_snapshot_station` to filter observations efficiently.
- **Execution Time**: ~1.3ms.
- **Complexity**: $O(N \log N)$ based on the subset of trains stopping at the stations, avoiding $O(N^2)$ cross joins.

### 5. Proposed Endpoints

* `GET /api/v1/network/station-triplets/{station_a}/{station_b}/{station_c}/sequential-traversals`
  * Returns the triplet analytics for a specified snapshot.

### 6. Proposed Schema

```python
class StationTripletSequentialTraversalMetrics(BaseModel):
    traversal_occurrence_count: int = Field(..., description="Number of valid A -> B -> C sequential traversals")
    distinct_train_count: int = Field(..., description="Number of distinct trains providing this sequential triplet service")

class StationTripletSequentialTraversalResponse(BaseModel):
    snapshot_id: int
    station_a: str
    station_b: str
    station_c: str
    metrics: StationTripletSequentialTraversalMetrics
```

### 7. Next Steps

Awaiting explicit approval to proceed with Phase 50 implementation. No code changes have been made to the application.
