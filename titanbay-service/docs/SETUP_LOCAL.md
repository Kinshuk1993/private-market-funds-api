# Local Development Setup (without Docker)

[← Back to README](../README.md)

## Prerequisites

- **Python 3.14** installed
- **PostgreSQL 15+** installed and **running** locally. The application **will not start** without a reachable PostgreSQL instance — it connects to the database during startup to create tables.
  - **Windows:** Install from <https://www.postgresql.org/download/windows/> or via `winget install PostgreSQL.PostgreSQL`. After installation, ensure the PostgreSQL service is running (check *Services* or run `pg_isready`).
  - **macOS:** `brew install postgresql@16 && brew services start postgresql@16`
  - **Linux:** `sudo apt install postgresql` (or equivalent for your distro) and `sudo systemctl start postgresql`
- **PostgreSQL superuser credentials** — You need to know the password for the `postgres` superuser (set during installation) to create the application database and user in the next step.

## 1. Create the database and user

Connect to PostgreSQL using the `postgres` superuser and create the application database:

```bash
psql -U postgres -h 127.0.0.1 -c "CREATE USER titanbay_user WITH PASSWORD 'titanbay_password';"
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE titanbay_db OWNER titanbay_user;"
```

> **Note:** You will be prompted for the `postgres` superuser password. If you haven't set one, refer to your OS-specific PostgreSQL installation docs to configure it.

## 2. Set up virtual environment and install dependencies

```bash
cd titanbay-service
python -m venv venv
source venv/bin/activate        # Linux/macOS
# or: source venv/Scripts/activate  # Git Bash on Windows

pip install -r requirements.txt
```

## 3. Configure environment

```bash
cp .env.example .env
# Edit .env — set POSTGRES_SERVER=127.0.0.1 for local development
```

## 4. Start the application

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

> **What happens on startup:** The application automatically creates all required database tables (`funds`, `investors`, `investments`) if they don't already exist. This is handled by the `lifespan` function in `app/main.py`, which calls `SQLModel.metadata.create_all` against the configured database. You do **not** need to run any migrations or SQL scripts manually — just ensure the database and user from step 1 exist. If the database is unreachable at startup, the application will fail with a connection error.

## 5. Seed sample data (optional)

```bash
python -m app.seed
```

> **What the seed does:** The seed script inserts sample funds, investors, and investments into the database for development and demo purposes. It is **completely optional** — the application works fine without it. If you skip seeding, API endpoints like `GET /funds` will return empty arrays (`[]`) until you create data via the `POST` endpoints. The seed is idempotent: running it multiple times will not create duplicate records.

## One-Command Test (Local)

Instead of running steps 1-5 manually, you can use the automated test script.
It checks PostgreSQL connectivity, sets up the venv, starts uvicorn, runs **51 tests**
(happy-path + edge-cases + infrastructure) against all 8 endpoints, captures output to `logs/local_test.log`,
and stops the server on exit:

```bash
bash scripts/test_local.sh
```

> **Windows (Git Bash):** `"C:\Program Files\Git\bin\bash.exe" scripts/test_local.sh`
> **Production safety:** The local test uses an isolated database named `titanbay_db_test` —
> your production `titanbay_db` is **never** touched. The script temporarily writes a
> test `.env` (pointing at `titanbay_db_test`), and restores the original `.env` on exit.

**Will it prompt for a password?** No — the script **never** opens an interactive prompt.
Here is how it works depending on your database state:

| Scenario | What happens | Action needed |
| -------- | ------------ | ------------- |
| Test DB (`titanbay_db_test`) + user already exist | Script connects, truncates test tables, runs tests. **Fully automatic.** | None |
| Test DB doesn't exist, you provide `-p` flag | Script uses the postgres superuser to create `titanbay_db_test`. **Fully automatic.** | Pass `-p` (see below) |
| Test DB doesn't exist, no `-p` flag | Script prints clear setup instructions and **exits immediately** (does not hang). | Either use `-p` or create the DB manually (see below) |

**First-time setup** — provide the PostgreSQL superuser password via the `-p` flag:

```bash
# Linux / macOS
bash scripts/test_local.sh -p <your_postgres_password>

# Windows (Git Bash)
"C:\Program Files\Git\bin\bash.exe" scripts/test_local.sh -p <your_postgres_password>
```

Or create the test database manually (one-time), then run without `-p`:

```bash
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE titanbay_db_test OWNER titanbay_user;"
bash scripts/test_local.sh
```

Once the test database exists (after the first successful run or manual creation),
the `-p` flag is never needed again — every subsequent run is fully automatic with zero
interaction.
