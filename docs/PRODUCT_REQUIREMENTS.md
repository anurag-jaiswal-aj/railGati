# Product Requirements

## Vision

RailGati is an Indian railway intelligence platform that empowers users to discover, plan, analyze, and understand the Indian railway network through data-driven intelligence.

## Long-Term Product Scope

- **Railway Discovery** — Search and explore stations, trains, and routes across the Indian railway network.
- **Journey Planning** — Find and compare journey options including direct trains, connections, and multi-leg routes.
- **Network Analysis** — Understand the railway network as a graph: connectivity, centrality, reachability.
- **Station Intelligence** — Detailed station profiles with metrics, connectivity scores, traffic patterns.
- **Reliability Analytics** — Historical on-time performance, delay trends, route reliability.
- **Delay Prediction** — ML-based prediction of train delays and connection risks.
- **AI-Assisted Exploration** — Natural language queries over railway data using local LLMs.

## v0.1 Scope

v0.1 establishes the **engineering foundation** only:

- Project structure (monorepo: backend, frontend, docs, docker)
- FastAPI backend with health endpoint
- Next.js frontend application shell
- PostgreSQL database connection foundation
- Configuration via environment variables
- Structured logging
- Code quality tooling (ruff, mypy, ESLint, TypeScript)
- Testing foundation (pytest)
- CI (GitHub Actions)
- Documentation skeleton

## Explicitly Out of Scope (v0.1)

The following are intentionally deferred to future versions:

- Railway station, train, and route data models
- External railway API integration (RailRadar or any other provider)
- Data ingestion pipeline
- Railway search functionality
- Map visualization
- Journey planning
- Analytics and dashboards
- User authentication and accounts
- Redis caching
- PostGIS spatial extensions
- ML/AI features
- Production deployment
