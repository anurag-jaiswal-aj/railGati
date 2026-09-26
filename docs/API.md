# RailGati API v1.0

## Base URL
`/api/v1`

## Endpoints

### 1. Station Search
**GET** `/stations/search`

Search for railway stations by code or name using the current active dataset snapshot.

**Parameters:**
- `q` (string, required): Search query (case-insensitive, 1-50 chars).
- `page` (integer, optional): Pagination page number (default 1).
- `size` (integer, optional): Number of results per page (max 100, default 20).

**Response (200 OK):**
```json
{
  "items": [
    {
      "code": "NDLS",
      "name": "New Delhi",
      "state": "Delhi",
      "zone": "NR",
      "latitude": 28.642,
      "longitude": 77.22
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20
}
```

### 2. Station Detail
**GET** `/stations/{station_code}`

Get detailed canonical information and provenance for a specific station.

**Parameters:**
- `station_code` (string, path): Canonical station code (e.g. `NDLS`).

**Response (200 OK):**
```json
{
  "code": "NDLS",
  "name": "New Delhi",
  "state": "Delhi",
  "zone": "NR",
  "latitude": 28.642,
  "longitude": 77.22,
  "id": 1,
  "provenance": {
    "snapshot_id": 3,
    "source_name": "Datameet Railways",
    "retrieved_at": "2026-09-25T18:00:00Z"
  }
}
```

**Response (404 Not Found):**
Station does not exist or is not present in the active snapshot.

### 3. Train Discovery
**GET** `/trains/between`

Discover trains between two stations.

**Parameters:**
- `source` (string, required): Departure station code.
- `destination` (string, required): Arrival station code.

**Response (501 Not Implemented):**
Currently returns a graceful empty state due to missing £0-compliant timetable data.
```json
{
  "message": "Train timetable and discovery data is currently unavailable...",
  "available": false
}
```
