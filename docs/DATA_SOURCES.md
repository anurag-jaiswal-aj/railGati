# Data Sources

## Status Categories

- **Verified** — Source has been located, license confirmed, data format understood.
- **Candidate** — Source appears promising but requires further evaluation.
- **Requires License Verification** — Data exists but legal usability is not yet confirmed.

---

## Verified

### datameet/railways (GitHub)

- **URL:** https://github.com/datameet/railways
- **Format:** GeoJSON
- **Content:** Indian railway station names, codes, and coordinates
- **License:** CC0 (Creative Commons Zero) — free to use
- **Quality:** Community-maintained; widely referenced in open-source projects
- **Limitation:** May not include all stations; data freshness varies

---

## Candidates

### Kaggle Indian Railways Datasets

- **URL:** https://www.kaggle.com/ (search "Indian Railways")
- **Format:** CSV, JSON
- **Content:** Train schedules, routes, station lists
- **License:** Varies per dataset — must be checked individually
- **Quality:** Static snapshots; may not reflect current timetables
- **Risk:** Some datasets may be scraped without permission. Do not treat as production-usable without verifying the specific dataset license.

### RailRadar API

- **URL:** https://railradar.in
- **Type:** Third-party REST API
- **Free tier:** 1,000 requests/month (sandbox, no credit card required)
- **Capabilities:** Live train status, schedules, availability forecasts, station boards
- **Affiliation:** **Not** officially affiliated with Indian Railways or IRCTC
- **Risk:** Third-party service with no SLA. Free tier may change. Data accuracy unverified.

---

## Requires License Verification

### "Trains At A Glance" (Indian Railways)

- **Publisher:** Indian Railways (annual publication)
- **Content:** Comprehensive official train schedule
- **License:** Unknown — requires legal review before programmatic use
- **Notes:** Authoritative source, but unclear if data extraction is permitted

### National Train Enquiry System (NTES)

- **URL:** https://enquiry.indianrail.gov.in
- **Type:** Official Indian Railways web portal
- **API:** No official public API
- **License:** No programmatic access permitted
- **Risk:** **Do NOT scrape.** Use only if an official API becomes available.

### data.gov.in Railway Datasets

- **URL:** https://data.gov.in
- **License:** Open Government Data License (OGDL)
- **Content:** Some railway-related datasets, but no comprehensive timetable
- **Notes:** Worth monitoring for new dataset publications

---

## Principles

1. Only use data sources with clearly permissive licenses for production.
2. Do not silently treat community/Kaggle datasets as production-ready without license verification.
3. Do not scrape official government portals unless an explicit API is provided.
4. Track provenance for all ingested data.
