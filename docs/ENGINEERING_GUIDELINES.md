# Engineering Guidelines

## ₹0 Budget Constraint

This is a hard architectural constraint. Every technology choice must be free and open-source, or have a genuinely free tier that does not require a credit card or risk silent charges.

Before adding any dependency or service, verify:

- Is it free/open-source?
- Does it require a credit card or account that could generate charges?
- Could it silently become paid?

If there is any cost risk, document it explicitly before introducing it.

## Code Quality

### Python (Backend)

- **Type annotations** on all function signatures and return types
- **Ruff** for linting and formatting (replaces flake8, black, isort)
- **mypy** in strict mode for static type checking
- **pytest** for testing
- No `# type: ignore` without a comment explaining why

### TypeScript (Frontend)

- **Strict mode** enabled in `tsconfig.json`
- **ESLint** with Next.js recommended rules
- Explicit types — avoid `any`

## Naming Conventions

### Python

- `snake_case` for functions, variables, modules
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Descriptive names over abbreviations

### TypeScript

- `camelCase` for functions and variables
- `PascalCase` for components, types, and interfaces
- Files named to match their default export

## Dependency Discipline

- Add dependencies only when they solve a real, current problem
- Do not add speculative dependencies for future features
- Pin dependency version ranges in `pyproject.toml` and `package.json`
- Use lockfiles (`uv.lock`, `pnpm-lock.yaml`) for reproducibility

## Testing

- Write tests for business logic and API endpoints
- Tests must be deterministic — no external API calls, no network dependencies
- Use fixtures and factories for test data
- See [TESTING_STRATEGY.md](TESTING_STRATEGY.md) for the full strategy

## Git Conventions

- Branch from `main`
- Use clear, conventional commit messages:
  - `feat:` — new feature
  - `fix:` — bug fix
  - `docs:` — documentation
  - `chore:` — maintenance, tooling
  - `test:` — test additions/changes
  - `refactor:` — code restructuring without behavior change
- Keep commits focused — one logical change per commit
- Do not commit secrets, `.env` files, or generated artifacts

## Avoiding Unnecessary Complexity

- Start simple. Add complexity only when a concrete problem demands it.
- A modular monolith before microservices.
- Direct function calls before message queues.
- PostgreSQL before adding Redis, PostGIS, or other extensions.
- Local development before cloud deployment.

## Data Ingestion Rules

- **Deterministic processing**: The same raw dataset must always produce the exact same database state.
- **Idempotency**: Running ingestion twice must safely no-op the second time without duplicating data.
- **Validate before activation**: Validate all coordinates, codes, and strings. Report errors explicitly.
- **No silent data loss**: Keep track of every parsed row, accepted row, and rejected row in a clear report.
- **Provenance required**: Every domain row must link to a `DatasetSnapshot` showing exactly when and where it came from.
- **Reproducibility**: Keep manifests and ingestion CLI tools checked in to Git. Large raw files stay out of Git.
- **Explicit licensing**: Never ingest data whose license does not explicitly allow it. No scraping official portals.
