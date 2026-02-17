# API Reference

> Complete endpoint reference for the Titanbay Private Markets API.
> Every endpoint, request schema, response schema, status code, and business rule is documented here.

[← Back to README](../README.md)

---

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication

None (open API). In production, add OAuth 2.0 / API-key middleware.

## Common Response Envelopes

### Error Response

Every non-2xx response follows this structure:

```json
{
  "error": true,
  "message": "Human-readable description"
}
```

### Validation Error Response (422)

Validation failures include per-field details:

```json
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> field_name", "message": "Explanation of the failure" }
  ]
}
```

---

## Data Types

| Type | Format | Example |
| ---- | ------ | ------- |
| UUID | RFC 4122 v4 | `550e8400-e29b-41d4-a716-446655440000` |
| Decimal | JSON number (NOT string) | `250000000.0` |
| DateTime | ISO 8601 UTC | `2024-01-15T10:30:00Z` |
| Date | ISO 8601 | `2024-03-15` |
| Enum | Case-sensitive string | `"Fundraising"` |

---

## Enumerations

### FundStatus

| Value | Description |
| ----- | ----------- |
| `Fundraising` | Fund is actively raising capital (default on creation) |
| `Investing` | Fund has closed fundraising and is deploying capital |
| `Closed` | Fund is fully closed — no new investments accepted |

**Lifecycle transitions are one-way:** `Fundraising` → `Investing` → `Closed`. Backward transitions (e.g. `Closed` → `Fundraising`) are rejected with a 422.

### InvestorType

| Value | Description |
| ----- | ----------- |
| `Individual` | Natural person investor |
| `Institution` | Institutional investor (pension fund, bank, etc.) |
| `Family Office` | Family office entity |

---

## Pagination

All list endpoints support pagination via query parameters:

| Parameter | Type | Default | Constraints | Description |
| --------- | ---- | ------- | ----------- | ----------- |
| `skip` | integer | `0` | `>= 0` | Number of records to skip |
| `limit` | integer | `100` | `1 – 1000` | Maximum number of records to return |

---

## Endpoints

### 1. POST /funds

Create a new fund.

#### POST /funds — Request Body

| Field | Type | Required | Constraints | Description |
| ----- | ---- | -------- | ----------- | ----------- |
| `name` | string | Yes | 1–255 chars, not blank | Name of the fund |
| `vintage_year` | integer | Yes | 1900 – (current year + 5) | Year the fund was established |
| `target_size_usd` | number | Yes | > 0 | Target fund size in USD |
| `status` | FundStatus | No | Must be valid enum value | Defaults to `"Fundraising"` |

#### POST /funds — Response (201 Created)

| Field | Type | Description |
| ----- | ---- | ----------- |
| `id` | UUID | Auto-generated unique identifier |
| `name` | string | Name of the fund |
| `vintage_year` | integer | Vintage year |
| `target_size_usd` | number | Target size in USD |
| `status` | FundStatus | Lifecycle status |
| `created_at` | DateTime | UTC timestamp of creation |

#### POST /funds — Status Codes

| Code | Condition |
| ---- | --------- |
| **201** | Fund created successfully |
| **422** | Validation error — missing/invalid fields (e.g. blank name, `vintage_year` out of range, `target_size_usd` ≤ 0, invalid status enum) |

---

### 2. GET /funds

List all funds with optional pagination.

#### GET /funds — Query Parameters

| Parameter | Type | Default | Constraints | Description |
| --------- | ---- | ------- | ----------- | ----------- |
| `skip` | integer | `0` | `>= 0` | Records to skip |
| `limit` | integer | `100` | `1 – 1000` | Max records to return |

#### GET /funds — Response (200 OK)

JSON array of Fund objects (same schema as POST response). Returns `[]` if no funds exist.

#### GET /funds — Status Codes

| Code | Condition |
| ---- | --------- |
| **200** | Success (may be empty array) |
| **422** | Invalid query parameter (e.g. `skip=-1`, `limit=0`) |

---

### 3. GET /funds/{id}

Retrieve a single fund by UUID.

#### GET /funds/{id} — Path Parameters

| Parameter | Type | Required | Description |
| --------- | ---- | -------- | ----------- |
| `id` | UUID | Yes | Fund identifier |

#### GET /funds/{id} — Response (200 OK)

Single Fund object (same schema as POST response).

#### GET /funds/{id} — Status Codes

| Code | Condition |
| ---- | --------- |
| **200** | Fund found and returned |
| **404** | Fund with the given UUID does not exist |
| **422** | Path parameter is not a valid UUID format |

---

### 4. PUT /funds

Full replacement update of an existing fund. Per the API specification, the `id` is passed in the request body (not the URL path).

#### PUT /funds — Request Body

| Field | Type | Required | Constraints | Description |
| ----- | ---- | -------- | ----------- | ----------- |
| `id` | UUID | Yes | Must exist in database | UUID of the fund to update |
| `name` | string | Yes | 1–255 chars, not blank | Updated name |
| `vintage_year` | integer | Yes | 1900 – (current year + 5) | Updated vintage year |
| `target_size_usd` | number | Yes | > 0 | Updated target size |
| `status` | FundStatus | Yes | Valid enum + valid transition | Updated status |

#### Status Transition Rules

| Current Status | Allowed Target Status |
| -------------- | --------------------- |
| `Fundraising` | `Fundraising`, `Investing`, `Closed` |
| `Investing` | `Investing`, `Closed` |
| `Closed` | `Closed` (terminal — no going back) |

#### PUT /funds — Response (200 OK)

Updated Fund object (same schema as POST response, with original `created_at` preserved).

#### PUT /funds — Status Codes

| Code | Condition |
| ---- | --------- |
| **200** | Fund updated successfully |
| **404** | Fund with the given UUID does not exist |
| **422** | Validation error — missing/invalid fields, OR invalid status transition (e.g. `Closed` → `Fundraising`) |

---

### 5. POST /investors

Create a new investor.

#### POST /investors — Request Body

| Field | Type | Required | Constraints | Description |
| ----- | ---- | -------- | ----------- | ----------- |
| `name` | string | Yes | 1–255 chars, not blank | Full name of the investor or institution |
| `investor_type` | InvestorType | Yes | Must be valid enum value | Classification |
| `email` | string (email) | Yes | Valid email format, unique | Contact email address |

#### POST /investors — Response (201 Created)

| Field | Type | Description |
| ----- | ---- | ----------- |
| `id` | UUID | Auto-generated unique identifier |
| `name` | string | Investor name |
| `investor_type` | InvestorType | Classification |
| `email` | string | Email address |
| `created_at` | DateTime | UTC timestamp of creation |

#### POST /investors — Status Codes

| Code | Condition |
| ---- | --------- |
| **201** | Investor created successfully |
| **409** | Duplicate email — an investor with this email already exists |
| **422** | Validation error — missing/invalid fields (e.g. blank name, invalid email format, invalid `investor_type`) |

---

### 6. GET /investors

List all investors with optional pagination.

#### GET /investors — Query Parameters

| Parameter | Type | Default | Constraints | Description |
| --------- | ---- | ------- | ----------- | ----------- |
| `skip` | integer | `0` | `>= 0` | Records to skip |
| `limit` | integer | `100` | `1 – 1000` | Max records to return |

#### GET /investors — Response (200 OK)

JSON array of Investor objects (same schema as POST response). Returns `[]` if no investors exist.

#### GET /investors — Status Codes

| Code | Condition |
| ---- | --------- |
| **200** | Success (may be empty array) |
| **422** | Invalid query parameter (e.g. `skip=-1`, `limit=0`) |

---

### 7. POST /funds/{fund_id}/investments

Record a capital commitment from an investor into a fund.

#### POST /investments — Path Parameters

| Parameter | Type | Required | Description |
| --------- | ---- | -------- | ----------- |
| `fund_id` | UUID | Yes | Target fund identifier |

#### POST /investments — Request Body

| Field | Type | Required | Constraints | Description |
| ----- | ---- | -------- | ----------- | ----------- |
| `investor_id` | UUID | Yes | Must exist in database | UUID of the investing entity |
| `amount_usd` | number | Yes | > 0 | Investment amount in USD |
| `investment_date` | date | Yes | Not more than 1 year in the future | Date of the commitment (ISO 8601) |

#### Validation Sequence

The service validates in this exact order — the first failure stops processing:

1. **Fund exists** — 404 if the `fund_id` is not found
2. **Fund is not Closed** — 422 if the fund's status is `Closed`
3. **Investor exists** — 404 if the `investor_id` is not found
4. **Persist** — insert into database with FK constraint safety net

#### POST /investments — Response (201 Created)

| Field | Type | Description |
| ----- | ---- | ----------- |
| `id` | UUID | Auto-generated unique identifier |
| `fund_id` | UUID | Fund the investment belongs to |
| `investor_id` | UUID | Investor who made the commitment |
| `amount_usd` | number | Investment amount in USD |
| `investment_date` | date | Date of the commitment |

#### POST /investments — Status Codes

| Code | Condition |
| ---- | --------- |
| **201** | Investment created successfully |
| **404** | Fund or investor not found |
| **422** | Validation error — missing/invalid fields, `amount_usd` ≤ 0, future date > 1 year, OR business rule violation (fund is `Closed`) |

---

### 8. GET /funds/{fund_id}/investments

List all investments for a specific fund.

#### GET /investments — Path Parameters

| Parameter | Type | Required | Description |
| --------- | ---- | -------- | ----------- |
| `fund_id` | UUID | Yes | Fund identifier |

#### GET /investments — Query Parameters

| Parameter | Type | Default | Constraints | Description |
| --------- | ---- | ------- | ----------- | ----------- |
| `skip` | integer | `0` | `>= 0` | Records to skip |
| `limit` | integer | `100` | `1 – 1000` | Max records to return |

#### GET /investments — Response (200 OK)

JSON array of Investment objects (same schema as POST response). Returns `[]` if the fund has no investments.

#### GET /investments — Status Codes

| Code | Condition |
| ---- | --------- |
| **200** | Success (may be empty array) |
| **404** | Fund with the given UUID does not exist |
| **422** | Invalid path parameter (not a UUID) or invalid query parameter |

---

## Non-API Endpoints

### GET /health

Liveness / readiness probe with database connectivity check.

#### GET /health — Response (200 OK)

```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": true,
  "circuit_breaker": {
    "name": "database",
    "state": "closed",
    "failure_count": 0,
    "failure_threshold": 5,
    "success_count": 0,
    "recovery_timeout_s": 30.0
  },
  "cache": {
    "enabled": true,
    "size": 42,
    "max_size": 1000,
    "ttl_seconds": 30.0,
    "hits": 128,
    "misses": 15,
    "hit_rate": "89.51%"
  }
}
```

| Field | Type | Description |
| ----- | ---- | ----------- |
| `status` | string | `"ok"` when healthy, `"degraded"` when database is unreachable |
| `version` | string | API version |
| `database` | boolean | `true` if a `SELECT 1` succeeds against PostgreSQL |
| `circuit_breaker` | object | Circuit breaker state (`closed`/`open`/`half_open`), failure count, and thresholds |
| `cache` | object | Cache statistics: `enabled`, `size`, `max_size`, `ttl_seconds`, `hits`, `misses`, `hit_rate` |

### GET /docs

**Swagger UI** — auto-generated interactive API documentation. Lets you browse endpoints, see request/response schemas, and execute API calls directly from the browser. Powered by the OpenAPI 3.1 schema that FastAPI generates from the route definitions and Pydantic models.

### GET /redoc

**ReDoc** — auto-generated read-only API reference. A cleaner, three-panel layout optimized for reading rather than interaction. Uses the same OpenAPI schema as Swagger UI. Served via a custom route using the unpkg CDN (the default cdn.redoc.ly is blocked by Chrome ORB).

> Both `/docs` and `/redoc` are auto-generated by FastAPI at zero maintenance cost — they stay in sync with the code automatically. `/docs` is for developers who want to test endpoints interactively; `/redoc` is for stakeholders who want a polished reference view.

---

## Global Error Handling

| Status Code | Source | When |
| ----------- | ------ | ---- |
| **404** | `NotFoundException` | Resource (fund, investor) not found by UUID |
| **405** | FastAPI router | Wrong HTTP method for a path (e.g. `DELETE /funds`) |
| **409** | `ConflictException` | Unique constraint violation (duplicate investor email) |
| **422** | `RequestValidationError` | Pydantic validation failure on request body/params |
| **422** | `BusinessRuleViolation` | Domain rule violated (closed fund, invalid status transition, DB constraint) |
| **503** | `CircuitBreakerError` | Circuit breaker is open (database unreachable). Includes `Retry-After` header with seconds until recovery probe. |
| **500** | Global catch-all | Unhandled exception (logged for investigation) |

All errors return the [standard error envelope](#common-response-envelopes) documented above.

---

## Response Headers

Every response includes these observability headers:

| Header | Description | Example |
| ------ | ----------- | ------- |
| `X-Request-ID` | Unique request correlation ID. Honoured from upstream proxy if present, otherwise generated as UUID4. Propagated through all log entries for distributed tracing. | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `X-Process-Time` | Server-side processing time in seconds. Requests exceeding 500ms are logged at WARNING level. | `0.0234` |
