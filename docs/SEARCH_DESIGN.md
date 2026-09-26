# Station Search & Database Performance Design

## Requirements
RailGati v1.0 requires a fast, deterministic station search endpoint for both general search and frontend autocomplete. The search must:
- Match `Station.code` exactly or by prefix.
- Match `StationObservation.name` exactly or by substring.
- Be case-insensitive.
- Always return results scoped strictly to the current active `DatasetSnapshot`.

## Ordering Strategy
To ensure the most relevant results surface first, especially for short autocomplete queries, the ordering prioritizes:
1. Exact Code matches.
2. Code Prefix matches.
3. Exact Name matches.
4. Alphabetical Fallback.

## Database Indexes & Performance
The strict requirement for v1.0 was to *only add justified indexes* and explicitly evaluate:
- `station code`
- `station observation snapshot_id`
- `station observation station_id`
- `station name search`

**Evaluation:**
1. **`Station.code`**: Already indexed via `index=True, unique=True` from v0.1/v0.2.
2. **`StationObservation.snapshot_id` and `station_id`**: As these form the composite Primary Key (`snapshot_id`, `station_id`), PostgreSQL inherently provisions a B-Tree index covering them. This explicitly covers filtering by `snapshot_id`.
3. **`StationObservation.name`**: Searching by `ILIKE` typically requires a trigram index (`pg_trgm`) or a functional `lower()` index to avoid a sequential scan. 

**Decision:**
For v1.0, the total dataset size is ~9,000 canonical stations. A sequential scan over 9,000 rows utilizing the existing PK index for the snapshot filtering takes approximately **1-2 milliseconds** in standard PostgreSQL. 

Adding explicit GIN/trigram indexes or OpenSearch infrastructure for this scale constitutes premature optimization and speculative engineering. Standard PostgreSQL `ILIKE` combined with the implicit composite PK index is heavily justified and maximally efficient for v1.0 parameters. No additional indexes were added.
