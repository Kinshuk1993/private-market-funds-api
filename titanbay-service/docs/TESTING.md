# Testing Guide

Comprehensive unit and integration test suite for the Titanbay Private Markets API.

---

## Overview

| Metric | Value |
| ------- | ------- |
| **Framework** | pytest 8+ with pytest-asyncio |
| **Total tests** | 154 |
| **Coverage** | ~90% (services: 100%, schemas: 100%, cache: 100%) |
| **Execution time** | < 1 second |
| **Database required** | No — all tests use mocked repositories |

## Test Architecture

```text
tests/
├── conftest.py                  # Shared fixtures, factories, global cache reset
├── test_schemas.py              # Pydantic schema validation (32 tests)
├── test_cache.py                # In-memory TTL cache (22 tests)
├── test_resilience.py           # Circuit breaker & retry decorator (20 tests)
├── test_exceptions.py           # Domain exceptions (12 tests)
├── test_fund_service.py         # FundService business logic (23 tests)
├── test_investor_service.py     # InvestorService business logic (7 tests)
├── test_investment_service.py   # InvestmentService business logic (11 tests)
├── test_middleware.py           # Request ID & timing middleware (4 tests)
├── test_config.py               # Settings / configuration (6 tests)
└── test_api.py                  # API endpoint integration tests (18 tests)
```

### Test Layers

| Layer | What's tested | Mocking strategy |
| ------- | --------------- | ------------------ |
| **Schemas** | Pydantic validators, serializers, edge cases | None — pure unit tests |
| **Services** | Business logic, cache behaviour, error handling | Repository → `AsyncMock` |
| **Core** | Cache, circuit breaker, retry, exceptions, config | Standalone — no dependencies |
| **Middleware** | Request ID injection, timing headers | Lightweight FastAPI test app |
| **API endpoints** | Full HTTP request → response cycle, status codes | Service → `AsyncMock` via DI |

---

## Quick Start

### Prerequisites

```bash
# From the titanbay-service directory
pip install -r requirements.txt
```

### Run All Tests

```bash
# Basic run (verbose output, short tracebacks)
pytest

# With coverage report
pytest --cov=app --cov-report=term-missing

# Generate HTML coverage report
pytest --cov=app --cov-report=html
# Open htmlcov/index.html in your browser
```

### Run Specific Test Files

```bash
# Only service tests
pytest tests/test_fund_service.py tests/test_investor_service.py tests/test_investment_service.py

# Only schema validation tests
pytest tests/test_schemas.py

# Only API integration tests
pytest tests/test_api.py

# Only infrastructure tests (cache, resilience, middleware)
pytest tests/test_cache.py tests/test_resilience.py tests/test_middleware.py
```

### Run by Keyword

```bash
# All tests related to "create"
pytest -k "create"

# All tests related to cache
pytest -k "cache"

# All circuit breaker tests
pytest -k "circuit"
```

---

## Test Coverage

### Coverage Configuration

Coverage is configured in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["app"]
omit = [
    "app/__pycache__/*",
    "app/seed.py",
    "app/main.py",          # Lifespan requires real DB connection
    "app/core/logging.py",  # File/console handlers — side-effect heavy
    "app/db/session.py",    # Engine creation — requires DB drivers
    "app/db/base.py",       # Import-only module
]

[tool.coverage.report]
show_missing = true
fail_under = 85
```

### Coverage Summary by Module

| Module | Coverage | Notes |
| -------- | ---------- | ------- |
| `services/` | **100%** | All business logic fully covered |
| `schemas/` | **100%** | All validators & serializers covered |
| `core/cache.py` | **100%** | Full TTL, eviction, invalidation |
| `core/resilience.py` | **99%** | All CB states + retry decorator |
| `core/exceptions.py` | **89%** | All exceptions + handler registration |
| `api/endpoints/` | **95%** | All routes, DI functions line-only miss |
| `middleware.py` | **96%** | Full dispatch cycle covered |
| `repositories/` | **27-100%** | Base repo has low coverage (mocked in service tests) |

### Omitted from Coverage

These modules are excluded because they require real infrastructure (database connections, file system) and are covered by the shell-based integration test scripts (`scripts/test_local.sh`, `scripts/test_docker.sh`):

- `app/main.py` — Application lifespan with DB retry logic
- `app/core/logging.py` — File handlers, console formatters
- `app/db/session.py` — SQLAlchemy engine creation
- `app/db/base.py` — Model import barrel

---

## What's Tested

### Schema Validation (32 tests)

- **FundCreate**: Valid input, name stripping, blank/empty name rejection, vintage year boundaries (1900, current+5), target_size_usd > 0, all fund statuses, default status
- **FundUpdate**: Includes UUID `id` field, missing `id` rejected
- **FundResponse**: Decimal → float serialization, `from_attributes` mode
- **InvestorCreate**: Valid input, blank name, name stripping, invalid email, all investor types
- **InvestorResponse**: Includes id and created_at
- **InvestmentCreate**: Valid input, zero/negative amount, far-future date (>1yr), near-future accepted, past date accepted
- **InvestmentResponse**: Decimal → float serialization

### Service Business Logic (41 tests)

**FundService** (23 tests):

- `get_all_funds`: Cache miss → DB fetch, cache hit → skip DB, pagination params
- `get_fund`: Found, not found (404), cached
- `create_fund`: Success, IntegrityError → 422, cache invalidation
- `update_fund`: Success, not found (404), invalid status transition (422), IntegrityError (422), cache invalidation
- `_validate_status_transition`: 6 valid transitions (parametrized), 3 invalid transitions (parametrized)

**InvestorService** (7 tests):

- `get_all_investors`: Cache miss, cache hit, pagination
- `create_investor`: Success, duplicate email pre-check → 409, TOCTOU race IntegrityError → 409, cache invalidation

**InvestmentService** (11 tests):

- `get_investments_by_fund`: Fund exists, fund not found (404), cached, pagination
- `create_investment`: Success, fund not found (404), closed fund (422), investor not found (404), IntegrityError (422), investing-status fund accepted, cache invalidation

### Infrastructure (38 tests)

**Cache** (22 tests): Get/set, overwrite, multiple types, TTL expiry, entry removal, FIFO eviction, no eviction on update, prefix invalidation, multi-prefix, clear, disabled mode (3 tests), stats (initial, after ops, 100% hit rate)

**Resilience** (20 tests): CircuitBreakerError attributes, CB closed state (success, failure counting), CB open (threshold, fast-fail, no function call), CB half-open (timeout transition, successful probe, failed probe reopens), unexpected exception passthrough, get_status dict, retry (first-try success, retries on retryable, exhaustion, non-retryable passthrough, zero retries, max_delay cap)

**Middleware** (4 tests): Request ID generation, existing ID honoured, process time header present, process time positive

**Exceptions** (12 tests): All exception types (attributes, status codes, inheritance), handler registration count

**Config** (6 tests): Project name, API prefix, SQLite flag, cache defaults, circuit breaker defaults, SQLite URL

### API Integration (18 tests)

Full HTTP request → response cycle using `httpx.AsyncClient`:

- **Funds**: List 200, empty list, create 201, create 422 (validation), get 200, get 404, update 200, update 404, update 422 (invalid transition)
- **Investors**: List 200, create 201, create 409 (duplicate), create 422 (invalid email)
- **Investments**: List 200, list 404 (fund not found), create 201, create 404 (fund not found), create 422 (closed fund)

---

## Test Design Principles

### 1. No Real Database

All tests use `unittest.mock.AsyncMock` for repository calls. This makes tests:

- **Fast** — 154 tests in < 1 second
- **Deterministic** — No flaky failures from DB state
- **Portable** — No PostgreSQL or Docker required

### 2. Isolated Cache

The `conftest.py` fixture `_clear_global_cache` (autouse) resets the global in-memory cache before and after every test, preventing cross-test pollution.

### 3. Factory Helpers

`conftest.py` provides `make_fund()`, `make_investor()`, and `make_investment()` factory functions with sensible defaults, reducing boilerplate:

```python
# Creates a Fund with all required fields pre-filled
fund = make_fund(status=FundStatus.CLOSED)
```

### 4. Dependency Injection in API Tests

API endpoint tests override FastAPI's dependency injection:

```python
self.app.dependency_overrides[_get_fund_service] = lambda: self.mock_service
```

This injects a mocked service without needing a real DB session.

---

## CI Integration

Add to your CI pipeline (GitHub Actions example):

```yaml
- name: Run unit tests
  run: |
    cd titanbay-service
    pip install -r requirements.txt
    pytest --cov=app --cov-report=xml --cov-report=term-missing

- name: Upload coverage
  uses: codecov/codecov-action@v4
  with:
    file: titanbay-service/coverage.xml
```

---

## Troubleshooting

| Problem | Solution |
| --------- | ---------- |
| `ModuleNotFoundError: No module named 'app'` | Run pytest from the `titanbay-service/` directory |
| `pytest-asyncio` warnings | Ensure `asyncio_mode = "auto"` in `pyproject.toml` |
| Coverage below threshold | Run with `--cov-report=term-missing` to see uncovered lines |
| Import errors in tests | Check that `tests/__init__.py` exists |
