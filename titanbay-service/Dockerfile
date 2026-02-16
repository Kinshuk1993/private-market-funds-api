# ─────────────────────────────────────────────────────────────
# Titanbay Private Markets API  —  Production Dockerfile
#
# Multi-stage build:
#   1. builder  – installs Python deps into a virtual-env
#   2. runtime  – copies only the venv + app code (smaller image)
# ─────────────────────────────────────────────────────────────

# ── Stage 1: Builder ──
FROM python:3.14-slim AS builder

WORKDIR /build

# Install build dependencies only in the builder stage
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ──
FROM python:3.14-slim AS runtime

# libpq is needed at runtime for asyncpg / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /code
COPY . .

# Run as non-root for security
RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 8000

# Production: run with a single worker; scale horizontally via orchestrator.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
