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
| Language | Python 3.14+ |
| Framework | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.0 (async) + SQLModel |
| Database | PostgreSQL 15+ |
| Validation | Pydantic v2 |
| Container | Docker (multi-stage build) |

> **Database Design & Scalability:** For a deep-dive into schema design decisions,
> index strategy, query analysis, and a scaling playbook from 10K to 1B+ records,
> see [DATABASE_DESIGN.md](DATABASE_DESIGN.md).

## Quick Start

### Option A: Docker (Recommended)

> **No local PostgreSQL required.** Both the app and the database run as Docker containers
> on a shared network. This is also easily portable to Kubernetes for testing.

#### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS) or Docker Engine (Linux)

#### 1. Create a Docker network

A user-defined bridge network lets the two containers resolve each other by name:

```bash
docker network create titanbay-net
```

#### 2. Start PostgreSQL

```bash
docker run -d \
  --name titanbay-db \
  --network titanbay-net \
  -e POSTGRES_USER=titanbay_user \
  -e POSTGRES_PASSWORD=titanbay_password \
  -e POSTGRES_DB=titanbay_db \
  -p 5432:5432 \
  postgres:15-alpine
```

> `-p 5432:5432` is optional — it exposes Postgres to the host for debugging with tools like `psql` or pgAdmin. The app container connects via the Docker network, not the host port.

#### 3. Build the app image

```bash
cd titanbay-service
docker build -t titanbay-service .
```

#### 4. Run the app

```bash
docker run -d \
  --name titanbay-app \
  --network titanbay-net \
  -p 8000:8000 \
  -e POSTGRES_USER=titanbay_user \
  -e POSTGRES_PASSWORD=titanbay_password \
  -e POSTGRES_SERVER=titanbay-db \
  -e POSTGRES_DB=titanbay_db \
  -e POSTGRES_PORT=5432 \
  titanbay-service
```

> `POSTGRES_SERVER=titanbay-db` uses the container name — Docker DNS resolves it within the `titanbay-net` network.

The app will auto-create all database tables on first startup. Verify with:

```bash
docker logs titanbay-app
# Expected: "Database tables ready" followed by "Uvicorn running on http://0.0.0.0:8000"
```

#### 5. Seed sample data (optional)

```bash
docker exec titanbay-app python -m app.seed
```

#### 6. Verify

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"1.0.0","database":true}
```

#### Teardown

```bash
docker rm -f titanbay-app titanbay-db   # stop & remove containers
docker network rm titanbay-net          # remove the network
```

To also remove the built image:

```bash
docker rmi titanbay-service
```

#### One-Command Test (Docker)

Instead of running steps 1-6 manually, you can use the automated test script.
It starts PostgreSQL + the app in Docker, runs **41 curl tests** (happy-path + edge-cases)
against all 8 endpoints, captures output to `logs/docker_test.log`, and tears everything down:

```bash
bash scripts/test_docker.sh
```

> **Windows (Git Bash):** `"C:\Program Files\Git\bin\bash.exe" scripts/test_docker.sh`

**No manual prompts — fully automatic.** All database credentials are passed via
Docker environment variables (`-e`). The script never calls `psql` or asks for any
passwords. It creates the containers, waits for them to be healthy, runs every test,
prints a pass/fail summary, and tears down. Zero interaction required.

### Option B: Local Development (without Docker)

#### Local Setup Prerequisites

- **Python 3.14+** installed
- **PostgreSQL 15+** installed and **running** locally. The application **will not start** without a reachable PostgreSQL instance — it connects to the database during startup to create tables.
  - **Windows:** Install from <https://www.postgresql.org/download/windows/> or via `winget install PostgreSQL.PostgreSQL`. After installation, ensure the PostgreSQL service is running (check *Services* or run `pg_isready`).
  - **macOS:** `brew install postgresql@16 && brew services start postgresql@16`
  - **Linux:** `sudo apt install postgresql` (or equivalent for your distro) and `sudo systemctl start postgresql`
- **PostgreSQL superuser credentials** — You need to know the password for the `postgres` superuser (set during installation) to create the application database and user in the next step.

#### 1. Create the database and user

Connect to PostgreSQL using the `postgres` superuser and create the application database:

```bash
psql -U postgres -h 127.0.0.1 -c "CREATE USER titanbay_user WITH PASSWORD 'titanbay_password';"
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE titanbay_db OWNER titanbay_user;"
```

> **Note:** You will be prompted for the `postgres` superuser password. If you haven't set one, refer to your OS-specific PostgreSQL installation docs to configure it.

#### 2. Set up virtual environment and install dependencies

```bash
cd titanbay-service
python -m venv venv
source venv/bin/activate        # Linux/macOS
# or: source venv/Scripts/activate  # Git Bash on Windows

pip install -r requirements.txt
```

#### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — set POSTGRES_SERVER=127.0.0.1 for local development
```

#### 4. Start the application

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

> **What happens on startup:** The application automatically creates all required database tables (`funds`, `investors`, `investments`) if they don't already exist. This is handled by the `lifespan` function in `app/main.py`, which calls `SQLModel.metadata.create_all` against the configured database. You do **not** need to run any migrations or SQL scripts manually — just ensure the database and user from step 1 exist. If the database is unreachable at startup, the application will fail with a connection error.

#### 5. Seed sample data — local (optional)

```bash
python -m app.seed
```

> **What the seed does:** The seed script inserts sample funds, investors, and investments into the database for development and demo purposes. It is **completely optional** — the application works fine without it. If you skip seeding, API endpoints like `GET /funds` will return empty arrays (`[]`) until you create data via the `POST` endpoints. The seed is idempotent: running it multiple times will not create duplicate records.

#### One-Command Test (Local)

Instead of running steps 1-5 manually, you can use the automated test script.
It checks PostgreSQL connectivity, sets up the venv, starts uvicorn, runs **41 curl tests**
(happy-path + edge-cases) against all 8 endpoints, captures output to `logs/local_test.log`,
and stops the server on exit:

```bash
bash scripts/test_local.sh
```

> **Windows (Git Bash):** `"C:\Program Files\Git\bin\bash.exe" scripts/test_local.sh`

**Will it prompt for a password?** No — the script **never** opens an interactive prompt.
Here is how it works depending on your database state:

| Scenario | What happens | Action needed |
| -------- | ------------ | ------------- |
| DB + user already exist (typical after first setup) | Script connects as `titanbay_user`, skips admin setup entirely. **Fully automatic.** | None |
| DB/user don't exist, `postgres` superuser has **trust** auth (common on macOS Homebrew) | Script auto-creates the user and database via `psql --no-password`. **Fully automatic.** | None |
| DB/user don't exist, `postgres` superuser **requires a password** | Script cannot authenticate as the superuser. It **fails immediately** (does not hang) with a clear error message. | Either set `PGPASSWORD_ADMIN` (see below) or run the two SQL commands from Step 1 once manually. |

To supply the postgres superuser password without any prompt:

```bash
# Linux / macOS
PGPASSWORD_ADMIN=your_postgres_password bash scripts/test_local.sh

# Windows (Git Bash)
PGPASSWORD_ADMIN=your_postgres_password "C:\Program Files\Git\bin\bash.exe" scripts/test_local.sh
```

Once the database and user exist (after the first successful run or manual Step 1),
`PGPASSWORD_ADMIN` is never needed again — the script detects the existing setup and
skips all superuser operations. Every subsequent run is fully automatic with zero
interaction.

### 3. Open the docs

| URL | Description |
| --- | ----------- |
| <http://localhost:8000/docs> | Swagger UI (interactive) |
| <http://localhost:8000/redoc> | ReDoc (read-only reference docs) |
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

## Sample Requests & Responses

> All examples use `curl`. Replace `localhost:8000` with your host if different.
> UUIDs in responses will differ — the ones below are illustrative.

---

### POST /api/v1/funds — Create a fund

**Happy path (201 Created):**

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Titanbay Growth Fund II",
    "vintage_year": 2025,
    "target_size_usd": 500000000.00,
    "status": "Fundraising"
  }'
```

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Titanbay Growth Fund II",
  "vintage_year": 2025,
  "target_size_usd": 500000000.0,
  "status": "Fundraising",
  "created_at": "2025-02-16T12:00:00Z"
}
```

**Error path (422 Validation Error) — missing required field:**

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bad Fund",
    "vintage_year": 2025
  }'
```

```json
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> target_size_usd", "message": "Field required" }
  ]
}
```

---

### GET /api/v1/funds — List all funds

**Happy path (200 OK):**

```bash
curl -s http://localhost:8000/api/v1/funds
```

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Titanbay Growth Fund I",
    "vintage_year": 2024,
    "target_size_usd": 250000000.0,
    "status": "Fundraising",
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

> Returns `[]` if no funds exist yet.

**Error path (422 Validation Error) — invalid query parameter:**

```bash
curl -s "http://localhost:8000/api/v1/funds?limit=-1"
```

```json
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "query -> limit", "message": "Input should be greater than or equal to 1" }
  ]
}
```

---

### GET /api/v1/funds/{id} — Get a specific fund

**Happy path (200 OK):**

```bash
curl -s http://localhost:8000/api/v1/funds/550e8400-e29b-41d4-a716-446655440000
```

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Titanbay Growth Fund I",
  "vintage_year": 2024,
  "target_size_usd": 250000000.0,
  "status": "Fundraising",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Error path (404 Not Found) — fund does not exist:**

```bash
curl -s http://localhost:8000/api/v1/funds/00000000-0000-0000-0000-000000000000
```

```json
{
  "error": true,
  "message": "Fund with id '00000000-0000-0000-0000-000000000000' not found"
}
```

---

### PUT /api/v1/funds — Update a fund

**Happy path (200 OK):**

```bash
curl -s -X PUT http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Titanbay Growth Fund I",
    "vintage_year": 2024,
    "target_size_usd": 300000000.00,
    "status": "Investing"
  }'
```

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Titanbay Growth Fund I",
  "vintage_year": 2024,
  "target_size_usd": 300000000.0,
  "status": "Investing",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Error path (404 Not Found) — fund id does not exist:**

```bash
curl -s -X PUT http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "id": "00000000-0000-0000-0000-000000000000",
    "name": "Ghost Fund",
    "vintage_year": 2024,
    "target_size_usd": 100000000.00,
    "status": "Fundraising"
  }'
```

```json
{
  "error": true,
  "message": "Fund with id '00000000-0000-0000-0000-000000000000' not found"
}
```

---

### POST /api/v1/investors — Create an investor

**Happy path (201 Created):**

```bash
curl -s -X POST http://localhost:8000/api/v1/investors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CalPERS",
    "investor_type": "Institution",
    "email": "privateequity@calpers.ca.gov"
  }'
```

```json
{
  "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "name": "CalPERS",
  "investor_type": "Institution",
  "email": "privateequity@calpers.ca.gov",
  "created_at": "2025-02-16T12:05:00Z"
}
```

**Error path (409 Conflict) — duplicate email:**

```bash
curl -s -X POST http://localhost:8000/api/v1/investors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CalPERS Duplicate",
    "investor_type": "Institution",
    "email": "privateequity@calpers.ca.gov"
  }'
```

```json
{
  "error": true,
  "message": "An investor with email 'privateequity@calpers.ca.gov' already exists"
}
```

---

### GET /api/v1/investors — List all investors

**Happy path (200 OK):**

```bash
curl -s http://localhost:8000/api/v1/investors
```

```json
[
  {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "name": "Goldman Sachs Asset Management",
    "investor_type": "Institution",
    "email": "investments@gsam.com",
    "created_at": "2024-02-10T09:15:00Z"
  }
]
```

> Returns `[]` if no investors exist yet.

**Error path (422 Validation Error) — invalid query parameter:**

```bash
curl -s "http://localhost:8000/api/v1/investors?skip=-5"
```

```json
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "query -> skip", "message": "Input should be greater than or equal to 0" }
  ]
}
```

---

### POST /api/v1/funds/{fund_id}/investments — Create an investment

**Happy path (201 Created):**

```bash
curl -s -X POST http://localhost:8000/api/v1/funds/550e8400-e29b-41d4-a716-446655440000/investments \
  -H "Content-Type: application/json" \
  -d '{
    "investor_id": "770e8400-e29b-41d4-a716-446655440002",
    "amount_usd": 75000000.00,
    "investment_date": "2024-09-22"
  }'
```

```json
{
  "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "fund_id": "550e8400-e29b-41d4-a716-446655440000",
  "investor_id": "770e8400-e29b-41d4-a716-446655440002",
  "amount_usd": 75000000.0,
  "investment_date": "2024-09-22"
}
```

**Error path (422 Business Rule Violation) — fund is closed:**

```bash
curl -s -X POST http://localhost:8000/api/v1/funds/220e8400-e29b-41d4-a716-446655440020/investments \
  -H "Content-Type: application/json" \
  -d '{
    "investor_id": "770e8400-e29b-41d4-a716-446655440002",
    "amount_usd": 10000000.00,
    "investment_date": "2024-09-22"
  }'
```

```json
{
  "error": true,
  "message": "Cannot invest in fund 'Titanbay Venture Fund I' — status is Closed"
}
```

---

### GET /api/v1/funds/{fund_id}/investments — List investments for a fund

**Happy path (200 OK):**

```bash
curl -s http://localhost:8000/api/v1/funds/550e8400-e29b-41d4-a716-446655440000/investments
```

```json
[
  {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "fund_id": "550e8400-e29b-41d4-a716-446655440000",
    "investor_id": "770e8400-e29b-41d4-a716-446655440002",
    "amount_usd": 50000000.0,
    "investment_date": "2024-03-15"
  }
]
```

> Returns `[]` if the fund has no investments.

**Error path (404 Not Found) — fund does not exist:**

```bash
curl -s http://localhost:8000/api/v1/funds/00000000-0000-0000-0000-000000000000/investments
```

```json
{
  "error": true,
  "message": "Fund with id '00000000-0000-0000-0000-000000000000' not found"
}
```

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
