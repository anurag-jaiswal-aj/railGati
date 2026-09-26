# Data Sources

## Status Categories

- **VERIFIED** — Source has been located, license confirmed, data format understood, and ingested.
- **CANDIDATE** — Source appears promising but requires further evaluation.
- **REQUIRES VERIFICATION** — Data exists but legal usability is not yet confirmed.
- **REJECTED** — Source violates constraints (cost, license, scrape policy).

---

## VERIFIED

### datameet/railways (GitHub)

- **Publisher:** Datameet Community
- **URL:** https://github.com/datameet/railways
- **Format:** GeoJSON
- **Content:** Indian railway station names, codes, and coordinates
- **License:** CC0 (Creative Commons Zero) — free to use
- **Decision:** **USED** in v0.2 for the initial Station foundation.
- **Reason:** Explicitly licensed as CC0, provides natural identifiers (codes) and geospatial data.

---

## REQUIRES VERIFICATION

### data.gov.in Railway Datasets

- **Publisher:** Government of India
- **URL:** https://data.gov.in
- **License:** Open Government Data License (OGDL)
- **Decision:** **CANDIDATE** (Not used in v0.2).
- **Reason:** While legally usable (OGDL), a single comprehensive master list of all current station metadata (codes, coordinates) was not found in a unified dataset. Most datasets are granular statistical data rather than infrastructure masters.

---

## REJECTED

### Kaggle Indian Railways Datasets

- **URL:** https://www.kaggle.com/
- **License:** Varies
- **Decision:** **REJECTED**
- **Reason:** Risk of unverified scraped data. Licenses are often unclear or incorrectly attributed.

### National Train Enquiry System (NTES)

- **Publisher:** Indian Railways
- **Decision:** **REJECTED**
- **Reason:** Scraping is prohibited. No official public API available.

### RailRadar API

- **Publisher:** RailRadar
- **Decision:** **REJECTED** (for v0.2 data foundation)
- **Reason:** It is an API provider, not a raw open dataset. v0.2 focuses purely on the static data foundation.

---

## Principles

1. Only use data sources with clearly permissive licenses for production.
2. Do not silently treat community/Kaggle datasets as production-ready without license verification.
3. Do not scrape official government portals unless an explicit API is provided.
4. Track provenance for all ingested data.
