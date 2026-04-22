# Design: `open-legis validate` command

**Date:** 2026-04-22  
**Status:** Approved

## Goal

A developer-run command that validates the full data pipeline — local DV mirror → AKN fixtures → PostgreSQL DB — before the corpus goes public. Surfaces coverage gaps, parser errors, misclassifications, duplicate/fragment acts, and ELI structural analysis. Exit code 1 if any errors; 0 if only warnings.

---

## Command

```
open-legis validate
  --fixtures    fixtures/akn       (default)
  --mirror      local_dv           (default)
  --index-file  .dv-index.json     (default)
  --layer       mirror|fixtures|classify|db|eli   (optional; runs all if omitted)
  --verbose / -v                   show all issues, not just first 20 per category
  --json PATH                      write full report as JSON to file
```

---

## Module Layout

```
src/open_legis/validate/
    __init__.py
    mirror.py      # Layer 1 — index vs local_dv
    fixtures.py    # Layer 2 — XML validity + path structure
    classify.py    # Layer 3 — act-type classification sanity
    db.py          # Layer 4 — DB coverage + dupe/fragment detection
    eli.py         # Layer 5 — ELI structure analysis (informational)
    report.py      # terminal output + JSON serialisation
```

---

## Data Model

Each layer returns a `LayerResult`:

```python
@dataclass
class Issue:
    severity: Literal["error", "warn", "info"]
    code: str          # e.g. "MISSING_FILE", "TYPE_MISMATCH"
    message: str       # human-readable one-liner
    path: str | None   # file path or ELI URI
    detail: str | None # extra context (expected vs actual, title text, etc.)

@dataclass
class LayerResult:
    name: str
    issues: list[Issue]
    stats: dict[str, int]   # e.g. {"checked": 4070, "missing": 0, "too_small": 3}
```

JSON report structure:

```json
{
  "run_at": "2026-04-22T14:30:00",
  "summary": {"errors": 3, "warnings": 12, "layers_run": 5},
  "layers": [
    {
      "name": "mirror",
      "stats": {"checked": 4070, "missing": 0, "too_small": 0},
      "issues": []
    },
    ...
  ]
}
```

---

## Layer 1 — Mirror Coverage

**Input:** `.dv-index.json` (4,070 entries), `local_dv/`  
**Checks:**
- For each `{year, broy, idObj}`: `local_dv/{year}/{broy:03d}-{idObj}.rtf` or `.pdf` exists
- File size > 1 KB (catches truncated downloads)

**Issue codes:**

| Code | Severity | Meaning |
|------|----------|---------|
| `MISSING_FILE` | error | Issue in index but no file on disk |
| `TOO_SMALL` | warn | File < 1 KB — likely corrupt/empty download |

---

## Layer 2 — Fixture Structure

**Input:** all `fixtures/akn/**/*.bul.xml`  
**Checks per file:**
- Parses as valid XML
- Has `<act>`, `<meta>`, `<FRBRalias name="short">` (title present)
- Has `<body>` with at least one child element (not empty act)
- File path matches `{act_type}/{year}/{slug}/expressions/{date}.bul.xml`
- ELI in `FRBRalias[@name='eli' other='...']` matches path components (act_type, year, slug)

**Issue codes:**

| Code | Severity | Meaning |
|------|----------|---------|
| `MALFORMED_XML` | error | File is not valid XML |
| `MISSING_TITLE` | error | `FRBRalias name="short"` absent |
| `EMPTY_BODY` | error | `<body>` has no child elements |
| `BAD_PATH` | warn | File path doesn't match `{type}/{year}/{slug}/expressions/{date}.bul.xml` |
| `ELI_MISMATCH` | warn | ELI embedded in XML doesn't match file path |

---

## Layer 3 — Classification Sanity

**Input:** `FRBRalias[@name='short']` title from each fixture  
**Method:** call existing `detect_act_type(title)` and compare to directory `act_type`

**Reshenie subtype checks** — if directory is `reshenie_*`, verify the title's issuing body matches:
- `Решение` + КЕВР/ДКЕВР suffix codes → `reshenie_kevr`
- `Решение` + КФН suffix codes → `reshenie_kfn`
- `Решение` + РД-НС prefix → `reshenie_nhif`
- `Решение` + МС concession keywords → `reshenie_ms`
- `Решение за` / `Решение на Народното събрание` → `reshenie_ns`

**Issue codes:**

| Code | Severity | Meaning |
|------|----------|---------|
| `TYPE_MISMATCH` | error | `detect_act_type(title)` returns X, directory says Y |
| `UNDETECTED` | warn | Title returns `_other` — could not classify |
| `RESHENIE_WRONG_BODY` | error | Reshenie subtype doesn't match issuing body in title |

---

## Layer 4 — DB Coverage + Duplicate Detection

### 4a — Coverage

**Checks:**
- Per `act_type`: fixture XML count vs DB work count — flag any type present in fixtures but absent in DB entirely
- Per fixture: look up `(dv_broy, dv_year, dv_position)` in DB — flag if not found
- DB works with 0 elements (expression loaded but parser produced nothing)

**Issue codes:**

| Code | Severity | Meaning |
|------|----------|---------|
| `TYPE_NOT_IN_DB` | error | Act type has fixtures but 0 DB rows |
| `FIXTURE_NOT_LOADED` | error | Fixture coordinates not found in DB |
| `ZERO_ELEMENTS` | warn | Work in DB has 0 parsed elements |

**Known gaps at time of writing:**
- `reshenie_kevr`: 81 fixtures, 0 DB rows
- `reshenie_kfn`: 139 fixtures, 0 DB rows
- `reshenie_nhif`: 16 fixtures, 0 DB rows
- `zakon`: 794 fixtures vs 653 DB rows (141 gap)
- `zid`: 2,209 vs 1,891 (318 gap)
- `reshenie_ms`: 613 vs 248 (365 gap)

### 4b — Duplicate / Fragment Detection

**Method:** group DB works by `(dv_broy, dv_year, act_type)`. For groups with > threshold entries, compare titles with fuzzy similarity.

**Thresholds (configurable):**
- `zakon`, `kodeks`, `byudjet`, `konstitutsiya`: flag if > 3 per issue
- `naredba`, `pravilnik`, `postanovlenie`, `zid`, `ratifikatsiya`: flag if > 8 per issue
- `reshenie_*`: flag if > 15 per issue

**Fragment heuristic:** within a flagged group, if two titles share a long common prefix (> 60% of the shorter title), flag as probable parser fragment — the RTF splitter split one act at an internal heading.

**Position gap heuristic:** positions within a same-issue same-type group are expected to be densely packed (1,2,3,...). Large even gaps (2,4,8,10) suggest the position is being read from page numbers rather than sequential counters — flag for parser review.

**Issue codes:**

| Code | Severity | Meaning |
|------|----------|---------|
| `ISSUE_OVERCOUNT` | warn | More acts of this type than threshold for one DV issue |
| `PROBABLE_FRAGMENT` | error | Two works share title prefix — likely one act split by parser |
| `POSITION_GAPS` | warn | Non-sequential positions in same issue — page-number vs counter confusion |

**Follow-on:** any DV issue flagged by 4b should be reviewed in `dv_to_akn.py` — specifically the body-split and TOC-matching logic in `scraper/rtf_parser.py`.

---

## Layer 5 — ELI Structure Analysis (informational only)

**No errors or warnings — INFO only.**

**Current scheme:** `/eli/bg/{act_type}/{year}/dv-{broy}-{2digit_year}-{position}`

**Checks / reports:**
- Slug pattern consistency — are all slugs `dv-{N}-{NN}-{N}` or are any handcrafted?
- Per act type: how many works have a parseable official number in their title (e.g. `Постановление № 42`, `Наредба № Н-8`)
- Report count of works where `work.number` is NULL vs populated

**Recommendation (recorded in report):**
Keep current slugs — they are stable, derivable from DV coordinates, and should not change once published. For human-readable display and search, populate the existing `work.number` DB field for act types that carry official numbers (postanovlenie, naredba, pravilnik, reshenie_*). This is already in the schema and requires a backfill pass, not a URI change.

**Follow-on (separate design):** `?format=json` API response schema — richer JSON for programmatic consumers.

---

## Output

Terminal (default): section headers per layer, counts, first 20 issues per category (all with `--verbose`). Final line: `{N} errors, {M} warnings — exit 1` or `all checks passed — exit 0`.

JSON (`--json PATH`): full `LayerResult` tree as above.

---

## Out of Scope

- `?format=json` API response schema (separate design)
- Parser fixes (follow-on after running validate and reviewing flagged issues)
- Cross-reference extraction
- Consolidation engine
