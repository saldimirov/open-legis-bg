# DV Sections — Design Spec

**Date:** 2026-04-25
**Status:** Approved

## Goal

Digitize every DV issue completely — both official and unofficial sections — and expose them via a structured, tabbed DV issue view. Currently only official acts are scraped and stored. Unofficial items (announcements, court notices, tenders, etc.) are silently discarded.

## Scope

1. New `dv_item` DB table — unified index of all DV materials
2. RTF scraper — track section + category per material, emit unofficial fixtures
3. Body text cleaning — strip DV page headers and Word metadata artifacts
4. Loader — populate `dv_item` for both official and unofficial materials
5. UI — tabbed DV issue view grouped by section → sub-section
6. Full re-scrape of all indexed issues

## Background (Закон за Държавен вестник)

Per Чл. 3, DV has exactly two sections. Per Чл. 4, official acts are ordered by issuing body. Per Чл. 7, unofficial section contains: индивидуални административни актове, обявления, съобщения, призовки, съдебни решения, покани, и др. известия.

Original law: Обн. ДВ бр. 89/1995 г. Key amendments: бр. 16/2008 (online publication added — Чл. 3(2)), бр. 40/2018 (annexes online-only — Чл. 6), бр. 108/2023 (distribution). The two-section structure and Чл. 4/7 sub-category ordering are **unchanged throughout our corpus period (2009–2026)** — no era-specific handling needed.

---

## 1. DB Schema

### New table: `dv_item`

```sql
CREATE TABLE dv_item (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dv_year     INTEGER NOT NULL,
    dv_broy     INTEGER NOT NULL,
    dv_position INTEGER NOT NULL,
    section     VARCHAR NOT NULL,   -- "official" | "unofficial"
    category    VARCHAR,            -- sub-section, extracted from DV page header
    title       TEXT NOT NULL,
    body        TEXT,               -- full raw text; NULL for official acts (body lives in AKN)
    work_id     UUID REFERENCES work(id) ON DELETE SET NULL,
    UNIQUE (dv_year, dv_broy, dv_position)
);
```

- Official acts: `work_id` set, `body` NULL (full text in AKN fixture)
- Unofficial items: `work_id` NULL, `body` contains full text
- `category` for official items derived from issuer enum at load time; for unofficial items extracted from sub-heading lines during scraping
- One Alembic migration

---

## 2. Body Text Cleaning

Applies to both RTF and HTML scraping paths, before any structural parsing.

### DV page header (multi-line, repeats at every page break)

Pattern:
```
Държавен вестник
<Institution>     брой: N, от дата DD.MM.YYYY г.   <Section> / <Sub-section>    стр.N
```

New function `_strip_dv_page_headers(lines) -> list[str]`:
- Detect `Държавен вестник` line followed by `брой:.*стр\.` line → drop both
- If the line immediately after the two-line header matches a known institution name (e.g. `МИНИСТЕРСТВО НА ВЪТРЕШНИТЕ РАБОТИ`) — drop it too (repeated page-break artifact)
- Pure text transformation, no side effects

### Word metadata block

Pattern: a block starting with a resolution (`800x600`, `1024x768`, etc.) followed by `Normal`, then numbers/booleans/language codes, ending with `MicrosoftInternetExplorer4`.

New regex: detect and drop the entire block.

---

## 3. RTF Scraper Changes

### `rtf_parser._split_acts` return type

Currently: `list[tuple[str, str]]` — `(title, body)`

New: `list[tuple[str, str, str, str | None]]` — `(title, body, section, category)`

### Section tracking

`_split_acts` maintains two state variables:
- `current_section: str` — initialized to `"official"` (acts before any section header belong to official)
- `current_category: str | None` — initialized to `None`, reset at each section boundary

On encountering `ОФИЦИАЛЕН РАЗДЕЛ` line → `current_section = "official"`, `current_category = None`
On encountering `НЕОФИЦИАЛЕН РАЗДЕЛ` line → `current_section = "unofficial"`, `current_category = None`

### Category detection

**Official section:** no category tracking in the scraper. Category is derived at load time from the Work's `issuer` enum (see loader pass 2 table).

**Unofficial section:** detect ALL-CAPS sub-heading lines that are not act titles (e.g. `СЪОБЩЕНИЯ`, `ОБЯВЛЕНИЯ`, `ПРИЗОВКИ`, `ПОКАНИ`) → set `current_category`.

### `batch.process_issue_local`

Currently: writes AKN fixture for each official act.

New behavior:
- Official materials: AKN fixture as before (no change to fixture format)
- Unofficial materials: write `fixtures/dv-unofficial/{year}/{broy:03d}-{position}.json`

JSON format:
```json
{
  "dv_year": 2026,
  "dv_broy": 36,
  "dv_position": 15,
  "section": "unofficial",
  "category": "Съобщения",
  "title": "...",
  "body": "..."
}
```

Dedup logic for unofficial: same `(title[:120])` within an issue → keep longest body (mirrors official dedup).

---

## 4. Loader Changes

`open-legis load` gets a second pass after the existing AKN → Work pass:

### Pass 1 (existing): AKN fixtures → Work rows

No change.

### Pass 2 (new): Work rows → `dv_item` rows (official)

For each loaded Work:
- `section = "official"`
- `category`: derived from Work's `issuer` enum per table below
- `work_id = work.id`
- `body = NULL`
- Upsert on `(dv_year, dv_broy, dv_position)`

Category derivation from issuer:
| issuer | category |
|---|---|
| `ns` | НАРОДНО СЪБРАНИЕ |
| `president` | ПРЕЗИДЕНТ НА РЕПУБЛИКАТА |
| `ms` | МИНИСТЕРСКИ СЪВЕТ |
| `ks` | КОНСТИТУЦИОНЕН СЪД |
| `vas` | ВЪРХОВЕН АДМИНИСТРАТИВЕН СЪД |
| ministry/agency/commission | МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА |

### Pass 3 (new): `fixtures/dv-unofficial/**/*.json` → `dv_item` rows (unofficial)

- Scan directory recursively
- Create `dv_item` row per JSON file
- `work_id = NULL`
- Upsert on `(dv_year, dv_broy, dv_position)`

---

## 5. UI

### Route: `GET /dv/{year}/{broy}`

Query: `SELECT * FROM dv_item WHERE dv_year=? AND dv_broy=? ORDER BY dv_position`

Group in Python:
```
sections_map: dict[str, dict[str | None, list[DvItem]]]
  "official" → { "НАРОДНО СЪБРАНИЕ" → [...], "ПРЕЗИДЕНТ НА РЕПУБЛИКАТА" → [...] }
  "unofficial" → { "Съобщения" → [...], None → [...] }
```

Pass to template: `sections` list ordered as `["official", "unofficial"]` (if present).

### Template: `dv_issue.html`

**Tabs:** one per section present in data. Labels: `Официален раздел` / `Неофициален раздел`. Tab only rendered if section has items.

**Within each tab:** sub-section groups as labeled dividers (not nested tabs). Groups ordered by first appearance (position order preserves legal ordering from Чл. 4).

**Official items:** same as current — title, act_type badge, adoption date, link to `/ui/eli/...`

**Unofficial items:** title + `<details>/<summary>` expand-in-place showing full body text. No dedicated page.

**Summary line:** change from `N акта в този брой` to `N акта · M известия` (or similar split).

---

## 6. Re-scrape

Full re-scrape of all indexed issues. Run locally on Mac with 8 workers:

```bash
uv run open-legis scrape-dv-batch --workers 8
uv run open-legis load
```

All changes must be committed and pushed before running.

---

## Files Affected

| File | Change |
|---|---|
| `model/schema.py` | Add `DvItem` model |
| `model/alembic/versions/0011_dv_item_table.py` | Migration |
| `scraper/rtf_parser.py` | Section/category tracking, body cleaning |
| `scraper/batch.py` | Emit unofficial JSON fixtures |
| `loader/akn_parser.py` | Passes 2 + 3 for `dv_item` population |
| `api/routes_ui.py` | `dv_issue` route queries `dv_item` |
| `api/templates/dv_issue.html` | Tabbed UI |
