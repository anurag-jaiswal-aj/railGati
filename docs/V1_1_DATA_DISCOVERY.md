# RailGati v1.1 — Timetable Data Foundation Discovery

## 1. Executive Summary
This document explores the viability of establishing a railway timetable data foundation for RailGati v1.1 that strictly adheres to the project's absolute ₹0 budget and "no scraping" architectural rules. The research concludes that while no genuinely open, actively maintained, and free *live* timetable API exists for public use, the **Datameet Railways** repository provides a legally usable (CC0), structured, and reproducible historical snapshot of Indian Railway timetables (circa 2016). 

It is proposed that v1.1 will utilize this historical static dataset to build out the timetable ingestion pipeline, database models, and internal discovery API, explicitly treating it as a "point-in-time" historical snapshot rather than live operational data. This respects all project constraints while allowing architectural progression.

## 2. Current v1.0 Data Situation
RailGati v1.0 successfully implemented a robust station discovery engine using the Datameet `stations.json` dataset. It utilizes an idempotent, provenance-aware architecture (`Station`, `StationObservation`, `DatasetSnapshot`) to securely version the data. However, train timetables and station-to-station train discovery remain at 0% coverage and are exposed via a graceful `501 Not Implemented` fallback in the v1.0 API.

## 3. Requirements
- **Strictly ₹0 budget**: No paid APIs, databases, or infrastructure.
- **No scraping**: Fragile web scraping (e.g., IRCTC, NTES, eRail) is prohibited.
- **Legally usable**: Permissive open-data licenses (CC0, GODL) required.
- **Reproducible**: Ingestion must rely on a stable, hashable, or versioned data artifact.
- **Provenance-aware**: Must slot into the existing `DatasetSnapshot` architecture.

## 4. Candidate Source Evaluation

### Candidate A: Datameet Railways (GitHub)
- **Source name**: Datameet Railways (`trains.json`, `schedules.json`)
- **Publisher**: Datameet Community (https://github.com/datameet/railways)
- **Data format**: JSON
- **License**: Creative Commons Zero (CC0)
- **API vs downloadable**: Downloadable static files.
- **Cost**: ₹0
- **Train / Station coverage**: Extensive national coverage for the time period.
- **Data freshness**: Historical (circa 2016). No longer actively updated.
- **Suitability**: **Suitable for v1.1 investigation** (with freshness limitations).

### Candidate B: Open Government Data Platform (data.gov.in)
- **Source name**: Indian Railways Time Table
- **Publisher**: Ministry of Railways
- **Data format**: CSV / JSON (often mirrored via Kaggle)
- **License**: Government Open Data License (GODL)
- **API vs downloadable**: Downloadable datasets.
- **Cost**: ₹0
- **Data freshness**: Historical (mostly 2015-2017 snapshots).
- **Suitability**: **Potentially suitable with limitations** (Structure requires heavy normalization compared to Datameet).

### Candidate C: shwetankg07/railpull (NTES Scraper)
- **Source name**: Railpull
- **Publisher**: Community maintainer
- **License**: MIT
- **Data format**: Dynamic scraping script
- **Suitability**: **Requires prohibited scraping**. While highly praised for generating up-to-date data, it crawls NTES directly, violating the core "no scraping" architecture mandate.

### Candidate D: Official CRIS / IRCTC APIs
- **Publisher**: Centre for Railway Information Systems (CRIS)
- **Suitability**: **Paid/Restricted**. Requires official B2B commercial tie-ups, steep integration fees, or authorization limits. Violates the ₹0 mandate.

## 5. License/Terms Analysis
- **Datameet Railways**: Released under **CC0 (Public Domain)**. Commercial use, redistribution, and modification are fully permitted without attribution, avoiding any legal ambiguity.
- **data.gov.in**: Released under **GODL**. Permits commercial use and redistribution but requires specific attribution statements.
- **Third-party APIs**: Generally possess strict Terms of Service prohibiting scraping, reverse engineering, and unlicensed commercial use.

## 6. ₹0 Analysis
The Datameet repository files can be fetched directly via HTTP from GitHub's raw CDN. There are no API keys, no subscription tiers, and no hidden bandwidth costs (assuming responsible caching/downloading during ingestion). It guarantees a ₹0 implementation.

## 7. Data-Quality Analysis
Using the Datameet `schedules.json` and `trains.json` exposes several data quality hurdles:
- **Duplicate trains**: Multiple trains might share numbers across different zones or historical periods.
- **Operating days**: Represented often as bitmaps or boolean flags needing parsing.
- **Missing times**: Some stations (like pass-throughs) may lack explicit arrival/departure times.
- **Timezone**: Assumed IST (+05:30) but encoded as raw strings (e.g., "14:30").
- **Overnight journeys**: Cross-midnight journeys require calculating day offsets (Day 1, Day 2).

## 8. Freshness Analysis
The timetable data is **historical and static**. It does not reflect new Vande Bharat routes, recent station renames, or current COVID/post-COVID operational realignments.
- **Recommendation**: RailGati must explicitly represent this via the `DatasetSnapshot.retrieved_at` metadata and render frontend disclaimers that the timetable is a "historical snapshot for architectural demonstration."

## 9. Reproducibility Analysis
Datameet is hosted on GitHub. We can achieve 100% reproducibility by fetching the raw JSON files using a specific **commit hash** (e.g., `https://raw.githubusercontent.com/datameet/railways/<COMMIT_HASH>/data/schedules.json`). This ensures identical data ingestion across environments.

## 10. Station Matching Analysis
Timetable records reference stations by their alpha-codes (e.g., `NDLS`).
- **Strategy**: The v1.1 ingestion pipeline must strictly match timetable station codes against the canonical `Station.code` populated in v0.2.
- **Missing Stations**: If a timetable record references a code that does not exist in our canonical `Station` table, the ingestion pipeline must safely reject or orphan the specific stop observation, recording the rejection in a provenance artifact. Silently creating empty stations from timetable data should be avoided.

## 11. Proposed v1.1 Domain Model
To preserve canonical identity while allowing snapshots, the following minimal architecture is proposed:

```python
class Train(Base):
    """Canonical train identity."""
    id: Mapped[int] = primary_key
    number: Mapped[str] = unique_index # e.g. "12004"

class TrainObservation(Base):
    """Snapshot provenance of a train."""
    snapshot_id: Mapped[int] = foreign_key(DatasetSnapshot.id)
    train_id: Mapped[int] = foreign_key(Train.id)
    name: Mapped[str] # e.g. "SHATABDI EXP"
    type: Mapped[str] # e.g. "Shatabdi"
    runs_on: Mapped[str] # e.g. "1111111" (Mon-Sun bitmap)

class TrainStopObservation(Base):
    """A specific stop on a train's route within a snapshot."""
    snapshot_id: Mapped[int] = foreign_key(DatasetSnapshot.id)
    train_id: Mapped[int] = foreign_key(Train.id)
    station_id: Mapped[int] = foreign_key(Station.id)
    stop_number: Mapped[int] # Ordered index of the stop
    arrival_time: Mapped[str | None] # "HH:MM"
    departure_time: Mapped[str | None]
    day_offset: Mapped[int] # 1 for day 1, 2 for next day, etc.
```
*Why this works:* It separates the immutable identity (`Train.number`) from the volatile, snapshot-dependent operational data (`TrainObservation` and `TrainStopObservation`), mirroring the proven v0.2 `Station` pattern.

## 12. Proposed Ingestion Architecture
1. **Source**: Download `trains.json` and `schedules.json` via exact GitHub commit hash.
2. **Parser**: Parse JSON, extracting train details and arrays of stops.
3. **Normalization**: Convert time strings to standard formats, normalize operating-day bitmaps.
4. **Validation**: Validate station codes against existing `Station` canonical identities.
5. **Canonical Entities**: UPSERT `Train` entities by train number.
6. **Snapshot Observations**: Bulk insert `TrainObservation` and `TrainStopObservation` tied to the new `DatasetSnapshot.id`.
7. **Idempotency**: If the pipeline fails, the snapshot is marked `FAILED` and `TrainObservation`s are rolled back atomically via standard SQLAlchemy session commits.

## 13. Data Validation Strategy
- Trains without a valid starting and ending stop are rejected.
- Stops referencing non-existent station codes are recorded in a `rejections.json` artifact (similar to v0.2).
- Malformed time strings (e.g., "25:99") trigger a rejection of the specific stop observation.

## 14. Snapshot/Provenance Strategy
- The timetable ingestion creates a NEW `DatasetSnapshot` referencing the Datameet `DataSource`. 
- Train search queries will explicitly filter by `TrainObservation.snapshot_id = active_snapshot_id`, ensuring no cross-contamination of historical or failed data.

## 15. Known Risks
- **Data Staleness**: The primary risk is that users expect live timetables, but v1.1 will supply 2016-era static data.
- **Complex Joins**: Station-to-station discovery queries (finding trains between A and B) require self-joins on `TrainStopObservation` checking that A's `stop_number` < B's `stop_number`. This could introduce performance bottlenecks requiring targeted indexing.

## 16. Explicit Exclusions
- **No live API integrations** (NTES, IRCTC).
- **No scraping**.
- **No fare/pricing ingestion** (highly volatile and unavailable in CC0 datasets).
- **No live delay tracking**.

## 17. Proposed v1.1 Implementation Scope
**In Scope:**
1. SQLAlchemy models and migrations for `Train`, `TrainObservation`, and `TrainStopObservation`.
2. Idempotent timetable ingestion pipeline pulling from Datameet GitHub via commit hash.
3. API endpoint for Train Search (`GET /api/v1/trains/{train_number}`).
4. API endpoint for Station-to-Station Discovery (`GET /api/v1/trains/between?source=X&destination=Y`).
5. Frontend UI updates to remove the 501 empty state and actually query the historical timetable foundation.

**Out of Scope:**
- Route visualization (Maps).
- Operating-day filtering in the UI (deferred to v1.2 to limit complexity).

## 18. Open Questions
- Should `arrival_time` and `departure_time` be stored as Postgres `TIME` types or plain `VARCHAR`? Using `VARCHAR` (e.g., "14:30") bypasses timezone and date arithmetic complexities during basic v1.1 search, but `TIME` allows for sorting. (Recommendation: `TIME` type is safer for later querying).
