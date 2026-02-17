# Titanbay Private Markets API

> RESTful API for managing private-market funds, investors, and their investment commitments.

## Architecture

```text
app/
├── main.py                 # FastAPI app, lifespan, middleware
├── middleware.py            # Request-ID + timing middleware
├── seed.py                 # Sample data seeder (idempotent)
├── core/
│   ├── cache.py            # In-memory TTL cache with FIFO eviction
│   ├── config.py           # Pydantic-settings (env → typed config)
│   ├── exceptions.py       # Domain exceptions + global handlers
│   ├── logging.py          # JSON structured logging + rotation
│   └── resilience.py       # Circuit breaker + retry with backoff
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
| Language | Python 3.14 |
| Framework | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.0 (async) + SQLModel |
| Database | PostgreSQL 15+ |
| Validation | Pydantic v2 |
| Container | Docker (multi-stage build) |

## Documentation

| Document | Description |
| -------- | ----------- |
| [API Reference](docs/API_REFERENCE.md) | Every endpoint, request/response schema, status code, and business rule |
| [API Examples](docs/API_EXAMPLES.md) | Sample curl requests & responses for all 8 endpoints |
| [Edge Cases](docs/EDGE_CASES.md) | Comprehensive edge-case test scenarios (28+ cases) |
| [Design Decisions](docs/DESIGN_DECISIONS.md) | Architecture, resilience, caching, logging, and infrastructure choices |
| [Database Design](docs/DATABASE_DESIGN.md) | Schema design, index strategy, query analysis, scaling playbook |
| [Docker Setup](docs/SETUP_DOCKER.md) | Full Docker walkthrough (steps 1-6, teardown, one-command test) |
| [Local Setup](docs/SETUP_LOCAL.md) | Local dev prerequisites, venv, DB creation, one-command test |
| [No-DB Setup](docs/SETUP_NO_DB.md) | Zero-dependency testing with in-memory SQLite (no Docker, no PostgreSQL) |
| [Testing Guide](docs/TESTING.md) | Unit test suite: 154 pytest tests, ~90% coverage, test architecture |
| [Code Quality](docs/CODE_QUALITY.md) | black, isort, flake8 setup: formatting, import sorting, linting |

## Quick Start

### Option A: Docker (Recommended)

Full step-by-step instructions: **[docs/SETUP_DOCKER.md](docs/SETUP_DOCKER.md)**

```bash
docker network create titanbay-net

docker run -d --name titanbay-db --network titanbay-net \
  -e POSTGRES_USER=titanbay_user -e POSTGRES_PASSWORD=titanbay_password \
  -e POSTGRES_DB=titanbay_db -p 5432:5432 postgres:15-alpine

cd titanbay-service
docker build -t titanbay-service .

docker run -d --name titanbay-app --network titanbay-net -p 8000:8000 \
  -e POSTGRES_USER=titanbay_user -e POSTGRES_PASSWORD=titanbay_password \
  -e POSTGRES_SERVER=titanbay-db -e POSTGRES_DB=titanbay_db -e POSTGRES_PORT=5432 \
  titanbay-service

curl http://localhost:8000/health
```

Or run all 51 tests in one command:

```bash
bash scripts/test_docker.sh
```

### Option B: Local Development

Full step-by-step instructions: **[docs/SETUP_LOCAL.md](docs/SETUP_LOCAL.md)**

```bash
psql -U postgres -h 127.0.0.1 -c "CREATE USER titanbay_user WITH PASSWORD 'titanbay_password';"
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE titanbay_db OWNER titanbay_user;"

cd titanbay-service
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Or run all 51 tests in one command:

```bash
bash scripts/test_local.sh -p <your_postgres_password>
```

### Option C: No Database (Easiest)

Full step-by-step instructions: **[docs/SETUP_NO_DB.md](docs/SETUP_NO_DB.md)**

No Docker. No PostgreSQL. Just Python and curl.
Uses an **in-memory SQLite** database.

```bash
cd titanbay-service
bash scripts/test_no_db.sh
```

This single command creates a venv, installs deps, starts the server with SQLite, runs all 51 tests, and cleans up.

### Open the docs

| URL | Description |
| --- | ----------- |
| <http://localhost:8000/docs> | **Swagger UI** — interactive explorer, lets you try endpoints from the browser |
| <http://localhost:8000/redoc> | **ReDoc** — polished read-only reference (three-panel layout) |
| <http://localhost:8000/health> | Liveness / readiness probe with DB connectivity, circuit breaker state, and cache stats |

> Both `/docs` and `/redoc` are auto-generated by FastAPI from the OpenAPI schema — they stay in sync with the code at zero maintenance cost. Swagger UI is for developers testing endpoints; ReDoc is for stakeholders who want a clean reference view.

## API Endpoints

All endpoints are prefixed with `/api/v1`.
For detailed schemas, status codes, and business rules, see **[API Reference](docs/API_REFERENCE.md)**.
For curl examples, see **[API Examples](docs/API_EXAMPLES.md)**.

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

All errors follow a consistent JSON envelope. See **[API Reference → Common Response Envelopes](docs/API_REFERENCE.md#common-response-envelopes)** for the full specification and **[API Reference → Global Error Handling](docs/API_REFERENCE.md#global-error-handling)** for a complete status-code matrix.

## Environment Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `USE_SQLITE` | `false` | Use in-memory SQLite instead of PostgreSQL (for testing) |
| `POSTGRES_USER` | — | Database user (**required** unless `USE_SQLITE=true`) |
| `POSTGRES_PASSWORD` | — | Database password (**required** unless `USE_SQLITE=true`) |
| `POSTGRES_SERVER` | — | Database host (**required** unless `USE_SQLITE=true`) |
| `POSTGRES_DB` | — | Database name (**required** unless `USE_SQLITE=true`) |
| `POSTGRES_PORT` | `5432` | Database port |
| `DB_POOL_SIZE` | `10` | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | `20` | Extra connections above pool size |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `LOG_FILE_MAX_BYTES` | `10485760` | Max size per log file before rotation (10 MB) |
| `LOG_FILE_BACKUP_COUNT` | `5` | Number of rotated log files to keep |
| `CB_FAILURE_THRESHOLD` | `5` | Consecutive DB failures before circuit opens |
| `CB_RECOVERY_TIMEOUT` | `30.0` | Seconds before circuit breaker probes recovery |
| `CACHE_ENABLED` | `true` | Enable/disable in-memory TTL cache |
| `CACHE_TTL` | `30.0` | Cache entry time-to-live in seconds |
| `CACHE_MAX_SIZE` | `1000` | Maximum number of cached entries |
| `DEBUG` | `false` | Enable debug logging + SQL echo |
