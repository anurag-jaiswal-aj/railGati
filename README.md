# RailGati

**Intelligent Railway Discovery, Planning & Analytics**

> **Current version: 0.1.0** — Engineering foundation.
> Railway search functionality is not yet available. See the [roadmap](#roadmap) below.

RailGati is an Indian railway intelligence platform that will cover railway discovery, journey planning, network analysis, station intelligence, reliability analytics, prediction, and AI-assisted railway exploration.

## ₹0 Budget Constraint

RailGati is developed with a **₹0 budget**. All technologies are free and open-source. No paid APIs, hosting, databases, or services are used. See [docs/ENGINEERING_GUIDELINES.md](docs/ENGINEERING_GUIDELINES.md) for details.

## Architecture (v0.1)

```
Browser → Next.js → FastAPI → PostgreSQL
```

This is intentionally simple. Redis, PostGIS, and external railway API integrations are deferred to future versions when concrete requirements justify them. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Local Setup

### Prerequisites

- Python 3.12+
- Node.js 22+
- pnpm
- uv
- Docker & Docker Compose (for PostgreSQL)

### 1. Clone & configure

```bash
git clone <repo-url> railGati
cd railGati
cp .env.example .env
```

### 2. Start PostgreSQL

```bash
docker compose -f docker/docker-compose.yml up -d
```

Verify it is healthy:

```bash
docker compose -f docker/docker-compose.yml ps
```

### 3. Backend

```bash
cd backend
uv sync --all-extras
uv run uvicorn railgati.main:app --reload
```

The API is available at [http://localhost:8000](http://localhost:8000).

- Health check: [http://localhost:8000/health](http://localhost:8000/health)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

The frontend is available at [http://localhost:3000](http://localhost:3000).

## Testing

### Backend

```bash
cd backend
uv run pytest tests/ -v          # tests
uv run ruff check src/ tests/    # lint
uv run ruff format --check src/ tests/  # format check
uv run mypy src/                 # type check
```

### Frontend

```bash
cd frontend
pnpm lint                        # eslint
pnpm build                       # type check + build
```

## CI

GitHub Actions runs on every push/PR to `main`:

- **Backend:** ruff lint, ruff format, mypy, pytest
- **Frontend:** eslint, TypeScript build

No external APIs, secrets, or paid services are required by CI.

## Current Limitations (v0.1)

- No railway search, station data, or train data
- No external API integrations
- No data ingestion pipeline
- No maps, analytics, or AI features
- No user authentication
- Frontend is an application shell only

These will be implemented in future versions.

## Roadmap

| Version | Scope |
|:--------|:------|
| **v0.1** | Engineering foundation (current) |
| **v0.2** | Data ingestion pipeline + railway domain models |
| **v1.0** | Station & train search |
| **v1.1** | Journey planning & comparison |
| **v1.2** | Destination discovery |
| **v1.3** | Station intelligence |
| **v2.0** | Railway network graph |
| **v2.1** | Historical analytics |
| **v2.2** | Reliability engine |
| **v2.3** | ML delay prediction |
| **v3.0** | Natural-language railway exploration |
| **v4.0** | Intelligent trip-planning agent |

## Documentation

See [docs/](docs/) for detailed documentation:

- [Product Requirements](docs/PRODUCT_REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Engineering Guidelines](docs/ENGINEERING_GUIDELINES.md)
- [Data Strategy](docs/DATA_STRATEGY.md)
- [Data Sources](docs/DATA_SOURCES.md)
- [Security](docs/SECURITY.md)
- [Testing Strategy](docs/TESTING_STRATEGY.md)

## License

TBD
