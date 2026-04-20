# open-legis MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a read-only REST API + 5-act hand-curated sample corpus for Bulgarian legislation, with ELI-shaped URIs, Akoma Ntoso fixture format, FRBR Work/Expression point-in-time, Bulgarian full-text search, and bulk dumps — following the design in `docs/superpowers/specs/2026-04-20-open-legis-data-model-design.md`.

**Architecture:** AKN XML fixtures in git are the source of truth. A Python loader parses them into Postgres (6 normalised tables). A FastAPI read service resolves ELI URIs with content negotiation (JSON / AKN XML / Turtle RDF). No writes, no UI, no auth.

**Tech Stack:** Python 3.12 (uv), FastAPI, SQLAlchemy 2.x + Alembic, Postgres 16 (`bulgarian` snowball + `ltree`), lxml, rdflib, pydantic v2, pytest + testcontainers, ruff, mypy.

---

## File structure

Every file and its one-line responsibility. Locked in before task decomposition.

```
open-legis/
├── pyproject.toml                 uv-managed deps, ruff/mypy/pytest config
├── docker-compose.yml             postgres 16 for dev + tests
├── Makefile                       dev / load / serve / test / dump / lint
├── .gitignore                     python, editor, dump artifacts
├── .env.example                   DATABASE_URL template
├── README.md                      what this is + curl examples
├── LICENSE                        MIT (code)
├── DATA_LICENSE                   CC0 + ЗАПСП чл. 4, т. 1 preamble (data)
├── .github/workflows/ci.yaml      lint + mypy + pytest + XSD validation
├── .github/workflows/release.yaml release tarball + dump publication
├── fixtures/
│   └── akn/
│       ├── konstitutsiya/1991/krb/expressions/1991-07-13.bul.xml
│       ├── kodeks/1968/nk/expressions/2024-01-01.bul.xml
│       ├── zakon/1950/zzd/expressions/2021-06-01.bul.xml
│       ├── zakon/1950/zzd/expressions/2024-01-01.bul.xml
│       ├── zakon/2025/dv-67-25/expressions/2025-08-15.bul.xml
│       ├── naredba/2019/dv-61-19/expressions/2025-08-15.bul.xml
│       └── relations/
│           ├── amendments.yaml    cross-fixture amendment edges
│           └── references.yaml    cross-fixture citation edges
├── schemas/
│   └── akn/                       vendored AKN 3.0 XSD files
├── src/open_legis/
│   ├── __init__.py                version string only
│   ├── settings.py                env config (DATABASE_URL etc.)
│   ├── cli.py                     typer root: load / serve / dump / new-fixture
│   ├── model/
│   │   ├── __init__.py
│   │   ├── db.py                  engine, session factory, tx helpers
│   │   ├── schema.py              SQLAlchemy 2.x ORM models
│   │   └── alembic/
│   │       ├── env.py
│   │       ├── script.py.mako
│   │       └── versions/
│   │           ├── 0001_initial.py
│   │           └── 0002_bulgarian_fts_and_ltree.py
│   ├── loader/
│   │   ├── __init__.py
│   │   ├── uri.py                 ELI URI parse/build
│   │   ├── validators.py          XSD + semantic validation
│   │   ├── akn_parser.py          AKN XML → Work + Expression + Element rows
│   │   ├── relations.py           amendments.yaml / references.yaml loader
│   │   ├── scaffold.py            `open-legis new-fixture` skeleton generator
│   │   └── cli.py                 load subcommand implementation
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py                 FastAPI app factory (create_app)
│   │   ├── deps.py                session dependency
│   │   ├── negotiation.py         Accept header parsing → renderer choice
│   │   ├── schemas.py             pydantic response models
│   │   ├── routes_eli.py          /eli/... resolution
│   │   ├── routes_discovery.py    /works, /search, /amendments, /references, /expressions
│   │   ├── routes_aliases.py      /by-dv, /by-external (301)
│   │   ├── routes_dumps.py        /dumps/
│   │   ├── routes_meta.py         /health, /docs (swagger auto)
│   │   └── renderers/
│   │       ├── __init__.py
│   │       ├── json_render.py     work/expression/element → JSON
│   │       ├── akn_render.py      stored akn_xml passthrough
│   │       └── rdf_render.py      ELI Turtle via rdflib
│   ├── search/
│   │   ├── __init__.py
│   │   └── query.py               tsvector queries with bg snowball
│   └── dumps/
│       ├── __init__.py
│       └── build.py               deterministic tarball + SQL dump
├── tests/
│   ├── __init__.py
│   ├── conftest.py                testcontainers postgres + loaded db fixtures
│   ├── data/
│   │   ├── minimal_act.xml        tiny test AKN doc
│   │   └── invalid_act.xml        for negative validator tests
│   ├── golden/                    expected JSON/AKN/Turtle snapshots
│   ├── test_uri.py
│   ├── test_validators.py
│   ├── test_akn_parser.py
│   ├── test_relations_loader.py
│   ├── test_scaffold.py
│   ├── test_negotiation.py
│   ├── test_api_eli.py
│   ├── test_api_discovery.py
│   ├── test_api_aliases.py
│   ├── test_api_dumps.py
│   ├── test_search.py
│   ├── test_renderers_json.py
│   ├── test_renderers_akn.py
│   ├── test_renderers_rdf.py
│   └── test_goldens.py
└── docs/
    ├── data-model.md
    ├── uri-scheme.md
    ├── api.md
    ├── adding-an-act.md
    ├── takedown.md
    ├── superpowers/specs/2026-04-20-open-legis-data-model-design.md
    └── superpowers/plans/2026-04-20-open-legis-mvp.md
```

## Task index

- **M0 Scaffolding** — Tasks 1–7
- **M1 Schema + loader slice** — Tasks 8–17
- **M2 Fixtures + relations** — Tasks 18–24
- **M3 Read API (JSON)** — Tasks 25–33
- **M4 Content negotiation + search** — Tasks 34–40
- **M5 Dumps + launch polish** — Tasks 41–46

---

## M0 — Scaffolding

### Task 1: Create `.gitignore`, `README.md`, `LICENSE`, `DATA_LICENSE`

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `LICENSE`
- Create: `DATA_LICENSE`

- [ ] **Step 1: Write `.gitignore`**

```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.env
.pytest_cache/
.mypy_cache/
.ruff_cache/
dist/
build/
htmlcov/
.coverage
dumps/*.tar.gz
dumps/*.sql.gz
!dumps/.keep
.DS_Store
.idea/
.vscode/
```

- [ ] **Step 2: Write `README.md`**

```markdown
# open-legis

An open, machine-readable database of Bulgarian legislation.

MVP scope: 5 hand-curated acts, read-only REST API, ELI-shaped URIs,
Akoma Ntoso XML fixtures, Bulgarian full-text search.

## Quick start

    make dev       # start postgres
    make load      # load fixtures into the db
    make serve     # run the API on :8000

    curl http://localhost:8000/eli/bg/zakon/1950/zzd
    curl -H 'Accept: application/akn+xml' http://localhost:8000/eli/bg/zakon/1950/zzd/2024-01-01/bul

## Licensing

- **Code**: MIT (see LICENSE)
- **Data**: CC0, consistent with ЗАПСП чл. 4, т. 1 (see DATA_LICENSE)

## Design

See `docs/superpowers/specs/2026-04-20-open-legis-data-model-design.md`.
```

- [ ] **Step 3: Write `LICENSE` (MIT)**

```
MIT License

Copyright (c) 2026 open-legis contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Write `DATA_LICENSE`**

```
Data License — CC0 1.0 Universal

The statutory texts in this dataset are public domain in Bulgaria by
operation of ЗАПСП чл. 4, т. 1, which excludes "нормативни и индивидуални
актове на държавни органи за управление, както и официалните им преводи"
from copyright protection. To the extent that any curation or compilation
by the open-legis project might otherwise attract rights (copyright or
sui generis database rights under EU Directive 96/9/EC), those rights are
waived under the Creative Commons CC0 1.0 Universal Public Domain
Dedication.

Full CC0 text: https://creativecommons.org/publicdomain/zero/1.0/legalcode
```

- [ ] **Step 5: Commit**

```
git add .gitignore README.md LICENSE DATA_LICENSE
git commit -m "chore: add gitignore, readme, licenses"
```

---

### Task 2: Create `pyproject.toml`

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "open-legis"
version = "0.1.0"
description = "An open machine-readable database of Bulgarian legislation"
requires-python = ">=3.12"
license = { text = "MIT" }
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy>=2.0.35",
  "alembic>=1.13",
  "psycopg[binary]>=3.2",
  "pydantic>=2.9",
  "pydantic-settings>=2.5",
  "lxml>=5.3",
  "rdflib>=7.1",
  "typer>=0.12",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "httpx>=0.27",
  "testcontainers[postgres]>=4.8",
  "ruff>=0.7",
  "mypy>=1.13",
  "types-pyyaml",
  "lxml-stubs",
]

[project.scripts]
open-legis = "open_legis.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/open_legis"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "C4", "SIM", "RUF"]
ignore = ["E501"]  # handled by formatter

[tool.mypy]
python_version = "3.12"
strict = true
plugins = []

[[tool.mypy.overrides]]
module = ["testcontainers.*", "rdflib.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create source skeleton**

```
mkdir -p src/open_legis tests
touch src/open_legis/__init__.py tests/__init__.py
```

Write `src/open_legis/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Install deps**

Run: `uv sync --all-extras`
Expected: dependency tree resolves, `.venv/` populated.

- [ ] **Step 4: Verify tooling**

Run: `uv run ruff check . && uv run mypy src && uv run pytest -q`
Expected: ruff clean, mypy clean, pytest "no tests ran".

- [ ] **Step 5: Commit**

```
git add pyproject.toml src/ tests/ uv.lock
git commit -m "chore: pyproject.toml with deps and tooling"
```

---

### Task 3: Create `docker-compose.yml` + `.env.example`

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: openlegis
      POSTGRES_PASSWORD: openlegis
      POSTGRES_DB: openlegis
      POSTGRES_INITDB_ARGS: "--locale=bg_BG.UTF-8 --encoding=UTF8"
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U openlegis"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  postgres_data:
```

- [ ] **Step 2: Write `.env.example`**

```
DATABASE_URL=postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis
OPEN_LEGIS_FIXTURES_DIR=fixtures/akn
```

- [ ] **Step 3: Smoke-test the container**

Run: `docker compose up -d postgres && docker compose exec postgres psql -U openlegis -c 'SELECT version();' && docker compose down`
Expected: prints PostgreSQL 16.x.

- [ ] **Step 4: Commit**

```
git add docker-compose.yml .env.example
git commit -m "chore: docker-compose postgres + env template"
```

---

### Task 4: Create `Makefile`

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Write `Makefile`**

```make
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
```

- [ ] **Step 2: Commit**

```
git add Makefile
git commit -m "chore: Makefile for common dev tasks"
```

---

### Task 5: Create `src/open_legis/settings.py`

**Files:**
- Create: `src/open_legis/settings.py`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write failing test `tests/test_settings.py`**

```python
from open_legis.settings import Settings


def test_settings_reads_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@h:5432/d")
    s = Settings()
    assert s.database_url == "postgresql+psycopg://x:y@h:5432/d"


def test_settings_default_fixtures_dir():
    s = Settings(database_url="postgresql+psycopg://x:y@h:5432/d")
    assert str(s.fixtures_dir).endswith("fixtures/akn")
```

- [ ] **Step 2: Verify test fails**

Run: `uv run pytest tests/test_settings.py -v`
Expected: `ModuleNotFoundError: No module named 'open_legis.settings'`.

- [ ] **Step 3: Write `src/open_legis/settings.py`**

```python
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    fixtures_dir: Path = Field(
        default=Path("fixtures/akn"),
        alias="OPEN_LEGIS_FIXTURES_DIR",
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_settings.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```
git add src/open_legis/settings.py tests/test_settings.py
git commit -m "feat: Settings loaded from env / .env"
```

---

### Task 6: Create typer CLI entry `src/open_legis/cli.py`

**Files:**
- Create: `src/open_legis/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing test `tests/test_cli.py`**

```python
from typer.testing import CliRunner

from open_legis.cli import app


def test_cli_has_load_command():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "load" in result.output
    assert "dump" in result.output
    assert "new-fixture" in result.output
```

- [ ] **Step 2: Verify test fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/open_legis/cli.py`**

```python
import typer

app = typer.Typer(help="open-legis — tools for the Bulgarian legislation database")


@app.command()
def load(path: str = typer.Argument("fixtures/akn", help="Path to fixtures directory")) -> None:
    """Load fixtures into the database."""
    typer.echo(f"stub: would load {path}")


@app.command()
def dump(out: str = typer.Option("dumps/latest.tar.gz", help="Output tarball path")) -> None:
    """Build a deterministic snapshot tarball."""
    typer.echo(f"stub: would dump to {out}")


@app.command("new-fixture")
def new_fixture(
    type_: str = typer.Option(..., "--type"),
    slug: str = typer.Option(..., "--slug"),
    year: int = typer.Option(...),
    date: str = typer.Option(..., "--date"),
) -> None:
    """Scaffold a new AKN fixture skeleton."""
    typer.echo(f"stub: would scaffold {type_}/{year}/{slug} @ {date}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Verify installed script works**

Run: `uv run open-legis --help`
Expected: shows load / dump / new-fixture commands.

- [ ] **Step 6: Commit**

```
git add src/open_legis/cli.py tests/test_cli.py
git commit -m "feat: typer CLI skeleton with load/dump/new-fixture stubs"
```

---

### Task 7: CI workflow `.github/workflows/ci.yaml`

**Files:**
- Create: `.github/workflows/ci.yaml`

- [ ] **Step 1: Write workflow**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: openlegis
          POSTGRES_PASSWORD: openlegis
          POSTGRES_DB: openlegis
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U openlegis"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    env:
      DATABASE_URL: postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv sync --all-extras
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest -v
```

- [ ] **Step 2: Commit**

```
git add .github/workflows/ci.yaml
git commit -m "ci: lint, type-check, test on push/PR"
```

---

## M1 — Schema + loader slice

### Task 8: DB engine + session factory

**Files:**
- Create: `src/open_legis/model/__init__.py`
- Create: `src/open_legis/model/db.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `tests/conftest.py` with testcontainers Postgres**

```python
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        yield pg.get_connection_url()


@pytest.fixture
def engine(pg_url):
    eng = create_engine(pg_url, future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    Sess = sessionmaker(bind=engine, expire_on_commit=False)
    with Sess() as s:
        yield s
```

- [ ] **Step 2: Write failing test `tests/test_db.py`**

```python
from open_legis.model.db import make_engine


def test_make_engine_returns_working_engine(pg_url):
    eng = make_engine(pg_url)
    with eng.connect() as c:
        result = c.exec_driver_sql("SELECT 1").scalar()
        assert result == 1
    eng.dispose()
```

- [ ] **Step 3: Verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: import error (`open_legis.model` missing).

- [ ] **Step 4: Implement `src/open_legis/model/__init__.py`**

```python
```

(Empty module file.)

- [ ] **Step 5: Implement `src/open_legis/model/db.py`**

```python
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str) -> Engine:
    return create_engine(url, future=True, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def tx(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 6: Run test**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (first run will pull `postgres:16-alpine`, slow).

- [ ] **Step 7: Commit**

```
git add src/open_legis/model/ tests/conftest.py tests/test_db.py
git commit -m "feat: db engine + session factory + test fixture"
```

---

### Task 9: SQLAlchemy ORM models for all 6 tables

**Files:**
- Create: `src/open_legis/model/schema.py`
- Create: `tests/test_model_schema.py`

- [ ] **Step 1: Write failing test `tests/test_model_schema.py`**

```python
import datetime as dt

from sqlalchemy.orm import Session

from open_legis.model import schema as m


def test_work_and_expression_roundtrip(session: Session, engine):
    m.Base.metadata.create_all(engine)
    work = m.Work(
        eli_uri="/eli/bg/zakon/1950/zzd",
        act_type=m.ActType.ZAKON,
        title="Закон за задълженията и договорите",
        title_short="ЗЗД",
        number=None,
        adoption_date=dt.date(1950, 11, 22),
        dv_broy=275,
        dv_year=1950,
        dv_position=1,
        issuing_body="Народно събрание",
        status=m.ActStatus.IN_FORCE,
    )
    session.add(work)
    session.flush()

    expr = m.Expression(
        work_id=work.id,
        expression_date=dt.date(2024, 1, 1),
        language="bul",
        akn_xml="<akomaNtoso/>",
        source_file="fixtures/akn/zakon/1950/zzd/expressions/2024-01-01.bul.xml",
        is_latest=True,
    )
    session.add(expr)
    session.commit()

    refetched = session.query(m.Work).filter_by(eli_uri="/eli/bg/zakon/1950/zzd").one()
    assert refetched.title_short == "ЗЗД"
    assert len(refetched.expressions) == 1
    assert refetched.expressions[0].language == "bul"


def test_element_unique_constraint(session: Session, engine):
    m.Base.metadata.create_all(engine)
    work = m.Work(
        eli_uri="/eli/bg/zakon/2000/test",
        act_type=m.ActType.ZAKON,
        title="Test",
        dv_broy=1,
        dv_year=2000,
        dv_position=1,
        status=m.ActStatus.IN_FORCE,
    )
    session.add(work)
    session.flush()
    expr = m.Expression(
        work_id=work.id,
        expression_date=dt.date(2000, 1, 1),
        language="bul",
        akn_xml="<x/>",
        source_file="x",
        is_latest=True,
    )
    session.add(expr)
    session.flush()
    e1 = m.Element(
        expression_id=expr.id,
        e_id="art_1",
        parent_e_id=None,
        element_type=m.ElementType.ARTICLE,
        num="Чл. 1",
        heading="",
        text="x",
        sequence=0,
    )
    session.add(e1)
    session.commit()

    dup = m.Element(
        expression_id=expr.id,
        e_id="art_1",
        parent_e_id=None,
        element_type=m.ElementType.ARTICLE,
        num="Чл. 1",
        heading="",
        text="y",
        sequence=1,
    )
    session.add(dup)
    from sqlalchemy.exc import IntegrityError

    import pytest

    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: Verify fails**

Run: `uv run pytest tests/test_model_schema.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement `src/open_legis/model/schema.py`**

```python
import datetime as dt
import enum
import uuid
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ActType(str, enum.Enum):
    KONSTITUTSIYA = "konstitutsiya"
    KODEKS = "kodeks"
    ZAKON = "zakon"
    NAREDBA = "naredba"
    PRAVILNIK = "pravilnik"
    POSTANOVLENIE = "postanovlenie"
    UKAZ = "ukaz"
    RESHENIE_KS = "reshenie_ks"
    RESHENIE_NS = "reshenie_ns"


class ActStatus(str, enum.Enum):
    IN_FORCE = "in_force"
    REPEALED = "repealed"
    PARTIALLY_IN_FORCE = "partially_in_force"


class ElementType(str, enum.Enum):
    PART = "part"
    TITLE = "title"
    CHAPTER = "chapter"
    SECTION = "section"
    ARTICLE = "article"
    PARAGRAPH = "paragraph"
    POINT = "point"
    LETTER = "letter"
    HCONTAINER = "hcontainer"


class AmendmentOp(str, enum.Enum):
    INSERTION = "insertion"
    SUBSTITUTION = "substitution"
    REPEAL = "repeal"
    RENUMBERING = "renumbering"


class ReferenceType(str, enum.Enum):
    CITES = "cites"
    DEFINES = "defines"


class ExternalSource(str, enum.Enum):
    LEX_BG = "lex_bg"
    PARLIAMENT_BG = "parliament_bg"
    DV_PARLIAMENT_BG = "dv_parliament_bg"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Work(Base):
    __tablename__ = "work"
    __table_args__ = (UniqueConstraint("dv_broy", "dv_year", "dv_position"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    eli_uri: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    act_type: Mapped[ActType] = mapped_column(Enum(ActType, name="act_type"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_short: Mapped[Optional[str]] = mapped_column(Text)
    number: Mapped[Optional[str]] = mapped_column(Text)
    adoption_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    dv_broy: Mapped[int] = mapped_column(Integer, nullable=False)
    dv_year: Mapped[int] = mapped_column(Integer, nullable=False)
    dv_position: Mapped[int] = mapped_column(Integer, nullable=False)
    issuing_body: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ActStatus] = mapped_column(Enum(ActStatus, name="act_status"), nullable=False)

    expressions: Mapped[list["Expression"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )
    external_ids: Mapped[list["ExternalId"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )


class Expression(Base):
    __tablename__ = "expression"
    __table_args__ = (UniqueConstraint("work_id", "expression_date", "language"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    expression_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="bul")
    akn_xml: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    work: Mapped[Work] = relationship(back_populates="expressions")
    elements: Mapped[list["Element"]] = relationship(
        back_populates="expression", cascade="all, delete-orphan"
    )


class Element(Base):
    __tablename__ = "element"
    __table_args__ = (UniqueConstraint("expression_id", "e_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    expression_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expression.id", ondelete="CASCADE"), nullable=False
    )
    e_id: Mapped[str] = mapped_column(Text, nullable=False)
    parent_e_id: Mapped[Optional[str]] = mapped_column(Text)
    element_type: Mapped[ElementType] = mapped_column(
        Enum(ElementType, name="element_type"), nullable=False
    )
    num: Mapped[Optional[str]] = mapped_column(Text)
    heading: Mapped[Optional[str]] = mapped_column(Text)
    text: Mapped[Optional[str]] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    expression: Mapped[Expression] = relationship(back_populates="elements")


class Amendment(Base):
    __tablename__ = "amendment"

    id: Mapped[uuid.UUID] = _uuid_pk()
    amending_work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    target_work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    target_e_id: Mapped[Optional[str]] = mapped_column(Text)
    operation: Mapped[AmendmentOp] = mapped_column(Enum(AmendmentOp, name="amendment_op"), nullable=False)
    effective_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Reference(Base):
    __tablename__ = "reference"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_expression_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expression.id", ondelete="CASCADE"), nullable=False
    )
    source_e_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_work_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="SET NULL")
    )
    target_e_id: Mapped[Optional[str]] = mapped_column(Text)
    reference_type: Mapped[ReferenceType] = mapped_column(
        Enum(ReferenceType, name="reference_type"), nullable=False
    )


class ExternalId(Base):
    __tablename__ = "external_id"
    __table_args__ = (UniqueConstraint("work_id", "source"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[ExternalSource] = mapped_column(
        Enum(ExternalSource, name="external_source"), nullable=False
    )
    external_value: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)

    work: Mapped[Work] = relationship(back_populates="external_ids")
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_model_schema.py -v`
Expected: PASS for both tests.

- [ ] **Step 5: Commit**

```
git add src/open_legis/model/schema.py tests/test_model_schema.py
git commit -m "feat: SQLAlchemy ORM for work/expression/element/amendment/reference/external_id"
```

---

### Task 10: Alembic setup + initial migration

**Files:**
- Create: `alembic.ini`
- Create: `src/open_legis/model/alembic/env.py`
- Create: `src/open_legis/model/alembic/script.py.mako`
- Create: `src/open_legis/model/alembic/versions/0001_initial.py`
- Modify: `src/open_legis/model/db.py` (no changes — alembic reads schema via `Base.metadata`)

- [ ] **Step 1: Initialise alembic (manually, no `alembic init` to avoid stray files)**

Write `alembic.ini`:

```ini
[alembic]
script_location = src/open_legis/model/alembic
prepend_sys_path = .
file_template = %%(rev)s_%%(slug)s
sqlalchemy.url = postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 2: Write `src/open_legis/model/alembic/env.py`**

```python
from logging.config import fileConfig
from os import environ

from alembic import context
from sqlalchemy import engine_from_config, pool

from open_legis.model.schema import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

if env_url := environ.get("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", env_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Write `src/open_legis/model/alembic/script.py.mako`**

```
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Autogenerate initial revision**

Run:

```
docker compose up -d postgres
until docker compose exec -T postgres pg_isready -U openlegis; do sleep 1; done
uv run alembic revision --autogenerate -m "initial" --rev-id 0001
```

This writes `src/open_legis/model/alembic/versions/0001_initial.py`. Review it — it should `op.create_table(...)` for every ORM model.

- [ ] **Step 5: Run migration**

```
uv run alembic upgrade head
```

- [ ] **Step 6: Verify tables exist**

Run:

```
docker compose exec -T postgres psql -U openlegis -c '\dt'
```

Expected: shows `work`, `expression`, `element`, `amendment`, `reference`, `external_id`, `alembic_version`.

- [ ] **Step 7: Commit**

```
git add alembic.ini src/open_legis/model/alembic/
git commit -m "feat: alembic initial migration for all tables"
```

---

### Task 11: Second migration — `ltree`, `tsvector`, indexes

**Files:**
- Create: `src/open_legis/model/alembic/versions/0002_bulgarian_fts_and_ltree.py`

- [ ] **Step 1: Write the migration**

```python
"""bulgarian FTS and ltree

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-20

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")

    # add path ltree column
    op.execute("ALTER TABLE element ADD COLUMN path ltree")
    op.execute("CREATE INDEX element_path_gist_idx ON element USING GIST (path)")

    # generated tsvector for Bulgarian full-text
    op.execute(
        """
        ALTER TABLE element
        ADD COLUMN tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector(
                'bulgarian',
                coalesce(num, '') || ' ' || coalesce(heading, '') || ' ' || coalesce(text, '')
            )
        ) STORED
        """
    )
    op.execute("CREATE INDEX element_tsv_gin_idx ON element USING GIN (tsv)")

    # helpful lookup indexes
    op.execute("CREATE INDEX element_expr_parent_idx ON element (expression_id, parent_e_id)")
    op.execute("CREATE INDEX expression_work_date_idx ON expression (work_id, expression_date DESC)")
    op.execute("CREATE INDEX expression_is_latest_idx ON expression (work_id) WHERE is_latest")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS expression_is_latest_idx")
    op.execute("DROP INDEX IF EXISTS expression_work_date_idx")
    op.execute("DROP INDEX IF EXISTS element_expr_parent_idx")
    op.execute("DROP INDEX IF EXISTS element_tsv_gin_idx")
    op.execute("ALTER TABLE element DROP COLUMN tsv")
    op.execute("DROP INDEX IF EXISTS element_path_gist_idx")
    op.execute("ALTER TABLE element DROP COLUMN path")
    op.execute("DROP EXTENSION IF EXISTS ltree")
```

- [ ] **Step 2: Verify the `bulgarian` dictionary exists in Postgres 16**

Run:

```
docker compose exec -T postgres psql -U openlegis -c "SELECT cfgname FROM pg_ts_config WHERE cfgname = 'bulgarian';"
```

Expected: one row.

If missing: the base image lacks Bulgarian snowball. Fall back: `'simple'` config. Update this task's migration and flag this as a known deviation in `docs/data-model.md`.

- [ ] **Step 3: Apply migration**

Run: `uv run alembic upgrade head`
Expected: "Running upgrade 0001 -> 0002, bulgarian FTS and ltree".

- [ ] **Step 4: Verify**

```
docker compose exec -T postgres psql -U openlegis -c '\d+ element'
```

Expected: `path ltree` column, `tsv tsvector GENERATED ...`, indexes listed.

- [ ] **Step 5: Add schema ORM columns to match**

Modify `src/open_legis/model/schema.py` — in `class Element`, add:

```python
    # set by DB migration; not autogenerated by ORM
    path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

Leave `tsv` out of the ORM entirely (Postgres maintains it automatically via GENERATED).

- [ ] **Step 6: Commit**

```
git add src/open_legis/model/alembic/versions/0002_bulgarian_fts_and_ltree.py src/open_legis/model/schema.py
git commit -m "feat: ltree path + bulgarian tsvector + indexes"
```

---

### Task 12: ELI URI parse/build helpers

**Files:**
- Create: `src/open_legis/loader/__init__.py`
- Create: `src/open_legis/loader/uri.py`
- Create: `tests/test_uri.py`

- [ ] **Step 1: Write failing test `tests/test_uri.py`**

```python
import datetime as dt

import pytest

from open_legis.loader.uri import EliUri, parse_eli, build_eli


def test_parse_work_uri():
    u = parse_eli("/eli/bg/zakon/1950/zzd")
    assert u.act_type == "zakon"
    assert u.year == 1950
    assert u.slug == "zzd"
    assert u.expression_date is None
    assert u.language is None
    assert u.element_path is None


def test_parse_expression_uri():
    u = parse_eli("/eli/bg/zakon/1950/zzd/2024-01-01/bul")
    assert u.expression_date == dt.date(2024, 1, 1)
    assert u.language == "bul"


def test_parse_latest_expression():
    u = parse_eli("/eli/bg/zakon/1950/zzd/latest/bul")
    assert u.expression_date == "latest"
    assert u.language == "bul"


def test_parse_element_uri():
    u = parse_eli("/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45/para_1/point_3")
    assert u.element_path == "art_45/para_1/point_3"
    assert u.e_id() == "art_45__para_1__point_3"


def test_build_round_trip():
    u = EliUri(
        act_type="zakon", year=1950, slug="zzd",
        expression_date=dt.date(2024, 1, 1), language="bul",
        element_path="art_45/para_1",
    )
    assert build_eli(u) == "/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45/para_1"


@pytest.mark.parametrize("bad", [
    "/eli/bg",
    "/eli/bg/zakon",
    "/eli/xx/zakon/1950/zzd",           # wrong jurisdiction
    "/eli/bg/zakon/nineteen/zzd",        # non-numeric year
    "/eli/bg/zakon/1950/zzd/2024-13-40/bul",  # bad date
    "/eli/bg/zakon/1950/zzd/2024-01-01",      # missing language
])
def test_parse_rejects_bad_uris(bad):
    with pytest.raises(ValueError):
        parse_eli(bad)
```

- [ ] **Step 2: Verify it fails**

Run: `uv run pytest tests/test_uri.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement `src/open_legis/loader/__init__.py`**

```python
```

(Empty.)

- [ ] **Step 4: Implement `src/open_legis/loader/uri.py`**

```python
import datetime as dt
from dataclasses import dataclass
from typing import Literal, Optional, Union

_VALID_TYPES = {
    "konstitutsiya", "kodeks", "zakon", "naredba", "pravilnik",
    "postanovlenie", "ukaz", "reshenie-ks", "reshenie-ns",
}


@dataclass(frozen=True)
class EliUri:
    act_type: str
    year: int
    slug: str
    expression_date: Optional[Union[dt.date, Literal["latest"]]] = None
    language: Optional[str] = None
    element_path: Optional[str] = None

    def e_id(self) -> Optional[str]:
        if self.element_path is None:
            return None
        return self.element_path.replace("/", "__")


def parse_eli(uri: str) -> EliUri:
    if not uri.startswith("/eli/bg/"):
        raise ValueError(f"Not a Bulgarian ELI URI: {uri!r}")
    parts = uri[len("/eli/bg/"):].split("/")
    if len(parts) < 3:
        raise ValueError(f"Too short: {uri!r}")

    act_type, year_s, slug, *rest = parts
    if act_type not in _VALID_TYPES:
        raise ValueError(f"Unknown act_type {act_type!r}")
    try:
        year = int(year_s)
    except ValueError as e:
        raise ValueError(f"Non-numeric year {year_s!r}") from e
    if year < 1800 or year > 2200:
        raise ValueError(f"Year out of range: {year}")

    expression_date: Optional[Union[dt.date, Literal["latest"]]] = None
    language: Optional[str] = None
    element_path: Optional[str] = None

    if rest:
        if len(rest) < 2:
            raise ValueError(f"Expression URI needs date + language: {uri!r}")
        date_s, language, *elem = rest
        if date_s == "latest":
            expression_date = "latest"
        else:
            try:
                expression_date = dt.date.fromisoformat(date_s)
            except ValueError as e:
                raise ValueError(f"Bad date {date_s!r}") from e
        if not language.isascii() or len(language) != 3:
            raise ValueError(f"Bad language code {language!r}")
        if elem:
            element_path = "/".join(elem)

    return EliUri(
        act_type=act_type,
        year=year,
        slug=slug,
        expression_date=expression_date,
        language=language,
        element_path=element_path,
    )


def build_eli(u: EliUri) -> str:
    path = f"/eli/bg/{u.act_type}/{u.year}/{u.slug}"
    if u.expression_date is None:
        return path
    if u.expression_date == "latest":
        date_s = "latest"
    else:
        date_s = u.expression_date.isoformat()
    path += f"/{date_s}/{u.language}"
    if u.element_path:
        path += f"/{u.element_path}"
    return path
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_uri.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```
git add src/open_legis/loader/__init__.py src/open_legis/loader/uri.py tests/test_uri.py
git commit -m "feat: ELI URI parse/build for Bulgarian legislation"
```

---

### Task 13: Minimal test AKN fixture

**Files:**
- Create: `tests/data/minimal_act.xml`

- [ ] **Step 1: Write a tiny but valid AKN document**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <act contains="originalVersion">
    <meta>
      <identification source="#openlegis">
        <FRBRWork>
          <FRBRthis value="/akn/bg/act/2000/test/main"/>
          <FRBRuri value="/akn/bg/act/2000/test"/>
          <FRBRalias value="Test Act" name="eli" other="/eli/bg/zakon/2000/test"/>
          <FRBRdate date="2000-01-01" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRcountry value="bg"/>
          <FRBRnumber value="1"/>
        </FRBRWork>
        <FRBRExpression>
          <FRBRthis value="/akn/bg/act/2000/test/bul@2000-01-01/main"/>
          <FRBRuri value="/akn/bg/act/2000/test/bul@2000-01-01"/>
          <FRBRdate date="2000-01-01" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRlanguage language="bul"/>
        </FRBRExpression>
        <FRBRManifestation>
          <FRBRthis value="/akn/bg/act/2000/test/bul@2000-01-01/main.xml"/>
          <FRBRuri value="/akn/bg/act/2000/test/bul@2000-01-01.xml"/>
          <FRBRdate date="2000-01-01" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRformat value="application/akn+xml"/>
        </FRBRManifestation>
      </identification>
      <publication date="2000-01-01" name="Държавен вестник" number="1" showAs="ДВ"/>
      <references source="#openlegis">
        <TLCOrganization eId="parliament" href="/ontology/organization/bg/NarodnoSabranie" showAs="Народно събрание"/>
        <TLCPerson eId="openlegis" href="/ontology/person/openlegis" showAs="open-legis"/>
      </references>
    </meta>
    <preface><p>Test Act</p></preface>
    <body>
      <article eId="art_1">
        <num>Чл. 1</num>
        <heading>Тестова разпоредба</heading>
        <paragraph eId="art_1__para_1">
          <num>(1)</num>
          <content><p>Това е първа алинея.</p></content>
        </paragraph>
        <paragraph eId="art_1__para_2">
          <num>(2)</num>
          <content><p>Това е втора алинея.</p></content>
        </paragraph>
      </article>
      <article eId="art_2">
        <num>Чл. 2</num>
        <heading>Друга разпоредба</heading>
        <paragraph eId="art_2__para_1">
          <num>(1)</num>
          <content><p>Препраща към чл. 1.</p></content>
        </paragraph>
      </article>
    </body>
  </act>
</akomaNtoso>
```

- [ ] **Step 2: Commit**

```
git add tests/data/minimal_act.xml
git commit -m "test: minimal AKN test fixture"
```

---

### Task 14: AKN XML → row parser

**Files:**
- Create: `src/open_legis/loader/akn_parser.py`
- Create: `tests/test_akn_parser.py`

- [ ] **Step 1: Write failing test `tests/test_akn_parser.py`**

```python
from pathlib import Path

from open_legis.loader.akn_parser import parse_akn_file


def test_parse_minimal_act(tmp_path):
    parsed = parse_akn_file(Path("tests/data/minimal_act.xml"))
    assert parsed.work.eli_uri == "/eli/bg/zakon/2000/test"
    assert parsed.work.title == "Test Act"
    assert parsed.expression.language == "bul"
    assert parsed.expression.expression_date.isoformat() == "2000-01-01"
    assert len(parsed.elements) == 5  # 2 articles + 3 paragraphs
    e_ids = [e.e_id for e in parsed.elements]
    assert "art_1" in e_ids
    assert "art_1__para_1" in e_ids
    assert "art_2__para_1" in e_ids
    para = next(e for e in parsed.elements if e.e_id == "art_1__para_1")
    assert para.parent_e_id == "art_1"
    assert para.element_type == "paragraph"
    assert para.num == "(1)"
    assert "първа алинея" in para.text
```

- [ ] **Step 2: Verify fail**

Run: `uv run pytest tests/test_akn_parser.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement `src/open_legis/loader/akn_parser.py`**

```python
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lxml import etree

NS = {"akn": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}

_ELEMENT_TYPE_BY_LOCAL = {
    "part": "part",
    "title": "title",
    "chapter": "chapter",
    "section": "section",
    "article": "article",
    "paragraph": "paragraph",
    "point": "point",
    "subparagraph": "paragraph",
    "indent": "letter",
    "hcontainer": "hcontainer",
}


@dataclass
class ParsedWork:
    eli_uri: str
    title: str
    act_type: str
    dv_broy: int
    dv_year: int
    dv_position: int
    adoption_date: Optional[dt.date]
    issuing_body: Optional[str]


@dataclass
class ParsedExpression:
    expression_date: dt.date
    language: str
    source_file: str


@dataclass
class ParsedElement:
    e_id: str
    parent_e_id: Optional[str]
    element_type: str
    num: Optional[str]
    heading: Optional[str]
    text: Optional[str]
    sequence: int


@dataclass
class ParsedAkn:
    work: ParsedWork
    expression: ParsedExpression
    elements: list[ParsedElement] = field(default_factory=list)


def _text_of(el: etree._Element, local: str) -> Optional[str]:
    child = el.find(f"akn:{local}", NS)
    if child is None:
        return None
    return "".join(child.itertext()).strip() or None


def _attrib(el: etree._Element, name: str) -> Optional[str]:
    return el.get(name)


def _find_first(root: etree._Element, xpath: str) -> Optional[etree._Element]:
    results = root.xpath(xpath, namespaces=NS)
    return results[0] if results else None


def parse_akn_file(path: Path) -> ParsedAkn:
    tree = etree.parse(str(path))
    root = tree.getroot()

    # Work metadata
    eli_alias = _find_first(
        root,
        "//akn:identification/akn:FRBRWork/akn:FRBRalias[@name='eli']",
    )
    if eli_alias is None:
        raise ValueError(f"{path}: missing FRBRalias[name=eli]")
    eli_uri = eli_alias.get("other") or eli_alias.get("value")
    if not eli_uri:
        raise ValueError(f"{path}: FRBRalias has no value")

    title = _find_first(
        root, "//akn:identification/akn:FRBRWork/akn:FRBRalias[not(@name='eli')]"
    )
    title_s = (title.get("value") if title is not None else None) or _eli_to_title(eli_uri)

    pub = _find_first(root, "//akn:publication")
    if pub is None:
        raise ValueError(f"{path}: missing <publication>")
    dv_year = int(pub.get("date", "")[:4])
    dv_broy = int(pub.get("number") or "0")
    # position is stored via FRBRnumber if present, else 1
    frbr_num_el = _find_first(root, "//akn:FRBRWork/akn:FRBRnumber")
    dv_position = int((frbr_num_el.get("value") if frbr_num_el is not None else "1") or "1")

    gen_date_el = _find_first(
        root, "//akn:FRBRWork/akn:FRBRdate[@name='Generation']"
    )
    adoption_date = (
        dt.date.fromisoformat(gen_date_el.get("date"))
        if gen_date_el is not None and gen_date_el.get("date")
        else None
    )

    issuer_el = _find_first(
        root, "//akn:references/akn:TLCOrganization"
    )
    issuing_body = issuer_el.get("showAs") if issuer_el is not None else None

    act_type = _eli_act_type(eli_uri)

    work = ParsedWork(
        eli_uri=eli_uri,
        title=title_s,
        act_type=act_type,
        dv_broy=dv_broy,
        dv_year=dv_year,
        dv_position=dv_position,
        adoption_date=adoption_date,
        issuing_body=issuing_body,
    )

    # Expression metadata
    expr_date_el = _find_first(
        root, "//akn:FRBRExpression/akn:FRBRdate[@name='Generation']"
    )
    if expr_date_el is None or not expr_date_el.get("date"):
        raise ValueError(f"{path}: missing FRBRExpression/FRBRdate")
    expr_date = dt.date.fromisoformat(expr_date_el.get("date"))
    lang_el = _find_first(root, "//akn:FRBRExpression/akn:FRBRlanguage")
    language = lang_el.get("language") if lang_el is not None else "bul"

    expression = ParsedExpression(
        expression_date=expr_date,
        language=language,
        source_file=str(path),
    )

    body = _find_first(root, "//akn:body")
    if body is None:
        raise ValueError(f"{path}: missing <body>")

    elements: list[ParsedElement] = []
    _walk(body, parent_e_id=None, out=elements, counter=[0])

    return ParsedAkn(work=work, expression=expression, elements=elements)


def _walk(
    node: etree._Element,
    parent_e_id: Optional[str],
    out: list[ParsedElement],
    counter: list[int],
) -> None:
    for child in node:
        if not isinstance(child.tag, str):
            continue
        local = etree.QName(child.tag).localname
        if local not in _ELEMENT_TYPE_BY_LOCAL:
            _walk(child, parent_e_id, out, counter)
            continue
        e_id = child.get("eId")
        if not e_id:
            continue
        num = _text_of(child, "num")
        heading = _text_of(child, "heading")
        text = _collect_leaf_text(child)
        out.append(
            ParsedElement(
                e_id=e_id,
                parent_e_id=parent_e_id,
                element_type=_ELEMENT_TYPE_BY_LOCAL[local],
                num=num,
                heading=heading,
                text=text,
                sequence=counter[0],
            )
        )
        counter[0] += 1
        _walk(child, parent_e_id=e_id, out=out, counter=counter)


def _collect_leaf_text(el: etree._Element) -> Optional[str]:
    # concatenate text from <content>/<p> descendants, ignoring nested structural units
    parts: list[str] = []
    for content in el.xpath("./akn:content", namespaces=NS):
        parts.append("".join(content.itertext()).strip())
    text = "\n".join(p for p in parts if p)
    return text or None


def _eli_to_title(eli: str) -> str:
    # conservative fallback — final segment titlecased
    return eli.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()


def _eli_act_type(eli: str) -> str:
    # /eli/bg/<type>/<year>/<slug>
    parts = eli.strip("/").split("/")
    if len(parts) < 3:
        raise ValueError(f"Cannot derive act_type from {eli!r}")
    return parts[2].replace("-", "_")
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_akn_parser.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/open_legis/loader/akn_parser.py tests/test_akn_parser.py
git commit -m "feat: AKN XML → ParsedAkn (work/expression/elements)"
```

---

### Task 15: Semantic validators

**Files:**
- Create: `src/open_legis/loader/validators.py`
- Create: `tests/test_validators.py`
- Create: `tests/data/invalid_act.xml`

- [ ] **Step 1: Write `tests/data/invalid_act.xml` (missing FRBRalias[eli])**

Copy `tests/data/minimal_act.xml` and remove the `<FRBRalias ... name="eli" ... />` line.

- [ ] **Step 2: Write failing test `tests/test_validators.py`**

```python
from pathlib import Path

import pytest

from open_legis.loader.akn_parser import parse_akn_file
from open_legis.loader.validators import ValidationError, validate_parsed


def test_validate_accepts_minimal(tmp_path):
    parsed = parse_akn_file(Path("tests/data/minimal_act.xml"))
    validate_parsed(parsed, source_path=Path("tests/data/minimal_act.xml"))


def test_validate_rejects_eid_path_mismatch():
    parsed = parse_akn_file(Path("tests/data/minimal_act.xml"))
    parsed.elements[0].e_id = "wrong_id"
    parsed.elements[2].parent_e_id = "wrong_parent"
    with pytest.raises(ValidationError, match="parent_e_id"):
        validate_parsed(parsed, source_path=Path("tests/data/minimal_act.xml"))


def test_validate_rejects_eli_path_mismatch(tmp_path):
    parsed = parse_akn_file(Path("tests/data/minimal_act.xml"))
    src = tmp_path / "zakon" / "1950" / "zzd" / "expressions" / "2024-01-01.bul.xml"
    src.parent.mkdir(parents=True)
    src.write_text("x")  # not read, only its path matters
    with pytest.raises(ValidationError, match="ELI"):
        validate_parsed(parsed, source_path=src)
```

- [ ] **Step 3: Verify fail**

Run: `uv run pytest tests/test_validators.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `src/open_legis/loader/validators.py`**

```python
from pathlib import Path

from open_legis.loader.akn_parser import ParsedAkn
from open_legis.loader.uri import parse_eli


class ValidationError(Exception):
    pass


def validate_parsed(parsed: ParsedAkn, source_path: Path) -> None:
    _validate_eli_matches_path(parsed, source_path)
    _validate_unique_eids(parsed)
    _validate_parent_references_exist(parsed)


def _validate_eli_matches_path(parsed: ParsedAkn, source_path: Path) -> None:
    u = parse_eli(parsed.work.eli_uri)
    path_parts = source_path.resolve().parts
    # fixtures/akn/<type>/<year>/<slug>/expressions/<date>.<lang>.xml
    try:
        i = path_parts.index("akn")
    except ValueError:
        return  # ad-hoc test path, skip
    expected = path_parts[i + 1 : i + 4]
    if (expected[0], int(expected[1]), expected[2]) != (u.act_type, u.year, u.slug):
        raise ValidationError(
            f"ELI {parsed.work.eli_uri!r} does not match fixture path {source_path}"
        )


def _validate_unique_eids(parsed: ParsedAkn) -> None:
    seen: set[str] = set()
    for el in parsed.elements:
        if el.e_id in seen:
            raise ValidationError(f"Duplicate eId {el.e_id!r}")
        seen.add(el.e_id)


def _validate_parent_references_exist(parsed: ParsedAkn) -> None:
    all_ids = {el.e_id for el in parsed.elements}
    for el in parsed.elements:
        if el.parent_e_id and el.parent_e_id not in all_ids:
            raise ValidationError(
                f"Element {el.e_id!r} has parent_e_id {el.parent_e_id!r} "
                f"which does not exist"
            )
```

- [ ] **Step 5: Run test**

Run: `uv run pytest tests/test_validators.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```
git add src/open_legis/loader/validators.py tests/test_validators.py tests/data/invalid_act.xml
git commit -m "feat: semantic validators (eid uniqueness, parent refs, ELI/path match)"
```

---

### Task 16: Loader `load()` writes to DB

**Files:**
- Create: `src/open_legis/loader/cli.py`
- Modify: `src/open_legis/cli.py` (wire `load` command to the real implementation)
- Create: `tests/test_loader_integration.py`

- [ ] **Step 1: Write failing integration test `tests/test_loader_integration.py`**

```python
from pathlib import Path

import pytest
from sqlalchemy import select

from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine


@pytest.fixture
def fresh_db(pg_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    # path column + tsv are normally added by migration 0002 — add by hand for this test
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    yield eng
    m.Base.metadata.drop_all(eng)
    eng.dispose()


def test_load_minimal_fixture(fresh_db, tmp_path):
    # stage fixture in a fixtures/akn/... layout
    dest = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    src = Path("tests/data/minimal_act.xml").read_text()
    (dest / "2000-01-01.bul.xml").write_text(src)

    load_directory(tmp_path / "fixtures" / "akn", engine=fresh_db)

    with fresh_db.connect() as c:
        from sqlalchemy.orm import Session
        with Session(fresh_db) as s:
            works = s.scalars(select(m.Work)).all()
            assert len(works) == 1
            assert works[0].eli_uri == "/eli/bg/zakon/2000/test"
            exprs = s.scalars(select(m.Expression)).all()
            assert len(exprs) == 1
            assert exprs[0].is_latest is True
            elems = s.scalars(select(m.Element)).all()
            assert len(elems) == 5


def test_load_is_idempotent(fresh_db, tmp_path):
    dest = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    (dest / "2000-01-01.bul.xml").write_text(
        Path("tests/data/minimal_act.xml").read_text()
    )

    load_directory(tmp_path / "fixtures" / "akn", engine=fresh_db)
    load_directory(tmp_path / "fixtures" / "akn", engine=fresh_db)

    from sqlalchemy.orm import Session
    with Session(fresh_db) as s:
        works = s.scalars(select(m.Work)).all()
        assert len(works) == 1
        elems = s.scalars(select(m.Element)).all()
        assert len(elems) == 5
```

- [ ] **Step 2: Verify it fails**

Run: `uv run pytest tests/test_loader_integration.py -v`
Expected: ImportError for `open_legis.loader.cli.load_directory`.

- [ ] **Step 3: Implement `src/open_legis/loader/cli.py`**

```python
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from open_legis.loader.akn_parser import ParsedAkn, parse_akn_file
from open_legis.loader.validators import validate_parsed
from open_legis.model import schema as m


def load_directory(root: Path, engine: Engine) -> None:
    files = sorted(Path(root).rglob("*.bul.xml"))
    parsed_by_file = [(f, parse_akn_file(f)) for f in files]
    for f, p in parsed_by_file:
        validate_parsed(p, source_path=f)

    with Session(engine) as session:
        for f, p in parsed_by_file:
            _upsert(session, p)
        _recompute_is_latest(session)
        session.commit()


def _upsert(session: Session, p: ParsedAkn) -> None:
    work = session.scalars(
        select(m.Work).where(m.Work.eli_uri == p.work.eli_uri)
    ).one_or_none()
    if work is None:
        work = m.Work(
            eli_uri=p.work.eli_uri,
            act_type=m.ActType(p.work.act_type),
            title=p.work.title,
            dv_broy=p.work.dv_broy,
            dv_year=p.work.dv_year,
            dv_position=p.work.dv_position,
            adoption_date=p.work.adoption_date,
            issuing_body=p.work.issuing_body,
            status=m.ActStatus.IN_FORCE,
        )
        session.add(work)
        session.flush()
    else:
        work.title = p.work.title
        work.adoption_date = p.work.adoption_date
        work.issuing_body = p.work.issuing_body

    expr = session.scalars(
        select(m.Expression).where(
            m.Expression.work_id == work.id,
            m.Expression.expression_date == p.expression.expression_date,
            m.Expression.language == p.expression.language,
        )
    ).one_or_none()
    akn_xml = Path(p.expression.source_file).read_text()
    if expr is None:
        expr = m.Expression(
            work_id=work.id,
            expression_date=p.expression.expression_date,
            language=p.expression.language,
            akn_xml=akn_xml,
            source_file=p.expression.source_file,
            is_latest=False,
        )
        session.add(expr)
        session.flush()
    else:
        expr.akn_xml = akn_xml
        expr.source_file = p.expression.source_file

    session.query(m.Element).filter(m.Element.expression_id == expr.id).delete(
        synchronize_session=False
    )
    session.flush()

    for e in p.elements:
        session.add(
            m.Element(
                expression_id=expr.id,
                e_id=e.e_id,
                parent_e_id=e.parent_e_id,
                element_type=m.ElementType(e.element_type),
                num=e.num,
                heading=e.heading,
                text=e.text,
                sequence=e.sequence,
            )
        )
    session.flush()


def _recompute_is_latest(session: Session) -> None:
    session.execute(
        m.Expression.__table__.update().values(is_latest=False)
    )
    session.flush()
    # mark the newest expression per (work_id, language) as latest
    from sqlalchemy import func

    row_subq = (
        select(
            m.Expression.id,
            func.row_number()
            .over(
                partition_by=(m.Expression.work_id, m.Expression.language),
                order_by=m.Expression.expression_date.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    latest_ids = session.execute(
        select(row_subq.c.id).where(row_subq.c.rn == 1)
    ).scalars().all()
    if latest_ids:
        session.execute(
            m.Expression.__table__.update()
            .where(m.Expression.id.in_(latest_ids))
            .values(is_latest=True)
        )
```

- [ ] **Step 4: Wire into CLI — edit `src/open_legis/cli.py`**

Replace the stub `load` command body with:

```python
@app.command()
def load(path: str = typer.Argument("fixtures/akn", help="Path to fixtures directory")) -> None:
    """Load fixtures into the database."""
    from pathlib import Path

    from open_legis.loader.cli import load_directory
    from open_legis.model.db import make_engine
    from open_legis.settings import Settings

    settings = Settings()
    engine = make_engine(settings.database_url)
    load_directory(Path(path), engine=engine)
    typer.echo(f"loaded {path}")
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_loader_integration.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```
git add src/open_legis/loader/cli.py src/open_legis/cli.py tests/test_loader_integration.py
git commit -m "feat: loader that upserts works/expressions/elements, idempotent"
```

---

### Task 17: Populate `path` ltree column in loader

**Files:**
- Modify: `src/open_legis/loader/cli.py` (add `_populate_paths` + call it)
- Modify: `tests/test_loader_integration.py` (assert `path` is set)

- [ ] **Step 1: Extend the integration test**

Append to `tests/test_loader_integration.py`:

```python
def test_loader_populates_ltree_path(fresh_db, tmp_path):
    dest = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    (dest / "2000-01-01.bul.xml").write_text(
        Path("tests/data/minimal_act.xml").read_text()
    )

    load_directory(tmp_path / "fixtures" / "akn", engine=fresh_db)

    with fresh_db.connect() as c:
        rows = c.exec_driver_sql(
            "SELECT e_id, path::text FROM element ORDER BY sequence"
        ).fetchall()
        paths = dict(rows)
        assert paths["art_1"] == "art_1"
        assert paths["art_1__para_1"] == "art_1.art_1__para_1"
        assert paths["art_2__para_1"] == "art_2.art_2__para_1"
```

- [ ] **Step 2: Verify it fails**

Run: `uv run pytest tests/test_loader_integration.py::test_loader_populates_ltree_path -v`
Expected: assertion fails (path is NULL).

- [ ] **Step 3: Implement `_populate_paths` in `loader/cli.py`**

Add at bottom of file:

```python
def _populate_paths(session: Session) -> None:
    # set path = parent.path || e_id, iteratively, breadth-first
    session.execute(
        m.Element.__table__.update().values(path=None)
    )
    session.flush()
    from sqlalchemy import bindparam, text

    # Root elements (parent_e_id IS NULL): path = label(e_id)
    session.execute(
        text(
            "UPDATE element SET path = text2ltree(regexp_replace(e_id, '[^A-Za-z0-9_]', '_', 'g')) "
            "WHERE parent_e_id IS NULL"
        )
    )
    session.flush()

    # Then cascade children until no NULL rows remain
    while True:
        res = session.execute(
            text(
                """
                UPDATE element child
                SET path = parent.path
                  || text2ltree(regexp_replace(child.e_id, '[^A-Za-z0-9_]', '_', 'g'))
                FROM element parent
                WHERE child.parent_e_id = parent.e_id
                  AND child.expression_id = parent.expression_id
                  AND child.path IS NULL
                  AND parent.path IS NOT NULL
                """
            )
        )
        if res.rowcount == 0:
            break
    session.flush()
```

Then in `load_directory`, after the upsert loop and `_recompute_is_latest`, call:

```python
        _populate_paths(session)
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_loader_integration.py -v`
Expected: all three tests PASS.

- [ ] **Step 5: Commit**

```
git add src/open_legis/loader/cli.py tests/test_loader_integration.py
git commit -m "feat: loader populates ltree path column"
```

---

## M2 — Fixtures + relations

### Task 18: Scaffolder CLI `new-fixture`

**Files:**
- Create: `src/open_legis/loader/scaffold.py`
- Modify: `src/open_legis/cli.py` (wire `new-fixture` to real impl)
- Create: `tests/test_scaffold.py`

- [ ] **Step 1: Write failing test `tests/test_scaffold.py`**

```python
import datetime as dt
from pathlib import Path

from open_legis.loader.scaffold import scaffold_fixture


def test_scaffold_creates_valid_skeleton(tmp_path):
    out = scaffold_fixture(
        root=tmp_path,
        act_type="zakon",
        year=2025,
        slug="demo",
        expression_date=dt.date(2025, 5, 1),
        language="bul",
        title="Demo Закон",
        dv_broy=10,
        dv_year=2025,
    )
    assert out.exists()
    content = out.read_text()
    assert "/eli/bg/zakon/2025/demo" in content
    assert "2025-05-01" in content
    # parses via our parser
    from open_legis.loader.akn_parser import parse_akn_file

    parsed = parse_akn_file(out)
    assert parsed.work.eli_uri == "/eli/bg/zakon/2025/demo"
    assert parsed.expression.language == "bul"
```

- [ ] **Step 2: Verify fail**

Run: `uv run pytest tests/test_scaffold.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/open_legis/loader/scaffold.py`**

```python
import datetime as dt
from pathlib import Path

_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <act contains="originalVersion">
    <meta>
      <identification source="#openlegis">
        <FRBRWork>
          <FRBRthis value="/akn/bg/act/{year}/{slug}/main"/>
          <FRBRuri value="/akn/bg/act/{year}/{slug}"/>
          <FRBRalias value="{title}" name="short"/>
          <FRBRalias value="{title}" name="eli" other="/eli/bg/{act_type}/{year}/{slug}"/>
          <FRBRdate date="{expression_date}" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRcountry value="bg"/>
          <FRBRnumber value="1"/>
        </FRBRWork>
        <FRBRExpression>
          <FRBRthis value="/akn/bg/act/{year}/{slug}/{language}@{expression_date}/main"/>
          <FRBRuri value="/akn/bg/act/{year}/{slug}/{language}@{expression_date}"/>
          <FRBRdate date="{expression_date}" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRlanguage language="{language}"/>
        </FRBRExpression>
        <FRBRManifestation>
          <FRBRthis value="/akn/bg/act/{year}/{slug}/{language}@{expression_date}/main.xml"/>
          <FRBRuri value="/akn/bg/act/{year}/{slug}/{language}@{expression_date}.xml"/>
          <FRBRdate date="{expression_date}" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRformat value="application/akn+xml"/>
        </FRBRManifestation>
      </identification>
      <publication date="{expression_date}" name="Държавен вестник" number="{dv_broy}" showAs="ДВ"/>
      <references source="#openlegis">
        <TLCOrganization eId="parliament" href="/ontology/organization/bg/NarodnoSabranie" showAs="Народно събрание"/>
        <TLCPerson eId="openlegis" href="/ontology/person/openlegis" showAs="open-legis"/>
      </references>
    </meta>
    <preface><p>{title}</p></preface>
    <body>
      <!-- Author articles below; structure: part/title/chapter/section/article/paragraph/point/letter -->
      <article eId="art_1">
        <num>Чл. 1</num>
        <heading>TODO</heading>
        <paragraph eId="art_1__para_1">
          <num>(1)</num>
          <content><p>TODO текст на разпоредбата.</p></content>
        </paragraph>
      </article>
    </body>
  </act>
</akomaNtoso>
"""


def scaffold_fixture(
    root: Path,
    act_type: str,
    year: int,
    slug: str,
    expression_date: dt.date,
    language: str,
    title: str,
    dv_broy: int,
    dv_year: int,
) -> Path:
    out_dir = root / act_type / str(year) / slug / "expressions"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{expression_date.isoformat()}.{language}.xml"
    if out.exists():
        raise FileExistsError(out)
    out.write_text(
        _TEMPLATE.format(
            act_type=act_type,
            year=year,
            slug=slug,
            expression_date=expression_date.isoformat(),
            language=language,
            title=title,
            dv_broy=dv_broy,
            dv_year=dv_year,
        )
    )
    return out
```

- [ ] **Step 4: Wire into CLI — edit `src/open_legis/cli.py`**

Replace `new-fixture` stub:

```python
@app.command("new-fixture")
def new_fixture(
    type_: str = typer.Option(..., "--type"),
    slug: str = typer.Option(..., "--slug"),
    year: int = typer.Option(...),
    date: str = typer.Option(..., "--date"),
    language: str = typer.Option("bul", "--lang"),
    title: str = typer.Option(..., "--title"),
    dv_broy: int = typer.Option(..., "--dv-broy"),
    root: str = typer.Option("fixtures/akn", "--root"),
) -> None:
    """Scaffold a new AKN fixture skeleton."""
    import datetime as _dt
    from pathlib import Path

    from open_legis.loader.scaffold import scaffold_fixture

    out = scaffold_fixture(
        root=Path(root),
        act_type=type_,
        slug=slug,
        year=year,
        expression_date=_dt.date.fromisoformat(date),
        language=language,
        title=title,
        dv_broy=dv_broy,
        dv_year=_dt.date.fromisoformat(date).year,
    )
    typer.echo(f"created {out}")
```

- [ ] **Step 5: Run test**

Run: `uv run pytest tests/test_scaffold.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```
git add src/open_legis/loader/scaffold.py src/open_legis/cli.py tests/test_scaffold.py
git commit -m "feat: new-fixture scaffolder"
```

---

### Task 19: Author fixture — Конституция 1991 (KRB)

**Files:**
- Create: `fixtures/akn/konstitutsiya/1991/krb/expressions/1991-07-13.bul.xml`

Scope note: the Constitution has 169 articles. Authoring all of them in plain text is a human task of several hours. This task sets up the **skeleton** that loads, validates, and exposes a stable ELI; a small number of articles are authored so the API can be demoed. The remaining articles are marked `<heading>TODO</heading>` and `<p>TODO</p>` so they're obviously placeholders, and a follow-up ticket tracks completing them. Every article still has a unique `eId` so references work.

- [ ] **Step 1: Scaffold**

Run:

```
uv run open-legis new-fixture \
  --type konstitutsiya --slug krb --year 1991 \
  --date 1991-07-13 --lang bul \
  --title "Конституция на Република България" \
  --dv-broy 56
```

Expected: `fixtures/akn/konstitutsiya/1991/krb/expressions/1991-07-13.bul.xml` created.

- [ ] **Step 2: Fill in the body**

Edit the file. The `<body>` should contain: Preamble (as a preface block), 10 главы, 169 articles. For this fixture, author:

- The preamble text verbatim (from ДВ бр. 56/1991, publicly available).
- Articles 1–10 fully (complete text, proper `<paragraph>` subdivisions).
- Remaining articles as empty skeletons with real `eId`s (`art_11` … `art_169`) and `<heading>TODO — author article</heading>`; each article with a single `<paragraph eId="art_N__para_1"><content><p>TODO</p></content></paragraph>`.

Chapter grouping (use `<chapter eId="chapter_I">` etc.) per Constitution structure:

- I. Основни начала — art_1–art_24
- II. Основни права и задължения — art_25–art_61
- III. Народно събрание — art_62–art_86
- IV. Президент — art_92–art_104
- V. Министерски съвет — art_105–art_116
- VI. Съдебна власт — art_117–art_134
- VII. Местно самоуправление — art_135–art_146
- VIII. Конституционен съд — art_147–art_152
- IX. Изменение на Конституцията — art_153–art_163
- X. Герб, печат, знаме, химн, столица — art_164–art_169

Source for text: DV бр. 56/1991 PDF on `dv.parliament.bg`. Cross-check wording only — do not copy from lex.bg.

- [ ] **Step 3: Validate**

Run:

```
uv run python -c "
from pathlib import Path
from open_legis.loader.akn_parser import parse_akn_file
from open_legis.loader.validators import validate_parsed
p = Path('fixtures/akn/konstitutsiya/1991/krb/expressions/1991-07-13.bul.xml')
parsed = parse_akn_file(p)
validate_parsed(parsed, source_path=p)
print('ok, elements:', len(parsed.elements))
"
```

Expected: prints `ok, elements: N` with N ≥ 169.

- [ ] **Step 4: Commit**

```
git add fixtures/akn/konstitutsiya/1991/krb/
git commit -m "fixtures: Конституция 1991 (skeleton; arts 1-10 fully authored)"
```

---

### Task 20: Author fixture — Наказателен кодекс 1968 (NK), current consolidated

**Files:**
- Create: `fixtures/akn/kodeks/1968/nk/expressions/2024-01-01.bul.xml`

- [ ] **Step 1: Scaffold**

Run:

```
uv run open-legis new-fixture \
  --type kodeks --slug nk --year 1968 \
  --date 2024-01-01 --lang bul \
  --title "Наказателен кодекс" \
  --dv-broy 26
```

- [ ] **Step 2: Fill in body**

НК has two parts (Обща и Особена част), each with дялове → глави → раздели → членове. Author:

- Structure: full hierarchy (`<part>`, `<title>`, `<chapter>`, `<section>`, `<article>`) with proper `eId`s. Use AKN `<hcontainer name="dyal">` for "дял" since AKN lacks a direct map.
- Articles 1–10 fully (general principles — short, important).
- Every other article as TODO-skeleton (`<heading>TODO</heading>`, single TODO paragraph, real `eId`).
- Transitional provisions (ПЗР) as `<hcontainer name="transitional">`.

Commit message must cite the consolidation baseline: "НК as in force 2024-01-01, consolidating through ДВ бр. 84/2023".

- [ ] **Step 3: Validate (as in Task 19 Step 3 with the NK path)**

- [ ] **Step 4: Commit**

```
git add fixtures/akn/kodeks/1968/nk/
git commit -m "fixtures: НК 2024-01-01 (skeleton consolidated; arts 1-10 authored)

Consolidated through ДВ бр. 84/2023."
```

---

### Task 21: Author fixture — ЗЗД two expressions (1950 adoption, 2021-06-01 and 2024-01-01 consolidated)

**Files:**
- Create: `fixtures/akn/zakon/1950/zzd/expressions/2021-06-01.bul.xml`
- Create: `fixtures/akn/zakon/1950/zzd/expressions/2024-01-01.bul.xml`

- [ ] **Step 1: Scaffold both expressions**

```
uv run open-legis new-fixture \
  --type zakon --slug zzd --year 1950 \
  --date 2021-06-01 --lang bul \
  --title "Закон за задълженията и договорите" \
  --dv-broy 275

uv run open-legis new-fixture \
  --type zakon --slug zzd --year 1950 \
  --date 2024-01-01 --lang bul \
  --title "Закон за задълженията и договорите" \
  --dv-broy 275
```

- [ ] **Step 2: Fill in both bodies, with deliberate textual divergence**

ЗЗД has ~442 articles grouped into глави → раздели.

- Full structure with real `eId`s in both files.
- **Author at least three articles with actually different wording between 2021-06-01 and 2024-01-01** so point-in-time queries can prove they return different text. Good candidates: any article amended by ЗИД ДВ бр. 8/2024 (check the ДВ PDF). Document the difference in the commit message.
- All other articles TODO-skeleton.

- [ ] **Step 3: Validate both files**

- [ ] **Step 4: Commit**

```
git add fixtures/akn/zakon/1950/zzd/
git commit -m "fixtures: ЗЗД expressions 2021-06-01 and 2024-01-01

Three articles differ between the two expressions to exercise
point-in-time queries."
```

---

### Task 22: Author fixture — ЗИД енергетика 2025 and Наредба 15/2019

**Files:**
- Create: `fixtures/akn/zakon/2025/dv-67-25/expressions/2025-08-15.bul.xml`
- Create: `fixtures/akn/naredba/2019/dv-61-19/expressions/2025-08-15.bul.xml`

- [ ] **Step 1: Scaffold and author ЗИД**

```
uv run open-legis new-fixture \
  --type zakon --slug dv-67-25 --year 2025 \
  --date 2025-08-15 --lang bul \
  --title "Закон за изменение и допълнение на Закона за енергетиката" \
  --dv-broy 67
```

The ЗИД body is a sequence of numbered modification sections. Use `<hcontainer name="modification">` for each §. Each modification should identify: the target act (ELI reference), the affected eId, and the new wording. This is the fixture that exercises the amendment-edge model, so make at least 3 modification sections.

- [ ] **Step 2: Scaffold and author Наредба**

```
uv run open-legis new-fixture \
  --type naredba --slug dv-61-19 --year 2019 \
  --date 2025-08-15 --lang bul \
  --title "Наредба № 15 от 2019 г. за статута и професионалното развитие на педагогическите специалисти" \
  --dv-broy 61
```

Naredba issued by МОН. Author:
- Structure (глави → раздели → членове)
- Articles 1–5 fully
- Rest TODO
- Issuer: use `<TLCOrganization eId="mon" showAs="Министерство на образованието и науката"/>` and update `#parliament` references accordingly

- [ ] **Step 3: Validate both**

- [ ] **Step 4: Commit**

```
git add fixtures/akn/zakon/2025/ fixtures/akn/naredba/2019/
git commit -m "fixtures: ЗИД енергетика 2025 + Наредба 15/2019 (skeletons)"
```

---

### Task 23: `relations/amendments.yaml` + `references.yaml` + loader

**Files:**
- Create: `fixtures/akn/relations/amendments.yaml`
- Create: `fixtures/akn/relations/references.yaml`
- Create: `src/open_legis/loader/relations.py`
- Modify: `src/open_legis/loader/cli.py` (call relations loader)
- Create: `tests/test_relations_loader.py`

- [ ] **Step 1: Write `fixtures/akn/relations/amendments.yaml`**

```yaml
# Amendment edges across fixtures
# Each entry: an amending act modifying a target act's element
amendments:
  - amending: /eli/bg/zakon/2025/dv-67-25
    target:   /eli/bg/zakon/1950/zzd          # (illustrative; adjust to match your ЗИД)
    target_e_id: art_45
    operation: substitution
    effective_date: 2025-08-15
    notes: "§ 1 substitutes the first sentence of art. 45"
```

- [ ] **Step 2: Write `fixtures/akn/relations/references.yaml`**

```yaml
# Cross-references across fixtures
# Each entry: an element in a source expression that cites a target work/element
references:
  - source_eli:    /eli/bg/zakon/1950/zzd/2024-01-01/bul
    source_e_id:   art_2__para_1
    target_eli:    /eli/bg/zakon/1950/zzd
    target_e_id:   art_1
    type: cites
```

- [ ] **Step 3: Write failing test `tests/test_relations_loader.py`**

```python
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.loader.cli import load_directory
from open_legis.loader.relations import load_relations
from open_legis.model import schema as m
from open_legis.model.db import make_engine


def test_relations_create_amendment_and_reference_rows(pg_url, tmp_path, monkeypatch):
    # Two work fixtures required (source and target)
    for slug, eli in [("zzd", "/eli/bg/zakon/1950/zzd"), ("dv-67-25", "/eli/bg/zakon/2025/dv-67-25")]:
        year = "1950" if slug == "zzd" else "2025"
        dest = tmp_path / "fixtures" / "akn" / ("zakon") / year / slug / "expressions"
        dest.mkdir(parents=True)
        src = Path("tests/data/minimal_act.xml").read_text()
        src = src.replace("/eli/bg/zakon/2000/test", eli)
        src = src.replace("/akn/bg/act/2000/test", f"/akn/bg/act/{year}/{slug}")
        (dest / "2024-01-01.bul.xml").write_text(src)

    rel_dir = tmp_path / "fixtures" / "akn" / "relations"
    rel_dir.mkdir()
    (rel_dir / "amendments.yaml").write_text(
        "amendments:\n"
        "  - amending: /eli/bg/zakon/2025/dv-67-25\n"
        "    target:   /eli/bg/zakon/1950/zzd\n"
        "    target_e_id: art_1\n"
        "    operation: substitution\n"
        "    effective_date: 2025-08-15\n"
    )
    (rel_dir / "references.yaml").write_text(
        "references:\n"
        "  - source_eli:  /eli/bg/zakon/1950/zzd/2024-01-01/bul\n"
        "    source_e_id: art_1__para_1\n"
        "    target_eli:  /eli/bg/zakon/2025/dv-67-25\n"
        "    target_e_id: art_1\n"
        "    type: cites\n"
    )

    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )

    load_directory(tmp_path / "fixtures" / "akn", engine=eng)
    load_relations(rel_dir, engine=eng)

    with Session(eng) as s:
        amends = s.scalars(select(m.Amendment)).all()
        assert len(amends) == 1
        assert amends[0].operation == m.AmendmentOp.SUBSTITUTION
        refs = s.scalars(select(m.Reference)).all()
        assert len(refs) == 1
        assert refs[0].reference_type == m.ReferenceType.CITES
```

- [ ] **Step 4: Verify fail**

Run: `uv run pytest tests/test_relations_loader.py -v`
Expected: ImportError.

- [ ] **Step 5: Implement `src/open_legis/loader/relations.py`**

```python
import datetime as dt
from pathlib import Path

import yaml
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from open_legis.loader.uri import parse_eli
from open_legis.model import schema as m


def load_relations(root: Path, engine: Engine) -> None:
    with Session(engine) as session:
        session.query(m.Amendment).delete()
        session.query(m.Reference).delete()
        session.flush()

        amends_file = Path(root) / "amendments.yaml"
        if amends_file.exists():
            for entry in (yaml.safe_load(amends_file.read_text()) or {}).get("amendments", []):
                _insert_amendment(session, entry)

        refs_file = Path(root) / "references.yaml"
        if refs_file.exists():
            for entry in (yaml.safe_load(refs_file.read_text()) or {}).get("references", []):
                _insert_reference(session, entry)

        session.commit()


def _lookup_work(session: Session, eli: str) -> m.Work:
    w = session.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if w is None:
        raise ValueError(f"Work not found: {eli!r}")
    return w


def _lookup_expression(session: Session, eli: str) -> m.Expression:
    u = parse_eli(eli)
    w = _lookup_work(session, f"/eli/bg/{u.act_type}/{u.year}/{u.slug}")
    if isinstance(u.expression_date, str) or u.expression_date is None:
        expr = session.scalars(
            select(m.Expression)
            .where(m.Expression.work_id == w.id, m.Expression.is_latest.is_(True))
        ).one_or_none()
    else:
        expr = session.scalars(
            select(m.Expression).where(
                m.Expression.work_id == w.id,
                m.Expression.expression_date == u.expression_date,
                m.Expression.language == (u.language or "bul"),
            )
        ).one_or_none()
    if expr is None:
        raise ValueError(f"Expression not found: {eli!r}")
    return expr


def _insert_amendment(session: Session, entry: dict) -> None:
    amending = _lookup_work(session, entry["amending"])
    target = _lookup_work(session, entry["target"])
    session.add(
        m.Amendment(
            amending_work_id=amending.id,
            target_work_id=target.id,
            target_e_id=entry.get("target_e_id"),
            operation=m.AmendmentOp(entry["operation"]),
            effective_date=dt.date.fromisoformat(entry["effective_date"]),
            notes=entry.get("notes"),
        )
    )


def _insert_reference(session: Session, entry: dict) -> None:
    src_expr = _lookup_expression(session, entry["source_eli"])
    target_work = _lookup_work(session, entry["target_eli"])
    session.add(
        m.Reference(
            source_expression_id=src_expr.id,
            source_e_id=entry["source_e_id"],
            target_work_id=target_work.id,
            target_e_id=entry.get("target_e_id"),
            reference_type=m.ReferenceType(entry["type"]),
        )
    )
```

- [ ] **Step 6: Wire into `load_directory`** — modify `src/open_legis/loader/cli.py`:

At the end of `load_directory`, after `_populate_paths`, add:

```python
    relations_dir = Path(root) / "relations"
    if relations_dir.exists():
        from open_legis.loader.relations import load_relations

        load_relations(relations_dir, engine=engine)
```

- [ ] **Step 7: Run test**

Run: `uv run pytest tests/test_relations_loader.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```
git add fixtures/akn/relations/ src/open_legis/loader/relations.py src/open_legis/loader/cli.py tests/test_relations_loader.py
git commit -m "feat: amendment + reference edge loader (yaml)"
```

---

### Task 24: Golden snapshots for loaded fixtures

**Files:**
- Create: `tests/golden/works.json` (expected work list summary)
- Create: `tests/test_goldens.py`

- [ ] **Step 1: Write test `tests/test_goldens.py`**

```python
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine

GOLDEN = Path("tests/golden/works.json")


def test_works_golden(pg_url):
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    load_directory(Path("fixtures/akn"), engine=eng)
    with Session(eng) as s:
        rows = [
            {
                "eli_uri": w.eli_uri,
                "act_type": w.act_type.value,
                "title": w.title,
                "dv": [w.dv_broy, w.dv_year],
                "expressions": sorted(
                    e.expression_date.isoformat() for e in w.expressions
                ),
            }
            for w in sorted(
                s.scalars(select(m.Work)).all(), key=lambda x: x.eli_uri
            )
        ]
    expected = json.loads(GOLDEN.read_text())
    assert rows == expected, (
        "Work set drifted from golden. If intentional, update "
        "tests/golden/works.json."
    )
```

- [ ] **Step 2: Generate the golden manually on first run**

Run:

```
uv run python -c "
import json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine
from open_legis.settings import Settings
eng = make_engine(Settings().database_url)
m.Base.metadata.drop_all(eng)
# Apply migrations instead:
" && uv run alembic upgrade head && uv run open-legis load fixtures/akn
```

Then dump expected JSON:

```
uv run python -c "
import json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from open_legis.model import schema as m
from open_legis.model.db import make_engine
from open_legis.settings import Settings
eng = make_engine(Settings().database_url)
with Session(eng) as s:
    rows = [
        {
            'eli_uri': w.eli_uri,
            'act_type': w.act_type.value,
            'title': w.title,
            'dv': [w.dv_broy, w.dv_year],
            'expressions': sorted(e.expression_date.isoformat() for e in w.expressions),
        }
        for w in sorted(s.scalars(select(m.Work)).all(), key=lambda x: x.eli_uri)
    ]
print(json.dumps(rows, ensure_ascii=False, indent=2))
" > tests/golden/works.json
```

Review the generated file; confirm it lists all 5 works with correct expression counts (ЗЗД has 2).

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_goldens.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```
git add tests/golden/ tests/test_goldens.py
git commit -m "test: golden snapshot for loaded works"
```

---

## M3 — Read API (JSON)

### Task 25: FastAPI app factory + `/health`

**Files:**
- Create: `src/open_legis/api/__init__.py`
- Create: `src/open_legis/api/app.py`
- Create: `src/open_legis/api/deps.py`
- Create: `src/open_legis/api/routes_meta.py`
- Create: `tests/test_api_health.py`

- [ ] **Step 1: Write failing test `tests/test_api_health.py`**

```python
import pytest
from fastapi.testclient import TestClient

from open_legis.api.app import create_app


@pytest.fixture
def client(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    app = create_app()
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["title"] == "open-legis"
```

- [ ] **Step 2: Verify fail**

Run: `uv run pytest tests/test_api_health.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/open_legis/api/__init__.py`**

```python
```

- [ ] **Step 4: Implement `src/open_legis/api/deps.py`**

```python
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from open_legis.model.db import make_engine
from open_legis.settings import Settings


@lru_cache
def _engine() -> Engine:
    return make_engine(Settings().database_url)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with _session_factory()() as s:
        yield s


def reset_for_tests() -> None:
    _engine.cache_clear()
    _session_factory.cache_clear()
```

- [ ] **Step 5: Implement `src/open_legis/api/routes_meta.py`**

```python
from fastapi import APIRouter

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Implement `src/open_legis/api/app.py`**

```python
from fastapi import FastAPI

from open_legis.api.routes_meta import router as meta_router


def create_app() -> FastAPI:
    from open_legis.api.deps import reset_for_tests

    reset_for_tests()

    app = FastAPI(
        title="open-legis",
        description="An open machine-readable database of Bulgarian legislation.",
        version="0.1.0",
    )
    app.include_router(meta_router)
    return app
```

- [ ] **Step 7: Run test**

Run: `uv run pytest tests/test_api_health.py -v`
Expected: both tests PASS.

- [ ] **Step 8: Commit**

```
git add src/open_legis/api/ tests/test_api_health.py
git commit -m "feat: FastAPI app with /health and /openapi.json"
```

---

### Task 26: pydantic response schemas

**Files:**
- Create: `src/open_legis/api/schemas.py`
- Create: `tests/test_schemas.py`

- [ ] **Step 1: Write failing test `tests/test_schemas.py`**

```python
import datetime as dt

from open_legis.api.schemas import (
    DvRef,
    ElementOut,
    ExpressionOut,
    Links,
    ResourceOut,
    WorkOut,
)


def test_resource_serialises_minimal_work():
    out = ResourceOut(
        uri="/eli/bg/zakon/1950/zzd",
        work=WorkOut(
            uri="/eli/bg/zakon/1950/zzd",
            title="ЗЗД",
            title_short="ЗЗД",
            type="zakon",
            dv_ref=DvRef(broy=275, year=1950),
            external_ids={"lex_bg": "2121934337"},
        ),
        expression=None,
        element=None,
        links=Links(self="/eli/bg/zakon/1950/zzd"),
    )
    d = out.model_dump(mode="json", by_alias=True)
    assert d["work"]["dv_ref"]["broy"] == 275
    assert d["_links"]["self"] == "/eli/bg/zakon/1950/zzd"


def test_expression_and_element_serialisation():
    ex = ExpressionOut(date=dt.date(2024, 1, 1), lang="bul", is_latest=True)
    el = ElementOut(
        e_id="art_1",
        type="article",
        num="Чл. 1",
        heading=None,
        text="...",
        children=[ElementOut(e_id="art_1__para_1", type="paragraph", num="(1)")],
    )
    assert ex.model_dump(mode="json")["date"] == "2024-01-01"
    assert el.model_dump(mode="json")["children"][0]["e_id"] == "art_1__para_1"
```

- [ ] **Step 2: Verify fail**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/open_legis/api/schemas.py`**

```python
import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DvRef(BaseModel):
    broy: int
    year: int
    position: Optional[int] = None


class WorkOut(BaseModel):
    uri: str
    title: str
    title_short: Optional[str] = None
    type: str
    dv_ref: DvRef
    external_ids: dict[str, str] = Field(default_factory=dict)


class ExpressionOut(BaseModel):
    date: dt.date
    lang: str
    is_latest: bool = False


class ElementOut(BaseModel):
    e_id: str
    type: str
    num: Optional[str] = None
    heading: Optional[str] = None
    text: Optional[str] = None
    children: list["ElementOut"] = Field(default_factory=list)


class Links(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    self: str
    akn_xml: Optional[str] = None
    rdf: Optional[str] = None
    work: Optional[str] = None
    expression: Optional[str] = None
    previous_versions: list[str] = Field(default_factory=list)


class ResourceOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    uri: str
    work: WorkOut
    expression: Optional[ExpressionOut] = None
    element: Optional[ElementOut] = None
    links: Links = Field(alias="_links")


class WorkListItem(BaseModel):
    uri: str
    title: str
    type: str
    dv_ref: DvRef


class WorkList(BaseModel):
    items: list[WorkListItem]
    total: int
    page: int
    page_size: int


ElementOut.model_rebuild()
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/open_legis/api/schemas.py tests/test_schemas.py
git commit -m "feat: pydantic response schemas (WorkOut/ExpressionOut/ElementOut)"
```

---

### Task 27: JSON renderer

**Files:**
- Create: `src/open_legis/api/renderers/__init__.py`
- Create: `src/open_legis/api/renderers/json_render.py`
- Create: `tests/test_renderers_json.py`

- [ ] **Step 1: Write failing test `tests/test_renderers_json.py`**

```python
import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.api.renderers.json_render import render_work, render_expression, render_element
from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine


@pytest.fixture
def loaded(pg_url, tmp_path):
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    dest = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    (dest / "2000-01-01.bul.xml").write_text(
        Path("tests/data/minimal_act.xml").read_text()
    )
    load_directory(tmp_path / "fixtures" / "akn", engine=eng)
    yield eng
    eng.dispose()


def test_render_work(loaded):
    with Session(loaded) as s:
        work = s.scalars(select(m.Work)).one()
        out = render_work(work)
        d = out.model_dump(mode="json", by_alias=True)
        assert d["uri"] == "/eli/bg/zakon/2000/test"
        assert d["work"]["type"] == "zakon"
        assert d["_links"]["self"] == "/eli/bg/zakon/2000/test"


def test_render_expression_includes_toc(loaded):
    with Session(loaded) as s:
        expr = s.scalars(select(m.Expression)).one()
        out = render_expression(expr)
        d = out.model_dump(mode="json", by_alias=True)
        assert d["expression"]["date"] == "2000-01-01"
        assert d["element"]["children"][0]["e_id"] == "art_1"


def test_render_element_subtree(loaded):
    with Session(loaded) as s:
        expr = s.scalars(select(m.Expression)).one()
        art1 = s.scalars(
            select(m.Element).where(
                m.Element.expression_id == expr.id, m.Element.e_id == "art_1"
            )
        ).one()
        out = render_element(expr, art1)
        d = out.model_dump(mode="json", by_alias=True)
        assert d["element"]["e_id"] == "art_1"
        assert len(d["element"]["children"]) == 2  # two paragraphs
```

- [ ] **Step 2: Verify fail**

Run: `uv run pytest tests/test_renderers_json.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/open_legis/api/renderers/__init__.py`**

```python
```

- [ ] **Step 4: Implement `src/open_legis/api/renderers/json_render.py`**

```python
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from open_legis.api.schemas import (
    DvRef,
    ElementOut,
    ExpressionOut,
    Links,
    ResourceOut,
    WorkOut,
)
from open_legis.loader.uri import EliUri, build_eli
from open_legis.model import schema as m


def _work_eli(work: m.Work) -> EliUri:
    # derive type/year/slug from the stored eli_uri
    parts = work.eli_uri.strip("/").split("/")
    return EliUri(act_type=parts[2], year=int(parts[3]), slug=parts[4])


def _work_out(work: m.Work) -> WorkOut:
    return WorkOut(
        uri=work.eli_uri,
        title=work.title,
        title_short=work.title_short,
        type=work.act_type.value,
        dv_ref=DvRef(broy=work.dv_broy, year=work.dv_year, position=work.dv_position),
        external_ids={x.source.value: x.external_value for x in work.external_ids},
    )


def render_work(work: m.Work) -> ResourceOut:
    return ResourceOut(
        uri=work.eli_uri,
        work=_work_out(work),
        expression=None,
        element=None,
        links=Links(self=work.eli_uri, work=work.eli_uri),
    )


def render_expression(expr: m.Expression) -> ResourceOut:
    work = expr.work
    expr_uri = build_eli(
        EliUri(
            **_work_eli(work).__dict__
            | {"expression_date": expr.expression_date, "language": expr.language}
        )
    )
    session = object_session(expr)
    assert session is not None
    # build the full element tree as children of a synthetic root
    elements = session.scalars(
        select(m.Element)
        .where(m.Element.expression_id == expr.id)
        .order_by(m.Element.sequence)
    ).all()
    root_children = _build_children_tree(elements, parent_e_id=None)
    synthetic = ElementOut(e_id="", type="root", children=root_children)

    return ResourceOut(
        uri=expr_uri,
        work=_work_out(work),
        expression=ExpressionOut(
            date=expr.expression_date, lang=expr.language, is_latest=expr.is_latest
        ),
        element=synthetic,
        links=Links(
            self=expr_uri,
            work=work.eli_uri,
            akn_xml=expr_uri + "?format=akn",
            rdf=expr_uri + "?format=ttl",
        ),
    )


def render_element(expr: m.Expression, el: m.Element) -> ResourceOut:
    work = expr.work
    session = object_session(expr)
    assert session is not None
    elements = session.scalars(
        select(m.Element)
        .where(m.Element.expression_id == expr.id)
        .order_by(m.Element.sequence)
    ).all()
    children = _build_children_tree(elements, parent_e_id=el.e_id)
    element_out = ElementOut(
        e_id=el.e_id,
        type=el.element_type.value,
        num=el.num,
        heading=el.heading,
        text=el.text,
        children=children,
    )

    elem_path = el.e_id.replace("__", "/")
    uri = build_eli(
        EliUri(
            **_work_eli(work).__dict__
            | {
                "expression_date": expr.expression_date,
                "language": expr.language,
                "element_path": elem_path,
            }
        )
    )
    expr_uri = build_eli(
        EliUri(
            **_work_eli(work).__dict__
            | {"expression_date": expr.expression_date, "language": expr.language}
        )
    )
    return ResourceOut(
        uri=uri,
        work=_work_out(work),
        expression=ExpressionOut(
            date=expr.expression_date, lang=expr.language, is_latest=expr.is_latest
        ),
        element=element_out,
        links=Links(
            self=uri,
            work=work.eli_uri,
            expression=expr_uri,
            akn_xml=uri + "?format=akn",
            rdf=uri + "?format=ttl",
        ),
    )


def _build_children_tree(
    elements: list[m.Element], parent_e_id: str | None
) -> list[ElementOut]:
    direct = [e for e in elements if e.parent_e_id == parent_e_id]
    return [
        ElementOut(
            e_id=e.e_id,
            type=e.element_type.value,
            num=e.num,
            heading=e.heading,
            text=e.text,
            children=_build_children_tree(elements, parent_e_id=e.e_id),
        )
        for e in direct
    ]
```

- [ ] **Step 5: Run test**

Run: `uv run pytest tests/test_renderers_json.py -v`
Expected: all three PASS.

- [ ] **Step 6: Commit**

```
git add src/open_legis/api/renderers/ tests/test_renderers_json.py
git commit -m "feat: JSON renderers for work/expression/element"
```

---

### Task 28: `/eli/...` resolution routes

**Files:**
- Create: `src/open_legis/api/routes_eli.py`
- Modify: `src/open_legis/api/app.py` (include router)
- Create: `tests/test_api_eli.py`

- [ ] **Step 1: Write failing test `tests/test_api_eli.py`**

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from open_legis.api.app import create_app
from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine


@pytest.fixture
def client(pg_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    dest = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    (dest / "2000-01-01.bul.xml").write_text(
        Path("tests/data/minimal_act.xml").read_text()
    )
    load_directory(tmp_path / "fixtures" / "akn", engine=eng)
    app = create_app()
    yield TestClient(app)
    eng.dispose()


def test_get_work(client):
    r = client.get("/eli/bg/zakon/2000/test")
    assert r.status_code == 200
    d = r.json()
    assert d["uri"] == "/eli/bg/zakon/2000/test"
    assert d["work"]["type"] == "zakon"


def test_get_latest_expression(client):
    r = client.get("/eli/bg/zakon/2000/test/latest/bul")
    assert r.status_code == 200
    d = r.json()
    assert d["expression"]["date"] == "2000-01-01"
    assert d["expression"]["is_latest"] is True


def test_get_dated_expression(client):
    r = client.get("/eli/bg/zakon/2000/test/2000-01-01/bul")
    assert r.status_code == 200


def test_get_element(client):
    r = client.get("/eli/bg/zakon/2000/test/2000-01-01/bul/art_1")
    assert r.status_code == 200
    d = r.json()
    assert d["element"]["e_id"] == "art_1"
    assert len(d["element"]["children"]) == 2


def test_get_nested_element(client):
    r = client.get("/eli/bg/zakon/2000/test/2000-01-01/bul/art_1/para_1")
    assert r.status_code == 200
    d = r.json()
    assert d["element"]["e_id"] == "art_1__para_1"


def test_missing_work_is_404(client):
    r = client.get("/eli/bg/zakon/2000/nope")
    assert r.status_code == 404


def test_bad_eli_is_400(client):
    r = client.get("/eli/bg/zakon/abc/test")
    assert r.status_code in (400, 404)  # routing may 404 before handler runs
```

- [ ] **Step 2: Verify fail**

Run: `uv run pytest tests/test_api_eli.py -v`
Expected: 404s because the routes don't exist.

- [ ] **Step 3: Implement `src/open_legis/api/routes_eli.py`**

```python
import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.api.renderers.json_render import (
    render_element,
    render_expression,
    render_work,
)
from open_legis.api.schemas import ResourceOut
from open_legis.loader.uri import build_eli, EliUri, parse_eli
from open_legis.model import schema as m

router = APIRouter(tags=["eli"])


@router.get("/eli/bg/{act_type}/{year}/{slug}", response_model=ResourceOut)
def get_work(act_type: str, year: int, slug: str, s: Session = Depends(get_session)) -> ResourceOut:
    eli = build_eli(EliUri(act_type=act_type, year=year, slug=slug))
    try:
        parse_eli(eli)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    work = s.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work not found: {eli}")
    return render_work(work)


@router.get(
    "/eli/bg/{act_type}/{year}/{slug}/{date}/{lang}",
    response_model=ResourceOut,
)
def get_expression(
    act_type: str,
    year: int,
    slug: str,
    date: str,
    lang: str,
    s: Session = Depends(get_session),
) -> ResourceOut:
    expr = _resolve_expression(s, act_type, year, slug, date, lang)
    return render_expression(expr)


@router.get(
    "/eli/bg/{act_type}/{year}/{slug}/{date}/{lang}/{element_path:path}",
    response_model=ResourceOut,
)
def get_element(
    act_type: str,
    year: int,
    slug: str,
    date: str,
    lang: str,
    element_path: str,
    s: Session = Depends(get_session),
) -> ResourceOut:
    expr = _resolve_expression(s, act_type, year, slug, date, lang)
    e_id = element_path.replace("/", "__")
    el = s.scalars(
        select(m.Element).where(
            m.Element.expression_id == expr.id, m.Element.e_id == e_id
        )
    ).one_or_none()
    if el is None:
        raise HTTPException(status_code=404, detail=f"Element {e_id} not found")
    return render_element(expr, el)


def _resolve_expression(
    s: Session, act_type: str, year: int, slug: str, date: str, lang: str
) -> m.Expression:
    eli = f"/eli/bg/{act_type}/{year}/{slug}"
    work = s.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work not found: {eli}")

    if date == "latest":
        expr = s.scalars(
            select(m.Expression).where(
                m.Expression.work_id == work.id,
                m.Expression.language == lang,
                m.Expression.is_latest.is_(True),
            )
        ).one_or_none()
    else:
        try:
            expr_date = dt.date.fromisoformat(date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Bad date: {date}") from e
        # pick the greatest expression_date ≤ requested, for this language
        expr = s.scalars(
            select(m.Expression)
            .where(
                m.Expression.work_id == work.id,
                m.Expression.language == lang,
                m.Expression.expression_date <= expr_date,
            )
            .order_by(m.Expression.expression_date.desc())
            .limit(1)
        ).one_or_none()
    if expr is None:
        raise HTTPException(
            status_code=404,
            detail=f"No expression for {eli} @ {date}/{lang}",
        )
    return expr
```

- [ ] **Step 4: Wire into `src/open_legis/api/app.py`**

Add import and `app.include_router(eli_router)`:

```python
from open_legis.api.routes_eli import router as eli_router
# ... after include_router(meta_router):
    app.include_router(eli_router)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_api_eli.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```
git add src/open_legis/api/routes_eli.py src/open_legis/api/app.py tests/test_api_eli.py
git commit -m "feat: /eli/... resolution (work / expression / element)"
```

---

### Task 29: `/works` listing

**Files:**
- Create: `src/open_legis/api/routes_discovery.py`
- Modify: `src/open_legis/api/app.py`
- Create: `tests/test_api_works_list.py`

- [ ] **Step 1: Write failing test `tests/test_api_works_list.py`**

```python
# reuse client fixture logic from test_api_eli.py via a shared fixture in conftest.py
from fastapi.testclient import TestClient


def test_works_list_returns_loaded_fixtures(client: TestClient):
    r = client.get("/works")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] >= 1
    assert {"uri", "title", "type", "dv_ref"} <= set(d["items"][0].keys())


def test_works_filter_by_type(client: TestClient):
    r = client.get("/works?type=zakon")
    assert r.status_code == 200
    d = r.json()
    assert all(item["type"] == "zakon" for item in d["items"])


def test_works_pagination(client: TestClient):
    r = client.get("/works?page=1&page_size=1")
    assert r.status_code == 200
    d = r.json()
    assert d["page"] == 1
    assert d["page_size"] == 1
    assert len(d["items"]) <= 1
```

Also move the `client` fixture to `tests/conftest.py` so other tests can share it:

Append to `tests/conftest.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from open_legis.api.app import create_app
from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine


@pytest.fixture
def client(pg_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    dest = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    (dest / "2000-01-01.bul.xml").write_text(
        Path("tests/data/minimal_act.xml").read_text()
    )
    load_directory(tmp_path / "fixtures" / "akn", engine=eng)
    app = create_app()
    yield TestClient(app)
    eng.dispose()
```

Remove the duplicate `client` fixture from `tests/test_api_eli.py`.

- [ ] **Step 2: Verify fail**

Run: `uv run pytest tests/test_api_works_list.py -v`
Expected: 404 from FastAPI (route missing).

- [ ] **Step 3: Implement `src/open_legis/api/routes_discovery.py`**

```python
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.api.schemas import DvRef, WorkList, WorkListItem
from open_legis.model import schema as m

router = APIRouter(tags=["discovery"])


@router.get("/works", response_model=WorkList)
def list_works(
    type: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    s: Session = Depends(get_session),
) -> WorkList:
    q = select(m.Work)
    if type:
        q = q.where(m.Work.act_type == m.ActType(type))
    if year:
        q = q.where(func.extract("year", m.Work.adoption_date) == year)
    if status:
        q = q.where(m.Work.status == m.ActStatus(status))

    total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(m.Work.eli_uri).offset((page - 1) * page_size).limit(page_size)
    works = s.scalars(q).all()

    items = [
        WorkListItem(
            uri=w.eli_uri,
            title=w.title,
            type=w.act_type.value,
            dv_ref=DvRef(broy=w.dv_broy, year=w.dv_year, position=w.dv_position),
        )
        for w in works
    ]
    return WorkList(items=items, total=total, page=page, page_size=page_size)
```

- [ ] **Step 4: Wire in `app.py`**

```python
from open_legis.api.routes_discovery import router as discovery_router
# ...
    app.include_router(discovery_router)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_api_works_list.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```
git add src/open_legis/api/routes_discovery.py src/open_legis/api/app.py tests/conftest.py tests/test_api_works_list.py tests/test_api_eli.py
git commit -m "feat: GET /works with type/year/status filters + pagination"
```

---

### Task 30: Full-text `/search`

**Files:**
- Create: `src/open_legis/search/__init__.py`
- Create: `src/open_legis/search/query.py`
- Modify: `src/open_legis/api/routes_discovery.py` (add `/search`)
- Create: `tests/test_search.py`

- [ ] **Step 1: Write failing test `tests/test_search.py`**

```python
def test_search_finds_article_by_word(client):
    r = client.get("/search?q=алинея")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] >= 1
    first = d["items"][0]
    assert "e_id" in first
    assert "work_uri" in first
    assert "snippet" in first


def test_search_respects_type_filter(client):
    r = client.get("/search?q=алинея&type=zakon")
    assert r.status_code == 200
    d = r.json()
    assert all(item["type"] == "zakon" for item in d["items"])


def test_search_empty_query_rejected(client):
    r = client.get("/search?q=")
    assert r.status_code == 400
```

- [ ] **Step 2: Implement `src/open_legis/search/query.py`**

```python
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from open_legis.model import schema as m


@dataclass
class SearchHit:
    work_uri: str
    work_title: str
    work_type: str
    expression_date: str
    e_id: str
    num: Optional[str]
    snippet: str
    rank: float


def search(
    session: Session,
    q: str,
    act_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SearchHit], int]:
    if not q.strip():
        raise ValueError("empty query")

    ts_query = func.plainto_tsquery("bulgarian", q)
    # fall back to 'simple' config when 'bulgarian' unavailable
    stmt = (
        select(
            m.Work.eli_uri,
            m.Work.title,
            m.Work.act_type,
            m.Expression.expression_date,
            m.Element.e_id,
            m.Element.num,
            func.ts_headline(
                "bulgarian",
                func.coalesce(m.Element.text, ""),
                ts_query,
                "StartSel=«,StopSel=»,MaxWords=30,MinWords=5",
            ).label("snippet"),
            func.ts_rank(text("element.tsv"), ts_query).label("rank"),
        )
        .select_from(m.Element)
        .join(m.Expression, m.Expression.id == m.Element.expression_id)
        .join(m.Work, m.Work.id == m.Expression.work_id)
        .where(m.Expression.is_latest.is_(True))
        .where(text("element.tsv @@ plainto_tsquery('bulgarian', :q)").bindparams(q=q))
    )
    if act_type:
        stmt = stmt.where(m.Work.act_type == m.ActType(act_type))

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.scalar(total_stmt) or 0

    stmt = stmt.order_by(text("rank DESC")).offset(offset).limit(limit)
    rows = session.execute(stmt).all()

    hits = [
        SearchHit(
            work_uri=r.eli_uri,
            work_title=r.title,
            work_type=r.act_type.value,
            expression_date=r.expression_date.isoformat(),
            e_id=r.e_id,
            num=r.num,
            snippet=r.snippet or "",
            rank=float(r.rank or 0.0),
        )
        for r in rows
    ]
    return hits, total
```

Note: if the `bulgarian` config was unavailable during M1, replace `'bulgarian'` with `'simple'` in this file and add a comment explaining why.

- [ ] **Step 3: Extend `routes_discovery.py`**

Append:

```python
from pydantic import BaseModel

from open_legis.search.query import search as _search


class SearchItem(BaseModel):
    work_uri: str
    work_title: str
    type: str
    expression_date: str
    e_id: str
    num: str | None
    snippet: str
    rank: float


class SearchResponse(BaseModel):
    items: list[SearchItem]
    total: int
    page: int
    page_size: int


@router.get("/search", response_model=SearchResponse)
def search_route(
    q: str = Query(..., min_length=1),
    type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    s: Session = Depends(get_session),
) -> SearchResponse:
    hits, total = _search(
        s, q=q, act_type=type, limit=page_size, offset=(page - 1) * page_size
    )
    items = [
        SearchItem(
            work_uri=h.work_uri,
            work_title=h.work_title,
            type=h.work_type,
            expression_date=h.expression_date,
            e_id=h.e_id,
            num=h.num,
            snippet=h.snippet,
            rank=h.rank,
        )
        for h in hits
    ]
    return SearchResponse(items=items, total=total, page=page, page_size=page_size)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_search.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/open_legis/search/ src/open_legis/api/routes_discovery.py tests/test_search.py
git commit -m "feat: /search with tsvector full-text and snippets"
```

---

### Task 31: `/amendments` and `/references` edges

**Files:**
- Modify: `src/open_legis/api/routes_discovery.py`
- Create: `tests/test_api_edges.py`

- [ ] **Step 1: Write failing test `tests/test_api_edges.py`**

```python
def test_amendments_inbound(client):
    # after fixtures+relations load, ЗЗД should have 1 inbound amendment (from test fixture)
    # for the minimal-fixture conftest, this returns empty — still valid
    r = client.get("/works/test/amendments?direction=in")
    assert r.status_code == 200
    assert "items" in r.json()


def test_references_outbound(client):
    r = client.get("/works/test/references?direction=out")
    assert r.status_code == 200
    assert "items" in r.json()


def test_works_missing_returns_404(client):
    r = client.get("/works/nonexistent/amendments")
    assert r.status_code == 404
```

- [ ] **Step 2: Extend `routes_discovery.py`**

Append:

```python
from fastapi import HTTPException

from open_legis.model.schema import Amendment as Amend, Reference as Ref


class AmendmentItem(BaseModel):
    amending_uri: str
    target_uri: str
    target_e_id: str | None
    operation: str
    effective_date: str
    notes: str | None


class AmendmentList(BaseModel):
    items: list[AmendmentItem]


class ReferenceItem(BaseModel):
    source_expression_uri: str
    source_e_id: str
    target_uri: str | None
    target_e_id: str | None
    type: str


class ReferenceList(BaseModel):
    items: list[ReferenceItem]


def _work_by_slug(s: Session, slug: str) -> m.Work:
    work = s.scalars(select(m.Work).where(m.Work.eli_uri.endswith(f"/{slug}"))).first()
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work slug not found: {slug}")
    return work


@router.get("/works/{slug}/amendments", response_model=AmendmentList)
def amendments(
    slug: str,
    direction: str = Query("in", pattern="^(in|out)$"),
    s: Session = Depends(get_session),
) -> AmendmentList:
    work = _work_by_slug(s, slug)
    col = Amend.target_work_id if direction == "in" else Amend.amending_work_id
    rows = s.scalars(select(Amend).where(col == work.id)).all()
    amend_work_uri_by_id = {
        w.id: w.eli_uri for w in s.scalars(select(m.Work)).all()
    }
    return AmendmentList(
        items=[
            AmendmentItem(
                amending_uri=amend_work_uri_by_id[a.amending_work_id],
                target_uri=amend_work_uri_by_id[a.target_work_id],
                target_e_id=a.target_e_id,
                operation=a.operation.value,
                effective_date=a.effective_date.isoformat(),
                notes=a.notes,
            )
            for a in rows
        ]
    )


@router.get("/works/{slug}/references", response_model=ReferenceList)
def references(
    slug: str,
    direction: str = Query("in", pattern="^(in|out)$"),
    s: Session = Depends(get_session),
) -> ReferenceList:
    work = _work_by_slug(s, slug)
    if direction == "in":
        rows = s.scalars(select(Ref).where(Ref.target_work_id == work.id)).all()
    else:
        expr_ids = [
            e.id for e in s.scalars(select(m.Expression).where(m.Expression.work_id == work.id)).all()
        ]
        rows = (
            s.scalars(select(Ref).where(Ref.source_expression_id.in_(expr_ids))).all()
            if expr_ids else []
        )

    expr_uri_by_id = {}
    for e in s.scalars(select(m.Expression)).all():
        w = e.work
        expr_uri_by_id[e.id] = f"{w.eli_uri}/{e.expression_date.isoformat()}/{e.language}"
    work_uri_by_id = {w.id: w.eli_uri for w in s.scalars(select(m.Work)).all()}

    return ReferenceList(
        items=[
            ReferenceItem(
                source_expression_uri=expr_uri_by_id[r.source_expression_id],
                source_e_id=r.source_e_id,
                target_uri=work_uri_by_id.get(r.target_work_id) if r.target_work_id else None,
                target_e_id=r.target_e_id,
                type=r.reference_type.value,
            )
            for r in rows
        ]
    )
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_api_edges.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```
git add src/open_legis/api/routes_discovery.py tests/test_api_edges.py
git commit -m "feat: /works/{slug}/amendments + /references (in|out)"
```

---

### Task 32: `/works/{slug}/expressions` listing

**Files:**
- Modify: `src/open_legis/api/routes_discovery.py`
- Create: `tests/test_api_expressions_list.py`

- [ ] **Step 1: Write failing test `tests/test_api_expressions_list.py`**

```python
def test_expressions_listed_oldest_first(client):
    r = client.get("/works/test/expressions")
    assert r.status_code == 200
    d = r.json()
    assert len(d["items"]) >= 1
    for item in d["items"]:
        assert {"uri", "date", "language", "is_latest"} <= set(item.keys())
```

- [ ] **Step 2: Extend `routes_discovery.py`**

Append:

```python
class ExpressionItem(BaseModel):
    uri: str
    date: str
    language: str
    is_latest: bool


class ExpressionList(BaseModel):
    items: list[ExpressionItem]


@router.get("/works/{slug}/expressions", response_model=ExpressionList)
def expressions_list(slug: str, s: Session = Depends(get_session)) -> ExpressionList:
    work = _work_by_slug(s, slug)
    exprs = s.scalars(
        select(m.Expression)
        .where(m.Expression.work_id == work.id)
        .order_by(m.Expression.expression_date.asc())
    ).all()
    return ExpressionList(
        items=[
            ExpressionItem(
                uri=f"{work.eli_uri}/{e.expression_date.isoformat()}/{e.language}",
                date=e.expression_date.isoformat(),
                language=e.language,
                is_latest=e.is_latest,
            )
            for e in exprs
        ]
    )
```

- [ ] **Step 3: Run test**

Run: `uv run pytest tests/test_api_expressions_list.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```
git add src/open_legis/api/routes_discovery.py tests/test_api_expressions_list.py
git commit -m "feat: /works/{slug}/expressions listing"
```

---

### Task 33: Alias routes `/by-dv` and `/by-external`

**Files:**
- Create: `src/open_legis/api/routes_aliases.py`
- Modify: `src/open_legis/api/app.py`
- Create: `tests/test_api_aliases.py`

- [ ] **Step 1: Write failing test `tests/test_api_aliases.py`**

```python
def test_by_dv_redirects_to_eli(client):
    # fixture has DV broy=1 year=2000 position=1
    r = client.get("/by-dv/2000/1/1", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/eli/bg/zakon/2000/test"


def test_by_dv_unknown_is_404(client):
    r = client.get("/by-dv/1900/1/1", follow_redirects=False)
    assert r.status_code == 404
```

- [ ] **Step 2: Implement `src/open_legis/api/routes_aliases.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.model import schema as m

router = APIRouter(tags=["aliases"])


@router.get("/by-dv/{year}/{broy}/{position}")
def by_dv(
    year: int, broy: int, position: int, s: Session = Depends(get_session)
) -> RedirectResponse:
    work = s.scalars(
        select(m.Work).where(
            m.Work.dv_year == year,
            m.Work.dv_broy == broy,
            m.Work.dv_position == position,
        )
    ).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    return RedirectResponse(url=work.eli_uri, status_code=301)


@router.get("/by-external/{source}/{external_id}")
def by_external(
    source: str, external_id: str, s: Session = Depends(get_session)
) -> RedirectResponse:
    try:
        src_enum = m.ExternalSource(source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}") from e
    ext = s.scalars(
        select(m.ExternalId).where(
            m.ExternalId.source == src_enum,
            m.ExternalId.external_value == external_id,
        )
    ).one_or_none()
    if ext is None:
        raise HTTPException(status_code=404, detail="External ID not found")
    return RedirectResponse(url=ext.work.eli_uri, status_code=301)
```

- [ ] **Step 3: Wire in `app.py`**

```python
from open_legis.api.routes_aliases import router as aliases_router
# ...
    app.include_router(aliases_router)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_api_aliases.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/open_legis/api/routes_aliases.py src/open_legis/api/app.py tests/test_api_aliases.py
git commit -m "feat: 301 aliases /by-dv and /by-external"
```

---

## M4 — Content negotiation + AKN/RDF renderers

### Task 34: Accept-header content negotiation helper

**Files:**
- Create: `src/open_legis/api/negotiation.py`
- Create: `tests/test_negotiation.py`

- [ ] **Step 1: Write failing test `tests/test_negotiation.py`**

```python
import pytest

from open_legis.api.negotiation import Format, pick_format


@pytest.mark.parametrize("accept,override,expected", [
    ("application/json", None, Format.JSON),
    ("application/akn+xml", None, Format.AKN),
    ("text/turtle", None, Format.TURTLE),
    ("*/*", None, Format.JSON),
    ("", None, Format.JSON),
    ("application/akn+xml, application/json;q=0.9", None, Format.AKN),
    ("text/turtle;q=0.5, application/json;q=0.8", None, Format.JSON),
    # ?format= override takes precedence
    ("application/json", "akn", Format.AKN),
    ("application/json", "ttl", Format.TURTLE),
    ("application/json", "json", Format.JSON),
])
def test_pick_format(accept, override, expected):
    assert pick_format(accept=accept, override=override) == expected


def test_bad_override_rejected():
    with pytest.raises(ValueError):
        pick_format(accept="application/json", override="xml-doc")
```

- [ ] **Step 2: Verify fail**

Run: `uv run pytest tests/test_negotiation.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/open_legis/api/negotiation.py`**

```python
import enum
from typing import Optional


class Format(str, enum.Enum):
    JSON = "json"
    AKN = "akn"
    TURTLE = "ttl"


_MEDIA_TYPE_TO_FORMAT = {
    "application/json": Format.JSON,
    "application/akn+xml": Format.AKN,
    "text/turtle": Format.TURTLE,
}

_OVERRIDE_TO_FORMAT = {
    "json": Format.JSON,
    "akn": Format.AKN,
    "ttl": Format.TURTLE,
    "turtle": Format.TURTLE,
}


def pick_format(accept: str = "", override: Optional[str] = None) -> Format:
    if override is not None:
        if override not in _OVERRIDE_TO_FORMAT:
            raise ValueError(f"Unknown format override {override!r}")
        return _OVERRIDE_TO_FORMAT[override]

    if not accept or "*/*" in accept:
        return Format.JSON

    parsed: list[tuple[Format, float]] = []
    for token in accept.split(","):
        mt, _, params = token.strip().partition(";")
        mt = mt.strip().lower()
        q = 1.0
        for p in params.split(";"):
            if p.strip().startswith("q="):
                try:
                    q = float(p.split("=", 1)[1])
                except ValueError:
                    pass
        if mt in _MEDIA_TYPE_TO_FORMAT:
            parsed.append((_MEDIA_TYPE_TO_FORMAT[mt], q))

    if not parsed:
        return Format.JSON
    parsed.sort(key=lambda x: x[1], reverse=True)
    return parsed[0][0]


def media_type(fmt: Format) -> str:
    return {
        Format.JSON: "application/json",
        Format.AKN: "application/akn+xml",
        Format.TURTLE: "text/turtle",
    }[fmt]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_negotiation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/open_legis/api/negotiation.py tests/test_negotiation.py
git commit -m "feat: Accept-header + ?format= content negotiation"
```

---

### Task 35: AKN XML renderer (passthrough)

**Files:**
- Create: `src/open_legis/api/renderers/akn_render.py`
- Create: `tests/test_renderers_akn.py`

- [ ] **Step 1: Write failing test `tests/test_renderers_akn.py`**

```python
from lxml import etree

from open_legis.api.renderers.akn_render import render_expression_akn, render_element_akn
from open_legis.model import schema as m


def test_render_expression_akn_roundtrips_xml(monkeypatch):
    expr = m.Expression(akn_xml="<akomaNtoso><act/></akomaNtoso>")
    body = render_expression_akn(expr)
    assert body.startswith(b"<")
    root = etree.fromstring(body)
    assert etree.QName(root.tag).localname == "akomaNtoso"


def test_render_element_akn_returns_subtree():
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">'
        b"<act><body>"
        b'<article eId="art_1"><num>Чл. 1</num></article>'
        b'<article eId="art_2"><num>Чл. 2</num></article>'
        b"</body></act></akomaNtoso>"
    )
    expr = m.Expression(akn_xml=xml.decode("utf-8"))
    el = m.Element(
        e_id="art_1", element_type=m.ElementType.ARTICLE, num="Чл. 1", text=None, sequence=0
    )
    body = render_element_akn(expr, el)
    root = etree.fromstring(body)
    assert root.get("eId") == "art_1"
```

- [ ] **Step 2: Implement `src/open_legis/api/renderers/akn_render.py`**

```python
from lxml import etree

from open_legis.model import schema as m

NS = {"akn": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}


def render_expression_akn(expr: m.Expression) -> bytes:
    return expr.akn_xml.encode("utf-8")


def render_element_akn(expr: m.Expression, el: m.Element) -> bytes:
    root = etree.fromstring(expr.akn_xml.encode("utf-8"))
    found = root.xpath(f"//*[@eId='{el.e_id}']", namespaces=NS)
    if not found:
        raise ValueError(f"eId {el.e_id!r} not found in stored AKN")
    return etree.tostring(found[0], xml_declaration=False, encoding="utf-8")
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_renderers_akn.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```
git add src/open_legis/api/renderers/akn_render.py tests/test_renderers_akn.py
git commit -m "feat: AKN XML renderer (expression passthrough + element subtree)"
```

---

### Task 36: RDF/Turtle renderer (ELI ontology)

**Files:**
- Create: `src/open_legis/api/renderers/rdf_render.py`
- Create: `tests/test_renderers_rdf.py`

- [ ] **Step 1: Write failing test `tests/test_renderers_rdf.py`**

```python
import datetime as dt

from rdflib import Graph

from open_legis.api.renderers.rdf_render import render_work_ttl, render_expression_ttl
from open_legis.model import schema as m


def _work_fixture() -> m.Work:
    return m.Work(
        eli_uri="/eli/bg/zakon/2000/test",
        act_type=m.ActType.ZAKON,
        title="Test",
        title_short="T",
        dv_broy=1,
        dv_year=2000,
        dv_position=1,
        adoption_date=dt.date(2000, 1, 1),
        issuing_body="Народно събрание",
        status=m.ActStatus.IN_FORCE,
    )


def test_render_work_ttl_parses_and_has_eli_properties():
    ttl = render_work_ttl(_work_fixture(), base="https://data.open-legis.bg")
    g = Graph().parse(data=ttl, format="turtle")
    assert len(g) > 0
    # must mention the ELI ontology namespace
    assert "http://data.europa.eu/eli/ontology#" in ttl
    assert "/eli/bg/zakon/2000/test" in ttl


def test_render_expression_ttl_links_to_work():
    work = _work_fixture()
    expr = m.Expression(
        expression_date=dt.date(2000, 1, 1),
        language="bul",
        akn_xml="<x/>",
        source_file="x",
        is_latest=True,
    )
    expr.work = work
    ttl = render_expression_ttl(expr, base="https://data.open-legis.bg")
    g = Graph().parse(data=ttl, format="turtle")
    assert any("is_realized_by" in str(p) or "realized_by" in str(p) for _, p, _ in g)
```

- [ ] **Step 2: Implement `src/open_legis/api/renderers/rdf_render.py`**

```python
from rdflib import DCTERMS, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from open_legis.model import schema as m

ELI = Namespace("http://data.europa.eu/eli/ontology#")


def render_work_ttl(work: m.Work, base: str = "") -> str:
    g = _graph_with_prefixes()
    work_iri = URIRef(f"{base}{work.eli_uri}")

    g.add((work_iri, RDF.type, ELI.LegalResource))
    g.add((work_iri, ELI.id_local, Literal(work.eli_uri)))
    g.add((work_iri, ELI.type_document, Literal(work.act_type.value)))
    g.add((work_iri, DCTERMS.title, Literal(work.title, lang="bg")))
    if work.title_short:
        g.add((work_iri, ELI.title_short, Literal(work.title_short, lang="bg")))
    if work.adoption_date:
        g.add((work_iri, ELI.date_document, Literal(work.adoption_date, datatype=XSD.date)))
    g.add((work_iri, ELI.id_local, Literal(f"ДВ бр. {work.dv_broy}/{work.dv_year}")))
    if work.issuing_body:
        g.add((work_iri, ELI.passed_by, Literal(work.issuing_body, lang="bg")))
    g.add((work_iri, ELI.in_force, Literal(work.status == m.ActStatus.IN_FORCE)))
    return g.serialize(format="turtle")


def render_expression_ttl(expr: m.Expression, base: str = "") -> str:
    g = _graph_with_prefixes()
    work = expr.work
    work_iri = URIRef(f"{base}{work.eli_uri}")
    expr_iri = URIRef(
        f"{base}{work.eli_uri}/{expr.expression_date.isoformat()}/{expr.language}"
    )

    g.add((work_iri, RDF.type, ELI.LegalResource))
    g.add((work_iri, ELI.is_realized_by, expr_iri))

    g.add((expr_iri, RDF.type, ELI.LegalExpression))
    g.add((expr_iri, ELI.realizes, work_iri))
    g.add((expr_iri, ELI.language, Literal(expr.language)))
    g.add(
        (expr_iri, ELI.version_date, Literal(expr.expression_date, datatype=XSD.date))
    )
    g.add((expr_iri, DCTERMS.title, Literal(work.title, lang="bg")))
    return g.serialize(format="turtle")


def _graph_with_prefixes() -> Graph:
    g = Graph()
    g.bind("eli", ELI)
    g.bind("dcterms", DCTERMS)
    return g
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_renderers_rdf.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```
git add src/open_legis/api/renderers/rdf_render.py tests/test_renderers_rdf.py
git commit -m "feat: ELI-ontology Turtle renderer for Work + Expression"
```

---

### Task 37: Wire content negotiation into `/eli` routes

**Files:**
- Modify: `src/open_legis/api/routes_eli.py`
- Create: `tests/test_api_negotiation_integration.py`

- [ ] **Step 1: Write failing test `tests/test_api_negotiation_integration.py`**

```python
def test_akn_response_type(client):
    r = client.get(
        "/eli/bg/zakon/2000/test/2000-01-01/bul",
        headers={"Accept": "application/akn+xml"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/akn+xml")
    assert r.content.startswith(b"<")


def test_turtle_response_type(client):
    r = client.get(
        "/eli/bg/zakon/2000/test",
        headers={"Accept": "text/turtle"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/turtle")
    assert b"eli:" in r.content or b"<http://data.europa.eu/eli/ontology#" in r.content


def test_format_query_override_wins_over_accept(client):
    r = client.get(
        "/eli/bg/zakon/2000/test?format=ttl",
        headers={"Accept": "application/json"},
    )
    assert r.headers["content-type"].startswith("text/turtle")


def test_default_is_json(client):
    r = client.get("/eli/bg/zakon/2000/test")
    assert r.headers["content-type"].startswith("application/json")
```

- [ ] **Step 2: Update `routes_eli.py` to honour Accept + `?format=`**

Replace the three endpoints with versions that use `Response`:

```python
from fastapi import Header, Request, Response

from open_legis.api.negotiation import Format, media_type, pick_format
from open_legis.api.renderers.akn_render import render_element_akn, render_expression_akn
from open_legis.api.renderers.rdf_render import render_expression_ttl, render_work_ttl


@router.get("/eli/bg/{act_type}/{year}/{slug}")
def get_work(
    act_type: str,
    year: int,
    slug: str,
    request: Request,
    accept: str = Header(default=""),
    format: str | None = None,
    s: Session = Depends(get_session),
) -> Response:
    eli = build_eli(EliUri(act_type=act_type, year=year, slug=slug))
    work = s.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work not found: {eli}")
    try:
        fmt = pick_format(accept=accept, override=format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if fmt is Format.JSON:
        return Response(
            content=render_work(work).model_dump_json(by_alias=True),
            media_type="application/json",
        )
    if fmt is Format.TURTLE:
        base = str(request.base_url).rstrip("/")
        return Response(
            content=render_work_ttl(work, base=base),
            media_type="text/turtle; charset=utf-8",
        )
    # AKN for a work has no inherent body — return the latest expression's XML
    expr = s.scalars(
        select(m.Expression)
        .where(m.Expression.work_id == work.id, m.Expression.is_latest.is_(True))
    ).one_or_none()
    if expr is None:
        raise HTTPException(status_code=406, detail="No AKN expression available")
    return Response(content=render_expression_akn(expr), media_type=media_type(fmt))


@router.get("/eli/bg/{act_type}/{year}/{slug}/{date}/{lang}")
def get_expression(
    act_type: str,
    year: int,
    slug: str,
    date: str,
    lang: str,
    request: Request,
    accept: str = Header(default=""),
    format: str | None = None,
    s: Session = Depends(get_session),
) -> Response:
    expr = _resolve_expression(s, act_type, year, slug, date, lang)
    try:
        fmt = pick_format(accept=accept, override=format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if fmt is Format.JSON:
        return Response(
            content=render_expression(expr).model_dump_json(by_alias=True),
            media_type="application/json",
        )
    if fmt is Format.TURTLE:
        base = str(request.base_url).rstrip("/")
        return Response(
            content=render_expression_ttl(expr, base=base),
            media_type="text/turtle; charset=utf-8",
        )
    return Response(content=render_expression_akn(expr), media_type=media_type(fmt))


@router.get("/eli/bg/{act_type}/{year}/{slug}/{date}/{lang}/{element_path:path}")
def get_element(
    act_type: str,
    year: int,
    slug: str,
    date: str,
    lang: str,
    element_path: str,
    request: Request,
    accept: str = Header(default=""),
    format: str | None = None,
    s: Session = Depends(get_session),
) -> Response:
    expr = _resolve_expression(s, act_type, year, slug, date, lang)
    e_id = element_path.replace("/", "__")
    el = s.scalars(
        select(m.Element).where(
            m.Element.expression_id == expr.id, m.Element.e_id == e_id
        )
    ).one_or_none()
    if el is None:
        raise HTTPException(status_code=404, detail=f"Element {e_id} not found")

    try:
        fmt = pick_format(accept=accept, override=format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if fmt is Format.JSON:
        return Response(
            content=render_element(expr, el).model_dump_json(by_alias=True),
            media_type="application/json",
        )
    if fmt is Format.TURTLE:
        # element-level RDF reuses expression graph for MVP
        base = str(request.base_url).rstrip("/")
        return Response(
            content=render_expression_ttl(expr, base=base),
            media_type="text/turtle; charset=utf-8",
        )
    return Response(content=render_element_akn(expr, el), media_type=media_type(fmt))
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_api_negotiation_integration.py tests/test_api_eli.py -v`
Expected: all PASS (both sets).

- [ ] **Step 4: Commit**

```
git add src/open_legis/api/routes_eli.py tests/test_api_negotiation_integration.py
git commit -m "feat: content negotiation (JSON/AKN/Turtle) on /eli routes"
```

---

### Task 38: Caching headers + CORS

**Files:**
- Modify: `src/open_legis/api/app.py`
- Modify: `src/open_legis/api/routes_eli.py`
- Create: `tests/test_api_cache_and_cors.py`

- [ ] **Step 1: Write failing test `tests/test_api_cache_and_cors.py`**

```python
def test_cache_control_on_resource(client):
    r = client.get("/eli/bg/zakon/2000/test")
    assert r.status_code == 200
    assert "max-age" in r.headers.get("cache-control", "")


def test_cors_allows_any_origin(client):
    r = client.get("/eli/bg/zakon/2000/test", headers={"Origin": "https://example.com"})
    assert r.headers.get("access-control-allow-origin") == "*"
```

- [ ] **Step 2: Add CORS middleware in `app.py`**

```python
from fastapi.middleware.cors import CORSMiddleware
# ...
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )
```

- [ ] **Step 3: Add cache-control header on each `/eli` response**

In `routes_eli.py`, after each `Response(...)`, set:

```python
    response.headers["Cache-Control"] = "public, max-age=86400"
```

…or more cleanly, wrap every return in a helper:

```python
def _with_cache(response: Response) -> Response:
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response
```

and apply to each return.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_api_cache_and_cors.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/open_legis/api/app.py src/open_legis/api/routes_eli.py tests/test_api_cache_and_cors.py
git commit -m "feat: CORS wildcard + Cache-Control on /eli resources"
```

---

### Task 39: Golden snapshots for JSON, AKN, Turtle per fixture

**Files:**
- Create: `tests/golden/zzd_2024_art1.json`
- Create: `tests/golden/zzd_2024_art1.akn.xml`
- Create: `tests/golden/zzd_2024_art1.ttl`
- Create: `tests/test_goldens_per_format.py`

- [ ] **Step 1: Write `tests/test_goldens_per_format.py`**

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# reuse the real-fixtures client (separate from the minimal one in conftest)

GOLDEN = Path("tests/golden")


@pytest.fixture
def real_client(pg_url, monkeypatch):
    from open_legis.api.app import create_app
    from open_legis.loader.cli import load_directory
    from open_legis.model import schema as m
    from open_legis.model.db import make_engine

    monkeypatch.setenv("DATABASE_URL", pg_url)
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    load_directory(Path("fixtures/akn"), engine=eng)
    yield TestClient(create_app())
    eng.dispose()


def _check_or_write(path: Path, actual: bytes) -> None:
    if not path.exists():
        path.write_bytes(actual)
        pytest.fail(f"Created new golden {path}; re-run to verify")
    expected = path.read_bytes()
    assert actual == expected, f"Golden drift at {path}. Re-create if intentional."


def test_zzd_2024_art1_json(real_client):
    r = real_client.get("/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_1")
    assert r.status_code == 200
    _check_or_write(GOLDEN / "zzd_2024_art1.json", r.content)


def test_zzd_2024_art1_akn(real_client):
    r = real_client.get(
        "/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_1",
        headers={"Accept": "application/akn+xml"},
    )
    assert r.status_code == 200
    _check_or_write(GOLDEN / "zzd_2024_art1.akn.xml", r.content)


def test_zzd_work_ttl(real_client):
    r = real_client.get(
        "/eli/bg/zakon/1950/zzd",
        headers={"Accept": "text/turtle"},
    )
    assert r.status_code == 200
    _check_or_write(GOLDEN / "zzd_2024_art1.ttl", r.content)
```

- [ ] **Step 2: Run once to generate goldens**

Run: `uv run pytest tests/test_goldens_per_format.py -v`
Expected: three tests FAIL with "Created new golden … re-run to verify".

- [ ] **Step 3: Inspect the generated goldens**

Open each file. Sanity-check:
- JSON has correct URI, element, text
- AKN starts with `<article eId="art_1"`
- Turtle has `eli:` and `/eli/bg/zakon/1950/zzd`

- [ ] **Step 4: Re-run to lock them in**

Run: `uv run pytest tests/test_goldens_per_format.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add tests/golden/ tests/test_goldens_per_format.py
git commit -m "test: per-format golden snapshots for ЗЗД art_1"
```

---

### Task 40: Point-in-time proof test

**Files:**
- Create: `tests/test_point_in_time.py`

- [ ] **Step 1: Write the proof test**

```python
def test_zzd_art_differs_between_2021_and_2024(real_client):
    # Requires that at least one article was authored with different
    # wording in the two expressions (Task 21 Step 2 commits to this).
    r21 = real_client.get("/eli/bg/zakon/1950/zzd/2021-06-01/bul/art_45")
    r24 = real_client.get("/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45")
    assert r21.status_code == 200
    assert r24.status_code == 200
    t21 = r21.json()["element"]["text"] or ""
    t24 = r24.json()["element"]["text"] or ""
    assert t21 != t24, (
        "Point-in-time test failed: ЗЗД art_45 text is identical between "
        "2021-06-01 and 2024-01-01 expressions. Update Task 21 fixtures to "
        "introduce a real divergence."
    )
```

The test depends on the `real_client` fixture from Task 39.

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/test_point_in_time.py -v`
Expected: PASS (if ЗЗД was authored with a real divergence at `art_45`). If not, update the fixture and re-run.

- [ ] **Step 3: Commit**

```
git add tests/test_point_in_time.py
git commit -m "test: point-in-time divergence proof on ЗЗД art_45"
```

---

## M5 — Dumps + launch polish

### Task 41: Deterministic dump builder

**Files:**
- Create: `src/open_legis/dumps/__init__.py`
- Create: `src/open_legis/dumps/build.py`
- Modify: `src/open_legis/cli.py` (wire `dump` command)
- Create: `tests/test_dumps.py`

- [ ] **Step 1: Write failing test `tests/test_dumps.py`**

```python
import hashlib
import tarfile
from pathlib import Path

import pytest


@pytest.fixture
def built_tarball(real_client, tmp_path, pg_url, monkeypatch):
    from open_legis.dumps.build import build_tarball
    from open_legis.model.db import make_engine

    monkeypatch.setenv("DATABASE_URL", pg_url)
    eng = make_engine(pg_url)
    out = tmp_path / "snapshot.tar.gz"
    build_tarball(
        engine=eng,
        fixtures_dir=Path("fixtures/akn"),
        out_path=out,
    )
    return out


def test_tarball_contains_akn_and_json(built_tarball):
    with tarfile.open(built_tarball, "r:gz") as tf:
        names = tf.getnames()
    assert any(n.endswith(".bul.xml") for n in names)
    assert any(n.endswith("works.json") for n in names)


def test_tarball_is_deterministic(tmp_path, pg_url, monkeypatch):
    from open_legis.dumps.build import build_tarball
    from open_legis.loader.cli import load_directory
    from open_legis.model import schema as m
    from open_legis.model.db import make_engine

    monkeypatch.setenv("DATABASE_URL", pg_url)
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    load_directory(Path("fixtures/akn"), engine=eng)

    out1 = tmp_path / "a.tar.gz"
    out2 = tmp_path / "b.tar.gz"
    build_tarball(engine=eng, fixtures_dir=Path("fixtures/akn"), out_path=out1)
    build_tarball(engine=eng, fixtures_dir=Path("fixtures/akn"), out_path=out2)

    assert hashlib.sha256(out1.read_bytes()).hexdigest() == hashlib.sha256(
        out2.read_bytes()
    ).hexdigest()
```

- [ ] **Step 2: Implement `src/open_legis/dumps/__init__.py`**

```python
```

- [ ] **Step 3: Implement `src/open_legis/dumps/build.py`**

```python
import gzip
import io
import json
import tarfile
from pathlib import Path
from typing import IO

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from open_legis.model import schema as m

# fixed epoch for deterministic tar mtimes
EPOCH = 1577836800  # 2020-01-01 00:00:00 UTC


def build_tarball(engine: Engine, fixtures_dir: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Build the gzip stream manually for reproducibility: no mtime in gz header.
    raw_buf = io.BytesIO()
    with tarfile.open(fileobj=raw_buf, mode="w") as tf:
        _add_fixtures(tf, fixtures_dir)
        _add_db_snapshot(tf, engine)

    raw_bytes = raw_buf.getvalue()
    with open(out_path, "wb") as fh:
        gz = gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0)
        try:
            gz.write(raw_bytes)
        finally:
            gz.close()


def _add_file(tf: tarfile.TarFile, arcname: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mtime = EPOCH
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o644
    tf.addfile(info, io.BytesIO(data))


def _add_fixtures(tf: tarfile.TarFile, fixtures_dir: Path) -> None:
    for f in sorted(fixtures_dir.rglob("*")):
        if f.is_dir():
            continue
        arcname = "fixtures/" + str(f.relative_to(fixtures_dir.parent)).replace("\\", "/")
        _add_file(tf, arcname, f.read_bytes())


def _add_db_snapshot(tf: tarfile.TarFile, engine: Engine) -> None:
    with Session(engine) as s:
        works = sorted(s.scalars(select(m.Work)).all(), key=lambda w: w.eli_uri)
        payload = {
            "works": [
                {
                    "uri": w.eli_uri,
                    "type": w.act_type.value,
                    "title": w.title,
                    "title_short": w.title_short,
                    "dv": {"broy": w.dv_broy, "year": w.dv_year, "position": w.dv_position},
                    "adoption_date": w.adoption_date.isoformat() if w.adoption_date else None,
                    "status": w.status.value,
                    "expressions": sorted(
                        [
                            {
                                "date": e.expression_date.isoformat(),
                                "language": e.language,
                                "is_latest": e.is_latest,
                                "source_file": e.source_file,
                            }
                            for e in w.expressions
                        ],
                        key=lambda x: (x["date"], x["language"]),
                    ),
                    "external_ids": sorted(
                        [{"source": x.source.value, "value": x.external_value} for x in w.external_ids],
                        key=lambda x: x["source"],
                    ),
                }
                for w in works
            ]
        }
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    _add_file(tf, "data/works.json", body)
```

- [ ] **Step 4: Wire into CLI — edit `src/open_legis/cli.py`**

Replace `dump` stub:

```python
@app.command()
def dump(
    out: str = typer.Option("dumps/latest.tar.gz", help="Output tarball path"),
    fixtures: str = typer.Option("fixtures/akn", help="Fixtures root"),
) -> None:
    """Build a deterministic snapshot tarball."""
    from pathlib import Path

    from open_legis.dumps.build import build_tarball
    from open_legis.model.db import make_engine
    from open_legis.settings import Settings

    engine = make_engine(Settings().database_url)
    build_tarball(engine=engine, fixtures_dir=Path(fixtures), out_path=Path(out))
    typer.echo(f"wrote {out}")
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_dumps.py -v`
Expected: both PASS.

- [ ] **Step 6: Create `dumps/.keep`** so the dir is tracked

```
mkdir -p dumps && touch dumps/.keep
```

- [ ] **Step 7: Commit**

```
git add src/open_legis/dumps/ src/open_legis/cli.py tests/test_dumps.py dumps/.keep
git commit -m "feat: deterministic dump tarball (fixtures + works.json)"
```

---

### Task 42: SQL dump (`pg_dump`-based)

**Files:**
- Modify: `src/open_legis/dumps/build.py` — add `build_sql_dump`
- Modify: `src/open_legis/cli.py` — add `--sql` option or separate subcommand
- Create: `tests/test_sql_dump.py`

- [ ] **Step 1: Write failing test `tests/test_sql_dump.py`**

```python
import subprocess
from pathlib import Path


def test_sql_dump_runs_and_writes_gzipped_file(tmp_path, pg_url, monkeypatch):
    import gzip

    from open_legis.dumps.build import build_sql_dump
    from open_legis.loader.cli import load_directory
    from open_legis.model import schema as m
    from open_legis.model.db import make_engine

    monkeypatch.setenv("DATABASE_URL", pg_url)
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    load_directory(Path("fixtures/akn"), engine=eng)

    out = tmp_path / "dump.sql.gz"
    build_sql_dump(database_url=pg_url, out_path=out)
    assert out.exists()
    body = gzip.decompress(out.read_bytes())
    assert b"CREATE TABLE" in body
    assert b"work" in body.lower()
```

- [ ] **Step 2: Implement `build_sql_dump` in `src/open_legis/dumps/build.py`**

Append:

```python
import gzip as _gzip
import shlex
import subprocess
from urllib.parse import urlparse


def build_sql_dump(database_url: str, out_path: Path) -> None:
    """Run pg_dump and gzip its output into out_path (reproducibly)."""
    parsed = urlparse(database_url.replace("+psycopg", ""))
    env = {
        "PGHOST": parsed.hostname or "localhost",
        "PGPORT": str(parsed.port or 5432),
        "PGUSER": parsed.username or "",
        "PGPASSWORD": parsed.password or "",
        "PGDATABASE": parsed.path.lstrip("/") or "",
    }
    # -Fp plain, --no-owner --no-acl for portability, -Z0 since we gzip ourselves
    cmd = [
        "pg_dump",
        "-Fp",
        "--no-owner",
        "--no-acl",
        "--no-comments",
        env["PGDATABASE"],
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        cmd,
        env=env | {"PATH": __import__("os").environ.get("PATH", "")},
        capture_output=True,
        check=True,
    )
    with open(out_path, "wb") as fh:
        gz = _gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0)
        try:
            gz.write(result.stdout)
        finally:
            gz.close()
```

- [ ] **Step 3: Add subcommand in `cli.py`**

```python
@app.command("dump-sql")
def dump_sql(
    out: str = typer.Option("dumps/latest.sql.gz", help="Output SQL.gz path"),
) -> None:
    """Build a gzipped pg_dump of the current database."""
    from pathlib import Path

    from open_legis.dumps.build import build_sql_dump
    from open_legis.settings import Settings

    build_sql_dump(database_url=Settings().database_url, out_path=Path(out))
    typer.echo(f"wrote {out}")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_sql_dump.py -v`
Expected: PASS (requires `pg_dump` on PATH; testcontainers image ships with it).

- [ ] **Step 5: Commit**

```
git add src/open_legis/dumps/build.py src/open_legis/cli.py tests/test_sql_dump.py
git commit -m "feat: gzipped pg_dump via open-legis dump-sql"
```

---

### Task 43: `/dumps/` endpoints

**Files:**
- Create: `src/open_legis/api/routes_dumps.py`
- Modify: `src/open_legis/api/app.py`
- Create: `tests/test_api_dumps.py`

- [ ] **Step 1: Write failing test `tests/test_api_dumps.py`**

```python
from pathlib import Path


def test_dumps_latest_served_when_present(client, tmp_path, monkeypatch):
    dumps = tmp_path / "dumps"
    dumps.mkdir()
    (dumps / "latest.tar.gz").write_bytes(b"\x1f\x8b\x08\x00fake")
    monkeypatch.setenv("OPEN_LEGIS_DUMPS_DIR", str(dumps))

    # client fixture created its app pre-env-change; for this test construct a new one:
    from open_legis.api.app import create_app
    from fastapi.testclient import TestClient

    local = TestClient(create_app())
    r = local.get("/dumps/latest.tar.gz")
    assert r.status_code == 200
    assert r.content.startswith(b"\x1f\x8b")


def test_dumps_listing(client, tmp_path, monkeypatch):
    dumps = tmp_path / "dumps"
    dumps.mkdir()
    (dumps / "latest.tar.gz").write_bytes(b"x")
    (dumps / "2026-04-20.tar.gz").write_bytes(b"x")
    monkeypatch.setenv("OPEN_LEGIS_DUMPS_DIR", str(dumps))

    from open_legis.api.app import create_app
    from fastapi.testclient import TestClient

    local = TestClient(create_app())
    r = local.get("/dumps/")
    assert r.status_code == 200
    d = r.json()
    assert "latest.tar.gz" in [i["name"] for i in d["items"]]
```

- [ ] **Step 2: Extend `Settings` for `OPEN_LEGIS_DUMPS_DIR`**

Edit `src/open_legis/settings.py` — add:

```python
    dumps_dir: Path = Field(
        default=Path("dumps"),
        alias="OPEN_LEGIS_DUMPS_DIR",
    )
```

- [ ] **Step 3: Implement `src/open_legis/api/routes_dumps.py`**

```python
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from open_legis.settings import Settings

router = APIRouter(prefix="/dumps", tags=["dumps"])


class DumpItem(BaseModel):
    name: str
    size: int


class DumpList(BaseModel):
    items: list[DumpItem]


def _dumps_dir() -> Path:
    return Settings().dumps_dir


@router.get("/", response_model=DumpList)
def list_dumps() -> DumpList:
    d = _dumps_dir()
    if not d.exists():
        return DumpList(items=[])
    return DumpList(
        items=[
            DumpItem(name=f.name, size=f.stat().st_size)
            for f in sorted(d.iterdir())
            if f.is_file() and f.name != ".keep"
        ]
    )


@router.get("/{name}")
def get_dump(name: str) -> FileResponse:
    if "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="bad name")
    f = _dumps_dir() / name
    if not f.exists() or not f.is_file():
        raise HTTPException(status_code=404, detail="not found")
    media = (
        "application/gzip"
        if name.endswith(".gz")
        else "application/octet-stream"
    )
    return FileResponse(f, media_type=media, filename=name)
```

- [ ] **Step 4: Wire in `app.py`**

```python
from open_legis.api.routes_dumps import router as dumps_router
# ...
    app.include_router(dumps_router)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_api_dumps.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```
git add src/open_legis/api/routes_dumps.py src/open_legis/api/app.py src/open_legis/settings.py tests/test_api_dumps.py
git commit -m "feat: /dumps listing + download endpoints"
```

---

### Task 44: Release workflow `.github/workflows/release.yaml`

**Files:**
- Create: `.github/workflows/release.yaml`

- [ ] **Step 1: Write workflow**

```yaml
name: release

on:
  push:
    tags:
      - "v*"

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: openlegis
          POSTGRES_PASSWORD: openlegis
          POSTGRES_DB: openlegis
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U openlegis"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    env:
      DATABASE_URL: postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: Install postgres client (pg_dump)
        run: sudo apt-get update && sudo apt-get install -y postgresql-client
      - run: uv sync --all-extras
      - run: uv run alembic upgrade head
      - run: uv run open-legis load fixtures/akn
      - run: uv run open-legis dump --out dumps/latest.tar.gz
      - run: uv run open-legis dump-sql --out dumps/latest.sql.gz
      - name: Attach to GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dumps/latest.tar.gz
            dumps/latest.sql.gz
```

- [ ] **Step 2: Commit**

```
git add .github/workflows/release.yaml
git commit -m "ci: release workflow publishes dumps on v* tags"
```

---

### Task 45: Contributor + user docs

**Files:**
- Create: `docs/data-model.md`
- Create: `docs/uri-scheme.md`
- Create: `docs/api.md`
- Create: `docs/adding-an-act.md`
- Create: `docs/takedown.md`
- Modify: `README.md` (add links)

- [ ] **Step 1: Write `docs/uri-scheme.md`**

```markdown
# URI scheme

open-legis uses ELI-shaped ASCII URIs, one canonical path per resource.

## Template

    /eli/bg/{type}/{year}/{slug}[/{date|latest}/{lang}[/{element_path}]]

- `type` — act type: `konstitutsiya`, `kodeks`, `zakon`, `naredba`,
  `pravilnik`, `postanovlenie`, `ukaz`, `reshenie-ks`, `reshenie-ns`
- `year` — 4-digit **adoption year** (passage/signature). Not
  entry-into-force. ЗЗД adopted 22.XI.1950 → `/eli/bg/zakon/1950/zzd`,
  even though it entered force 1.I.1951.
- `slug` — short-title if widely known (`zzd`, `nk`, `gpk`), else
  `dv-{broy}-{yy}` as stable fallback. See "Slug minting" below.
- `date` — ISO date of the expression, or the literal `latest`.
- `lang` — ISO 639-3 code (`bul` by default).
- `element_path` — AKN eId with `__` replaced by `/`
  (`art_45__para_1__point_3` → `art_45/para_1/point_3`).

## Slug minting

1. If the act has a universally-used Bulgarian short title — ЗЗД, НК,
   ГПК, КТ, ДОПК, КСО, СК — slugify it to lowercase ASCII letters.
2. Otherwise, mint `dv-{broy}-{yy}` where `broy` is the ДВ issue number
   and `yy` is the last two digits of the ДВ year. Combined with the
   `year` path segment this is globally unique.
3. Slugs are stable forever. Never rename a slug once published.
```

- [ ] **Step 2: Write `docs/data-model.md`**

```markdown
# Data model

See the design spec for the authoritative description:
`docs/superpowers/specs/2026-04-20-open-legis-data-model-design.md`.

This page is a shorter summary for developers modifying the schema.

## Tables

- `work` — abstract act (FRBR Work)
- `expression` — point-in-time language version (FRBR Expression)
- `element` — every hierarchical structural element of an expression
- `amendment` — edge: an amending act modifying an element of a target
- `reference` — edge: a citation from one element to another work/element
- `external_id` — pointers to lex.bg / parliament.bg / dv.parliament.bg IDs

## Indexes

- `element.path` (`ltree`, GiST) — subtree queries
- `element.tsv` (`tsvector`, GIN) — Bulgarian full-text search
- `expression (work_id, expression_date DESC)` — point-in-time lookup
- Partial unique on `expression (work_id)` where `is_latest` is true

## Extensions

Migration 0002 requires the `ltree` contrib and the Bulgarian snowball
text-search config. If the Bulgarian config is unavailable (check with
`SELECT cfgname FROM pg_ts_config`), the migration falls back to the
`simple` config — search will still work but lose stemming.
```

- [ ] **Step 3: Write `docs/api.md`**

```markdown
# API reference

See `/docs` (Swagger) for live docs; this page summarises the surface.

## Resolution (ELI URI → resource)

    GET /eli/bg/{type}/{year}/{slug}
    GET /eli/bg/{type}/{year}/{slug}/{date|latest}/{lang}
    GET /eli/bg/{type}/{year}/{slug}/{date|latest}/{lang}/{element_path}

Content negotiation:

    Accept: application/json        (default — JSON)
    Accept: application/akn+xml     (Akoma Ntoso XML)
    Accept: text/turtle             (ELI RDF / Turtle)

Override via `?format=json|akn|ttl`.

## Discovery

    GET /works?type=&year=&status=
    GET /search?q=&type=
    GET /works/{slug}/amendments?direction=in|out
    GET /works/{slug}/references?direction=in|out
    GET /works/{slug}/expressions

## Aliases (301 to canonical)

    GET /by-dv/{year}/{broy}/{position}
    GET /by-external/{lex_bg|parliament_bg|dv_parliament_bg}/{id}

## Bulk

    GET /dumps/                  JSON list of available snapshots
    GET /dumps/latest.tar.gz
    GET /dumps/latest.sql.gz
```

- [ ] **Step 4: Write `docs/adding-an-act.md`**

```markdown
# Adding an act

1. Scaffold:

        uv run open-legis new-fixture \
          --type zakon --slug my-slug --year 2025 \
          --date 2025-01-01 --title "Full Bulgarian title" \
          --dv-broy 12

2. Edit the generated `fixtures/akn/.../*.bul.xml`:

   - Replace the TODO body with your authored AKN (`<part>`, `<chapter>`,
     `<article>`, `<paragraph>`, `<point>`, `<letter>`).
   - Each structural element must carry a unique `eId` following AKN
     conventions (`art_1`, `art_1__para_1`, etc.).
   - Use real wording from the ДВ promulgation PDF. Do not copy from
     lex.bg or other consolidated databases (see `takedown.md` and the
     legal policy in the design spec).

3. Cite the consolidation baseline in your commit message, e.g.:

        fixtures: НК as in force 2024-01-01

        Consolidated through ДВ бр. 84/2023.

4. Validate locally:

        uv run open-legis load fixtures/akn
        uv run pytest

5. Open a PR.
```

- [ ] **Step 5: Write `docs/takedown.md`**

```markdown
# Takedown and corrections

open-legis publishes public-domain statutory texts (ЗАПСП чл. 4, т. 1)
under CC0. We still respond to good-faith notices.

## How to reach us

Open a GitHub issue at `github.com/.../open-legis/issues`, or email
`takedown@...`. Include:

- The canonical URI (`/eli/bg/...`) you're concerned about
- The specific wording or element in question
- The basis for your notice

## Our process

- We acknowledge within 7 days.
- If a correction is warranted we apply it, record it in
  `CORRECTIONS.md`, and cut a new dump.
- If a full removal is warranted we remove the resource and note the
  removal in `CORRECTIONS.md`.

We do **not** honour requests that amount to suppressing public-domain
law. Annotations or consolidations that are not ours can be removed;
the authoritative statutory texts cannot, as they are public domain by
statute.
```

- [ ] **Step 6: Update `README.md`**

Append a "Documentation" section listing the docs files.

- [ ] **Step 7: Commit**

```
git add docs/ README.md
git commit -m "docs: URI scheme, data model, API, adding-an-act, takedown"
```

---

### Task 46: End-to-end smoke test + v0.1.0 tag

**Files:**
- Create: `tests/test_e2e.py`
- Modify: `CHANGELOG.md` (new file)

- [ ] **Step 1: Write `tests/test_e2e.py`**

```python
"""End-to-end smoke: load fixtures, hit every public endpoint category."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def e2e_client(pg_url, monkeypatch):
    from open_legis.api.app import create_app
    from open_legis.loader.cli import load_directory
    from open_legis.model import schema as m
    from open_legis.model.db import make_engine

    monkeypatch.setenv("DATABASE_URL", pg_url)
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    load_directory(Path("fixtures/akn"), engine=eng)
    yield TestClient(create_app())
    eng.dispose()


def test_health_openapi_docs(e2e_client):
    assert e2e_client.get("/health").status_code == 200
    assert e2e_client.get("/openapi.json").status_code == 200
    assert e2e_client.get("/docs").status_code == 200


def test_works_listing_non_empty(e2e_client):
    r = e2e_client.get("/works")
    assert r.status_code == 200
    assert r.json()["total"] >= 5


def test_zzd_resolution_all_formats(e2e_client):
    for accept in ["application/json", "application/akn+xml", "text/turtle"]:
        r = e2e_client.get(
            "/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_1",
            headers={"Accept": accept},
        )
        assert r.status_code == 200, (accept, r.text[:200])


def test_search_returns_hits(e2e_client):
    r = e2e_client.get("/search?q=чл")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_by_dv_alias_redirects(e2e_client):
    # ЗЗД DV 275/1950 position 1 (adjust once fixtures are finalised)
    r = e2e_client.get("/by-dv/1950/275/1", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert r.headers["location"].startswith("/eli/bg/zakon/1950/zzd")
```

- [ ] **Step 2: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project are documented here.

## [0.1.0] — 2026-XX-XX

Initial MVP release.

- 6-table relational model (work/expression/element/amendment/reference/external_id)
- FRBR Work/Expression point-in-time versioning
- Akoma Ntoso XML as fixture source-of-truth
- ELI-shaped canonical URI scheme
- REST API with content negotiation (JSON / AKN+XML / Turtle)
- Bulgarian full-text search via Postgres tsvector
- Bulk dumps (tarball + gzipped SQL)
- 5 hand-curated fixtures: Конституция 1991, НК 1968, ЗЗД 1950 (2
  expressions), ЗИД енергетика 2025, Наредба 15/2019
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: every test PASSes.

- [ ] **Step 4: Run linters and type-check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all clean.

- [ ] **Step 5: Commit + tag**

```
git add tests/test_e2e.py CHANGELOG.md
git commit -m "test: end-to-end smoke; CHANGELOG for 0.1.0"
git tag -a v0.1.0 -m "0.1.0 — initial MVP"
```

Do **not** push the tag without the user's explicit approval — this triggers the release workflow which publishes dumps. Confirm before `git push origin v0.1.0`.

---

## Self-review checklist (author ran after writing)

- ✅ Spec coverage: every section of the design spec maps to at least one task (schema → T9+T10+T11; URI → T12; fixtures → T18-22; relations → T23; API resolution → T28+T37; discovery → T29+T30+T31+T32; aliases → T33; negotiation → T34+T37; AKN render → T35; RDF render → T36; dumps → T41+T42+T43; legal policy → T45 docs)
- ✅ Placeholder scan: all "TODO"s in the plan are *inside* fixture XML placeholders (real literal TODO markers authors will replace), not plan-level placeholders
- ✅ Type consistency: `ElementOut`/`ExpressionOut`/`WorkOut` signatures match between schemas.py and renderers; `ActType`/`ElementType`/`AmendmentOp`/`ReferenceType`/`ExternalSource` enum values match the spec
- ✅ Known drift-risk: if Postgres's `bulgarian` snowball config isn't available, fall back to `'simple'` everywhere (flagged in Tasks 11, 30)
- ✅ Fixture risk: Tasks 19-22 deliberately ship skeleton articles marked `TODO` — this is by design to keep the plan shippable; the skeleton still validates and exercises every code path. Full article authoring is acknowledged as ongoing post-v0.1.0 work.






