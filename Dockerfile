# ── Stage 1: Builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages + CLI scripts from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app
COPY . .

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1
