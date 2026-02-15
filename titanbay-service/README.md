# Titanbay Private Markets API

> RESTful API for managing private-market funds, investors, and their investment commitments.

## Architecture

```bash
app/
├── main.py                 # FastAPI app, lifespan, middleware
├── seed.py                 # Sample data seeder (idempotent)
├── core/
│   ├── config.py           # Pydantic-settings (env → typed config)
│   └── exceptions.py       # Domain exceptions + global handlers
├── db/
│   ├── base.py             # Model registry for metadata
│   └── session.py          # Async engine + session factory
├── models/                 # SQLModel table definitions
│   ├── fund.py
│   ├── investor.py
│   └── investment.py
├── schemas/                # Pydantic request / response DTOs
│   ├── fund.py
│   ├── investor.py
│   └── investment.py
├── repositories/           # Data access layer (generic + concrete)
│   ├── base.py
│   ├── fund_repo.py
│   ├── investor_repo.py
│   └── investment_repo.py
├── services/               # Business logic layer
│   ├── fund_service.py
│   ├── investor_service.py
│   └── investment_service.py
└── api/v1/
    ├── api.py              # Router aggregation
    └── endpoints/
        ├── funds.py
        ├── investors.py
        └── investments.py
```

**Design Principles:**

- **Clean Architecture** — Endpoints → Services → Repositories → DB.  Each layer depends only on the one below.
- **SOLID** — Single-responsibility services, base repository generic, dependency injection via FastAPI `Depends()`.
- **Domain Exceptions** — Services raise `NotFoundException`, `ConflictException`, `BusinessRuleViolation` instead of framework HTTP exceptions, keeping business logic framework-agnostic.

## Tech Stack

| Component | Choice |
| --------- | ------ |
| Language | Python 3.11 |
| Framework | FastAPI 0.115 |
| ORM | SQLAlchemy 2.0 (async) + SQLModel |
| Database | PostgreSQL 15 |
| Validation | Pydantic v2 |
| Container | Docker + Docker Compose |

## Quick Start

### Prerequisites

- Docker & Docker Compose

### 1. Start the services

```bash
docker-compose up --build
```

### 2. Seed sample data (optional)

```bash
docker-compose exec web python -m app.seed
```

### 3. Open the docs

| URL | Description |
| --- | ----------- |
| <http://localhost:8000/docs> | Swagger UI (interactive) |
| <http://localhost:8000/redoc> | ReDoc (read-only) |
| <http://localhost:8000/health> | Liveness probe |

## API Endpoints

All endpoints are prefixed with `/api/v1`.

### Funds

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/funds` | List all funds |
| POST | `/funds` | Create a new fund |
| PUT | `/funds` | Update an existing fund (id in body) |
| GET | `/funds/{id}` | Get a specific fund |

### Investors

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/investors` | List all investors |
| POST | `/investors` | Create a new investor |

### Investments

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/funds/{fund_id}/investments` | List investments for a fund |
| POST | `/funds/{fund_id}/investments` | Create a new investment |

## Key Design Decisions

1. **PUT /funds with id in body** — The API spec shows `PUT /funds` with the `id` included in the JSON body rather than the URL path.  We follow the spec exactly.

2. **Closed-fund invariant** — Investments into funds with `status: Closed` are rejected with a 422 (Business Rule Violation), not a generic 400.

3. **Investor existence check on investment creation** — Before persisting an investment, we verify both the fund *and* the investor exist to avoid opaque FK-violation errors.

4. **Duplicate email detection** — Creating an investor with an email that already exists returns a 409 Conflict with a clear message, rather than a raw DB constraint error.

5. **Timezone-aware timestamps** — All `created_at` fields use `datetime.now(timezone.utc)` instead of the deprecated `datetime.utcnow()`.

6. **Connection pooling** — The async engine is configured with explicit `pool_size`, `max_overflow`, `pool_recycle`, and `pool_pre_ping` for production reliability.

7. **Multi-stage Docker build** — The Dockerfile uses a builder stage to install dependencies, then copies only the virtual environment into a slim runtime image.  The app runs as a non-root user.

## Error Response Format

All errors follow a consistent JSON structure:

```json
{
  "error": true,
  "message": "Human-readable description"
}
```

Validation errors (422) include additional detail:

```json
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> vintage_year", "message": "..." }
  ]
}
```

## Environment Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `POSTGRES_USER` | — | Database user |
| `POSTGRES_PASSWORD` | — | Database password |
| `POSTGRES_SERVER` | — | Database host |
| `POSTGRES_DB` | — | Database name |
| `POSTGRES_PORT` | `5432` | Database port |
| `DB_POOL_SIZE` | `10` | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | `20` | Extra connections above pool size |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `DEBUG` | `false` | Enable debug logging + SQL echo |
