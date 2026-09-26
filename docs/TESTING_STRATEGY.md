# Testing Strategy

## Test Pyramid

```
              ╱╲
             ╱  ╲
            ╱ E2E╲          Few, critical user journeys
           ╱──────╲
          ╱Contract╲        Provider response validation
         ╱──────────╲
        ╱ Integration╲     DB, API endpoints, caching
       ╱──────────────╲
      ╱   Unit Tests    ╲  Domain logic, parsers, algorithms
     ╱__________________╲
```

## Unit Tests

Test pure logic with no external dependencies.

**Future targets:**
- Domain model validation (station codes, train numbers)
- Data parsers (CSV, GeoJSON, API response mapping)
- Route graph algorithms (shortest path, connectivity)
- Journey planner logic (transfer detection, time window matching)
- Search algorithms (fuzzy matching, alias resolution)
- Value object calculations (distances, delays, durations)

**Tools:** pytest, factory_boy (for test data factories)

## Integration Tests

Test components with real infrastructure.

**Future targets:**
- Database repository operations (CRUD, complex queries)
- API endpoint request/response validation
- Data ingestion pipeline (file → DB)
- Cache layer behavior (when Redis is introduced)

**Tools:** pytest, testcontainers (disposable PostgreSQL for CI), httpx (async test client)

## Contract Tests

Validate that external provider responses match expected schemas.

**Future targets:**
- RailRadar API response structure (when integrated)
- Provider adapter mapping correctness
- API versioning (v1 response schema stability)

**Approach:** Record actual API responses using VCR.py / pytest-recording, then replay in tests. This avoids consuming external API quotas in CI.

## End-to-End Tests

Test critical user journeys through the full stack.

**Future targets:**
- Station search flow
- Journey planning flow
- Map interaction

**Tools:** Playwright (when justified)

## Data Validation Tests

Ensure dataset integrity after ingestion.

**Future targets:**
- No duplicate station codes
- All TrainStops reference valid Stations
- Geographic coordinates within India's bounding box
- Temporal consistency (departure ≤ arrival with day offsets)
- Cross-source consistency

## Currently Implemented (v0.1)

| Layer | What | Tool |
|:------|:-----|:-----|
| Unit | Health endpoint response | pytest + httpx (TestClient) |

All other test layers will be implemented as their corresponding features are built.

## Principles

- Tests must be **deterministic** — no network calls, no randomness.
- Tests must run **without external services** (except DB via testcontainers in integration tests).
- Tests must be **fast** — unit tests complete in seconds.
- Use **fixtures and factories** for test data, not hard-coded values.
- **No mocking of domain logic** — mock only external boundaries.
