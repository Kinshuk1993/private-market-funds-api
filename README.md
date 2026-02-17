# Titanbay Private Markets API

> RESTful API for managing private-market funds, investors, and their investment commitments.

## Structure

```text
titanbay-service/
├── .dockerignore            # Files excluded from Docker build context
├── .env.example             # Template for environment variables
├── .gitignore               # Git ignore rules
├── Dockerfile               # Multi-stage production build (builder → slim runtime)
├── README.md                # Service-level README (setup & usage)
├── requirements.txt         # Pinned Python dependencies
├── docs/
│   ├── API_EXAMPLES.md      # Sample curl requests & responses for all 8 endpoints
│   ├── API_REFERENCE.md     # Full endpoint specs, schemas, status codes, business rules
│   ├── DATABASE_DESIGN.md   # Schema design, index strategy, query analysis, scaling playbook
│   ├── EDGE_CASES.md        # 28+ edge-case test scenarios
│   ├── SETUP_DOCKER.md      # Docker walkthrough (steps 1-6, teardown)
│   ├── SETUP_LOCAL.md       # Local dev prerequisites, venv, DB creation
│   └── SETUP_NO_DB.md       # Zero-dependency testing with in-memory SQLite
├── scripts/
│   ├── test_docker.sh       # One-command Docker test suite (42 tests)
│   ├── test_local.sh        # One-command local PostgreSQL test suite (42 tests)
│   └── test_no_db.sh        # One-command SQLite in-memory test suite (42 tests)
└── app/
    ├── __init__.py
    ├── main.py              # FastAPI app factory, lifespan events, middleware registration
    ├── middleware.py         # Request-ID injection + request-timing logging
    ├── seed.py              # Idempotent sample data seeder (runs on startup)
    ├── core/
    │   ├── __init__.py
    │   ├── config.py        # Pydantic-settings: env → typed config, SQLite/PG switching
    │   └── exceptions.py    # Domain exceptions (NotFoundException, ConflictException, etc.)
    ├── db/
    │   ├── __init__.py
    │   ├── base.py          # Model registry — imports all models for metadata.create_all()
    │   └── session.py       # Async engine + session factory (PG pool / SQLite StaticPool)
    ├── models/              # SQLModel table definitions (DB schema)
    │   ├── __init__.py
    │   ├── fund.py          # Fund table — name, vintage_year, target_size, status enum
    │   ├── investor.py      # Investor table — name, type enum, unique email constraint
    │   └── investment.py    # Investment table — FK to fund & investor, amount, date
    ├── schemas/             # Pydantic request / response DTOs
    │   ├── __init__.py
    │   ├── common.py        # Shared error-response models for OpenAPI docs
    │   ├── fund.py          # FundCreate, FundUpdate, FundResponse
    │   ├── investor.py      # InvestorCreate, InvestorResponse
    │   └── investment.py    # InvestmentCreate, InvestmentResponse
    ├── repositories/        # Data-access layer (Repository pattern)
    │   ├── __init__.py
    │   ├── base.py          # Generic async CRUD repository (BaseRepository[T])
    │   ├── fund_repo.py     # Fund-specific queries
    │   ├── investor_repo.py # Investor-specific queries (e.g. find-by-email)
    │   └── investment_repo.py # Investment-specific queries (e.g. filter-by-fund)
    ├── services/            # Business logic layer
    │   ├── __init__.py
    │   ├── fund_service.py          # Fund CRUD + validation rules
    │   ├── investor_service.py      # Investor CRUD + duplicate-email check
    │   └── investment_service.py    # Investment creation + closed-fund guard
    └── api/v1/
        ├── __init__.py
        ├── api.py           # Router aggregation — mounts all endpoint routers
        └── endpoints/
            ├── __init__.py
            ├── funds.py     # GET/POST/PUT /funds, GET /funds/{id}
            ├── investors.py # GET/POST /investors
            └── investments.py # GET/POST /funds/{fund_id}/investments
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
| [API Reference](titanbay-service/docs/API_REFERENCE.md) | Every endpoint, request/response schema, status code, and business rule |
| [API Examples](titanbay-service/docs/API_EXAMPLES.md) | Sample curl requests & responses for all 8 endpoints |
| [Edge Cases](titanbay-service/docs/EDGE_CASES.md) | Comprehensive edge-case test scenarios (28+ cases) |
| [Database Design](titanbay-service/docs/DATABASE_DESIGN.md) | Schema design, index strategy, query analysis, scaling playbook |
| [Docker Setup](titanbay-service/docs/SETUP_DOCKER.md) | Full Docker walkthrough (steps 1-6, teardown, one-command test) |
| [Local Setup](titanbay-service/docs/SETUP_LOCAL.md) | Local dev prerequisites, venv, DB creation, one-command test) |
| [No-DB Setup](titanbay-service/docs/SETUP_NO_DB.md) | Zero-dependency testing with in-memory SQLite (no Docker, no PostgreSQL) |
| [Design Decisions](titanbay-service/docs/DESIGN_DECISIONS.md) | 28 architectural & engineering decisions across 6 categories |

## Quick Start

### Option A: Docker (Recommended)

Full step-by-step instructions: **[docs/SETUP_DOCKER.md](titanbay-service/docs/SETUP_DOCKER.md)**

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

Or run all 42 tests in one command:

```bash
cd titanbay-service
bash scripts/test_docker.sh
```

### Option B: Local Development

Full step-by-step instructions: **[docs/SETUP_LOCAL.md](titanbay-service/docs/SETUP_LOCAL.md)**

```bash
psql -U postgres -h 127.0.0.1 -c "CREATE USER titanbay_user WITH PASSWORD 'titanbay_password';"
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE titanbay_db OWNER titanbay_user;"

cd titanbay-service
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Or run all 42 tests in one command:

```bash
cd titanbay-service
bash scripts/test_local.sh -p <your_postgres_password>
```

### Option C: No Database (Easiest — recommended for reviewers)

Full step-by-step instructions: **[docs/SETUP_NO_DB.md](titanbay-service/docs/SETUP_NO_DB.md)**

No Docker. No PostgreSQL. Just **Python 3.14** and **curl**.
Uses an **in-memory SQLite** database — all 8 endpoints, all validation, all business rules work identically to PostgreSQL.

**Start the server interactively** (explore via Swagger UI at <http://localhost:8000/docs>):

```bash
cd titanbay-service
python -m venv venv && source venv/bin/activate   # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
USE_SQLITE=true uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Or **run all 42 tests in one command** (no manual setup needed):

```bash
cd titanbay-service
bash scripts/test_no_db.sh
```

The script creates a venv, installs deps, starts the server with SQLite, runs all 42 tests, and cleans up.

### Open the docs

| URL | Description |
| --- | ----------- |
| <http://localhost:8000/docs> | **Swagger UI** — interactive explorer, lets you try endpoints from the browser |
| <http://localhost:8000/redoc> | **ReDoc** — polished read-only reference (three-panel layout) |
| <http://localhost:8000/health> | Liveness / readiness probe with DB connectivity check |

> Both `/docs` and `/redoc` are auto-generated by FastAPI from the OpenAPI schema — they stay in sync with the code at zero maintenance cost. Swagger UI is for developers testing endpoints; ReDoc is for stakeholders who want a clean reference view.

## API Endpoints

All endpoints are prefixed with `/api/v1`.
For detailed schemas, status codes, and business rules, see **[API Reference](titanbay-service/docs/API_REFERENCE.md)**.
For curl examples, see **[API Examples](titanbay-service/docs/API_EXAMPLES.md)**.

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

> Full details: **[Design Decisions](titanbay-service/docs/DESIGN_DECISIONS.md)** (28 decisions across 6 categories).

Highlights:

- **Clean layered architecture** — `Router → Service → Repository → DB`, each layer depends only on the one below.
- **Domain exceptions** — Services raise `NotFoundException`, `ConflictException`, `BusinessRuleViolation` (framework-agnostic); global handlers map them to JSON.
- **Defence-in-depth** — Pydantic validation + DB-level CHECK constraints + native PostgreSQL ENUMs + FK `RESTRICT`.
- **TOCTOU-safe duplicate detection** — Optimistic pre-check + DB `UNIQUE` constraint catch for concurrent race conditions.
- **One-way fund lifecycle** — `Fundraising → Investing → Closed`; backwards transitions rejected.
- **Observability** — `X-Request-ID` tracing, `X-Process-Time` header, structured logging, health probe with DB check.
- **Production-grade infra** — Connection pooling with `pool_pre_ping`, GZip compression, multi-stage Docker build (non-root), exponential back-off on startup.
- **Dual-database support** — `USE_SQLITE=true` swaps to in-memory SQLite for zero-dependency testing; `model_validator` enforces PG credentials in production.

## Error Response Format

All errors follow a consistent JSON envelope. See **[API Reference → Common Response Envelopes](titanbay-service/docs/API_REFERENCE.md#common-response-envelopes)** for the full specification and **[API Reference → Global Error Handling](titanbay-service/docs/API_REFERENCE.md#global-error-handling)** for a complete status-code matrix.

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
| `DEBUG` | `false` | Enable debug logging + SQL echo |
