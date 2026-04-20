# open-legis — Data Model & API Design

**Status:** draft · **Date:** 2026-04-20 · **Scope:** MVP (subproject #1 of N)

## Problem

Bulgaria has no open, machine-readable, canonically-identified database of
national legislation. Commercial aggregators (Ciela, Apis) sit behind paywalls.
The free consolidated mirror at lex.bg is HTML-only, legacy-encoded, and has no
article-level deep linking or API. Primary state sources (parliament.bg,
dv.parliament.bg) publish only HTML + PDF with no structured data, no API, and
no stable public URIs for specific articles or their point-in-time versions.

Researchers, civic-tech projects, NGOs, downstream applications (including LLMs)
and the public cannot reliably cite, query, or ingest Bulgarian statutory law in
a programmatic way.

## Goal of this subproject

Deliver a **data model + sample dataset + read-only REST API** as a standalone
open-source project. Validate the shape of an open Bulgarian legislation
database against a small hand-curated corpus of 5 acts before committing to
automated ingestion.

Non-goal: a complete corpus. Non-goal: a production deployment. Non-goal: an
editor UI. These are deferred to follow-on subprojects.

## Scope (MVP)

**In scope**

- Relational data model covering acts, hierarchical structure, point-in-time
  versions, amendments, and cross-references
- Canonical URI scheme aligned with ELI (European Legislation Identifier)
- Akoma Ntoso XML as source-of-truth fixture format and as an export format
- FastAPI read-only HTTP API with REST endpoints, OpenAPI 3.1 spec, content
  negotiation (JSON / AKN XML / Turtle RDF)
- Bulgarian full-text search via Postgres `bulgarian` snowball
- Five hand-authored fixture acts covering the typological range
  (конституция / кодекс / закон / ЗИД / наредба)
- Bulk dump endpoints (tarball + SQL)
- Reproducible builds: `make load` from fixtures yields a deterministic DB
- Contributor docs (`adding-an-act.md`), URI-scheme doc, data-model doc
- Legal/sourcing policy for future ingestion

**Out of scope (deferred)**

- Automated ingestion from parliament.bg / dv.parliament.bg
- Web UI (Swagger at `/docs` is the only human interface)
- Authentication, writes, editor workflow — editing = PR to `fixtures/`
- English translations (schema reserves `lang=eng`; no fixtures)
- Case law (ВКС, ВАС, КС) — separate document type, separate subproject
- EuroVoc topic classification
- Bill lifecycle (законопроект → committee → vote → adopted)
- Cross-expression diff computation
- Hosted production deployment (only `docker-compose up`)

## Architecture

Three components, all derivable from `fixtures/` in git:

```
fixtures/ (AKN XML files + relations YAML, committed to git)
    │
    │ one-shot loader CLI (open-legis load)
    ▼
Postgres 16  (works / expressions / elements / amendments / references /
              external_ids · bulgarian tsvector · ltree)
    │
    ▼
FastAPI read service  (REST + OpenAPI · content negotiation)
    │
    ▼
consumers (curl, scripts, LLMs, downstream apps)
```

Source of truth: `fixtures/`. The database is a derived, rebuildable
projection. No write path into the DB from the API.

## Data model

Six relational tables. Designed around the FRBR Work/Expression split
(non-negotiable for point-in-time queries).

### `work` — the abstract act

| column | type | notes |
|---|---|---|
| `id` | uuid | |
| `eli_uri` | text | unique; e.g. `/eli/bg/zakon/1950/zzd` |
| `act_type` | enum | `konstitutsiya`, `kodeks`, `zakon`, `naredba`, `pravilnik`, `postanovlenie`, `ukaz`, `reshenie_ks`, `reshenie_ns` |
| `title` | text | Bulgarian full title |
| `title_short` | text | e.g. `ЗЗД` |
| `number` | text | original act number where assigned |
| `adoption_date` | date | |
| `dv_broy` | int | promulgation issue number |
| `dv_year` | int | |
| `dv_position` | int | position within the issue |
| `issuing_body` | text | Народно събрание, МС, etc. |
| `status` | enum | `in_force`, `repealed`, `partially_in_force` |

Constraints: `unique (dv_broy, dv_year, dv_position)` — the authoritative
Bulgarian-law natural key.

### `expression` — a point-in-time language version

| column | type | notes |
|---|---|---|
| `id` | uuid | |
| `work_id` | fk → work | |
| `expression_date` | date | valid-from |
| `language` | text | ISO 639-3; `bul` for MVP |
| `akn_xml` | text | canonical source, full `<akomaNtoso>` doc |
| `source_file` | text | path to fixture file |
| `is_latest` | bool | materialised flag |

Constraints: `unique (work_id, expression_date, language)`.

### `element` — every hierarchical element within an expression

| column | type | notes |
|---|---|---|
| `id` | uuid | |
| `expression_id` | fk → expression | |
| `e_id` | text | AKN eId (`art_45__para_2__point_a`) |
| `parent_e_id` | text | adjacency list, nullable for root children |
| `path` | ltree | materialised path for subtree queries |
| `element_type` | enum | `part`, `title`, `chapter`, `section`, `article`, `paragraph`, `point`, `letter`, `hcontainer` |
| `num` | text | `Чл. 5`, `(2)`, `1.`, `а)` |
| `heading` | text | |
| `text` | text | leaf or concatenated text content |
| `sequence` | int | order among siblings |
| `tsv` | tsvector | GENERATED, `bulgarian` config |

Constraints: `unique (expression_id, e_id)`. Indexes on `path` (GiST),
`tsv` (GIN), `(expression_id, parent_e_id)` (btree).

### `amendment` — active modifications

| column | type | notes |
|---|---|---|
| `amending_work_id` | fk → work | the ЗИД that made the change |
| `target_work_id` | fk → work | the act being amended |
| `target_e_id` | text | specific element (null ⇒ whole-act) |
| `operation` | enum | `insertion`, `substitution`, `repeal`, `renumbering` |
| `effective_date` | date | |
| `notes` | text | |

### `reference` — cross-references (citation graph)

| column | type | notes |
|---|---|---|
| `source_expression_id` | fk → expression | |
| `source_e_id` | text | element doing the citing |
| `target_work_id` | fk → work | nullable |
| `target_e_id` | text | nullable |
| `reference_type` | enum | `cites`, `defines` |

### `external_id` — pointers into lex.bg / parliament.bg / dv.parliament.bg

| column | type | notes |
|---|---|---|
| `work_id` | fk → work | |
| `source` | enum | `lex_bg`, `parliament_bg`, `dv_parliament_bg` |
| `external_value` | text | numeric ID from source |
| `url` | text | direct URL on source site |

Constraints: `unique (work_id, source)`.

### Key modelling choices

- **AKN XML is source of truth.** `expression.akn_xml` holds the authoritative
  content; `element` rows are a materialised, queryable projection produced by
  the loader. A rebuild from fixtures is deterministic.
- **FRBR is explicit.** Point-in-time queries resolve to the latest `expression`
  where `expression_date ≤ query_date`, then look up `element` by `e_id`.
- **Element tree is adjacency list AND ltree.** Adjacency for structural
  integrity, ltree for cheap subtree queries.
- **Amendments are assertions, not diff patches.** The consolidated expression
  is authored by hand as a separate AKN file; the amendment table records the
  edge but does not mechanically compute the new text. Matches how Normattiva
  and Indigo handle it.
- **Two keys, both unique.** ELI URI (public canonical) and
  `(dv_broy, dv_year, dv_position)` (Bulgarian-law natural key).
- **External IDs are peripheral.** They let consumers jump to source sites;
  nothing in our model depends on them.

## URI scheme

ELI-shaped, ASCII (Cyrillic lives in metadata, not URIs):

```
https://data.open-legis.bg/eli/bg/{type}/{year}/{slug}[/{date|latest}/{lang}[/{element_path}]]
```

- `type` — romanised slug from the `act_type` enum
- `year` — 4-digit **adoption year** (signature/passage), not entry-into-force.
  ЗЗД adopted 22.XI.1950 → `/eli/bg/zakon/1950/zzd`, even though it entered
  force 1.I.1951.
- `slug` — canonical short-title where one exists (`zzd`, `nk`, `gpk`),
  else `dv-{broy}-{yy}` as stable fallback. Minting rule documented in
  `docs/uri-scheme.md`.
- `date` — ISO date of the expression; `latest` selects the current consolidated
- `lang` — ISO 639-3 (`bul`; `eng` reserved)
- `element_path` — AKN eId with `__` → `/` (e.g. `art_45/para_1/point_3`)

### Examples

| Resource | URI |
|---|---|
| Work: ЗЗД | `/eli/bg/zakon/1950/zzd` |
| Latest expression | `/eli/bg/zakon/1950/zzd/latest/bul` |
| Dated expression | `/eli/bg/zakon/1950/zzd/2024-01-01/bul` |
| Art. 45 | `/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45` |
| Art. 45 ал. 1 т. 3 | `/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45/para_1/point_3` |
| Constitution | `/eli/bg/konstitutsiya/1991/krb` |
| Наказателен кодекс | `/eli/bg/kodeks/1968/nk` |
| ЗИД (no short title) | `/eli/bg/zakon/2025/dv-67-25` |

## API surface

Public, read-only, unauthenticated. CORS `*`. ETag + `Cache-Control: public,
max-age=86400` on resources; shorter on search.

### Resolution — ELI URI is the API path

```
GET /eli/bg/{type}/{year}/{slug}
GET /eli/bg/{type}/{year}/{slug}/{date|latest}/{lang}
GET /eli/bg/{type}/{year}/{slug}/{date|latest}/{lang}/{element_path}
```

### Discovery

```
GET /works?type=&year=&status=            paginated list (max 100/page)
GET /search?q=&type=&as_of=               full-text, bg stemming
GET /works/{slug}/amendments?direction=   inbound/outbound edges
GET /works/{slug}/references?direction=   citation graph
GET /works/{slug}/expressions             all point-in-time versions
```

### Aliases (301 → canonical ELI)

```
GET /by-dv/{year}/{broy}/{position}
GET /by-external/{lex_bg|parliament_bg|dv_parliament_bg}/{id}
```

### Bulk

```
GET /dumps/latest.tar.gz         AKN XML + JSON snapshot
GET /dumps/latest.sql.gz         Postgres dump
GET /dumps/{YYYY-MM-DD}.tar.gz   dated snapshots
```

### Meta

```
GET /openapi.json
GET /docs          Swagger UI (only human interface)
GET /health
```

### Content negotiation

Same URL, different `Accept`:

| Accept | Response |
|---|---|
| `application/json` (default) | structured JSON with `_links` |
| `application/akn+xml` | stored AKN XML unaltered |
| `text/turtle` | ELI RDF using `eli:` ontology |

### JSON response shape (sketch)

```json
{
  "uri": "/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45",
  "work": {
    "uri": "/eli/bg/zakon/1950/zzd",
    "title": "Закон за задълженията и договорите",
    "title_short": "ЗЗД",
    "type": "zakon",
    "dv_ref": {"broy": 275, "year": 1950},
    "external_ids": {"lex_bg": "2121934337"}
  },
  "expression": {"date": "2024-01-01", "lang": "bul", "is_latest": true},
  "element": {
    "e_id": "art_45",
    "type": "article",
    "num": "Чл. 45",
    "heading": "",
    "text": "...",
    "children": [{"e_id": "art_45__para_1", "num": "(1)", "text": "..."}]
  },
  "_links": {
    "self": "/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45",
    "akn_xml": "/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45?format=akn",
    "rdf": "/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45?format=ttl",
    "work": "/eli/bg/zakon/1950/zzd",
    "expression": "/eli/bg/zakon/1950/zzd/2024-01-01/bul",
    "previous_versions": ["/eli/bg/zakon/1950/zzd/2021-06-01/bul/art_45"]
  }
}
```

## Fixtures

One AKN XML file per expression, full `<akomaNtoso>` document including
`<meta><FRBRWork>…<FRBRExpression>…</meta>`. XSD-validated against AKN 3.0 in
CI. A scaffold CLI (`open-legis new-fixture --type=zakon --slug=zzd
--date=2024-01-01`) generates a valid skeleton so hand-authoring is tractable.

Amendment edges and cross-references that span fixtures live in
`fixtures/akn/relations/amendments.yaml` and `references.yaml` — graph data that
doesn't belong inside an act's AKN document.

### Fixture set (5 acts)

| # | Act | Slug | Rationale |
|---|---|---|---|
| 1 | Конституция на Република България (1991) | `konstitutsiya/1991/krb` | Constitutional act — distinct type |
| 2 | Наказателен кодекс (1968) | `kodeks/1968/nk` | Codex — deep hierarchy (part/dyal/glava) |
| 3 | Закон за задълженията и договорите (1950) | `zakon/1950/zzd` | Ship **two** expressions (2021-06-01 + 2024-01-01) to prove point-in-time |
| 4 | ЗИД на Закона за енергетиката (2025) | `zakon/2025/dv-67-25` | Amending act — exercises the amendment edge model |
| 5 | Наредба № 15/2019 | `naredba/2019/dv-61-19` | Secondary legislation — different issuing body |

## Repo layout

```
open-legis/
├── README.md
├── LICENSE                      MIT (code)
├── DATA_LICENSE                 CC0 + ЗАПСП чл. 4 notice (texts)
├── pyproject.toml
├── docker-compose.yml           postgres 16
├── Makefile                     dev / load / serve / test / dump
├── fixtures/
│   └── akn/
│       ├── konstitutsiya/1991/krb/expressions/1991-07-13.bul.xml
│       ├── kodeks/1968/nk/expressions/2024-01-01.bul.xml
│       ├── zakon/1950/zzd/expressions/2021-06-01.bul.xml
│       ├── zakon/1950/zzd/expressions/2024-01-01.bul.xml
│       ├── zakon/2025/dv-67-25/expressions/2025-08-15.bul.xml
│       ├── naredba/2019/dv-61-19/expressions/2025-08-15.bul.xml
│       └── relations/{amendments,references}.yaml
├── src/open_legis/
│   ├── api/       routes, content negotiation, renderers
│   ├── model/     SQLAlchemy models + alembic migrations
│   ├── loader/    AKN parser, relations loader, validators, CLI
│   └── search/    tsvector queries
├── tests/
│   ├── golden/    expected JSON/RDF per fixture (diff-checked in CI)
│   └── ...
├── docs/
│   ├── data-model.md
│   ├── uri-scheme.md
│   ├── api.md
│   ├── adding-an-act.md
│   ├── takedown.md
│   └── superpowers/specs/2026-04-20-open-legis-data-model-design.md
└── .github/workflows/{ci,release}.yaml
```

## Stack

- **Python 3.12** (via `uv`)
- **FastAPI** + uvicorn
- **SQLAlchemy 2.x** + Alembic
- **Postgres 16** with the `bulgarian` snowball FTS config + `ltree` extension
- **lxml** for AKN parsing, **rdflib** for Turtle/ELI RDF output
- **pydantic v2** for response models
- **pytest** + **testcontainers** (real Postgres in tests)
- **ruff** + **mypy --strict**

## Testing

- **Integration tests hit a real Postgres** via testcontainers. Mocks are
  forbidden for DB tests — they hide migration and FTS bugs.
- **Golden tests.** Every fixture has an expected JSON, AKN, and Turtle output
  in `tests/golden/`. Loader or renderer changes that perturb output fail CI
  until the golden is updated.
- **XSD validation** of every fixture XML against AKN 3.0 in CI.
- **Semantic validation** — our own checks: ELI URI matches path, every
  `<article>` has a unique eId, amendments reference existing works, fixture
  YAML relations resolve.
- **API contract** — OpenAPI spec stability assertions.
- **Determinism** — `make load && make dump` twice produces tarballs with
  identical sha256.

## Milestones

| # | Milestone | Output |
|---|---|---|
| M0 | Repo scaffolding | `pyproject.toml`, docker-compose, package stubs, CI green on stubs |
| M1 | Schema + loader slice | Alembic migrations; loader parses 1 trivial fixture; `open-legis load` works |
| M2 | All 5 fixtures authored & loading | AKN XML for each, XSD + semantic validation passing, relations wired, goldens committed |
| M3 | Read API — JSON | `/eli/...` resolution, `/works`, `/search`, `/amendments`, `/references` endpoints; OpenAPI served |
| M4 | Content negotiation + search polish | AKN + Turtle renderers; tsvector FTS tuned; 301 aliases |
| M5 | Bulk dumps + launch | `/dumps/` tarballs + SQL; release workflow; `adding-an-act.md`; `README.md` curl examples; v0.1.0 tag |

No time estimates — each milestone is independently small.

## Success criteria

1. `curl /eli/bg/zakon/1950/zzd` returns JSON with the current consolidated expression embedded.
2. `curl -H 'Accept: application/akn+xml' /eli/bg/zakon/1950/zzd/2024-01-01/bul` returns AKN XML that passes the AKN 3.0 XSD.
3. `curl -H 'Accept: text/turtle' /eli/bg/zakon/1950/zzd` returns valid Turtle using the `eli:` ontology.
4. Point-in-time proved: `GET .../zzd/2021-06-01/bul/art_X` and `.../zzd/2024-01-01/bul/art_X` return *different* texts for at least one article that changed between them.
5. `curl '/search?q=договор'` returns ranked hits with Bulgarian stemming (договор/договора/договори collapse to one root).
6. `make dump` twice on unchanged fixtures yields tarballs with identical sha256.
7. All 5 fixtures pass XSD + semantic validation in CI. Removing any required field fails CI.
8. Loader is idempotent: `make load` twice leaves the DB in the same state.

## Legal & sourcing policy

Two legal protections apply to Bulgarian legislation data:

1. **Copyright on the text itself.** Bulgarian ЗАПСП чл. 4, т. 1 excludes
   *"нормативни и индивидуални актове на държавни органи за управление, както и
   официалните им преводи"* from copyright protection. Statutory texts are
   public domain by statute.
2. **Sui generis database right** (EU Directive 96/9/EC, implemented in ЗАПСП
   гл. XI а, чл. 93б). This protects substantial investment in
   compiling/verifying/presenting a database **even where individual items are
   not copyrighted**. Commercial consolidated databases (Ciela, Apis) likely
   enjoy this protection regardless of the underlying texts being public domain.
3. **Contract law / terms of service.** Using a site under its terms can create
   contractual obligations independent of copyright.

### Permitted sources

- **dv.parliament.bg** (Държавен вестник) — authoritative state promulgation.
  State body performing a public function; robots.txt is unset (verified);
  texts are public domain by statute.
- **parliament.bg** — adopted acts and bill metadata. robots.txt permissive
  (verified: `User-agent: * / Disallow:`).

### Prohibited sources

- **lex.bg** — a Ciela-affiliated aggregator. Its consolidated DB (merging
  amendments across decades) represents the kind of editorial investment that
  attracts sui generis protection. Human browsing is fine; bulk extraction is
  not. We do not scrape lex.bg.
- **ciela.net, apis.bg** — commercial, paywalled, explicit ToS. Off-limits.

### Ingestion code-of-conduct (future subproject)

- Primary state sources only.
- Respect robots.txt even where permissive.
- User-Agent identifies the project + contact email.
- Rate-limit conservatively (≤1 req/s per host), conditional GETs
  (`If-Modified-Since` / ETag), long local caching.
- Record provenance per act: source URL, fetch timestamp, sha256 of retrieved
  bytes. Stored alongside the fixture.
- No circumvention of paywalls, logins, CAPTCHAs, or technical protections.
- Publish a takedown/remediation policy (`docs/takedown.md`) with a contact
  address; respond within 7 days.
- Publish a `CORRECTIONS.md` log when post-publication fixes happen.

### MVP-specific rules (hand-authored fixtures)

- Fixtures are hand-authored AKN XML created by a human reading
  publicly-available consolidated texts.
- lex.bg may be read as a convenient human-readable reference. It is **not**
  copy-pasted wholesale into fixtures.
- The author transcribes/paraphrases structure and sets the official wording
  from the DV PDF of the relevant amending act(s).
- Each fixture commit message cites the DV issues that produced the current
  consolidation (e.g. *"НК as in force 2024-01-01, consolidating amendments
  through ДВ бр. 84/2023"*).
- `external_id` rows record lex.bg / parliament.bg / dv.parliament.bg IDs as
  convenience pointers, not as canonical sources. The DV reference on `work` is
  canonical.

### Licensing

- **Code** — MIT (`LICENSE`).
- **Data** — CC0 (`DATA_LICENSE`), with a preamble citing ЗАПСП чл. 4, т. 1.
  The underlying texts are public domain by Bulgarian statute; any curation on
  our part is additionally waived under CC0 to remove ambiguity.
- **Schema & docs** — CC-BY 4.0.

## Open decisions / risks

1. **Hand-authoring 5 AKN fixtures is the bottleneck.** НК alone has
   ~400 articles. Mitigation: LLM-assisted draft of AKN skeleton from
   publicly-available HTML, followed by human review and correction against the
   DV PDFs. The scaffolding CLI absorbs boilerplate.
2. **Postgres `bulgarian` snowball config** — verify availability in
   Postgres 16 contrib during M1.
3. **The `slug` minting rule** — short-title when widely known, `dv-{broy}-{yy}`
   otherwise — must be codified in `docs/uri-scheme.md` up front so we stay
   consistent as we add acts.
4. **AKN 3.0 XSD strictness** could make hand-authoring painful. Fallback:
   author a simplified in-house XML, validate against our own RelaxNG, generate
   conforming AKN at export time. Defer this decision until we try and feel the
   pain.
5. **Bulk dump cadence** — if fixtures churn in a PR, do we regenerate dumps on
   every merge, on a schedule, or only on release tags? Default: release tags.
   Revisit in M5.

## References

- Akoma Ntoso 3.0 — OASIS LegalDocML. `docs.oasis-open.org/legaldocml/akn-core/v1.0/`
- ELI — European Legislation Identifier. `eur-lex.europa.eu/eli-register`
- Indigo — Laws.Africa's AKN-native Django app (reference implementation).
  `github.com/laws-africa/indigo`
- ЗАПСП — Закон за авторското право и сродните му права, чл. 4, т. 1 and
  гл. XI а.
- EU Directive 96/9/EC (database right).
