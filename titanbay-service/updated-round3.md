# Production Infrastructure — Logging, Resilience, and Caching

## Changes Made

### 1. Production Logging Framework (`app/core/logging.py`)

**What:** Added a complete logging framework with rotating file handlers, JSON structured output, and debug toggle.

**Why:** Industry-standard production services require machine-parsable log files for aggregation platforms (ELK, Datadog, Splunk). Rotating files prevent disk exhaustion. Separate error logs enable targeted alerting.

**Details:**

- `RotatingFileHandler` with configurable max size (10 MB) and backup count (5)
- `JSONFormatter` for machine-parsable log lines (timestamp, level, logger, message, module, function, line, request_id)
- `ConsoleFormatter` with ANSI colours for local development
- Separate `titanbay-error.log` for ERROR+ only
- `DEBUG=true` toggles all loggers to DEBUG level including SQL echo

### 2. Circuit Breaker Pattern (`app/core/resilience.py`)

**What:** Implemented the circuit breaker pattern for database operations with three states: CLOSED, OPEN, HALF_OPEN.

**Why:** When the database is down, continuing to send requests causes connection timeouts that exhaust threads and connections, creating cascading failures across the entire service. The circuit breaker fast-fails after a threshold, giving the database time to recover.

**Details:**

- `CircuitBreaker` class with configurable failure threshold (5) and recovery timeout (30s)
- Global `db_circuit_breaker` instance wraps all `BaseRepository` methods
- `CircuitBreakerError` → 503 Service Unavailable + `Retry-After` header
- `retry_with_backoff` decorator with exponential backoff + jitter

### 3. In-Memory TTL Cache (`app/core/cache.py`)

**What:** Added an in-memory cache with TTL expiration and write-through invalidation for read-heavy endpoints.

**Why:** Read endpoints (GET /funds, GET /investors, GET /investments) far outnumber writes. Caching reduces database round-trips and response latency. Write-through invalidation ensures data consistency.

**Details:**

- `TTLCache` with configurable TTL (30s), max size (1000), enable toggle
- Cache keys use entity prefix (`funds:`, `investors:`, `investments:`)
- Write operations invalidate all matching cache entries by prefix
- FIFO eviction at max size (Python dict insertion order)
- Zero external dependencies (swappable to Redis via same interface)
- Cache stats exposed via `/health` endpoint

### 4. Configuration Updates (`app/core/config.py`)

**Added settings:**

- `LOG_LEVEL`, `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT`
- `CB_FAILURE_THRESHOLD`, `CB_RECOVERY_TIMEOUT`
- `CACHE_ENABLED`, `CACHE_TTL`, `CACHE_MAX_SIZE`

### 5. Wiring & Integration

- `BaseRepository` — All DB operations routed through `db_circuit_breaker.call()`
- `FundService` — Cache on `get_all_funds`, `get_fund`; invalidation on `create_fund`, `update_fund`
- `InvestorService` — Cache on `get_all_investors`; invalidation on `create_investor`
- `InvestmentService` — Cache on `get_investments_by_fund`; invalidation on `create_investment`
- `exceptions.py` — Added `CircuitBreakerError` → 503 handler with `Retry-After`
- `main.py` — Health endpoint now reports circuit breaker state + cache stats
- `test_no_db.sh` — Added 9 infrastructure tests (circuit breaker, cache, logging, headers)

### 6. Documentation Updates

- `README.md` — Architecture tree, env vars table, design decision highlights
- `DESIGN_DECISIONS.md` — 7 new decisions added across 3 new categories (Resilience, Caching, updated Observability)
- `SETUP_NO_DB.md` — Updated health check response example

## Files Changed

| File | Action |
| ------ | -------- |
| `app/core/logging.py` | **Created** |
| `app/core/resilience.py` | **Created** |
| `app/core/cache.py` | **Created** |
| `app/core/config.py` | Modified (8 new settings) |
| `app/core/exceptions.py` | Modified (CircuitBreakerError handler) |
| `app/main.py` | Modified (logging init, health endpoint) |
| `app/repositories/base.py` | Modified (circuit breaker wrapping) |
| `app/services/fund_service.py` | Modified (cache integration) |
| `app/services/investor_service.py` | Modified (cache integration) |
| `app/services/investment_service.py` | Modified (cache integration) |
| `scripts/test_no_db.sh` | Modified (9 new infrastructure tests) |
| `README.md` | Modified (architecture, env vars, design decisions) |
| `docs/DESIGN_DECISIONS.md` | Modified (7 new decisions) |
| `docs/SETUP_NO_DB.md` | Modified (health response example) |
