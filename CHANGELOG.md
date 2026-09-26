# Changelog

All notable changes to RailGati are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/).

## 0.1.0

### Added

- Project monorepo structure (backend, frontend, docs, docker)
- FastAPI backend with health endpoint (`GET /health`)
- Pydantic Settings configuration via environment variables
- Structured logging with structlog
- SQLAlchemy database connection foundation (no domain tables)
- Docker Compose with PostgreSQL 16 for local development
- Next.js frontend application shell with TypeScript and Tailwind CSS
- Backend code quality: ruff (lint/format), mypy (type check), pytest (tests)
- Frontend code quality: ESLint, TypeScript strict mode
- GitHub Actions CI for both backend and frontend
- Documentation foundation (architecture, engineering guidelines, data strategy, security, testing)
- `.env.example` with safe development defaults
