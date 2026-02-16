# Edge Cases — Request & Response Reference

> All edge cases were tested against a **clean database** (no seed data) with tables auto-created on startup.
> Every request uses `curl`. Replace `localhost:8000` with your host if different.

---

## Table of Contents

- [1. Funds](#1-funds)
  - [1.1 POST /funds — Validation Errors](#11-post-funds--validation-errors)
  - [1.2 GET /funds/{id} — Not Found / Invalid ID](#12-get-fundsid--not-found--invalid-id)
  - [1.3 PUT /funds — Not Found / Missing Fields](#13-put-funds--not-found--missing-fields)
  - [1.4 GET /funds — Pagination Errors](#14-get-funds--pagination-errors)
- [2. Investors](#2-investors)
  - [2.1 POST /investors — Duplicate Email](#21-post-investors--duplicate-email)
  - [2.2 POST /investors — Validation Errors](#22-post-investors--validation-errors)
- [3. Investments](#3-investments)
  - [3.1 POST /investments — Business Rule: Closed Fund](#31-post-investments--business-rule-closed-fund)
  - [3.2 POST /investments — Not Found (Fund / Investor)](#32-post-investments--not-found-fund--investor)
  - [3.3 POST /investments — Validation Errors](#33-post-investments--validation-errors)
  - [3.4 GET /investments — Not Found](#34-get-investments--not-found)
- [4. General](#4-general)
  - [4.1 Non-existent Endpoint](#41-non-existent-endpoint)
  - [4.2 Wrong HTTP Method](#42-wrong-http-method)
  - [4.3 Malformed / Missing JSON Body](#43-malformed--missing-json-body)
  - [4.4 Health Check — Degraded State](#44-health-check--degraded-state)
  - [4.5 Database Unavailable at Startup](#45-database-unavailable-at-startup)

---

## 1. Funds

### 1.1 POST /funds — Validation Errors

#### Missing required fields

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{"name": "Bad Fund"}'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> vintage_year", "message": "Field required" },
    { "field": "body -> target_size_usd", "message": "Field required" }
  ]
}
```

#### Empty body

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{}'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> name", "message": "Field required" },
    { "field": "body -> vintage_year", "message": "Field required" },
    { "field": "body -> target_size_usd", "message": "Field required" }
  ]
}
```

#### Invalid status enum

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bad Fund",
    "vintage_year": 2024,
    "target_size_usd": 100000000,
    "status": "Invalid"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> status", "message": "Input should be 'Fundraising', 'Investing' or 'Closed'" }
  ]
}
```

#### Negative target size

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bad Fund",
    "vintage_year": 2024,
    "target_size_usd": -500,
    "status": "Fundraising"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> target_size_usd", "message": "Input should be greater than 0" }
  ]
}
```

#### Zero target size

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Zero Fund",
    "vintage_year": 2024,
    "target_size_usd": 0,
    "status": "Fundraising"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> target_size_usd", "message": "Input should be greater than 0" }
  ]
}
```

#### Vintage year out of range

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bad Fund",
    "vintage_year": 1800,
    "target_size_usd": 100000000,
    "status": "Fundraising"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> vintage_year", "message": "Value error, vintage_year must be between 1900 and 2031" }
  ]
}
```

#### Whitespace-only name

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "name": "   ",
    "vintage_year": 2024,
    "target_size_usd": 100000000,
    "status": "Fundraising"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> name", "message": "Value error, name must not be blank" }
  ]
}
```

#### Wrong type for numeric field

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bad Fund",
    "vintage_year": "not-a-year",
    "target_size_usd": 100000000,
    "status": "Fundraising"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> vintage_year", "message": "Input should be a valid integer, unable to parse string as an integer" }
  ]
}
```

---

### 1.2 GET /funds/{id} — Not Found / Invalid ID

#### Non-existent UUID

```bash
curl -s http://localhost:8000/api/v1/funds/00000000-0000-0000-0000-000000000000
```

```json
// HTTP 404
{
  "error": true,
  "message": "Fund with id '00000000-0000-0000-0000-000000000000' not found"
}
```

#### Malformed UUID

```bash
curl -s http://localhost:8000/api/v1/funds/not-a-uuid
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    {
      "field": "path -> fund_id",
      "message": "Input should be a valid UUID, invalid character: expected an optional prefix of `urn:uuid:` followed by [0-9a-fA-F-], found `n` at 1"
    }
  ]
}
```

---

### 1.3 PUT /funds — Not Found / Missing Fields

#### Non-existent fund ID

```bash
curl -s -X PUT http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "id": "00000000-0000-0000-0000-000000000000",
    "name": "Ghost Fund",
    "vintage_year": 2024,
    "target_size_usd": 100000000,
    "status": "Fundraising"
  }'
```

```json
// HTTP 404
{
  "error": true,
  "message": "Fund with id '00000000-0000-0000-0000-000000000000' not found"
}
```

#### Missing `id` field in PUT body

```bash
curl -s -X PUT http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{
    "name": "No ID Fund",
    "vintage_year": 2024,
    "target_size_usd": 100000000,
    "status": "Fundraising"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> id", "message": "Field required" }
  ]
}
```

---

### 1.4 GET /funds — Pagination Errors

#### Negative `skip`

```bash
curl -s "http://localhost:8000/api/v1/funds?skip=-1"
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "query -> skip", "message": "Input should be greater than or equal to 0" }
  ]
}
```

#### `limit` exceeds maximum (1000)

```bash
curl -s "http://localhost:8000/api/v1/funds?limit=5000"
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "query -> limit", "message": "Input should be less than or equal to 1000" }
  ]
}
```

---

## 2. Investors

### 2.1 POST /investors — Duplicate Email

> Requires an investor with `investments@gsam.com` to already exist.

```bash
curl -s -X POST http://localhost:8000/api/v1/investors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Duplicate Entry",
    "investor_type": "Institution",
    "email": "investments@gsam.com"
  }'
```

```json
// HTTP 409
{
  "error": true,
  "message": "An investor with email 'investments@gsam.com' already exists"
}
```

### 2.2 POST /investors — Validation Errors

#### Invalid email format

```bash
curl -s -X POST http://localhost:8000/api/v1/investors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bad Investor",
    "investor_type": "Institution",
    "email": "not-an-email"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> email", "message": "value is not a valid email address: An email address must have an @-sign." }
  ]
}
```

#### Invalid `investor_type` enum

```bash
curl -s -X POST http://localhost:8000/api/v1/investors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bad Investor",
    "investor_type": "Hedge Fund",
    "email": "test@example.com"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> investor_type", "message": "Input should be 'Individual', 'Institution' or 'Family Office'" }
  ]
}
```

#### Missing required fields (Investors)

```bash
curl -s -X POST http://localhost:8000/api/v1/investors \
  -H "Content-Type: application/json" \
  -d '{"name": "OnlyName"}'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> investor_type", "message": "Field required" },
    { "field": "body -> email", "message": "Field required" }
  ]
}
```

#### Empty body (Investors)

```bash
curl -s -X POST http://localhost:8000/api/v1/investors \
  -H "Content-Type: application/json" \
  -d '{}'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> name", "message": "Field required" },
    { "field": "body -> investor_type", "message": "Field required" },
    { "field": "body -> email", "message": "Field required" }
  ]
}
```

#### Whitespace-only name (Investors)

```bash
curl -s -X POST http://localhost:8000/api/v1/investors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "  ",
    "investor_type": "Individual",
    "email": "blank@example.com"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> name", "message": "Value error, name must not be blank" }
  ]
}
```

---

## 3. Investments

### 3.1 POST /investments — Business Rule: Closed Fund

> Attempting to invest in a fund with `status: Closed` is rejected.

```bash
curl -s -X POST http://localhost:8000/api/v1/funds/{closed_fund_id}/investments \
  -H "Content-Type: application/json" \
  -d '{
    "investor_id": "770e8400-e29b-41d4-a716-446655440002",
    "amount_usd": 1000000,
    "investment_date": "2024-09-22"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Fund 'Closed Legacy Fund' is closed and no longer accepts investments"
}
```

### 3.2 POST /investments — Not Found (Fund / Investor)

#### Non-existent fund

```bash
curl -s -X POST http://localhost:8000/api/v1/funds/00000000-0000-0000-0000-000000000000/investments \
  -H "Content-Type: application/json" \
  -d '{
    "investor_id": "770e8400-e29b-41d4-a716-446655440002",
    "amount_usd": 1000000,
    "investment_date": "2024-09-22"
  }'
```

```json
// HTTP 404
{
  "error": true,
  "message": "Fund with id '00000000-0000-0000-0000-000000000000' not found"
}
```

#### Non-existent investor

```bash
curl -s -X POST http://localhost:8000/api/v1/funds/{valid_fund_id}/investments \
  -H "Content-Type: application/json" \
  -d '{
    "investor_id": "00000000-0000-0000-0000-000000000000",
    "amount_usd": 1000000,
    "investment_date": "2024-09-22"
  }'
```

```json
// HTTP 404
{
  "error": true,
  "message": "Investor with id '00000000-0000-0000-0000-000000000000' not found"
}
```

### 3.3 POST /investments — Validation Errors

#### Negative amount

```bash
curl -s -X POST http://localhost:8000/api/v1/funds/{fund_id}/investments \
  -H "Content-Type: application/json" \
  -d '{
    "investor_id": "770e8400-e29b-41d4-a716-446655440002",
    "amount_usd": -500,
    "investment_date": "2024-09-22"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> amount_usd", "message": "Input should be greater than 0" }
  ]
}
```

#### Zero amount

```bash
curl -s -X POST http://localhost:8000/api/v1/funds/{fund_id}/investments \
  -H "Content-Type: application/json" \
  -d '{
    "investor_id": "770e8400-e29b-41d4-a716-446655440002",
    "amount_usd": 0,
    "investment_date": "2024-09-22"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> amount_usd", "message": "Input should be greater than 0" }
  ]
}
```

#### Investment date too far in the future (>1 year)

```bash
curl -s -X POST http://localhost:8000/api/v1/funds/{fund_id}/investments \
  -H "Content-Type: application/json" \
  -d '{
    "investor_id": "770e8400-e29b-41d4-a716-446655440002",
    "amount_usd": 1000000,
    "investment_date": "2099-01-01"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> investment_date", "message": "Value error, investment_date cannot be more than one year in the future (max: 2027-02-16)" }
  ]
}
```

#### Missing required fields (Funds)

```bash
curl -s -X POST http://localhost:8000/api/v1/funds/{fund_id}/investments \
  -H "Content-Type: application/json" \
  -d '{}'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> amount_usd", "message": "Field required" },
    { "field": "body -> investment_date", "message": "Field required" },
    { "field": "body -> investor_id", "message": "Field required" }
  ]
}
```

#### Invalid date format

```bash
curl -s -X POST http://localhost:8000/api/v1/funds/{fund_id}/investments \
  -H "Content-Type: application/json" \
  -d '{
    "investor_id": "770e8400-e29b-41d4-a716-446655440002",
    "amount_usd": 1000000,
    "investment_date": "not-a-date"
  }'
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body -> investment_date", "message": "Input should be a valid date or datetime, input is too short" }
  ]
}
```

### 3.4 GET /investments — Not Found

#### List investments for a non-existent fund

```bash
curl -s http://localhost:8000/api/v1/funds/00000000-0000-0000-0000-000000000000/investments
```

```json
// HTTP 404
{
  "error": true,
  "message": "Fund with id '00000000-0000-0000-0000-000000000000' not found"
}
```

---

## 4. General

### 4.1 Non-existent Endpoint

```bash
curl -s http://localhost:8000/api/v1/nonexistent
```

```json
// HTTP 404
{
  "error": true,
  "message": "Not Found"
}
```

### 4.2 Wrong HTTP Method

```bash
curl -s -X DELETE http://localhost:8000/api/v1/funds
```

```json
// HTTP 405
{
  "error": true,
  "message": "Method Not Allowed"
}
```

### 4.3 Malformed / Missing JSON Body

```bash
curl -s -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json"
```

```json
// HTTP 422
{
  "error": true,
  "message": "Validation failed",
  "details": [
    { "field": "body", "message": "Field required" }
  ]
}
```

### 4.4 Health Check — Degraded State

When the database is unreachable (e.g., PostgreSQL service stopped), the health endpoint still responds but reports degraded status:

```bash
curl -s http://localhost:8000/health
```

```json
// HTTP 200
{
  "status": "degraded",
  "version": "1.0.0",
  "database": false
}
```

### 4.5 Database Unavailable at Startup

If PostgreSQL is **not running** or the **database does not exist** when the application starts, the app handles it gracefully:

1. **Retry with exponential back-off** — The lifespan handler attempts to connect up to **5 times** with increasing delays (2s → 4s → 8s → 16s → 32s).
2. **Degraded mode** — If all retries fail, the app **still starts** but in degraded mode. The health check will report `"database": false`.
3. **Endpoint behavior** — All database-dependent endpoints will return `500 Internal Server Error` until the database becomes available.

**Startup logs when database is unavailable:**

```text
2026-02-16 19:00:00 | INFO     | Connecting to database (attempt 1/5)…
2026-02-16 19:00:02 | WARNING  | Database connection failed (attempt 1/5): ... — retrying in 2s…
2026-02-16 19:00:04 | INFO     | Connecting to database (attempt 2/5)…
2026-02-16 19:00:06 | WARNING  | Database connection failed (attempt 2/5): ... — retrying in 4s…
...
2026-02-16 19:00:30 | ERROR    | Could not connect to database after 5 attempts.
  The application will start in DEGRADED mode — all database-dependent endpoints
  will return 500 errors until the database becomes available.
```

**Why degraded mode instead of crashing:**

In a production Kubernetes/ECS deployment, a hard crash during startup would trigger a `CrashLoopBackOff`, making the pod unschedulable and hiding the root cause. Starting in degraded mode allows:

- The **health endpoint** to report status (readiness probes correctly mark the pod as unhealthy)
- **Observability tools** (Datadog, Prometheus) to scrape metrics and alert
- The pod to **self-heal** once the database comes back online (the next request will use `pool_pre_ping` to re-establish the connection)

---

## Summary of HTTP Status Codes

| Code | Meaning | When Returned |
| ---- | ------- | ------------- |
| 200 | OK | Successful GET, PUT |
| 201 | Created | Successful POST |
| 404 | Not Found | Resource doesn't exist, or endpoint doesn't exist |
| 405 | Method Not Allowed | Using an unsupported HTTP method on a valid path |
| 409 | Conflict | Duplicate email on investor creation |
| 422 | Unprocessable Entity | Validation errors, business rule violations |
| 500 | Internal Server Error | Unexpected server errors, database unavailable |
