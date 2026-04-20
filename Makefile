.PHONY: dev dev-down load serve test test-fast lint fmt type dump clean

dev:
	docker compose up -d postgres
	@until docker compose exec -T postgres pg_isready -U openlegis >/dev/null 2>&1; do sleep 1; done
	uv run alembic upgrade head

dev-down:
	docker compose down

load:
	uv run open-legis load fixtures/akn

serve:
	uv run uvicorn open_legis.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest -v

test-fast:
	uv run pytest -v -m "not slow"

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

type:
	uv run mypy src

dump:
	uv run open-legis dump --out dumps/latest.tar.gz

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build
