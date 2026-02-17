# No-Database Setup (SQLite In-Memory)

> Run all 42 tests with **zero external dependencies** — no Docker, no PostgreSQL, no database server of any kind.

This is the fastest way to verify the API works correctly.  The application starts with an **ephemeral in-memory SQLite database** that is created fresh on startup and destroyed when the server stops.

---

## Prerequisites

| Requirement | Why |
| ----------- | --- |
| **Python 3.14** | Runtime for the FastAPI application |
| **curl** | Used by the test script to hit API endpoints |
| **bash** | Shell to run the test script (Git Bash on Windows, native on macOS/Linux) |

> **That's it.** No Docker.  No PostgreSQL.  No database drivers or servers to install.

---

## How It Works

The application has a `USE_SQLITE` environment variable.  When set to `true`:

1. The SQLAlchemy engine switches from PostgreSQL (`asyncpg`) to **in-memory SQLite** (`aiosqlite`).
2. A `StaticPool` is used so all async connections share the **same** in-memory database.
3. SQLite foreign key enforcement is enabled via `PRAGMA foreign_keys=ON`.
4. All tables are created automatically on startup (just like the PostgreSQL path).
5. The database lives entirely in RAM — once the process stops, all data is gone.

This means the full API (all 8 endpoints, all validation, all business rules) works exactly the same as with PostgreSQL — just backed by SQLite.

---

## One-Command Test

```bash
bash scripts/test_no_db.sh
```

This single command will:

1. Create a Python virtual environment (if one doesn't exist)
2. Install all dependencies
3. Configure the app for SQLite in-memory mode
4. Start the uvicorn server
5. Run all **42 tests** (10 happy-path + 32 edge-case)
6. Print a pass/fail summary
7. Stop the server and clean up

---

## Step-by-Step Manual Setup

If you prefer to set things up manually (e.g., to explore the API interactively):

### Step 1: Clone and navigate to the project

```bash
cd titanbay-service
```

### Step 2: Create and activate a virtual environment

**Linux / macOS:**

```bash
python -m venv venv
source venv/bin/activate
```

**Windows (Git Bash):**

```bash
python -m venv venv
source venv/Scripts/activate
```

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure environment for SQLite mode

Create a `.env` file in the `titanbay-service/` directory:

```bash
cat > .env <<EOF
USE_SQLITE=true
DEBUG=true
CORS_ORIGINS=*
EOF
```

Or manually create `.env` with:

```ini
USE_SQLITE=true
DEBUG=true
CORS_ORIGINS=*
```

> **Note:** No `POSTGRES_*` variables are needed — they are ignored in SQLite mode.

### Step 5: Start the server

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Step 6: Verify it's running

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok", "version": "1.0.0", "database": true}
```

### Step 7: Try the API

```bash
# Create a fund
curl -X POST http://localhost:8000/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Fund","vintage_year":2025,"target_size_usd":100000000,"status":"Fundraising"}'

# List funds
curl http://localhost:8000/api/v1/funds
```

### Step 8: Open interactive docs

| URL | Description |
| --- | ----------- |
| <http://localhost:8000/docs> | **Swagger UI** — try endpoints from the browser |
| <http://localhost:8000/redoc> | **ReDoc** — polished read-only reference |

---

## Comparison of Test Methods

| | No-DB (this guide) | Local PostgreSQL | Docker |
| --- | --- | --- | --- |
| **Script** | `bash scripts/test_no_db.sh` | `bash scripts/test_local.sh -p <pw>` | `bash scripts/test_docker.sh` |
| **Requires Docker** | No | No | Yes |
| **Requires PostgreSQL** | No | Yes | No (runs in container) |
| **Setup time** | ~30 seconds | ~2 minutes | ~3 minutes |
| **Database** | In-memory SQLite | Local PostgreSQL | Containerized PostgreSQL |
| **Data persistence** | None (ephemeral) | Yes | Container lifecycle |
| **Best for** | Quick review / CI | Local development | Production-like testing |

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'aiosqlite'`

Run `pip install -r requirements.txt` again — `aiosqlite` was added as a dependency.

### Port 8000 already in use

Another process is using port 8000.  Kill it or change the port:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

### Script fails on Windows

The test script requires bash.  Use **Git Bash** (comes with Git for Windows) or **WSL**:

```bash
# Git Bash
bash scripts/test_no_db.sh

# WSL
wsl bash scripts/test_no_db.sh
```

### Server starts but tests fail with connection errors

Wait a few seconds after starting the server.  The test script has a built-in 30-second wait, but on very slow machines you may need to run it again.
