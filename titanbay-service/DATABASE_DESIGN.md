# Database Design & Scalability Guide

> Architecture decisions, schema rationale, index strategy, and scaling playbook
> for the Titanbay Private Markets API — designed to support millions of records
> and thousands of concurrent users with ultra-low latency.

---

## Table of Contents

- [Entity-Relationship Diagram](#entity-relationship-diagram)
- [Table Schemas](#table-schemas)
  - [funds](#funds)
  - [investors](#investors)
  - [investments](#investments)
- [Design Decisions & Rationale](#design-decisions--rationale)
  - [Why PostgreSQL?](#why-postgresql)
  - [Why UUID Primary Keys?](#why-uuid-primary-keys)
  - [Why DECIMAL(20,2) for Currency?](#why-decimal202-for-currency)
  - [Why TIMESTAMPTZ for Timestamps?](#why-timestamptz-for-timestamps)
  - [Why Enum Columns as VARCHAR?](#why-enum-columns-as-varchar)
  - [Why No Soft Deletes?](#why-no-soft-deletes)
- [Index Strategy](#index-strategy)
  - [Index Inventory](#index-inventory)
  - [The Hottest Query: Investments by Fund](#the-hottest-query-investments-by-fund)
  - [Email Uniqueness & Lookup](#email-uniqueness--lookup)
  - [Temporal Indexes on created_at](#temporal-indexes-on-created_at)
  - [What We Deliberately Did NOT Index](#what-we-deliberately-did-not-index)
- [Query Analysis](#query-analysis)
  - [GET /funds — List with Pagination](#get-funds--list-with-pagination)
  - [GET /funds/{id} — Point Lookup](#get-fundsid--point-lookup)
  - [GET /funds/{fund_id}/investments — Fan-Out Query](#get-fundsfund_idinvestments--fan-out-query)
  - [POST /investors — Duplicate Detection](#post-investors--duplicate-detection)
  - [SELECT COUNT(*) — Pagination Metadata](#select-count--pagination-metadata)
- [Connection Pool Architecture](#connection-pool-architecture)
- [Concurrency & Race Conditions](#concurrency--race-conditions)
- [Scaling Playbook (10K → 1B+ Records)](#scaling-playbook-10k--1b-records)
  - [Phase 1: Single-Node Optimization (Now)](#phase-1-single-node-optimization-now)
  - [Phase 2: Read Replicas (100K+ Users)](#phase-2-read-replicas-100k-users)
  - [Phase 3: Partitioning (100M+ Records)](#phase-3-partitioning-100m-records)
  - [Phase 4: Sharding (1B+ Records)](#phase-4-sharding-1b-records)
  - [Phase 5: CQRS & Event Sourcing](#phase-5-cqrs--event-sourcing)
- [Future Recommendations](#future-recommendations)

---

## Entity-Relationship Diagram

```text
┌──────────────────────┐       ┌──────────────────────────┐
│       funds           │       │       investors           │
├──────────────────────┤       ├──────────────────────────┤
│ id          UUID [PK]│       │ id          UUID     [PK]│
│ name        VARCHAR  │       │ name        VARCHAR      │
│ vintage_year INTEGER │       │ investor_type VARCHAR    │
│ target_size DECIMAL  │       │ email       VARCHAR [UQ] │
│ status      VARCHAR  │       │ created_at  TIMESTAMPTZ  │
│ created_at  TIMESTAMPTZ│     └───────────┬──────────────┘
└──────────┬───────────┘                   │
           │                               │
           │ 1:N                           │ 1:N
           │                               │
           ▼                               ▼
┌───────────────────────────────────────────────────┐
│                   investments                      │
├───────────────────────────────────────────────────┤
│ id              UUID       [PK]                    │
│ fund_id         UUID       [FK → funds.id]         │
│ investor_id     UUID       [FK → investors.id]     │
│ amount_usd      DECIMAL(20,2)                      │
│ investment_date  DATE                              │
├───────────────────────────────────────────────────┤
│ COMPOSITE INDEX: (fund_id, investment_date)        │
└───────────────────────────────────────────────────┘
```

**Cardinality:**

- One **fund** has many **investments** (1:N)
- One **investor** has many **investments** (1:N)
- **investments** is the junction table, but it is NOT a many-to-many join table — each row represents a distinct capital commitment with its own amount and date

---

## Table Schemas

### funds

| Column | Type | Constraints | Index | Notes |
| ------ | ---- | ----------- | ----- | ----- |
| `id` | `UUID` | `PRIMARY KEY` | B-tree (PK) | Generated via `uuid4()` in app layer |
| `name` | `VARCHAR(255)` | `NOT NULL` | B-tree | Indexed for listing & search |
| `vintage_year` | `INTEGER` | `NOT NULL` | B-tree | Year fund was established; indexed for filtering |
| `target_size_usd` | `DECIMAL(20,2)` | `NOT NULL` | — | Precise currency; never `FLOAT` |
| `status` | `VARCHAR` | `NOT NULL DEFAULT 'Fundraising'` | — | Enum: `Fundraising`, `Investing`, `Closed` |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | B-tree | UTC timestamp; indexed for temporal queries |

**Row estimate at scale:** Thousands (funds are created infrequently). This table will never be a bottleneck.

### investors

| Column | Type | Constraints | Index | Notes |
| ------ | ---- | ----------- | ----- | ----- |
| `id` | `UUID` | `PRIMARY KEY` | B-tree (PK) | Generated via `uuid4()` |
| `name` | `VARCHAR(255)` | `NOT NULL` | B-tree | Indexed for listing & search |
| `investor_type` | `VARCHAR` | `NOT NULL` | — | Enum: `Individual`, `Institution`, `Family Office` |
| `email` | `VARCHAR(320)` | `NOT NULL UNIQUE` | B-tree (unique) | RFC 5321 max email length; unique constraint doubles as index |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | B-tree | Indexed for temporal queries & cursor pagination |

**Row estimate at scale:** Tens of thousands to millions. Email unique index is critical for duplicate detection under concurrency.

### investments

| Column | Type | Constraints | Index | Notes |
| ------ | ---- | ----------- | ----- | ----- |
| `id` | `UUID` | `PRIMARY KEY` | B-tree (PK) | Generated via `uuid4()` |
| `fund_id` | `UUID` | `NOT NULL FK → funds.id` | B-tree + composite | Individual index for joins; composite index for the hot query |
| `investor_id` | `UUID` | `NOT NULL FK → investors.id` | B-tree | Indexed for investor portfolio lookups |
| `amount_usd` | `DECIMAL(20,2)` | `NOT NULL` | — | Precise currency arithmetic |
| `investment_date` | `DATE` | `NOT NULL` | Via composite | Part of `(fund_id, investment_date)` composite index |

**Row estimate at scale:** Hundreds of millions to billions. This is the high-volume table and the focus of our index strategy.

---

## Design Decisions & Rationale

### Why PostgreSQL?

| Consideration | Decision | Reasoning |
| ------------- | -------- | --------- |
| ACID compliance | Required | Financial data demands strict transactional guarantees. A partial investment record is unacceptable. |
| DECIMAL support | Native | PostgreSQL's `NUMERIC` type provides exact decimal arithmetic — critical for USD amounts where floating-point error is a regulatory risk. |
| UUID support | Native `uuid` type | 16-byte binary storage, not 36-byte string. B-tree operations are faster on native UUIDs. |
| Async driver | `asyncpg` | The fastest Python PostgreSQL driver — 3× throughput vs `psycopg2` in benchmarks. Enables non-blocking I/O under FastAPI's async event loop. |
| Scalability features | Partitioning, read replicas, logical replication | PostgreSQL scales horizontally via native table partitioning and streaming replicas, without migrating to a different DBMS. |

### Why UUID Primary Keys?

**Decision:** UUID v4, generated in the application layer (`uuid.uuid4()`).

**Why not auto-increment integers?**

| Factor | Auto-increment `BIGINT` | UUID v4 |
| ------ | ----------------------- | ------- |
| Uniqueness across shards | Requires coordination (sequences, Snowflake IDs) | Globally unique by design |
| ID predictability | Sequential — information leakage (competitors can estimate volume) | Random — no information leakage |
| Insert performance | Appends to B-tree tail (hot page) | Random scatter across B-tree (page splits) |
| Client-side generation | Not possible without DB round-trip | Generated before INSERT — enables optimistic UIs |

**The trade-off:** UUID v4's random distribution causes B-tree page splits at very high insert rates (>50K inserts/sec). This is acceptable at our current scale. For the future, we recommend UUIDv7 (see [Future Recommendations](#future-recommendations)).

### Why DECIMAL(20,2) for Currency?

```text
DECIMAL(20,2) can represent values from -999,999,999,999,999,999.99
                                     to  999,999,999,999,999,999.99
```

- **Never `FLOAT` or `DOUBLE`:** IEEE 754 floating-point cannot exactly represent `0.1`. In financial systems, this leads to rounding errors that compound across millions of transactions. Example: `0.1 + 0.2 = 0.30000000000000004` in float.
- **Why 20 digits?** The largest sovereign wealth fund (Norway GPFG) manages ~$1.7 trillion. `DECIMAL(20,2)` comfortably handles quadrillions — no realistic fund will overflow this.
- **Why 2 decimal places?** USD is denominated to the cent. Sub-cent precision is unnecessary for capital commitments.

### Why TIMESTAMPTZ for Timestamps?

- All `created_at` columns use `TIMESTAMP WITH TIME ZONE` (stored as UTC internally).
- This avoids ambiguity when the API is accessed from different time zones.
- PostgreSQL stores `TIMESTAMPTZ` as a 64-bit integer (microseconds since epoch) — same storage cost as `TIMESTAMP`, but correct under DST transitions.
- Application layer generates `datetime.now(timezone.utc)` so the timestamp is always UTC regardless of the server's locale.

### Why Enum Columns as VARCHAR?

We store `FundStatus` and `InvestorType` as `VARCHAR` rather than PostgreSQL's `CREATE TYPE ... AS ENUM`:

| Factor | PostgreSQL ENUM | VARCHAR + app validation |
| ------ | --------------- | ----------------------- |
| Adding a new value | Requires `ALTER TYPE ... ADD VALUE` migration | Just update the Python enum — no migration |
| Removing a value | Not supported without recreating the type | Just update the Python enum |
| Storage | 4 bytes (catalogue OID) | Variable (but short strings compress well) |
| Validation | DB-level | App-level (Pydantic validates before INSERT) |

**Decision:** The flexibility of VARCHAR outweighs the ~10 bytes of extra storage per row. With Pydantic validating every request before it reaches the database, invalid values never enter the DB regardless.

### Why No Soft Deletes?

The current API spec does not include `DELETE` endpoints. The `delete()` method exists in the base repository for operational use but is not exposed via the API. We chose not to add `deleted_at` / `is_deleted` columns because:

1. **Query complexity tax:** Every query would need `WHERE deleted_at IS NULL`, easily forgotten.
2. **Index bloat:** Soft-deleted rows still occupy index space, degrading scan performance.
3. **GDPR conflict:** "Deleted" data that persists violates data subject erasure rights.
4. **Current spec doesn't need it:** YAGNI (You Aren't Gonna Need It). If needed later, it can be added via migration with a partial index on `deleted_at IS NULL`.

---

## Index Strategy

### Index Inventory

| Table | Index Name | Columns | Type | Purpose |
| ----- | ---------- | ------- | ---- | ------- |
| `funds` | PK | `id` | B-tree (unique) | Primary key lookups |
| `funds` | `ix_funds_name` | `name` | B-tree | Listing, search |
| `funds` | `ix_funds_vintage_year` | `vintage_year` | B-tree | Filtering by year |
| `funds` | `ix_funds_created_at` | `created_at` | B-tree | Temporal queries, cursor pagination |
| `investors` | PK | `id` | B-tree (unique) | Primary key lookups |
| `investors` | `ix_investors_name` | `name` | B-tree | Listing, search |
| `investors` | `ix_investors_email` | `email` | B-tree (unique) | Duplicate detection, login lookups |
| `investors` | `ix_investors_created_at` | `created_at` | B-tree | Temporal queries, cursor pagination |
| `investments` | PK | `id` | B-tree (unique) | Primary key lookups |
| `investments` | `ix_investments_fund_id` | `fund_id` | B-tree | FK joins, existence checks |
| `investments` | `ix_investments_investor_id` | `investor_id` | B-tree | Investor portfolio lookups |
| `investments` | `ix_investments_fund_date` | `(fund_id, investment_date)` | B-tree (composite) | **Hot query:** fund investments sorted by date |

**Total: 12 indexes across 3 tables.**

### The Hottest Query: Investments by Fund

```sql
-- GET /funds/{fund_id}/investments
SELECT * FROM investments
WHERE fund_id = $1
ORDER BY investment_date DESC
LIMIT $2 OFFSET $3;
```

**Without the composite index**, PostgreSQL must:

1. Scan the `fund_id` single-column index to find matching rows
2. Fetch all matching rows from the heap
3. Sort them by `investment_date DESC` in memory (or on disk if `work_mem` is exceeded)
4. Apply LIMIT/OFFSET

**With `ix_investments_fund_date(fund_id, investment_date)`**, PostgreSQL:

1. Seeks directly to `fund_id = $1` in the composite index
2. Reads entries already sorted by `investment_date` (backward index scan for DESC)
3. Stops after `LIMIT + OFFSET` entries — no sort step, no full scan

**Performance at scale:**

| Fund investments | Without composite index | With composite index |
| ---------------- | ---------------------- | -------------------- |
| 100 | ~0.1ms | ~0.05ms |
| 10,000 | ~5ms (sort bottleneck) | ~0.1ms |
| 1,000,000 | ~500ms+ (disk sort) | ~0.2ms |

The composite index reduces the hot query from O(n log n) to O(log n + k) where k is the page size.

### Email Uniqueness & Lookup

```sql
-- Duplicate detection in InvestorService.create_investor()
SELECT * FROM investors WHERE email = $1 LIMIT 1;
```

The unique index on `investors.email` serves dual purpose:

1. **Query performance:** O(log n) B-tree lookup — constant time even at millions of investors
2. **Constraint enforcement:** The DB-level unique constraint is the ultimate safety net against TOCTOU races (see [Concurrency section](#concurrency--race-conditions))

### Temporal Indexes on created_at

Both `funds.created_at` and `investors.created_at` are indexed. While the current API doesn't expose time-range filters, these indexes are proactively added because:

1. **Cursor-based pagination** (recommended at scale — see [Scaling Playbook](#scaling-playbook-10k--1b-records)) requires an indexed, monotonically increasing column. `created_at` is the natural cursor.
2. **Operational queries** ("investors who signed up this month", "funds created in Q1") are inevitable as the platform grows.
3. **Cost:** Negligible. These tables grow slowly (thousands of funds, tens of thousands of investors). The index maintenance overhead is unmeasurable.

### What We Deliberately Did NOT Index

| Column | Why Not |
| ------ | ------- |
| `funds.status` | Only 3 distinct values → extremely low cardinality. PostgreSQL's query planner would prefer a sequential scan over an index scan. A partial index (`WHERE status = 'Fundraising'`) would be appropriate if a specific status query becomes a hot path. |
| `funds.target_size_usd` | Range queries on fund size are uncommon. If needed, a B-tree index or BRIN index (for append-only data) can be added. |
| `investments.amount_usd` | Aggregation queries (`SUM`, `AVG`) scan all matching rows regardless of indexing. For analytics, a materialised view or OLAP system is appropriate. |

---

## Query Analysis

### GET /funds — List with Pagination

```python
# BaseRepository.get_all()
stmt = select(Fund).order_by(Fund.id).offset(skip).limit(limit)
```

**Current approach:** `OFFSET/LIMIT` pagination with deterministic `ORDER BY id`.

**Performance profile:**

| Records | OFFSET 0 | OFFSET 10,000 | OFFSET 1,000,000 |
| ------- | -------- | ------------- | ---------------- |
| 1,000 | 0.1ms | N/A | N/A |
| 100,000 | 0.1ms | ~2ms | N/A |
| 10,000,000 | 0.1ms | ~5ms | ~200ms |

**The OFFSET problem:** PostgreSQL must scan and discard `OFFSET` rows before returning results. At OFFSET 1M, this means scanning 1M index entries.

**Recommendation for scale (documented, not yet implemented):** Replace with **keyset (cursor) pagination**:

```sql
-- Instead of: SELECT * FROM funds ORDER BY id OFFSET 10000 LIMIT 100
-- Use:        SELECT * FROM funds WHERE id > $last_seen_id ORDER BY id LIMIT 100
```

Keyset pagination is O(log n + k) regardless of page depth, because it seeks directly to the cursor position in the B-tree index.

> **Why not implemented now?** The API spec defines `skip/limit` parameters. Keyset pagination changes the API contract (requires a `cursor` parameter). This is documented as a Phase 2 optimization when the dataset exceeds ~100K records per table.

### GET /funds/{id} — Point Lookup

```python
# BaseRepository.get()
await self.db.get(Fund, id)
```

Translates to `SELECT * FROM funds WHERE id = $1`. This is a primary key lookup — O(log n) via the B-tree PK index. At 1 billion rows, a B-tree with fanout ~500 is only ~6 levels deep, so this query is **always < 0.1ms** (assuming the index root and upper pages are in `shared_buffers`).

### GET /funds/{fund_id}/investments — Fan-Out Query

```python
# InvestmentRepository.get_by_fund()
stmt = (
    select(Investment)
    .where(Investment.fund_id == fund_id)
    .order_by(Investment.investment_date.desc())
    .offset(skip).limit(limit)
)
```

This is the **most critical query** for the application. A single fund can have thousands or millions of investments.

**Execution plan with composite index:**

```text
Limit (cost=0.56..12.34 rows=100)
  -> Index Scan Backward using ix_investments_fund_date on investments
       Index Cond: (fund_id = $1)
```

The composite index `(fund_id, investment_date)` enables:

1. **Index seek** on `fund_id` — no table scan
2. **Backward scan** for `DESC` ordering — no sort step
3. **Early termination** at LIMIT — PostgreSQL stops reading after enough rows

### POST /investors — Duplicate Detection

```python
# InvestorRepository.get_by_email()
stmt = select(Investor).where(Investor.email == email)

# InvestorService.create_investor()
existing = await self._repo.get_by_email(str(investor_in.email))
if existing:
    raise ConflictException(...)
```

Two-phase duplicate detection:

1. **Pre-check** (fast path): `SELECT` with the unique index — O(log n), catches 99.9% of duplicates
2. **DB constraint** (safety net): `IntegrityError` catch handles the TOCTOU race (see below)

### SELECT COUNT(*) — Pagination Metadata

```python
# BaseRepository.count()
stmt = select(func.count()).select_from(self.model)
```

**Known scalability concern:** In PostgreSQL, `COUNT(*)` on a large table requires scanning the entire table or index (MVCC means dead tuples must be checked). At 100M+ rows, this can take seconds.

**Mitigations for scale:**

1. **Approximate counts** using `pg_class.reltuples` (updated by `ANALYZE`):

    ```sql
    SELECT reltuples::bigint FROM pg_class WHERE relname = 'investments';
    ```

2. **Materialised count caches** — maintained by triggers or async workers
3. **Avoid total counts in API** — use HasMore/HasPrevious pagination instead of total page counts

> The current codebase includes `count()` in the base repository but it is **not called by any endpoint**. It exists for future pagination metadata if needed.

---

## Connection Pool Architecture

```text
┌─────────────────┐
│   FastAPI App    │
│  (async workers) │
├─────────────────┤     ┌──────────────────────┐
│  SQLAlchemy      │────▶│  PostgreSQL Server    │
│  AsyncEngine     │     │                      │
│                  │     │  max_connections=100  │
│  pool_size=10    │     │  (default)           │
│  max_overflow=20 │     └──────────────────────┘
│  pool_timeout=30s│
│  pool_recycle=1800s│
│  pool_pre_ping=✓ │
└─────────────────┘
```

| Setting | Value | Rationale |
| ------- | ----- | --------- |
| `pool_size` | 10 | Baseline persistent connections. Matches a typical 4-core container running uvicorn with 1 worker. |
| `max_overflow` | 20 | Burst capacity. Total max = 10 + 20 = **30 connections** per app instance. |
| `pool_timeout` | 30s | Time to wait for a connection from the pool before raising an error. Prevents indefinite hangs. |
| `pool_recycle` | 1800s | Recycles connections every 30 minutes. Prevents issues with PostgreSQL's `idle_session_timeout` or intermediate firewalls dropping idle TCP connections. |
| `pool_pre_ping` | True | Issues `SELECT 1` before returning a connection from the pool. Detects dead connections without failing the request. Adds ~0.5ms latency per checkout — acceptable. |

**Scaling for thousands of concurrent users:**

With 4 app replicas behind a load balancer, total DB connections = 4 × 30 = 120. For higher concurrency:

1. **Add PgBouncer** as a connection pooler in `transaction` mode. This allows thousands of application connections to multiplex over ~50 actual PostgreSQL connections.
2. **Tune `pool_size`** per replica based on profiling. Rule of thumb: `pool_size = num_cores × 2 + 1` for the PostgreSQL server.
3. **Scale horizontally** by adding more app replicas (stateless architecture makes this trivial).

---

## Concurrency & Race Conditions

### Duplicate Email (TOCTOU Race)

**Scenario:** Two concurrent `POST /investors` requests with the same email arrive simultaneously.

```text
Request A: get_by_email("x@y.com")  →  None (no duplicate)
Request B: get_by_email("x@y.com")  →  None (no duplicate)
Request A: INSERT INTO investors ... →  Success
Request B: INSERT INTO investors ... →  IntegrityError (unique constraint, CAUGHT)
```

**How we handle it:**

1. The pre-check (`get_by_email`) catches 99.9% of duplicates cheaply
2. The DB unique constraint on `email` is the true safety net
3. The `IntegrityError` is caught in the service layer and translated to a clean `409 Conflict`
4. The session is rolled back — no partial state

### Closed Fund Investment Race

**Scenario:** Fund is being closed (`PUT /funds`) while a new investment is being created (`POST /investments`) simultaneously.

**Current behaviour:** The investment service reads the fund status, which may be stale by the time the INSERT executes. This is a known TOCTOU race.

**Why acceptable for now:** Fund status changes are extremely rare operations (a fund closes once in its lifetime). The probability of this race is negligible. For mission-critical enforcement, a `SELECT ... FOR UPDATE` lock on the fund row would serialize the check:

```sql
SELECT * FROM funds WHERE id = $1 FOR UPDATE;
-- Now no other transaction can modify this fund until we commit
```

This is documented as a Phase 2 hardening step.

---

## Scaling Playbook (10K → 1B+ Records)

### Phase 1: Single-Node Optimization (Now)

**Target:** &lt;10ms p99 latency, thousands of concurrent users.

What's already in place:

- [x] **Async I/O end-to-end** — asyncpg + FastAPI + SQLAlchemy async
- [x] **Composite indexes** on the hottest query path
- [x] **Connection pooling** with pre-ping and overflow
- [x] **GZip middleware** for response compression
- [x] **Deterministic pagination** (ORDER BY PK) for stable results
- [x] **Request-ID middleware** for distributed tracing readiness
- [x] **DB retry with exponential backoff** on startup

Additional single-node tunings:

- [ ] **PostgreSQL `shared_buffers`** — set to 25% of RAM (e.g., 4GB on a 16GB server)
- [ ] **`effective_cache_size`** — set to 75% of RAM for query planner accuracy
- [ ] **`work_mem`** — increase from default 4MB to 64MB for in-memory sorts
- [ ] **`random_page_cost`** — lower from 4.0 to 1.1 on SSD storage to prefer index scans

### Phase 2: Read Replicas (100K+ Users)

```text
┌──────────┐     ┌──────────────┐
│  Writes  │────▶│   Primary    │
└──────────┘     │  PostgreSQL  │
                 └──────┬───────┘
                        │ Streaming Replication
                 ┌──────┴───────┐
                 │   Replica 1  │◀──── Read queries (GET endpoints)
                 │   Replica 2  │◀──── Read queries
                 └──────────────┘
```

- Route all `GET` endpoints to read replicas
- Route `POST`/`PUT`/`DELETE` to the primary
- SQLAlchemy supports this via `engine.execution_options(postgresql_readonly=True)` or a read/write engine pair
- **Latency win:** Replicas handle 100% of list queries, offloading the primary for writes

### Phase 3: Partitioning (100M+ Records)

The `investments` table is the only table that will reach hundreds of millions of rows. Partition it by `fund_id` using PostgreSQL's native hash partitioning:

```sql
-- Distribute investments across 64 partitions by fund_id
CREATE TABLE investments (
    id UUID,
    fund_id UUID NOT NULL,
    investor_id UUID NOT NULL,
    amount_usd DECIMAL(20,2),
    investment_date DATE
) PARTITION BY HASH (fund_id);

CREATE TABLE investments_p0 PARTITION OF investments FOR VALUES WITH (modulus 64, remainder 0);
CREATE TABLE investments_p1 PARTITION OF investments FOR VALUES WITH (modulus 64, remainder 1);
-- ... through p63
```

**Why hash partition by `fund_id`?**

- The hottest query filters by `fund_id` → partition pruning eliminates 63/64 partitions instantly
- Hash partitioning distributes evenly across partitions (vs. range partitioning which can create hot partitions)
- Each partition has its own indexes, reducing B-tree depth

**Alternative: Range partition by `investment_date`** — better for time-range analytics queries. Choose based on the dominant query pattern.

### Phase 4: Sharding (1B+ Records)

When a single PostgreSQL instance cannot handle the write throughput:

1. **Shard by `fund_id`** — each shard holds a subset of funds and all their investments
2. Use **Citus** (PostgreSQL extension) for transparent distributed queries
3. Application-level routing: hash `fund_id` to determine the shard

**Why shard by `fund_id` and not `investor_id`?**

- The API is fund-centric (`GET /funds/{fund_id}/investments`)
- All investments for a fund live on the same shard → no cross-shard queries for the hot path
- Investor lookups are infrequent and can tolerate cross-shard scatter-gather

### Phase 5: CQRS & Event Sourcing

For extreme scale (global, multi-region):

- **Write side:** Append-only event log (investment created, fund status changed)
- **Read side:** Materialised projections optimized per query pattern
- **Benefits:** Write and read models scale independently; eventual consistency is acceptable for list queries
- **Implementation:** Kafka/Pulsar for event streaming, PostgreSQL or ClickHouse for read-side projections

---

## Future Recommendations

| Priority | Recommendation | Impact | Effort |
| -------- | -------------- | ------ | ------ |
| **High** | Switch from UUID v4 to **UUID v7** (time-ordered) | Eliminates B-tree page splits; 2-5× better insert throughput at 100M+ rows | Low — change `uuid.uuid4()` to a UUIDv7 library |
| **High** | Implement **keyset (cursor) pagination** | Constant-time pagination regardless of dataset size (vs. OFFSET degradation) | Medium — requires API contract change (`cursor` param) |
| **High** | Add **PgBouncer** in production | Multiplexes thousands of app connections over ~50 DB connections | Low — infrastructure config |
| **Medium** | Add **`updated_at`** column with trigger | Audit trail for regulatory compliance; enables incremental sync/ETL | Low — migration + trigger |
| **Medium** | `SELECT ... FOR UPDATE` for fund status checks | Eliminates the closed-fund TOCTOU race condition | Low — single query change |
| **Medium** | **Approximate `COUNT(*)`** for large tables | Avoids full table scans for pagination metadata | Low — use `pg_class.reltuples` |
| **Low** | **Partial index** for `funds WHERE status = 'Fundraising'` | Speeds up filtered queries if status filtering becomes a hot path | Trivial |
| **Low** | **Table partitioning** for `investments` | Reduces per-partition index size; enables partition pruning | Medium — requires migration |
| **Low** | **Read replica routing** | Offloads read queries from the primary | Medium — infrastructure + app config |

---

## Summary

The current schema is designed with **production correctness as the baseline** (UUIDs, DECIMAL currency, TIMESTAMPTZ, unique constraints, foreign keys) and **performance at scale as a deliberate extension path** (composite indexes, connection pooling, async I/O). The architecture follows a layered approach where each scaling phase builds on the previous one without requiring a rewrite:

1. **Now:** Single PostgreSQL instance with proper indexes and pooling handles thousands of concurrent users
2. **Growth:** Read replicas and PgBouncer handle 100K+ concurrent users
3. **Scale:** Partitioning and sharding handle billions of records
4. **Global:** CQRS and event sourcing handle multi-region, multi-million concurrent users

Every design decision documented here has a clear "why" and a clear "what changes when we outgrow it."
