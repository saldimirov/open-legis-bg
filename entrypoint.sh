#!/bin/sh
set -e
uv run alembic upgrade head
exec uv run uvicorn open_legis.api.app:create_app --factory --host 0.0.0.0 --port 8000
