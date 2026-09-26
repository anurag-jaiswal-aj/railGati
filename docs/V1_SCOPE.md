# RailGati V1.0 Scope

## Overview
RailGati v1.0 establishes the first user-facing product capability: **Railway Station Discovery**.

## Supported Data
- **Station Search**: Discover stations by exact code, code prefix, exact name, or name substring.
- **Station Details**: View canonical station identity, geographic coordinates (when available), and detailed provenance (source dataset and snapshot).
- **Data Source**: Initial discovery relies on the open CC0 `Datameet` railway dataset ingested in v0.2. 

## Unsupported Data
- **Train Timetables & Discovery**: Train search (`from` -> `to`) is intentionally **unsupported** in v1.0. There are currently no integrated open, static, and £0-compliant railway timetable datasets that meet the project's strict budget constraints without resorting to scraping live IRCTC/NTES endpoints (which violates architectural guidelines). 
- As such, the API correctly returns a graceful `501 Not Implemented` empty state explaining this limitation when users attempt to search for trains.

## Active Snapshot Semantics
All user-facing data is explicitly scoped to the **latest `ACTIVE` dataset snapshot**.
- Search queries strictly filter by `snapshot_id = active_snapshot_id`.
- Failed snapshots or partial ingestions are entirely excluded from the API and cannot leak into the frontend.
- Station entities that exist canonically but do not appear in the active snapshot will not be returned, ensuring the UI reflects the explicit truth of the current active dataset.

## £0 Compliance
V1.0 remains strictly £0 compliant.
- No paid maps (using semantic UI elements instead).
- No paid LLMs or Search engines (Elasticsearch/Algolia are excluded).
- No paid APIs for trains.
