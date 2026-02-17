# Key Design Decisions

A comprehensive catalogue of the architectural and engineering decisions behind the Titanbay Private Markets API, organized by concern.

---

## API & Spec Compliance

1. **PUT /funds with id in body** — The API spec shows `PUT /funds` with the `id` included in the JSON body rather than the URL path.  We follow the spec exactly.

2. **Decimal serialized as JSON number** — The spec shows `target_size_usd: 250000000.00` as a number. Pydantic v2 defaults to string serialization for `Decimal`, so we add a `field_serializer` to emit `float` in the response while keeping `Decimal` everywhere internally (never `float` for currency arithmetic).

3. **Separate schemas from table models** — Request/response DTOs (`schemas/`) are distinct from SQLModel table definitions (`models/`). This is the Interface Segregation Principle: the API contract can evolve independently of the persistence layer.

---

## Business Rules

1. **Closed-fund invariant** — Investments into funds with `status: Closed` are rejected with a 422 (Business Rule Violation), not a generic 400.

2. **One-way fund lifecycle** — Status transitions are enforced via an explicit allow-list: `Fundraising → Investing → Closed`. Backwards transitions (e.g. `Closed → Fundraising`) are rejected with a 422, preventing accidental fund re-opening.

3. **Investor existence check on investment creation** — Before persisting an investment, we verify both the fund *and* the investor exist to avoid opaque FK-violation errors from PostgreSQL.

4. **Duplicate email detection with TOCTOU handling** — An optimistic pre-check (`get_by_email`) catches 99.9% of duplicates with a clean 409 Conflict. The DB `UNIQUE` constraint is the true safety net for the race condition where two concurrent requests slip past the pre-check; the resulting `IntegrityError` is caught and translated to the same 409 response.

---

## Data Integrity & Defence-in-Depth

1. **DB-level CHECK constraints** — `target_size_usd > 0`, `amount_usd > 0`, `vintage_year >= 1900`, and `length(name) > 0` are enforced at the database level in addition to Pydantic validation. This protects against data corruption from direct SQL, admin scripts, or seed data that bypasses the API.

2. **Native PostgreSQL ENUMs** — `FundStatus` and `InvestorType` use SQLAlchemy's `Enum` type, which creates a native PostgreSQL ENUM (`fundstatus`, `investortype`) that rejects invalid values at the DB level — no CHECK constraint needed.

3. **FK `ondelete=RESTRICT`** — Investments reference funds and investors with `RESTRICT` foreign keys, preventing deletion of an entity that has dependent investments.

4. **`Decimal(20,2)` for currency** — All monetary values use `DECIMAL(20,2)` — never `float` — for cent-precise arithmetic that avoids floating-point rounding errors.

5. **Timezone-aware timestamps** — All `created_at` fields use `datetime.now(timezone.utc)` instead of the deprecated `datetime.utcnow()`, ensuring unambiguous UTC storage.

---

## Architecture & Patterns

1. **Clean layered architecture** — `Router → Service → Repository → DB`. Routers contain zero business logic; services never import FastAPI; repositories never import domain exceptions. Each layer depends only on the one below.

2. **Domain exceptions (framework-agnostic services)** — Services raise `NotFoundException`, `ConflictException`, `BusinessRuleViolation` instead of FastAPI's `HTTPException`. Global exception handlers map these to JSON responses, keeping the service layer portable and testable without a running HTTP server.

3. **Generic repository pattern** — `BaseRepository[T]` implements typed CRUD operations once. Concrete repos (fund, investor, investment) inherit and add only entity-specific queries. Zero duplicated data-access code.

4. **Dependency injection via `Depends()`** — Services are constructed per-request with their repositories injected, making every layer independently unit-testable with mock dependencies.

5. **Deterministic pagination** — `get_all()` orders by primary key. Without explicit ordering, PostgreSQL returns rows in heap-insertion order which can shift between queries, causing clients to see duplicate or missing records when paginating.

---

## Observability & Production Readiness

1. **Request ID tracing** — Every request carries an `X-Request-ID` header (honoured from upstream gateway or generated as UUID4). Propagated through logs and echoed in the response for distributed tracing.

2. **Request timing** — `X-Process-Time` header on every response. Requests exceeding 500ms are logged at `WARNING` level for latency monitoring without an external APM agent.

3. **Health check with DB + circuit breaker + cache stats** — `GET /health` executes `SELECT 1` against the database and reports circuit breaker state (`closed`/`open`/`half_open`) and cache statistics (`hits`, `misses`, `hit_rate`, `size`). Kubernetes readiness probes can route traffic away from unhealthy pods.

4. **Graceful degraded mode** — If the database is unreachable on startup, the app starts anyway (with logged warnings) instead of crash-looping. This lets liveness probes pass while readiness probes report degraded status.

5. **Exponential back-off on startup** — DB connection retries use exponential back-off (5 attempts, 2s → 4s → 8s → 16s) to handle slow container orchestration without hammering the database.

6. **JSON structured logging with rotation** — Log files use `RotatingFileHandler` with configurable max size (10 MB default) and backup count (5 files). Log entries are JSON-structured (`JSONFormatter`) for machine parsing by ELK/Datadog/Splunk.  A separate `titanbay-error.log` captures only ERROR+ for alerting pipelines.  Console output uses ANSI-coloured human-readable format for local dev.  `DEBUG=true` toggles all loggers to DEBUG level including SQL echo.

---

## Resilience & Fault Tolerance

1. **Circuit breaker on all database operations** — Every repository method is routed through a global `CircuitBreaker` instance.  After 5 consecutive connection failures (configurable via `CB_FAILURE_THRESHOLD`), the circuit opens and all subsequent calls fast-fail with `CircuitBreakerError` (→ 503 + `Retry-After` header) instead of timing out.  After `CB_RECOVERY_TIMEOUT` (30s default), a single probe is allowed through.  This prevents thread/connection exhaustion during a database outage and gives the DB time to recover.

2. **Exponential backoff with jitter** — The `retry_with_backoff` decorator implements retry logic with: configurable max retries, base delay that doubles each attempt, cap on maximum delay, and random jitter (0–50% of delay) to prevent thundering-herd effects when multiple replicas retry simultaneously.

3. **503 Service Unavailable + Retry-After header** — When the circuit breaker rejects a request, the API returns HTTP 503 with a `Retry-After` header containing the seconds until the circuit attempts recovery.  Well-behaved HTTP clients and load balancers honour this header, preventing retry storms.

---

## Caching

1. **In-memory TTL cache (zero external dependencies)** — Read-heavy endpoints (`GET /funds`, `GET /investors`, `GET /funds/{id}/investments`) are cached in-memory with configurable TTL (30s default) and max size (1000 entries).  No Redis dependency — the same interface can be swapped to Redis/Memcached in a distributed deployment.

2. **Write-through invalidation** — Every mutation (POST/PUT) invalidates all cache entries matching the entity's prefix (`funds:`, `investors:`, `investments:`), ensuring subsequent reads fetch fresh data from the database.  This bounds the staleness window to zero after any write.

3. **FIFO eviction at max size** — When the cache reaches `CACHE_MAX_SIZE`, the oldest entry is evicted (FIFO via Python dict insertion order). This prevents unbounded memory growth without the complexity of LRU.

4. **Configurable toggle** — `CACHE_ENABLED=false` disables caching entirely for load tests, debugging stale data, or environments where consistency is more critical than latency.

---

## Infrastructure

1. **Connection pooling** — The async engine is configured with explicit `pool_size`, `max_overflow`, `pool_recycle`, and `pool_pre_ping` for production reliability. `pool_pre_ping` detects stale connections before they cause request failures.

2. **GZip compression** — Responses over 500 bytes are compressed via `GZipMiddleware`, reducing bandwidth on list endpoints returning large JSON arrays.

3. **Multi-stage Docker build** — Builder stage installs dependencies into a venv; runtime stage copies only the venv + app code into a slim image. The app runs as a non-root user (`appuser`) for container security.

4. **Dual-database support** — Setting `USE_SQLITE=true` swaps PostgreSQL for an in-memory SQLite database with `StaticPool` (single shared connection), enabling the full test suite to run with zero external dependencies. A `model_validator` enforces that PostgreSQL credentials are present when SQLite mode is off — fail-fast over silent misconfiguration.

5. **Idempotent seed data** — The seed script checks for existing records before inserting, so it can run repeatedly (on every container restart) without creating duplicates.
