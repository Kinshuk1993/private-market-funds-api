# Docker Setup (Recommended)

> **No local PostgreSQL required.** Both the app and the database run as Docker containers
> on a shared network. This is also easily portable to Kubernetes for testing.

[← Back to README](../README.md)

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS) or Docker Engine (Linux)

## 1. Create a Docker network

A user-defined bridge network lets the two containers resolve each other by name:

```bash
docker network create titanbay-net
```

## 2. Start PostgreSQL

```bash
docker run -d \
  --name titanbay-db \
  --network titanbay-net \
  -e POSTGRES_USER=titanbay_user \
  -e POSTGRES_PASSWORD=titanbay_password \
  -e POSTGRES_DB=titanbay_db \
  -p 5432:5432 \
  postgres:15-alpine
```

> `-p 5432:5432` is optional — it exposes Postgres to the host for debugging with tools like `psql` or pgAdmin. The app container connects via the Docker network, not the host port.

## 3. Build the app image

```bash
cd titanbay-service
docker build -t titanbay-service .
```

## 4. Run the app

```bash
docker run -d \
  --name titanbay-app \
  --network titanbay-net \
  -p 8000:8000 \
  -e POSTGRES_USER=titanbay_user \
  -e POSTGRES_PASSWORD=titanbay_password \
  -e POSTGRES_SERVER=titanbay-db \
  -e POSTGRES_DB=titanbay_db \
  -e POSTGRES_PORT=5432 \
  titanbay-service
```

> `POSTGRES_SERVER=titanbay-db` uses the container name — Docker DNS resolves it within the `titanbay-net` network.

The app will auto-create all database tables on first startup. Verify with:

```bash
docker logs titanbay-app
# Expected: "Database tables ready" followed by "Uvicorn running on http://0.0.0.0:8000"
```

## 5. Seed sample data (optional)

```bash
docker exec titanbay-app python -m app.seed
```

## 6. Verify

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"1.0.0","database":true,"circuit_breaker":{"state":"closed",...},"cache":{"enabled":true,...}}
```

## Teardown

```bash
docker rm -f titanbay-app titanbay-db   # stop & remove containers
docker network rm titanbay-net          # remove the network
```

To also remove the built image:

```bash
docker rmi titanbay-service
```

## One-Command Test (Docker)

Instead of running steps 1-6 manually, you can use the automated test script.
It starts PostgreSQL + the app in Docker, runs **51 tests** (happy-path + edge-cases + infrastructure)
against all 8 endpoints, captures output to `logs/docker_test.log`, and tears everything down:

```bash
bash scripts/test_docker.sh
```

> **Windows (Git Bash):** `"C:\Program Files\Git\bin\bash.exe" scripts/test_docker.sh`
>
> **Windows note:** The test script uses `MSYS_NO_PATHCONV=1` for `docker exec` commands
> to prevent Git Bash (MSYS2) from converting Unix container paths like `/code/logs/...`
> into Windows paths like `C:/Program Files/Git/code/logs/...`.

**No manual prompts — fully automatic.** All database credentials are passed via
Docker environment variables (`-e`). The script never calls `psql` or asks for any
passwords. It creates the containers, waits for them to be healthy, runs every test,
prints a pass/fail summary, and tears down. Zero interaction required.

> **Production safety:** The Docker test uses an isolated database named `titanbay_db_test`
> inside ephemeral containers — your production `titanbay_db` is never touched.
