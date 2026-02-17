#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# test_docker.sh — One-command Docker smoke test
#
# Starts PostgreSQL + app in ephemeral Docker containers with a DEDICATED TEST
# DATABASE (titanbay_db_test) — production data is NEVER touched.
# Runs happy-path and edge-case curl tests against all 8 API endpoints,
# then tears everything down.
# All output is captured to  logs/docker_test.log
#
# Usage:
#   bash scripts/test_docker.sh
# ──────────────────────────────────────────────────────────────────────────────
set -uo pipefail

# ── Resolve paths ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/docker_test.log"
mkdir -p "$LOG_DIR"
> "$LOG_FILE"

# ── Logging: write to both console and log file ──
log() { echo "$*" | tee -a "$LOG_FILE"; }

# ── Test counters ──
PASS=0; FAIL=0; TOTAL=0
LAST_BODY=""

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
NET="titanbay-net"
DB_CTR="titanbay-db"
APP_CTR="titanbay-app"
IMAGE="titanbay-service"
BASE="http://localhost:8000"
API="$BASE/api/v1"
CT="Content-Type: application/json"

# ══════════════════════════════════════════════════════════════════════════════
# SETUP
# ══════════════════════════════════════════════════════════════════════════════
log "================================================================"
log "  Titanbay Docker Smoke Test — $(date '+%Y-%m-%d %H:%M:%S')"
log "================================================================"
log ""

log "[SETUP] Cleaning up previous containers..."
docker rm -f "$APP_CTR" "$DB_CTR" >/dev/null 2>&1 || true
docker network rm "$NET" >/dev/null 2>&1 || true

log "[SETUP] Creating Docker network..."
docker network create "$NET" >/dev/null 2>&1

log "[SETUP] Starting PostgreSQL container..."
docker run -d --name "$DB_CTR" --network "$NET" \
  -e POSTGRES_USER=titanbay_user \
  -e POSTGRES_PASSWORD=titanbay_password \
  -e POSTGRES_DB=titanbay_db_test \
  -p 5432:5432 postgres:15-alpine >/dev/null 2>&1

log "  Waiting for PostgreSQL..."
sleep 3
for _ in $(seq 1 10); do
    docker exec "$DB_CTR" pg_isready -U titanbay_user -d titanbay_db_test >/dev/null 2>&1 && { log "  PostgreSQL ready"; break; }
    sleep 2
done

log "[SETUP] Building app image (this may take a minute on first run)..."
docker build -t "$IMAGE" "$PROJECT_DIR" >/dev/null 2>&1
log "  Image built"

log "[SETUP] Starting app container..."
docker run -d --name "$APP_CTR" --network "$NET" -p 8000:8000 \
  -e POSTGRES_USER=titanbay_user \
  -e POSTGRES_PASSWORD=titanbay_password \
  -e POSTGRES_SERVER="$DB_CTR" \
  -e POSTGRES_DB=titanbay_db_test \
  -e POSTGRES_PORT=5432 \
  "$IMAGE" >/dev/null 2>&1

wait_for_url "$BASE/health" "App" 30 || {
    log "FATAL: App failed to start. Container logs:"
    docker logs "$APP_CTR" 2>&1 | tee -a "$LOG_FILE"
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
# TEARDOWN
# ══════════════════════════════════════════════════════════════════════════════
log "================================================================"
log "  TEARDOWN"
log "================================================================"
docker rm -f "$APP_CTR" "$DB_CTR" >/dev/null 2>&1 || true
docker network rm "$NET" >/dev/null 2>&1 || true
log "  Containers and network removed"
log ""

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
log "================================================================"
log "  RESULTS:  $PASS passed  /  $FAIL failed  /  $TOTAL total"
log "================================================================"
log ""
log "Full log: $LOG_FILE"

[ "$FAIL" -gt 0 ] && exit 1
exit 0
