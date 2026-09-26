# Security

## Secrets Management

### Rules

1. **Never commit secrets** to version control.
2. All secrets go in `.env` files, which are listed in `.gitignore`.
3. Use `.env.example` to document required environment variables with placeholder values.
4. API keys, database passwords, and tokens are loaded via Pydantic Settings from environment variables.

### Environment Variables

| Variable | Purpose | Secret? |
|:---------|:--------|:--------|
| `RAILGATI_DATABASE_URL` | PostgreSQL connection string | Yes — contains password |
| `RAILGATI_FRONTEND_ORIGIN` | CORS allowed origin | No |
| `RAILGATI_ENV` | Application environment | No |
| `RAILGATI_LOG_LEVEL` | Logging verbosity | No |

Future variables (e.g., API keys for external providers) must follow the same `RAILGATI_` prefix pattern.

## CORS

- Only the configured frontend origin is allowed (`RAILGATI_FRONTEND_ORIGIN`).
- Credentials are not sent cross-origin.
- Only necessary HTTP methods are permitted (GET-only in v0.1).

## Input Validation

- All API inputs are validated by Pydantic models via FastAPI's built-in validation.
- No raw SQL — SQLAlchemy parameterized queries prevent SQL injection.
- User-provided strings should be sanitized before storage.

## Dependency Security

- Use lockfiles (`uv.lock`, `pnpm-lock.yaml`) for reproducible, auditable dependencies.
- Periodically run `uv pip audit` (or equivalent) and `pnpm audit` to check for known vulnerabilities.
- Review dependency changelogs before major version upgrades.

## Logging

- **Never log secrets**, API keys, passwords, or tokens.
- Use structured logging (structlog) with consistent field names.
- Log levels: DEBUG for development details, INFO for operational events, WARNING/ERROR for problems.
- Sensitive request fields (if any in future) must be redacted before logging.

## Future Considerations

When external API integrations are added:

- API keys must be stored in `.env`, never in source code.
- External API responses should be validated before processing (defense against malformed data).
- Circuit breaker / retry patterns should handle API failures gracefully.
- Rate limiting should be implemented to prevent API abuse.

When user accounts are added (if ever):

- Full data privacy review required.
- Minimize PII collection.
- Consider Indian IT Act data protection provisions.
