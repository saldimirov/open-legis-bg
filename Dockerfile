FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install uv --no-cache-dir

WORKDIR /app

# Install dependencies first (better layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/
COPY alembic.ini ./
COPY entrypoint.sh ./
COPY fixtures/ ./fixtures/

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
