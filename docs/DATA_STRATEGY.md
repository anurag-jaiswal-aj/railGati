# Data Strategy

## Core Principle: Data Ownership

RailGati must **own its normalized railway data** rather than simply proxying external APIs.

```
External data sources
       │
       ▼
  Ingestion & validation
       │
       ▼
  RailGati database (owned, normalized)
       │
       ▼
  Domain services & computation
       │
       ▼
  API responses
```

## Data Categories

### Store Permanently

Data that forms the foundation of RailGati's intelligence:

- Railway stations (codes, names, coordinates, zones)
- Station aliases and alternative names
- Railway zones and divisions
- Train definitions (numbers, names, types)
- Train routes and timetables
- Static geographic information

### Cache Temporarily

Data that is transient and should not be treated as authoritative:

- Live train running status
- Current seat availability
- Current fares
- Transient API responses

Cached data must always carry a `fetched_at` timestamp and a defined TTL.

### Calculate Internally

Intelligence that RailGati derives from owned data:

- Route graphs and connectivity
- Transfer possibilities
- Reliability metrics and scores
- Station connectivity metrics
- Delay predictions (future)
- Journey scoring and comparison

### Never Depend On Permanently

- A single commercial API as the sole source of truth
- Raw third-party API responses without normalization
- A paid LLM for basic deterministic calculations
- An external service that could disappear or become paid

## Provider Abstraction

External data providers must be accessed through abstract interfaces:

```
RailwayDataProvider (interface)
        │
        ├── OpenDataProvider (CSV/JSON datasets)
        ├── RailRadarProvider (API, if/when used)
        └── FutureProvider
```

The domain layer must never be coupled to a specific provider. If a provider is removed, only its adapter code changes.

## Data Provenance

Every piece of data must be traceable to its source:

- Which dataset or API provided it
- When it was imported
- What license governs it
- How reliable the source is

This is tracked through `DataSource` and `DatasetSnapshot` entities (to be implemented in v0.2).

## Implementation Status

| Aspect | Status |
|:-------|:-------|
| Data ownership architecture | Designed |
| Provider abstraction | Designed, not implemented |
| Data ingestion pipeline | **Implemented (v0.2)** - Generator-based parsing, deterministic validation |
| Database tables | **Implemented (v0.2)** - Provenance models and Station |

## v0.2 Ingestion Architecture

The data ingestion pipeline guarantees reproducibility, idempotency, and failure safety:

1. **Source Tracking**: Every run associates a `DatasetSnapshot` with a `DataSource` and stores a SHA256 checksum of the raw file.
2. **Deterministic Parsing**: The dataset is parsed as a generator (`ParsedStation`) to maintain low memory overhead.
3. **Validation**: Records are validated *before* insertion. Invalid records (missing codes/names, impossible coordinates) are explicitly tracked in the report, never silently swallowed.
4. **Idempotency**: Existing `code` keys in the database are cached into a `set` to allow fast skip-checks, preventing duplicates without DB constraints failing the batch.
5. **Failure Safety**: If a fatal error occurs, the transaction is rolled back, the existing `ACTIVE` snapshot remains active, and the new snapshot is marked `FAILED` with the error reason.
6. **Dry-Run Mode**: Full validation and reporting without `COMMIT`, supporting safe CI integration.
