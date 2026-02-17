#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# test_local.sh — One-command local smoke test (no Docker)
#
# Requires: PostgreSQL running locally, Python 3.14+ installed.
# Creates the DB/user if missing, activates venv, starts uvicorn, runs
# happy-path and edge-case curl tests, then stops the server.
# All output is captured to  logs/local_test.log
#
# Usage:
#   bash scripts/test_local.sh
# ──────────────────────────────────────────────────────────────────────────────
set -uo pipefail

# ── Resolve paths ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/local_test.log"
mkdir -p "$LOG_DIR"
> "$LOG_FILE"

# ── Logging ──
log() { echo "$*" | tee -a "$LOG_FILE"; }

# ── Test counters ──
PASS=0; FAIL=0; TOTAL=0
LAST_BODY=""
APP_PID=""

cleanup() {
    if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
        log "[CLEANUP] Stopping uvicorn (PID $APP_PID)..."
        kill "$APP_PID" 2>/dev/null || true
        wait "$APP_PID" 2>/dev/null || true
        log "  Server stopped"
    fi
}
trap cleanup EXIT

run_test() {
    local name="$1" expected="$2"; shift 2
    TOTAL=$((TOTAL + 1))
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" "$@" 2>/dev/null) || true
    if [ "$code" = "$expected" ]; then
        log "  [PASS]  $name  ->  HTTP $code"
        PASS=$((PASS + 1))
    else
        log "  [FAIL]  $name  ->  HTTP $code (expected $expected)"
        FAIL=$((FAIL + 1))
    fi
}

run_test_verbose() {
    local name="$1" expected="$2"; shift 2
    TOTAL=$((TOTAL + 1))
    local tmpfile="$LOG_DIR/.curl_tmp_$$"
    local code
    code=$(curl -s -w "%{http_code}" -o "$tmpfile" "$@" 2>/dev/null) || true
    local body=""
    [ -f "$tmpfile" ] && body=$(cat "$tmpfile")
    rm -f "$tmpfile" 2>/dev/null
    if [ "$code" = "$expected" ]; then
        log "  [PASS]  $name  ->  HTTP $code"
        PASS=$((PASS + 1))
    else
        log "  [FAIL]  $name  ->  HTTP $code (expected $expected)"
        FAIL=$((FAIL + 1))
    fi
    log "          $body"
    LAST_BODY="$body"
}

extract_id() {
    echo "$LAST_BODY" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4
}

wait_for_url() {
    local url="$1" label="$2" max="${3:-30}" waited=0
    while [ $waited -lt "$max" ]; do
        curl -sf "$url" >/dev/null 2>&1 && { log "  $label is ready (${waited}s)"; return 0; }
        sleep 2; waited=$((waited + 2))
    done
    log "  WARNING: $label not ready within ${max}s"; return 1
}

# ── Constants ──
BASE="http://localhost:8000"
API="$BASE/api/v1"
CT="Content-Type: application/json"

DB_USER="titanbay_user"
DB_PASS="titanbay_password"
DB_NAME="titanbay_db"
DB_HOST="127.0.0.1"
DB_PORT="5432"

# ══════════════════════════════════════════════════════════════════════════════
# SETUP
# ══════════════════════════════════════════════════════════════════════════════
log "================================================================"
log "  Titanbay Local Smoke Test — $(date '+%Y-%m-%d %H:%M:%S')"
log "================================================================"
log ""

# ── 1. Check PostgreSQL ──
log "[SETUP] Checking local PostgreSQL..."
if command -v pg_isready &>/dev/null; then
    if pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
        log "  PostgreSQL is accepting connections"
    else
        log "  ERROR: PostgreSQL is not running on $DB_HOST:$DB_PORT"
        log "  Start PostgreSQL first, then re-run this script."
        exit 1
    fi
else
    log "  pg_isready not found — assuming PostgreSQL is running"
fi

# ── 2. Check / create DB user and database ──
log "[SETUP] Checking database connectivity..."

# First, try to connect directly as the app user.
if PGPASSWORD="$DB_PASS" psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
    log "  Database '$DB_NAME' accessible as '$DB_USER'"
else
    log "  Cannot connect as '$DB_USER' — attempting to create user/database..."
    log "  Set PGPASSWORD_ADMIN or ensure 'trust' auth for local postgres user."
    PG_ADMIN_PW="${PGPASSWORD_ADMIN:-}"

    # Create user if it doesn't exist (non-interactive)
    if PGPASSWORD="$PG_ADMIN_PW" psql -U postgres -h "$DB_HOST" -p "$DB_PORT" --no-password -tAc \
        "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null | grep -q 1; then
        log "  User '$DB_USER' already exists"
    else
        PGPASSWORD="$PG_ADMIN_PW" psql -U postgres -h "$DB_HOST" -p "$DB_PORT" --no-password -c \
            "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" >>"$LOG_FILE" 2>&1 \
            && log "  Created user '$DB_USER'" \
            || { log "  ERROR: Could not create user. Ensure PostgreSQL trust auth or set PGPASSWORD_ADMIN."; exit 1; }
    fi

    # Create database if it doesn't exist
    if PGPASSWORD="$PG_ADMIN_PW" psql -U postgres -h "$DB_HOST" -p "$DB_PORT" --no-password -tAc \
        "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
        log "  Database '$DB_NAME' already exists"
    else
        PGPASSWORD="$PG_ADMIN_PW" psql -U postgres -h "$DB_HOST" -p "$DB_PORT" --no-password -c \
            "CREATE DATABASE $DB_NAME OWNER $DB_USER;" >>"$LOG_FILE" 2>&1 \
            && log "  Created database '$DB_NAME'" \
            || { log "  ERROR: Could not create database. Ensure PostgreSQL trust auth or set PGPASSWORD_ADMIN."; exit 1; }
    fi
fi

# ── 3. Python venv + deps ──
log "[SETUP] Setting up Python environment..."
cd "$PROJECT_DIR"

if [ ! -d "venv" ]; then
    python -m venv venv
    log "  Created virtual environment"
fi

# Activate (Linux/macOS vs Git Bash on Windows)
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
else
    log "  ERROR: Cannot find venv activate script"
    exit 1
fi

pip install -q -r requirements.txt >>"$LOG_FILE" 2>&1
log "  Dependencies installed"

# ── 4. Write .env ──
cat > .env <<EOF
POSTGRES_USER=$DB_USER
POSTGRES_PASSWORD=$DB_PASS
POSTGRES_SERVER=$DB_HOST
POSTGRES_DB=$DB_NAME
POSTGRES_PORT=$DB_PORT
DEBUG=true
CORS_ORIGINS=*
EOF
log "  .env configured"

# ── 5. Start uvicorn ──
log "[SETUP] Starting uvicorn..."
uvicorn app.main:app --host 127.0.0.1 --port 8000 >>"$LOG_FILE" 2>&1 &
APP_PID=$!
log "  uvicorn PID=$APP_PID"

wait_for_url "$BASE/health" "App" 30 || {
    log "FATAL: App failed to start. Check logs/local_test.log for details."
    exit 1
}
log ""

# ══════════════════════════════════════════════════════════════════════════════
# HAPPY-PATH TESTS
# ══════════════════════════════════════════════════════════════════════════════
log "================================================================"
log "  HAPPY-PATH TESTS"
log "================================================================"

run_test "GET  /health" 200 "$BASE/health"

run_test_verbose "POST /funds (create)" 201 \
    -X POST "$API/funds" -H "$CT" \
    -d '{"name":"Smoke Test Fund","vintage_year":2025,"target_size_usd":100000000,"status":"Fundraising"}'
FUND_ID=$(extract_id)
log "          fund_id=$FUND_ID"

run_test "GET  /funds (list)" 200 "$API/funds"
run_test "GET  /funds/{id}" 200 "$API/funds/$FUND_ID"

run_test_verbose "PUT  /funds (update)" 200 \
    -X PUT "$API/funds" -H "$CT" \
    -d "{\"id\":\"$FUND_ID\",\"name\":\"Smoke Test Fund\",\"vintage_year\":2025,\"target_size_usd\":200000000,\"status\":\"Investing\"}"

run_test_verbose "POST /investors (create)" 201 \
    -X POST "$API/investors" -H "$CT" \
    -d '{"name":"Smoke Test Investor","investor_type":"Institution","email":"smoke@test.com"}'
INVESTOR_ID=$(extract_id)
log "          investor_id=$INVESTOR_ID"

run_test "GET  /investors (list)" 200 "$API/investors"

run_test_verbose "POST /investments (create)" 201 \
    -X POST "$API/funds/$FUND_ID/investments" -H "$CT" \
    -d "{\"investor_id\":\"$INVESTOR_ID\",\"amount_usd\":50000000,\"investment_date\":\"2025-06-15\"}"
INVESTMENT_ID=$(extract_id)
log "          investment_id=$INVESTMENT_ID"

run_test "GET  /investments (list)" 200 "$API/funds/$FUND_ID/investments"
log ""

# ══════════════════════════════════════════════════════════════════════════════
# EDGE-CASE TESTS
# ══════════════════════════════════════════════════════════════════════════════
log "================================================================"
log "  EDGE-CASE TESTS"
log "================================================================"

log "  -- Funds --"
run_test "GET  /funds/{id} non-existent UUID"       404  "$API/funds/00000000-0000-0000-0000-000000000000"
run_test "GET  /funds/{id} malformed UUID"           422  "$API/funds/not-a-uuid"
run_test "POST /funds missing required fields"       422  -X POST "$API/funds" -H "$CT" -d '{"name":"Bad Fund"}'
run_test "POST /funds invalid status enum"           422  -X POST "$API/funds" -H "$CT" -d '{"name":"Bad","vintage_year":2024,"target_size_usd":100,"status":"Invalid"}'
run_test "POST /funds negative target_size_usd"      422  -X POST "$API/funds" -H "$CT" -d '{"name":"Bad","vintage_year":2024,"target_size_usd":-500,"status":"Fundraising"}'
run_test "POST /funds zero target_size_usd"          422  -X POST "$API/funds" -H "$CT" -d '{"name":"Bad","vintage_year":2024,"target_size_usd":0,"status":"Fundraising"}'
run_test "POST /funds vintage_year out of range"     422  -X POST "$API/funds" -H "$CT" -d '{"name":"Bad","vintage_year":1800,"target_size_usd":100,"status":"Fundraising"}'
run_test "POST /funds whitespace-only name"          422  -X POST "$API/funds" -H "$CT" -d '{"name":"   ","vintage_year":2024,"target_size_usd":100,"status":"Fundraising"}'
run_test "POST /funds empty body"                    422  -X POST "$API/funds" -H "$CT" -d '{}'
run_test "POST /funds wrong type for vintage_year"   422  -X POST "$API/funds" -H "$CT" -d '{"name":"Bad","vintage_year":"abc","target_size_usd":100,"status":"Fundraising"}'
run_test "PUT  /funds non-existent id"               404  -X PUT "$API/funds" -H "$CT" -d '{"id":"00000000-0000-0000-0000-000000000000","name":"Ghost","vintage_year":2024,"target_size_usd":100,"status":"Fundraising"}'
run_test "PUT  /funds missing id field"              422  -X PUT "$API/funds" -H "$CT" -d '{"name":"No ID","vintage_year":2024,"target_size_usd":100,"status":"Fundraising"}'
run_test "GET  /funds negative skip"                 422  "$API/funds?skip=-1"
run_test "GET  /funds limit > 1000"                  422  "$API/funds?limit=5000"

log ""
log "  -- Investors --"
run_test "POST /investors duplicate email"   409  -X POST "$API/investors" -H "$CT" -d '{"name":"Dup","investor_type":"Institution","email":"smoke@test.com"}'
run_test "POST /investors invalid email"     422  -X POST "$API/investors" -H "$CT" -d '{"name":"Bad","investor_type":"Institution","email":"not-an-email"}'
run_test "POST /investors invalid type"      422  -X POST "$API/investors" -H "$CT" -d '{"name":"Bad","investor_type":"Hedge Fund","email":"hf@test.com"}'
run_test "POST /investors missing fields"    422  -X POST "$API/investors" -H "$CT" -d '{"name":"Only"}'
run_test "POST /investors empty body"        422  -X POST "$API/investors" -H "$CT" -d '{}'
run_test "POST /investors whitespace name"   422  -X POST "$API/investors" -H "$CT" -d '{"name":"  ","investor_type":"Individual","email":"ws@test.com"}'

log ""
log "  -- Investments --"

# Tests that need an active (non-Closed) fund run FIRST
run_test "POST /investments non-existent fund"      404  -X POST "$API/funds/00000000-0000-0000-0000-000000000000/investments" -H "$CT" -d "{\"investor_id\":\"$INVESTOR_ID\",\"amount_usd\":1000000,\"investment_date\":\"2025-06-15\"}"
run_test "POST /investments non-existent investor"   404  -X POST "$API/funds/$FUND_ID/investments" -H "$CT" -d '{"investor_id":"00000000-0000-0000-0000-000000000000","amount_usd":1000000,"investment_date":"2025-06-15"}'
run_test "POST /investments negative amount"         422  -X POST "$API/funds/$FUND_ID/investments" -H "$CT" -d "{\"investor_id\":\"$INVESTOR_ID\",\"amount_usd\":-500,\"investment_date\":\"2025-06-15\"}"
run_test "POST /investments zero amount"             422  -X POST "$API/funds/$FUND_ID/investments" -H "$CT" -d "{\"investor_id\":\"$INVESTOR_ID\",\"amount_usd\":0,\"investment_date\":\"2025-06-15\"}"
run_test "POST /investments far future date"         422  -X POST "$API/funds/$FUND_ID/investments" -H "$CT" -d "{\"investor_id\":\"$INVESTOR_ID\",\"amount_usd\":1000000,\"investment_date\":\"2099-01-01\"}"
run_test "POST /investments missing fields"          422  -X POST "$API/funds/$FUND_ID/investments" -H "$CT" -d '{}'
run_test "POST /investments invalid date"            422  -X POST "$API/funds/$FUND_ID/investments" -H "$CT" -d "{\"investor_id\":\"$INVESTOR_ID\",\"amount_usd\":1000000,\"investment_date\":\"not-a-date\"}"
run_test "GET  /investments non-existent fund"       404  "$API/funds/00000000-0000-0000-0000-000000000000/investments"

# Close fund -> test business rule (closed fund rejects investments)
curl -s -X PUT "$API/funds" -H "$CT" \
    -d "{\"id\":\"$FUND_ID\",\"name\":\"Smoke Test Fund\",\"vintage_year\":2025,\"target_size_usd\":200000000,\"status\":\"Closed\"}" >/dev/null 2>&1
run_test "POST /investments closed fund"        422  -X POST "$API/funds/$FUND_ID/investments" -H "$CT" -d "{\"investor_id\":\"$INVESTOR_ID\",\"amount_usd\":1000000,\"investment_date\":\"2025-06-15\"}"

# Test invalid status transition: Closed -> Fundraising (one-way lifecycle)
run_test "PUT  /funds invalid transition Closed->Fundraising" 422 \
    -X PUT "$API/funds" -H "$CT" \
    -d "{\"id\":\"$FUND_ID\",\"name\":\"Smoke Test Fund\",\"vintage_year\":2025,\"target_size_usd\":200000000,\"status\":\"Fundraising\"}"

log ""
log "  -- General --"
run_test "GET  non-existent endpoint"   404  "$API/nonexistent"
run_test "DELETE /funds (wrong method)" 405  -X DELETE "$API/funds"
run_test "POST /funds no body at all"   422  -X POST "$API/funds" -H "$CT"
log ""

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
log "================================================================"
log "  RESULTS:  $PASS passed  /  $FAIL failed  /  $TOTAL total"
log "================================================================"
log ""
log "Full log: $LOG_FILE"
log "Server will be stopped automatically (PID $APP_PID)"

[ "$FAIL" -gt 0 ] && exit 1
exit 0
