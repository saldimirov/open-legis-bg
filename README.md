# open-legis

An open, machine-readable database of Bulgarian legislation — a free alternative to commercial legal databases like APIS (apis.bg).

The primary source is [dv.parliament.bg](https://dv.parliament.bg) (State Gazette), which is public record. Laws are stored in [Akoma Ntoso 3.0](http://www.akomantoso.org/) XML and identified by ELI URIs (`/eli/bg/{type}/{year}/{slug}`).

**Current corpus** (end-of-year DV issues, 2003–2026):

| Type | Count |
|------|-------|
| Наредба (regulations) | 2 437 |
| Ратификация (treaty ratifications) | 843 |
| Изменение / Отмяна (amendments & repeals) | 784 |
| Закон (laws) | 415 |
| Бюджетен закон (budget laws) | 62 |
| Кодекс (codes) | 8 |
| Конституция | 1 |

## Features

- **REST API** — ELI-shaped JSON endpoints for works, expressions, full-text search
- **Server-rendered UI** — browse, search, and read laws at `/ui/...`
- **AKN & RDF** — content negotiation; each work is available as JSON, Akoma Ntoso XML, or RDF/Turtle
- **Full-text search** — PostgreSQL `tsvector` with Bulgarian `simple` dictionary
- **MCP server** — AI assistants (Claude, Cursor, etc.) can query the corpus via Model Context Protocol at `/mcp`
- **Scraper** — fetches and parses HTML from dv.parliament.bg into AKN XML fixtures
- **CLI** — `open-legis load`, `open-legis scrape-dv-batch`, `open-legis dump`, and more

## Quick start

```bash
# Prerequisites: Python 3.12+, uv, Docker

make dev                    # start postgres in Docker
uv run alembic upgrade head # run migrations
uv run open-legis load      # load fixtures into DB (~2 min for full corpus)
make serve                  # run API + UI on :8000
```

Browse at `http://localhost:8000/` or query the API:

```bash
curl http://localhost:8000/eli/bg/kodeks/1968/nakazatelen-kodeks
curl -H 'Accept: application/akn+xml' \
     http://localhost:8000/eli/bg/kodeks/1968/nakazatelen-kodeks/2024-01-01/bul
```

## Scraping

Fixtures are included in the repo. To re-scrape or extend the corpus:

```bash
# Scrape a single DV issue by idObj
uv run open-legis scrape-dv --idobj 12302

# Scrape a year range (builds a local issue index cache)
uv run open-legis scrape-dv-batch --from-year 2020 --to-year 2026 \
    --types zakon,zid,kodeks
```

Supported act types: `zakon`, `zid`, `byudjet`, `kodeks`, `naredba`, `postanovlenie`, `pravilnik`, `reshenie_ns`, `ratifikatsiya`.

## Docker

```bash
docker compose up -d
```

Runs postgres + the app. Migrations run automatically; fixtures load on first start (skipped if DB already has data).

## Project structure

```
src/open_legis/
  api/          FastAPI app — REST routes, UI routes, Jinja2 templates, renderers
  scraper/      dv.parliament.bg scraper → AKN XML
  loader/       AKN XML → PostgreSQL (parser, upsert, relations loader)
  model/        SQLAlchemy schema + Alembic migrations
  search/       Full-text search (PostgreSQL tsvector)
  mcp/          Model Context Protocol server
  dumps/        Snapshot / pg_dump tooling
  cli.py        Typer CLI entry point
fixtures/akn/   AKN XML corpus, organised by {act_type}/{year}/{slug}
```

## Licensing

- **Code**: MIT (see `LICENSE`)
- **Data**: CC0, consistent with ЗАПСП чл. 4, т. 1 (see `DATA_LICENSE`)

## Documentation

- [URI scheme](docs/uri-scheme.md) — ELI URI structure and slug rules
- [Data model](docs/data-model.md) — DB schema summary
- [API reference](docs/api.md) — endpoint listing
- [Adding an act](docs/adding-an-act.md) — contributor guide for new fixtures
- [Takedown policy](docs/takedown.md) — corrections and removal requests
