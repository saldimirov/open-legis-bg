# open-legis — Claude instructions

## Vision

Free, open equivalent of APIS (apis.bg) — the commercial Bulgarian legal database. APIS sources from the same public data (dv.parliament.bg) and charges for consolidation, search, and cross-referencing. We make that free.

## Stack

- **FastAPI** + **Jinja2** templates (server-rendered UI at `/ui/...`, JSON API at `/eli/...`)
- **PostgreSQL** with `tsvector` full-text search (Bulgarian `simple` dictionary)
- **AKN XML** (Akoma Ntoso 3.0) as the canonical document format in fixtures
- **ELI URIs** as the identifier scheme: `/eli/bg/{act_type}/{year}/{slug}`
- **SQLAlchemy** ORM + **Alembic** migrations
- **uv** for package management; `uv run open-legis <cmd>` for CLI

## Running

```bash
make dev        # start postgres
uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis uv run open-legis load
DATABASE_URL=... uv run uvicorn "open_legis.api.app:create_app" --factory --host 0.0.0.0 --port 8001
```

## Architecture decisions

### Source data
- Primary source: **dv.parliament.bg** (State Gazette). Public record, CC0-compatible.
- Never scrape APIS or other commercial databases — copyright/database-rights issues.
- `open-legis scrape-dv-batch` fetches issues, parses HTML → AKN XML fixtures.

### Act types
| type | Bulgarian | notes |
|------|-----------|-------|
| `zakon` | Закон | substantive law |
| `zid` | ЗИД | amendment law |
| `byudjet` | Бюджетен закон | annual budget laws — separate from zakon |
| `kodeks` | Кодекс | codes |
| `ratifikatsiya` | Ратификация | treaty ratification laws — separate from zid |
| `naredba` | Наредба | regulations |
| `postanovlenie` | Постановление | council of ministers decrees |
| `pravilnik` | Правилник | rules/procedures |
| `reshenie_ns` | Решение на НС | parliament decisions |
| `konstitutsiya` | Конституция | constitution |

### AKN structure rules
- Chapter/section headings → native `<chapter>`/`<section>` tags, never `<hcontainer name="chapter">`
- `§` items **always** belong to closing provisions (`<hcontainer name="final-provisions|transitional-provisions|additional-provisions">`), never to a chapter
- If the closing-provisions heading is absent in source HTML, auto-synthesise `sec_final` — `§` is never a child of a regular chapter
- Closing-provisions headings come in many forms (singular/plural/combined). All variants listed in `_SPECIAL_RE` and `_SPECIAL_NAME` in `dv_to_akn.py`
- Preserve original heading text verbatim in `<num>` — never normalise e.g. "ДОПЪЛНИТЕЛНА РАЗПОРЕДБА" to the plural form
- Sub-article structure: `(1)/(2)` → `<paragraph>`, `1./2.` → `<point>`, `а)/б)` → nested `<point>`

### Cross-references (infrastructure in place, extraction not yet built)
- `reference` table stores: `source_expression_id`, `source_e_id`, `raw_text` (verbatim), `target_work_id` (nullable), `target_e_id` (nullable), `resolved` (bool)
- **raw_text must always be preserved** — it's the verbatim text as it appears in the law
- `resolved=false` rows accumulate as corpus grows; a resolution pass re-runs at any time
- Do not render dead links in the UI until `resolved=true`
- Extraction pass (regex/NLP over element text) is not yet built — schema is ready

### Corpus strategy
- Currently: end-of-year DV issues only (Oct–Dec), 2010–2026
- Next: full-year scraping (all ~100 issues/year) to get complete coverage
- Index files (`.dv-index-*.json`) cache issue lists; re-scraping uses these

### Re-scraping
When scraper logic changes, re-scrape all fixtures and reload:
```bash
# Re-scrape from cached index files (6 parallel jobs)
# Then reload:
DATABASE_URL=... uv run open-legis load
```
Always include `--types zakon,zid,byudjet,kodeks,ratifikatsiya` in scrape commands.

## Roadmap (deferred — do not implement without explicit instruction)

- **M3 — Consolidation engine**: apply ZID amendments to base laws; schema has `amendment` table and `is_latest` flag; relations in `fixtures/akn/relations/amendments.yaml`
- **M4 — Full corpus**: full-year scraping all DV issues; all act types
- **M5 — Case law**: Constitutional Court (constcourt.bg), Supreme Court decisions
- **M6 — Bills**: legislative proposals from parliament.bg before they become law
- **M7 — EU law**: EUR-Lex open API, Bulgarian translations of EU regulations/directives
- **Cross-reference extraction**: regex/NLP pass to populate `reference` table from element text

## Key files

| Path | Purpose |
|------|---------|
| `src/open_legis/scraper/dv_to_akn.py` | HTML → AKN XML; act type detection, structural parsing |
| `src/open_legis/scraper/dv_index.py` | Crawls dv.parliament.bg issue lists |
| `src/open_legis/loader/akn_parser.py` | AKN XML → DB elements |
| `src/open_legis/model/schema.py` | SQLAlchemy ORM models |
| `src/open_legis/model/alembic/versions/` | DB migrations |
| `src/open_legis/api/routes_ui.py` | Server-rendered UI routes |
| `src/open_legis/api/templates/` | Jinja2 templates |
| `src/open_legis/search/query.py` | Full-text search |
| `fixtures/akn/` | AKN XML fixtures, organised by `{act_type}/{year}/{slug}` |
