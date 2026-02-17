# Sample Requests & Responses

> All examples use `curl`. Replace `localhost:8000` with your host if different.
> UUIDs in responses will differ — the ones below are illustrative.

[← Back to README](../README.md)

---

## POST /api/v1/funds — Create a fund

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

## GET /api/v1/funds — List all funds

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

## GET /api/v1/funds/{id} — Get a specific fund

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

## PUT /api/v1/funds — Update a fund

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

## POST /api/v1/investors — Create an investor

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

## GET /api/v1/investors — List all investors

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

## POST /api/v1/funds/{fund_id}/investments — Create an investment

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

## GET /api/v1/funds/{fund_id}/investments — List investments for a fund

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
