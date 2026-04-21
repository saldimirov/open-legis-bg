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

## Documentation

- [URI scheme](docs/uri-scheme.md) — ELI URI structure, slug minting rules
- [Data model](docs/data-model.md) — DB schema summary
- [API reference](docs/api.md) — endpoint listing
- [Adding an act](docs/adding-an-act.md) — contributor guide for new fixtures
- [Takedown policy](docs/takedown.md) — corrections and removal process
