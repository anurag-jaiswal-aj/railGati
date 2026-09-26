# RailGati Domain Model

This document outlines the domain entities explicitly modeled in the database for RailGati.

## Provenance Entities

### DataSource
- **Purpose**: Tracks the origin and metadata of datasets ingested into RailGati.
- **Fields**:
  - `id` (Primary Key, Integer)
  - `name` (String, Unique)
  - `publisher` (String)
  - `url` (String)
  - `license` (String)
  - `description` (Text)
  - `active` (Boolean)
- **Relationships**: One-to-Many with `DatasetSnapshot`

### DatasetSnapshot
- **Purpose**: Represents a point-in-time snapshot of data from a specific DataSource.
- **Fields**:
  - `id` (Primary Key, Integer)
  - `source_id` (Foreign Key -> `DataSource.id`)
  - `retrieved_at` (DateTime)
  - `record_count` (Integer)
  - `status` (String: PENDING, ACTIVE, FAILED, SUPERSEDED)
  - `error_message` (Text)
  - `checksum` (String)
- **Relationships**: Many-to-One with `DataSource`, One-to-Many with `Station`

## Railway Entities

### Station
- **Purpose**: Represents a railway station.
- **Fields**:
  - `id` (Primary Key, Surrogate Integer)
  - `code` (String, Unique, Index): The natural identifier of the station.
  - `name` (String)
  - `state` (String)
  - `zone` (String)
  - `latitude` (Float)
  - `longitude` (Float)
  - `snapshot_id` (Foreign Key -> `DatasetSnapshot.id`)
  - `created_at` (DateTime)
  - `updated_at` (DateTime)
- **Relationships**: Many-to-One with `DatasetSnapshot` (Provenance)
- **Constraints**: 
  - `code` must be unique.
  - `name` and `code` must not be null.
