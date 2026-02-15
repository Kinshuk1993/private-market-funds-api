# Titanbay Service — Change Log & Engineering Decisions

> Comprehensive record of every change made to bring the codebase to production-grade quality, with rationale for each decision.

---

## Table of Contents

1. [Summary of Issues Found](#1-summary-of-issues-found)
2. [API Spec Compliance Fixes](#2-api-spec-compliance-fixes)
3. [Architecture & SOLID Improvements](#3-architecture--solid-improvements)
4. [Model Layer Changes](#4-model-layer-changes)
5. [Schema Layer Changes](#5-schema-layer-changes)
6. [Repository Layer Changes](#6-repository-layer-changes)
7. [Service Layer Changes](#7-service-layer-changes)
8. [Endpoint Layer Changes](#8-endpoint-layer-changes)
9. [Infrastructure & DevOps Changes](#9-infrastructure--devops-changes)
10. [New Files Added](#10-new-files-added)
11. [Principles Applied](#11-principles-applied)

---

## 1. Summary of Issues Found

The existing codebase had a functional skeleton with the right architectural intent (Service/Repository pattern, async SQLAlchemy, Pydantic schemas), but contained multiple issues that would prevent it from passing a staff-level engineering review:

| # | Issue | Severity | File(s) |
| --- | ------- | ---------- | --------- |
| 1 | `PUT /funds/{fund_id}` — spec requires `PUT /funds` with `id` in body | **Critical** | `endpoints/funds.py`, `schemas/fund.py` |
| 2 | `FundUpdate` only allowed `status` update — spec shows full replacement | **Critical** | `schemas/fund.py` |
| 3 | `update_fund()` called `fund_repo.create()` instead of proper update | **High** | `services/fund_service.py` |
| 4 | `list_funds` bypassed service layer (`service.fund_repo.get_all()`) | **High** | `endpoints/funds.py` |
| 5 | No `update()` method in `BaseRepository` | **High** | `repositories/base.py` |
| 6 | No investor existence check when creating investments | **High** | `services/investment_service.py` |
| 7 | No duplicate email handling for investors | **Medium** | `services/investor_service.py` |
| 8 | Services raised `fastapi.HTTPException` — coupling biz logic to framework | **Medium** | All services |
| 9 | `datetime.utcnow()` deprecated since Python 3.12 | **Medium** | All models |
| 10 | No validation error handler — raw Pydantic errors leaked | **Medium** | `core/exceptions.py` |
| 11 | Deprecated `@app.on_event("startup")` instead of `lifespan` | **Low** | `main.py` |
| 12 | No connection pool configuration (defaults for production) | **Medium** | `db/session.py` |
| 13 | No CORS middleware | **Low** | `main.py` |
| 14 | Missing foreign key indexes on `investments` table | **Medium** | `models/investment.py` |
| 15 | `print()` used instead of `logging` | **Low** | `core/exceptions.py` |
| 16 | Requirements not pinned (no reproducible builds) | **Medium** | `requirements.txt` |
| 17 | Single-stage Dockerfile, running as root | **Medium** | `Dockerfile` |
| 18 | Missing `__init__.py` files in most packages | **Low** | Multiple dirs |
| 19 | No seed data | **Low** | — |
| 20 | No `.gitignore` or `.dockerignore` | **Low** | — |
| 21 | No docstrings or inline documentation | **Medium** | All files |

---

## 2. API Spec Compliance Fixes

### 2.1 `PUT /funds` — id in body, not URL path

**Before:** `PUT /funds/{fund_id}` with a minimal `FundUpdate(status: Optional[FundStatus])`.

**After:** `PUT /funds` with `FundUpdate` containing all fields including `id`.

**Why:** The API specification PDF explicitly shows the `PUT /funds` endpoint with the fund `id` included in the JSON request body, not as a URL path parameter. This is an unusual but valid REST design choice by the spec authors. We follow the spec exactly.

```python
# Before — WRONG
@router.put("/{fund_id}", ...)
async def update_fund(fund_id: UUID, fund_update: FundUpdate, ...):

# After — CORRECT per spec
@router.put("/", ...)
async def update_fund(fund_update: FundUpdate, ...):
    # fund_update.id is used to locate the fund
```

### 2.2 Full replacement semantics

**Before:** `FundUpdate` only exposed `status` — could not update `name`, `vintage_year`, or `target_size_usd`.

**After:** `FundUpdate` extends `FundBase` (same fields as `FundCreate`) plus `id`. This is proper PUT semantics (full resource replacement).

---

## 3. Architecture & SOLID Improvements

### 3.1 Service layer encapsulation (Broken before)

**Before:** The `list_funds` endpoint directly accessed the repository through the service:

```python
return await service.fund_repo.get_all()  # Leaks repository to endpoint
```

**After:** The service exposes a proper `get_all_funds()` method. The repository is a private attribute (`self._repo`).

**Principle:** Encapsulation + Single Responsibility. Endpoints should never know that repositories exist.

### 3.2 Domain exceptions instead of HTTPException

**Before:** Services raised `fastapi.HTTPException`, coupling business logic to the web framework.

**After:** Introduced domain-specific exceptions in `core/exceptions.py`:

- `NotFoundException(resource, id)` → 404
- `ConflictException(message)` → 409
- `BusinessRuleViolation(message)` → 422

These are caught by registered exception handlers in `add_exception_handlers()`. This follows the **Dependency Inversion Principle** — the service layer depends on abstractions, not framework details.

### 3.3 Consistent error response format

Every error now returns:

```json
{"error": true, "message": "..."}
```

Validation errors additionally include:

```json
{"error": true, "message": "Validation failed", "details": [...]}
```

This was achieved by adding a `RequestValidationError` handler that was completely missing before.

---

## 4. Model Layer Changes

### Files: `models/fund.py`, `models/investor.py`, `models/investment.py`

| Change | Rationale |
| ------ | --------- |
| `datetime.utcnow()` → `datetime.now(timezone.utc)` | `utcnow()` returns a naive datetime and is deprecated in Python 3.12+. The replacement returns a timezone-aware UTC datetime. |
| Added `index=True` on `Investment.fund_id` and `Investment.investor_id` | Foreign key columns should be indexed for JOIN and WHERE performance. The `GET /funds/{fund_id}/investments` query directly benefits. |
| Added `index=True` on `Fund.vintage_year` | Common filter/sort column in fund listings. |
| Added `max_length=255` on name fields, `max_length=320` on email | Explicit column length constraints prevent unbounded string storage and make schema intentions clear. |
| Added `TYPE_CHECKING` imports for relationship type hints | Avoids circular import issues at runtime while preserving IDE type support. |
| Added comprehensive docstrings | Every class and field documents its purpose and constraints. |

---

## 5. Schema Layer Changes

### Files: `schemas/fund.py`, `schemas/investor.py`, `schemas/investment.py`

| Change | Rationale |
| ------ | --------- |
| `FundUpdate` now extends `FundBase` + adds `id: UUID` | Matches the API spec's `PUT /funds` payload exactly. |
| Added `@field_validator("vintage_year")` | Rejects unrealistic years (< 1900 or > current + 5). |
| Added `@field_validator("name")` — strips whitespace, rejects blank | Prevents names like `"   "` from passing validation. |
| Added `@field_validator("investment_date")` | Rejects dates more than 1 year in the future (likely data-entry errors). |
| Added `min_length`, `max_length` on string fields | Defence in depth — matches DB column constraints. |
| Added `examples=` on fields | Populates Swagger UI with realistic sample values from the API spec. |
| Added `description=` on all fields | Self-documenting API schema in OpenAPI output. |

---

## 6. Repository Layer Changes

### Files: `repositories/base.py`, `repositories/fund_repo.py`, `repositories/investor_repo.py`, `repositories/investment_repo.py`

| Change | Rationale |
| ------ | --------- |
| Added `update()` method to `BaseRepository` | Previously missing — the service was calling `create()` to persist updates, which is semantically wrong and confusing. The new `update()` uses `session.merge()` + `commit()` + `refresh()`. |
| `get_all()` now wraps result in `list()` | `result.scalars().all()` returns a `Sequence`, not a `List`. Explicit conversion prevents downstream type issues. |
| Added `get_by_email()` to `InvestorRepository` | Required for the duplicate-email check in the service layer. Queries by the indexed `email` column. |
| Added comprehensive docstrings | Every method documents parameters, return values, and design intent. |

---

## 7. Service Layer Changes

### Files: `services/fund_service.py`, `services/investor_service.py`, `services/investment_service.py`

| Change | Rationale |
| ------ | --------- |
| Replaced `HTTPException` with domain exceptions | Decouples from FastAPI. See §3.2. |
| `fund_repo` / `invest_repo` → `_repo` (private) | Prevents endpoint layer from reaching through the service to the repository. |
| Added `get_all_funds()`, `get_fund()` methods | Endpoints no longer bypass the service for reads. |
| `update_fund()` now accepts `FundUpdate` (not `fund_id` + partial) | Matches the new PUT semantic — id is in the schema. |
| `update_fund()` calls `_repo.update()` instead of `_repo.create()` | Correct persistence operation for updates. |
| Added investor existence check in `create_investment()` | **Critical fix.** Before, passing a non-existent `investor_id` would cause a raw FK-violation error from Postgres. Now we validate upfront and return a clear 404. |
| Added duplicate email check in `create_investor()` | Pre-checks before hitting the DB unique constraint, returning a 409 Conflict with a human-readable message. |
| Added `logging.getLogger()` calls | Structured logging instead of `print()`. |

### Validation sequence in `create_investment()`

```bash
1. Fund exists?           → 404 Not Found
2. Fund.status != Closed? → 422 Business Rule Violation
3. Investor exists?       → 404 Not Found
4. Persist investment     → 201 Created
```

---

## 8. Endpoint Layer Changes

### Files: `api/v1/endpoints/funds.py`, `investors.py`, `investments.py`, `api/v1/api.py`

| Change | Rationale |
| ------ | --------- |
| `PUT /funds/{fund_id}` → `PUT /funds` | Spec compliance (§2.1). |
| `get_fund_service` → `_get_fund_service` (underscore prefix) | Convention for internal dependency factories (not part of public API). |
| Endpoints delegate entirely to service methods | No more `service.fund_repo.get_all()`. Clean separation. |
| `get_fund` endpoint no longer has its own 404 logic | Moved to `FundService.get_fund()`. Single Responsibility. |
| Added `summary=`, `description=` to all `@router` decorators | Rich OpenAPI documentation in Swagger UI. |
| Added return type annotations | Type safety and better IDE support. |
| Investment dependency factory now wires `InvestorRepository` | Required by the new investor-existence check in the service. |

---

## 9. Infrastructure & DevOps Changes

### 9.1 `core/config.py`

- Added `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE` settings.
- Added `CORS_ORIGINS` and `DEBUG` settings.
- Added comprehensive docstrings.

### 9.2 `db/session.py`

- Configured connection pool: `pool_size=10`, `max_overflow=20`, `pool_recycle=1800`, `pool_pre_ping=True`.
- `pool_pre_ping` issues a lightweight `SELECT 1` before handing out connections, detecting stale connections.
- `pool_recycle=1800` (30 min) prevents connections from being evicted by PostgreSQL's `idle_in_transaction_session_timeout`.
- `echo` is controlled by `DEBUG` setting.

### 9.3 `main.py`

- Replaced deprecated `@app.on_event("startup")` with `lifespan` async context manager.
- Added `engine.dispose()` on shutdown for clean connection pool teardown.
- Added `CORSMiddleware` for cross-origin requests.
- Added structured `logging.basicConfig()` configuration.

### 9.4 `core/exceptions.py`

- Added `AppException` base class and three domain-specific subclasses.
- Added `RequestValidationError` handler for clean 422 responses.
- Replaced `print()` with `logger.exception()`.

### 9.5 `requirements.txt`

- Pinned all dependency versions for reproducible builds.
- Added `pydantic[email]` for `EmailStr` support.

### 9.6 `Dockerfile`

- Multi-stage build (builder → runtime) for smaller image size.
- Runs as non-root `appuser` for security.
- Installs `libpq` only in runtime stage (not full `gcc` toolchain).
- Added `.dockerignore` to exclude unnecessary files from build context.

### 9.7 `docker-compose.yml`

- Added `DEBUG` and `CORS_ORIGINS` environment variables.

### 9.8 `.env`

- Added `DEBUG=true` and `CORS_ORIGINS=*`.

---

## 10. New Files Added

| File | Purpose |
| ---- | ------- |
| `app/seed.py` | Idempotent seed script with sample data from the API spec examples. Run via `python -m app.seed`. |
| `app/api/__init__.py` | Package marker (was missing). |
| `app/api/v1/__init__.py` | Package marker (was missing). |
| `app/api/v1/endpoints/__init__.py` | Package marker (was missing). |
| `app/core/__init__.py` | Package marker (was missing). |
| `app/db/__init__.py` | Package marker (was missing). |
| `app/models/__init__.py` | Model registry for metadata population. |
| `app/repositories/__init__.py` | Package marker (was missing). |
| `app/schemas/__init__.py` | Package marker (was missing). |
| `app/services/__init__.py` | Package marker (was missing). |
| `.dockerignore` | Excludes `__pycache__`, `.env`, `.git`, etc. from Docker build context. |
| `.gitignore` | Standard Python gitignore. |

---

## 11. Principles Applied

### DRY (Don't Repeat Yourself)

- Generic `BaseRepository` handles all CRUD — concrete repos only add entity-specific queries.
- `FundBase` schema is shared between `FundCreate`, `FundUpdate`, and `FundResponse`.
- Domain exception hierarchy prevents duplicating error-formatting logic.

### SOLID

- **S** — Each service has a single responsibility (one domain aggregate).
- **O** — `BaseRepository` is open for extension (e.g., `get_by_email`) without modifying the base.
- **L** — All concrete repos are substitutable wherever `BaseRepository` is expected.
- **I** — Schemas are segregated by use case (Create, Update, Response).
- **D** — Services depend on repository abstractions, not on SQLAlchemy internals. Endpoints depend on services, not repos.

### Clean Architecture

```bash
HTTP Request → Endpoint (thin) → Service (business logic) → Repository (data access) → DB
```

Each layer only imports the one below it. The service layer is fully framework-agnostic.

### Twelve-Factor App

- **Config:** All settings from environment variables.
- **Dependencies:** Pinned in `requirements.txt`.
- **Disposability:** Graceful startup/shutdown via `lifespan`.
- **Logs:** Structured to stdout (container-friendly).

---

*Document generated on 2026-02-15.*
