# RailGati v1.1 — Timetable Data Foundation Discovery

## 1. Executive Summary
This document investigates viable railway timetable data foundations for RailGati v1.1. The project operates under an absolute ₹0 budget and an anti-scraping mandate. The research concludes that no verified, current, live, and legally open (₹0) timetable API exists. 

To proceed architecturally, v1.1 will rely on a **Historical Timetable Discovery** scope. We evaluated `datameet/railways`, `data.gov.in`, and community repositories like `prasenjit-27/Indian-Railway-Data`. `datameet/railways` emerges as the only legally transparent, CC0, hash-reproducible baseline. Its freshness and data quality must be treated as severe historical limitations rather than current operational schedules.

## 2. Current v1.0 Data Situation
RailGati v1.0 implements a robust station discovery engine using the Datameet `stations.json` historical dataset via an idempotent, provenance-aware architecture (`Station`, `StationObservation`, `DatasetSnapshot`). Train search yields a `501 Not Implemented` fallback due to the lack of an ingested timetable.

## 3. Current vs. Historical Timetable Distinction
- **Current Timetable**: Represents a valid, live operating schedule. **No viable open/£0 source for this exists without prohibited scraping.**
- **Historical Timetable**: A static snapshot. Useful for route discovery, architectural development, and historical analysis, but explicitly **not evidence of today's service**.
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
- **Classification**: **Potential candidate requiring further verification**. The Government Open Data License (GODL) is viable, but the datasets are heavily fragmented across years (2015-2017) and mirrored haphazardly, complicating reproducible pipeline ingestion compared to a single GitHub repository.

### Candidate C: prasenjit-27/Indian-Railway-Data (GitHub)
- **Classification**: **Provenance unclear — not approved as a production source**. While technically convenient (pre-joined JSON containing 5,208 trains and 8,990+ stations), the repository does not explicitly attribute its original data source (e.g., NTES or Datameet), violating strict provenance requirements.

### Candidate D: Third-party Scrapers (e.g., railpull)
- **Classification**: **Requires prohibited scraping**. Violates project architecture.

## 5. Datameet Detailed Data Quality Verification
Direct inspection of Datameet `trains.json` and `schedules.json` yields:
- **Total Trains**: 5,208 records.
- **Total Unique Train Numbers**: 5,208.
- **Duplicate Train Numbers**: 0. The dataset guarantees strict uniqueness on the `train_number` field.
- **Total Schedules (Stops)**: 417,080 records.
- **Missing Arrival values**: Yes (27,835 records have `"None"`, typically representing origin stations).
- **Missing Departure values**: Yes (27,827 records have `"None"`, typically representing destination stations).
- **Missing/Pass-through Stops**: Some schedule records have `day: null` and arrival/departure `"None"`, acting as geographic waypoints without time constraints.
- **return_train Semantics**: The `return_train` field unequivocally represents the opposite-direction service paired train number (e.g., `04601` explicitly maps to return train `04602`, and vice-versa). 

## 6. Train Identity Analysis
- **Finding**: Datameet `trains.json` guarantees 100% uniqueness on the `number` field within this specific historical snapshot.
- **Conclusion**: `Train.number` alone is completely sufficient as the global canonical identifier. No composite key is required.

## 7. Schedule Ordering & Day Semantics
- **Ordering**: Stop sequences can be definitively reconstructed by sorting the auto-incrementing global `id` field in `schedules.json`. Inspecting records proves that `id` sequencing directly aligns with sequential station progressions and increasing `day` values.
- **Day Field Semantics**: The `day` field acts strictly as a relative integer "journey day offset" starting at `1`. As trains cross midnight boundaries (e.g., `23:59:00` -> `00:05:00`), the `day` field increments reliably (e.g., `1` -> `2`).
- **Cross-Midnight Limitation**: Because there are no absolute dates (only relative day offsets and string times), time queries spanning midnight will be inherently limited. RailGati must preserve these as relative offsets rather than inventing arbitrary calendar-date anchoring.

## 8. Station Matching Analysis
The timetable (`schedules.json`) references stations via the `station_code` field (e.g., `LTT`).
- **Matching Policy**: Ingestion must enforce an **exact code match** against the canonical v0.2 `Station.code`.
- **Rejection Policy**: Any schedule record containing an unknown `station_code` will be gracefully rejected and logged to a provenance artifact.

## 9. Proposed Domain Model
```python
class Train(Base):
    """Canonical train identity."""
    id: Mapped[int] = primary_key
    number: Mapped[str] = unique_index # 100% unique in dataset

class TrainObservation(Base):
    """Snapshot provenance of a train."""
    snapshot_id: Mapped[int] = foreign_key(DatasetSnapshot.id)
    train_id: Mapped[int] = foreign_key(Train.id)
    name: Mapped[str]
    type: Mapped[str]
    return_train_number: Mapped[str | None] # Opposite-direction service pair

class TrainStopObservation(Base):
    """A specific stop on a train's route within a snapshot."""
    snapshot_id: Mapped[int] = foreign_key(DatasetSnapshot.id)
    train_id: Mapped[int] = foreign_key(Train.id)
    station_id: Mapped[int] = foreign_key(Station.id)
    stop_sequence: Mapped[int] # Derived sequentially from sorting source 'id'
    arrival_time: Mapped[str | None] # Native string "HH:MM:SS" or null
    departure_time: Mapped[str | None]
    source_day: Mapped[int | None] # Native relative offset (1-indexed) or null
```

## 10. Proposed Ingestion Architecture
1. Download `trains.json` and `schedules.json` via a fixed GitHub commit hash.
2. Filter/Join the JSON, sorting `schedules.json` strictly by `id` to determine `stop_sequence`.
3. Validate `station_code` against canonical `Station` entities.
4. UPSERT `Train` canonical entities using `number`.
5. Bulk insert `TrainObservation` and `TrainStopObservation` bound to a new `DatasetSnapshot`.
6. Atomic failure rollback if dataset parsing faults.

## 11. v1.1 Scope
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
- **No calendar anchoring**: Timetables will be rendered relative to Day 1, avoiding cross-midnight timezone conversions into absolute dates.
