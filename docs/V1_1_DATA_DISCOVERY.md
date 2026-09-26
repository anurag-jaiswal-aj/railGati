# RailGati v1.1 — Timetable Data Foundation Discovery

## 1. Executive Summary
This document investigates viable railway timetable data foundations for RailGati v1.1. The project operates under an absolute ₹0 budget and an anti-scraping mandate. The research concludes that no verified, current, live, and legally open (₹0) timetable API exists. 

To proceed architecturally, v1.1 will rely on a **Historical Timetable Discovery** scope. We evaluated `datameet/railways`, `data.gov.in`, and community repositories like `prasenjit-27/Indian-Railway-Data`. `datameet/railways` emerges as the only legally transparent, CC0, hash-reproducible baseline, though its freshness and data quality must be treated as severe historical limitations rather than current 2026 operational schedules.

## 2. Current v1.0 Data Situation
RailGati v1.0 implements a robust station discovery engine using the Datameet `stations.json` historical dataset via an idempotent, provenance-aware architecture (`Station`, `StationObservation`, `DatasetSnapshot`). Train search yields a `501 Not Implemented` fallback due to the lack of an ingested timetable.

## 3. Current vs. Historical Timetable Distinction
- **Current Timetable**: Represents a valid, live operating schedule (e.g., IRCTC, NTES). **No viable open/£0 source for this exists without prohibited scraping.**
- **Historical Timetable**: A static snapshot (e.g., circa 2015-2016). Useful for route discovery, architectural development, and historical analysis, but explicitly **not evidence of today's service**.
- **Decision**: v1.1 will implement **Historical Timetable Discovery**.

## 4. Candidate Source Evaluation

### Candidate A: Datameet Railways (GitHub)
- **Source name**: Datameet Railways (`trains.json`, `schedules.json`)
- **URL**: `https://github.com/datameet/railways`
- **License**: CC0 (Public Domain).
- **Data format**: GeoJSON (`trains.json`) and JSON array (`schedules.json`).
- **Data freshness**: Historical (circa 2016). Not a current timetable.
- **Data quality**: See Section 5.
- **Classification**: **Suitable for historical v1.1** (CC0 license is clear, data is reproducible via git hash).

### Candidate B: Open Government Data Platform (data.gov.in)
- **Source name**: Indian Railways Time Table
- **Publisher**: Ministry of Railways
- **License**: Government Open Data License (GODL)
- **Data freshness**: Historical (catalog contains fragmented CSVs mostly from 2015-2017).
- **Classification**: **Potential candidate requiring further verification**. The GODL license is viable, but the datasets are fragmented across years, making reproducible pipeline ingestion difficult compared to a single GitHub commit hash.

### Candidate C: prasenjit-27/Indian-Railway-Data (GitHub)
- **Source name**: Indian-Railway-Data
- **URL**: `https://github.com/prasenjit-27/Indian-Railway-Data`
- **License**: MIT
- **Data format**: Highly structured JSON (pre-joined route arrays).
- **Train/Station Count**: Claims 5,208+ trains and 8,990+ stations (identical to Datameet counts).
- **Provenance**: The repository does not explicitly attribute its original data source (e.g., NTES or Datameet).
- **Classification**: **Provenance unclear — not approved as a production source**. While technically convenient, using derivative datasets without clear origin attribution violates strict provenance requirements.

### Candidate D: Third-party Scrapers (e.g., railpull)
- **Classification**: **Requires prohibited scraping**. Violates project architecture.

## 5. Datameet Detailed Data Quality Verification
Direct inspection of Datameet `trains.json` and `schedules.json` yields:
- **Total Trains**: 5,208 (GeoJSON FeatureCollection).
- **Total Schedules (Stops)**: 417,080.
- **Train-number format**: String (e.g., `"12101"`).
- **Station-code format**: String (e.g., `"NDLS"`).
- **Arrival/Departure representation**: String (`"HH:MM:SS"`).
- **Missing Arrival values**: Yes (27,835 records have `"None"`, representing origin stations).
- **Missing Departure values**: Yes (27,827 records have `"None"`, representing destination stations).
- **Day representation**: Integer (`day` field, e.g., `1`, `2`).
- **Ordering**: Explicitly maintained via an auto-incrementing `id` field in the schedules array, allowing deterministic stop-sequence reconstruction.
- **Duplicate train numbers**: Exists. Return journeys or different routes sometimes reuse numbers or share IDs.
- **Limitations**: Missing coordinate data on some stations, ambiguity in operational running days encoded as boolean bitmasks, and outdated route topologies.

## 6. Train Identity Analysis
- **Finding**: Datameet `trains.json` contains duplicate `number` fields (e.g., return journeys or divergent historical routes using the same number).
- **Conclusion**: `Train.number` alone is **insufficient** as a globally unique canonical identifier.
- **Proposed Identity**: The canonical identity must be a composite of `number` and `source_station` (or a generated UUID) to differentiate direction pairs (e.g., `12101-LTT-HWH` vs `12102-HWH-LTT`).

## 7. Station Matching Analysis
The timetable (`schedules.json`) references stations via the `station_code` field (e.g., `LTT`).
- **Matching Policy**: Ingestion must enforce an **exact code match** against the canonical v0.2 `Station.code`.
- **Rejection Policy**: Any schedule record containing an unknown `station_code` will be gracefully rejected and logged to a provenance artifact. The pipeline must **never** silently create a new station from a fuzzy match or a timetable anomaly.

## 8. Proposed Domain Model
```python
class Train(Base):
    """Canonical train identity."""
    id: Mapped[int] = primary_key
    number: Mapped[str]
    source_code: Mapped[str] # Required for directional identity
    __table_args__ = (UniqueConstraint('number', 'source_code'),)

class TrainObservation(Base):
    """Snapshot provenance of a train."""
    snapshot_id: Mapped[int] = foreign_key(DatasetSnapshot.id)
    train_id: Mapped[int] = foreign_key(Train.id)
    name: Mapped[str]
    type: Mapped[str]

class TrainStopObservation(Base):
    """A specific stop on a train's route within a snapshot."""
    snapshot_id: Mapped[int] = foreign_key(DatasetSnapshot.id)
    train_id: Mapped[int] = foreign_key(Train.id)
    station_id: Mapped[int] = foreign_key(Station.id)
    stop_sequence: Mapped[int] # Derived from schedule 'id' sorting
    arrival_time: Mapped[str | None] # Native string to bypass timezone logic
    departure_time: Mapped[str | None]
    day_offset: Mapped[int]
```

## 9. Proposed Ingestion Architecture
1. Download `trains.json` and `schedules.json` via a fixed GitHub commit hash.
2. Filter/Join the JSON to build contiguous routes.
3. Validate `station_code` against canonical `Station` entities.
4. UPSERT `Train` canonical entities using `(number, source_code)`.
5. Bulk insert `TrainObservation` and `TrainStopObservation` bound to a new `DatasetSnapshot`.
6. Atomic failure rollback if dataset parsing faults.

## 10. v1.1 Scope
**v1.1 = Historical Timetable Discovery**

**In Scope:**
- Search train by number.
- View train route details (ordered stops, arrival/departure, day offset).
- Search trains between two stations.
- Dataset freshness indicator explicitly marking data as historical.

**Explicit Exclusions:**
- **No live data**: Live running status, delay prediction, cancellations.
- **No commercial data**: Current seat availability, fares.
- **No scraping**: Web scraping integration.

## 11. Risks and Unknowns
- **Risk**: Performance degradation on station-to-station searches involving 417,000+ stop observations.
- **Unknowns**: Exact handling of overnight timezone boundaries if a user searches for journeys strictly by absolute time instead of day-offsets.
