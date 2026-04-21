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
