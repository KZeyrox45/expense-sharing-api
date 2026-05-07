# Base image - slim to reduce size
FROM python:3.12-slim

WORKDIR /app

# Copy uv binary from official image (no need to install uv into system)
# Use specific version to ensure reproducible
COPY --from=ghcr.io/astral-sh/uv:0.5.0 /uv /uvx /usr/local/bin/

# --- Layer caching strategy ---
# Copy dependency files BEFORE copying source code.
# If just change app code (don't add any new package),
# Docker will use this cached layer -> build faster.
COPY pyproject.toml uv.lock ./

# Install dependencies production only (don't install dev group)
# --frozen: use correct version in uv.lock, no update
# --no-dev: ignore [dependency-groups] dev
RUN uv sync --frozen --no-dev

# Copy whole source code
COPY . .

# Run with uvicorn
# Note: --reload is only used for dev, will be overridden in docker-compose
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]