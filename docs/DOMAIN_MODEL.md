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
- **Purpose**: Represents the canonical identity of a railway station.
- **Fields**:
  - `id` (Primary Key, Surrogate Integer)
  - `code` (String, Unique, Index): The natural identifier of the station.
  - `created_at` (DateTime)
- **Relationships**: One-to-Many with `StationObservation`
- **Constraints**: 
  - `code` must be unique and not null.

### StationObservation
- **Purpose**: Represents a record of a station as it appeared in a specific dataset snapshot.
- **Fields**:
  - `snapshot_id` (Primary Key, Foreign Key -> `DatasetSnapshot.id`)
  - `station_id` (Primary Key, Foreign Key -> `Station.id`)
  - `name` (String)
  - `state` (String)
  - `zone` (String)
  - `latitude` (Float)
  - `longitude` (Float)
- **Relationships**: Many-to-One with `DatasetSnapshot`, Many-to-One with `Station`
