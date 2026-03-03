FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Disable venv inside container
ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy dependency files first (cache layer)
COPY pyproject.toml poetry.lock* ./

RUN poetry install --no-interaction --no-ansi

# Copy project
COPY . .

ENV PYTHONPATH=/app