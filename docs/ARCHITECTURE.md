# Architecture

## Current Architecture (v0.1)

```
Browser
   │
   ▼
Next.js (frontend — port 3000)
   │
   ▼
FastAPI (backend — port 8000)
   │
   ▼
PostgreSQL (database — port 5432)
```

This is intentionally the simplest viable architecture for the engineering foundation.

### Frontend

- **Next.js** with App Router, TypeScript, and Tailwind CSS
- Serves the application shell
- Will call the FastAPI backend directly in future versions

### Backend

- **FastAPI** with Pydantic models and structured logging (structlog)
- Configuration via **Pydantic Settings** from environment variables
- Database connection via **SQLAlchemy** 2.x
- Database migrations via **Alembic** (configured, no domain tables yet)

### Database

- **PostgreSQL 16** running via Docker Compose
- No domain tables in v0.1 — only the connection infrastructure is established

## Intentionally Deferred

The following are excluded from v0.1 by design:

| Technology | Reason for Deferral |
|:-----------|:-------------------|
| **Redis** | No caching or rate-limiting requirement exists yet |
| **PostGIS** | No spatial queries exist yet |
| **Next.js BFF layer** | Adds unnecessary complexity before the API has domain endpoints |
| **External railway APIs** | Provider abstraction belongs to v0.2+ when data ingestion begins |
| **Microservices** | A modular monolith is the correct starting point |

These will be introduced when concrete requirements justify them.

## Principles

- **Modular monolith** — Single deployable backend with clear internal module boundaries.
- **Dependency inversion** — Domain logic does not depend on external providers or frameworks.
- **Provider abstraction** — External data sources will be accessed through replaceable adapter interfaces (future).
- **Configuration via environment** — All settings come from environment variables, never hard-coded.
