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
