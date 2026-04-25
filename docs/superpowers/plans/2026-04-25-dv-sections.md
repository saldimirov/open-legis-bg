# DV Sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store and display both official and unofficial sections of every DV issue, with tabbed navigation and inline expand for unofficial items.

**Architecture:** New `dv_item` table indexes every DV material (official acts link to `Work`, unofficial store body inline). RTF scraper gains section/category tracking and emits JSON fixtures for unofficial items. Loader populates `dv_item` from both sources. UI shows tabs per section, grouped by sub-section.

**Tech Stack:** SQLAlchemy + Alembic, Python regex, Jinja2 + Tailwind + vanilla JS tabs

---

## File Map

| File | Change |
|---|---|
| `src/open_legis/model/schema.py` | Add `DvItem` model + back-ref on `Work` |
| `src/open_legis/model/alembic/versions/0011_dv_item_table.py` | New migration |
| `src/open_legis/scraper/rtf_parser.py` | `_clean_body`, `_strip_dv_page_headers`, `_strip_word_metadata`; extend `_split_acts` with section/category tracking |
| `src/open_legis/scraper/batch.py` | Handle new 4-tuple; write unofficial JSON fixtures |
| `src/open_legis/loader/cli.py` | `_upsert_dv_items_official` + `_load_unofficial_fixtures` passes |
| `src/open_legis/api/routes_ui.py` | `dv_issue` queries `dv_item`, groups by section/category |
| `src/open_legis/api/templates/dv_issue.html` | Tabs + grouped sub-sections + inline expand |
| `tests/test_dv_cleaning.py` | Unit tests for body cleaning functions |
| `tests/test_rtf_parser_sections.py` | Unit tests for section/category tracking |
| `tests/test_dv_item_loader.py` | Integration tests for dv_item population |

---

## Task 1: DvItem model + migration

**Files:**
- Modify: `src/open_legis/model/schema.py`
- Create: `src/open_legis/model/alembic/versions/0011_dv_item_table.py`
- Test: `tests/test_model_schema.py` (extend existing)

- [ ] **Step 1: Write failing test**

Add to `tests/test_model_schema.py`:

```python
def test_dv_item_model(session, engine):
    from open_legis.model.schema import Base, DvItem
    import uuid
    Base.metadata.create_all(engine)
    item = DvItem(
        dv_year=2026, dv_broy=36, dv_position=1,
        section="official", category="НАРОДНО СЪБРАНИЕ",
        title="Закон за тест", body=None, work_id=None,
    )
    session.add(item)
    session.commit()
    fetched = session.get(DvItem, item.id)
    assert fetched.section == "official"
    assert fetched.category == "НАРОДНО СЪБРАНИЕ"
```

- [ ] **Step 2: Run test — verify it fails**

```bash
DATABASE_URL=postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis uv run pytest tests/test_model_schema.py::test_dv_item_model -v
```
Expected: `ImportError: cannot import name 'DvItem'`

- [ ] **Step 3: Add DvItem to schema.py**

At the end of `src/open_legis/model/schema.py`, before the last model (after the `ExternalId` class), add:

```python
class DvItem(Base):
    __tablename__ = "dv_item"
    __table_args__ = (UniqueConstraint("dv_year", "dv_broy", "dv_position"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    dv_year: Mapped[int] = mapped_column(Integer, nullable=False)
    dv_broy: Mapped[int] = mapped_column(Integer, nullable=False)
    dv_position: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    work_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work.id", ondelete="SET NULL"),
        nullable=True,
    )

    work: Mapped[Optional["Work"]] = relationship("Work", back_populates="dv_items")
```

Also add the back-reference to `Work` (around line 144, after `external_ids` relationship):

```python
    dv_items: Mapped[list["DvItem"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )
```

- [ ] **Step 4: Run test — verify it passes**

```bash
DATABASE_URL=postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis uv run pytest tests/test_model_schema.py::test_dv_item_model -v
```
Expected: PASS

- [ ] **Step 5: Create migration**

Create `src/open_legis/model/alembic/versions/0011_dv_item_table.py`:

```python
"""dv_item table

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dv_item",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dv_year", sa.Integer(), nullable=False),
        sa.Column("dv_broy", sa.Integer(), nullable=False),
        sa.Column("dv_position", sa.Integer(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("work_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["work_id"], ["work.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dv_year", "dv_broy", "dv_position"),
    )
    op.create_index("ix_dv_item_issue", "dv_item", ["dv_year", "dv_broy"])


def downgrade() -> None:
    op.drop_index("ix_dv_item_issue", "dv_item")
    op.drop_table("dv_item")
```

- [ ] **Step 6: Apply migration + verify**

```bash
DATABASE_URL=postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis uv run alembic upgrade head
```
Expected: `Running upgrade 0010 -> 0011`

- [ ] **Step 7: Commit**

```bash
git add src/open_legis/model/schema.py src/open_legis/model/alembic/versions/0011_dv_item_table.py tests/test_model_schema.py
git commit -m "feat(model): add DvItem table — unified index of all DV materials"
```

---

## Task 2: Body text cleaning

**Files:**
- Modify: `src/open_legis/scraper/rtf_parser.py`
- Create: `tests/test_dv_cleaning.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_dv_cleaning.py`:

```python
"""Unit tests for DV body text cleaning functions."""
from open_legis.scraper.rtf_parser import _strip_dv_page_headers, _strip_word_metadata, _clean_body


def test_strip_dv_page_header_basic():
    lines = [
        "Текст преди",
        "Държавен вестник",
        "Министерство на вътрешните работи          брой: 17, от дата 13.2.2026 г.   Официален раздел / МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА    стр.47",
        "Текст след",
    ]
    assert _strip_dv_page_headers(lines) == ["Текст преди", "Текст след"]


def test_strip_dv_page_header_drops_orphaned_institution_line():
    lines = [
        "Текст преди",
        "Държавен вестник",
        "Президент на Републиката          брой: 36, от дата 17.4.2026 г.   Официален раздел / ПРЕЗИДЕНТ НА РЕПУБЛИКАТА    стр.2",
        "МИНИСТЕРСТВО НА ВЪТРЕШНИТЕ РАБОТИ",
        "Текст след",
    ]
    result = _strip_dv_page_headers(lines)
    assert result == ["Текст преди", "Текст след"]


def test_strip_dv_page_header_multiple():
    lines = [
        "Ред 1",
        "Държавен вестник",
        "Народно събрание          брой: 99, от дата 1.12.2025 г.   Официален раздел / НАРОДНО СЪБРАНИЕ    стр.1",
        "Ред 2",
        "Държавен вестник",
        "Народно събрание          брой: 99, от дата 1.12.2025 г.   Официален раздел / НАРОДНО СЪБРАНИЕ    стр.5",
        "Ред 3",
    ]
    assert _strip_dv_page_headers(lines) == ["Ред 1", "Ред 2", "Ред 3"]


def test_strip_dv_page_header_no_match():
    lines = ["Нормален текст", "Без заглавие на страница"]
    assert _strip_dv_page_headers(lines) == lines


def test_strip_word_metadata_block():
    lines = [
        "Нормален текст преди",
        "800x600",
        "Normal",
        "0",
        "21",
        "false",
        "false",
        "false",
        "BG",
        "X-NONE",
        "X-NONE",
        "MicrosoftInternetExplorer4",
        "Нормален текст след",
    ]
    assert _strip_word_metadata(lines) == ["Нормален текст преди", "Нормален текст след"]


def test_strip_word_metadata_no_match():
    lines = ["Нормален текст", "800 апартамента", "Нещо друго"]
    assert _strip_word_metadata(lines) == lines


def test_clean_body_strips_both():
    lines = [
        "ЗАКОН ЗА НЕЩО",
        "Държавен вестник",
        "НС          брой: 1, от дата 1.1.2026 г.   Официален раздел / НАРОДНО СЪБРАНИЕ    стр.1",
        "800x600",
        "Normal",
        "0",
        "false",
        "BG",
        "X-NONE",
        "X-NONE",
        "MicrosoftInternetExplorer4",
        "Текст на закона",
    ]
    result = _clean_body(lines)
    assert result == ["ЗАКОН ЗА НЕЩО", "Текст на закона"]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_dv_cleaning.py -v
```
Expected: `ImportError: cannot import name '_strip_dv_page_headers'`

- [ ] **Step 3: Implement cleaning functions in rtf_parser.py**

Add these functions to `src/open_legis/scraper/rtf_parser.py` after the `_SKIP_HEADERS` pattern (around line 40):

```python
_DV_HEADER_LINE2 = re.compile(r"брой:\s*\d+.*стр\.\s*\d+", re.IGNORECASE)
_WORD_BLOCK_START = re.compile(r"^\d+x\d+$")


def _strip_dv_page_headers(lines: list[str]) -> list[str]:
    result: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "Държавен вестник" and i + 1 < len(lines):
            if _DV_HEADER_LINE2.search(lines[i + 1]):
                i += 2
                if i < len(lines) and _SKIP_HEADERS.match(lines[i].strip()):
                    i += 1
                continue
        result.append(lines[i])
        i += 1
    return result


def _strip_word_metadata(lines: list[str]) -> list[str]:
    result: list[str] = []
    i = 0
    while i < len(lines):
        if _WORD_BLOCK_START.match(lines[i].strip()):
            j = i + 1
            while j < min(i + 20, len(lines)):
                if "MicrosoftInternetExplorer4" in lines[j]:
                    i = j + 1
                    break
                j += 1
            else:
                result.append(lines[i])
                i += 1
            continue
        result.append(lines[i])
        i += 1
    return result


def _clean_body(lines: list[str]) -> list[str]:
    lines = _strip_dv_page_headers(lines)
    lines = _strip_word_metadata(lines)
    return lines
```

- [ ] **Step 4: Call `_clean_body` in `parse_rtf`**

In `parse_rtf` (line ~63), replace `lines = text.splitlines()` with:

```python
    lines = _clean_body(text.splitlines())
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/test_dv_cleaning.py -v
```
Expected: 7 tests PASS

- [ ] **Step 6: Run full suite — no regressions**

```bash
uv run pytest tests/ -x -q
```
Expected: all pass (or same failures as before this task)

- [ ] **Step 7: Commit**

```bash
git add src/open_legis/scraper/rtf_parser.py tests/test_dv_cleaning.py
git commit -m "feat(scraper): strip DV page headers and Word metadata artifacts from body text"
```

---

## Task 3: RTF parser section/category tracking

**Files:**
- Modify: `src/open_legis/scraper/rtf_parser.py`
- Create: `tests/test_rtf_parser_sections.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_rtf_parser_sections.py`:

```python
"""Unit tests for section/category tracking in _split_acts."""
from open_legis.scraper.rtf_parser import _split_acts


_LONG_BODY = " думи за изпълнение на теста" * 5  # > 80 chars


def test_official_section_tagged():
    lines = [
        "ОФИЦИАЛЕН РАЗДЕЛ",
        "НАРОДНО СЪБРАНИЕ",
        f"ЗАКОН за нещо важно{_LONG_BODY}",
    ]
    results = _split_acts(lines, [])
    assert len(results) == 1
    title, body, section, category = results[0]
    assert section == "official"


def test_unofficial_section_tagged():
    body_text = "Съобщение от съда за дело номер 123" + _LONG_BODY
    lines = [
        "ОФИЦИАЛЕН РАЗДЕЛ",
        f"ЗАКОН за нещо{_LONG_BODY}",
        "НЕОФИЦИАЛЕН РАЗДЕЛ",
        "СЪОБЩЕНИЯ",
        body_text,
        "",
    ]
    results = _split_acts(lines, [])
    official = [r for r in results if r[2] == "official"]
    unofficial = [r for r in results if r[2] == "unofficial"]
    assert len(official) >= 1
    assert len(unofficial) >= 1


def test_unofficial_category_captured():
    body_text = "Покана за участие в търг за доставка на нещо" + _LONG_BODY
    lines = [
        "НЕОФИЦИАЛЕН РАЗДЕЛ",
        "ПОКАНИ",
        body_text,
        "",
    ]
    results = _split_acts(lines, [])
    assert len(results) == 1
    _, _, section, category = results[0]
    assert section == "unofficial"
    assert category is not None
    assert "Покани" in category or "ПОКАНИ" in category


def test_default_section_is_official():
    """Content before any section header defaults to official."""
    lines = [f"ЗАКОН за нещо{_LONG_BODY}"]
    results = _split_acts(lines, [])
    assert all(r[2] == "official" for r in results)


def test_section_switch_mid_document():
    body_text = "Обявление за публична продан" + _LONG_BODY
    lines = [
        "ОФИЦИАЛЕН РАЗДЕЛ",
        f"НАРЕДБА № 1 за нещо{_LONG_BODY}",
        "НЕОФИЦИАЛЕН РАЗДЕЛ",
        "ОБЯВЛЕНИЯ",
        body_text,
        "",
    ]
    results = _split_acts(lines, [])
    sections = {r[2] for r in results}
    assert "official" in sections
    assert "unofficial" in sections
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_rtf_parser_sections.py -v
```
Expected: `TypeError` or assertion errors (returns 2-tuples, not 4-tuples)

- [ ] **Step 3: Rewrite `_split_acts` with section tracking**

Replace the entire `_split_acts` function in `src/open_legis/scraper/rtf_parser.py` (lines ~83–138):

```python
def _split_acts(
    body_lines: list[str], toc_titles: list[str]
) -> list[tuple[str, str, str, str | None]]:
    """Split body lines into materials, tagging each with (title, body, section, category)."""
    current_section: str = "official"
    current_category: str | None = None

    official_splits: list[tuple[int, str]] = []
    unofficial_items: list[tuple[str, str, str, str | None]] = []

    i = 0
    while i < len(body_lines):
        line = body_lines[i].strip()

        if line == "ОФИЦИАЛЕН РАЗДЕЛ":
            current_section = "official"
            current_category = None
            i += 1
            continue
        if line == "НЕОФИЦИАЛЕН РАЗДЕЛ":
            current_section = "unofficial"
            current_category = None
            i += 1
            continue

        if current_section == "unofficial":
            if _SKIP_HEADERS.match(line):
                current_category = line.title()
                i += 1
                continue
            if not line:
                i += 1
                continue
            # Collect paragraph block (blank-line delimited)
            block: list[str] = []
            while i < len(body_lines) and body_lines[i].strip():
                block.append(body_lines[i].strip())
                i += 1
            if block:
                full_text = " ".join(block)
                if len(full_text) >= 80:
                    unofficial_items.append(
                        (block[0], " ".join(block[1:]) or block[0], "unofficial", current_category)
                    )
        else:
            if _CAPS_ACT.match(line) and not _SKIP_HEADERS.match(line):
                heading_parts = [line]
                j = i + 1
                while j < len(body_lines):
                    next_line = body_lines[j].strip()
                    if not next_line:
                        break
                    if re.match(r"^(за |относно |и |на |от )", next_line, re.IGNORECASE):
                        heading_parts.append(next_line)
                        j += 1
                    else:
                        break
                official_splits.append((i, " ".join(heading_parts)))
                i = j
            else:
                i += 1

    # Process official splits into (title, body, section, category) tuples
    official_items: list[tuple[str, str, str, str | None]] = []
    for idx, (line_idx, caps_heading) in enumerate(official_splits):
        end_line = official_splits[idx + 1][0] if idx + 1 < len(official_splits) else len(body_lines)
        body_chunk = _clean("\n".join(body_lines[line_idx:end_line]))
        title = _match_toc_title(caps_heading, toc_titles) or _normalise_heading(caps_heading)
        body = body_chunk
        if body.startswith(caps_heading):
            body = body[len(caps_heading):].lstrip(" \n")
        elif body.lower().startswith(title[:30].lower()):
            body = body[len(title):].lstrip(" \n")
        official_items.append((title, body, "official", None))

    # Merge consecutive same-title official items
    merged: list[tuple[str, str, str, str | None]] = []
    for title, body, section, category in official_items:
        if merged and merged[-1][0] == title:
            prev = merged[-1]
            merged[-1] = (title, (prev[1] + " " + body).strip(), section, category)
        else:
            merged.append((title, body, section, category))

    merged = [(t, b, s, c) for t, b, s, c in merged if len(b) >= 80]

    return merged + unofficial_items
```

- [ ] **Step 4: Update `parse_rtf` return type annotation**

Change line `def parse_rtf(path: Path) -> list[tuple[str, str]]:` to:

```python
def parse_rtf(path: Path) -> list[tuple[str, str, str, str | None]]:
```

Change line `def parse_local_issue(path: Path) -> list[tuple[str, str]]:` to:

```python
def parse_local_issue(path: Path) -> list[tuple[str, str, str, str | None]]:
```

Also update `parse_pdf` return annotation the same way (PDF materials will have `section="official"`, `category=None` by default since `_split_acts` is also used there).

- [ ] **Step 5: Run section tests — verify they pass**

```bash
uv run pytest tests/test_rtf_parser_sections.py -v
```
Expected: 5 tests PASS

- [ ] **Step 6: Run full suite — no regressions**

```bash
uv run pytest tests/ -x -q
```
Expected: same pass/fail as before this task (batch tests may now fail — that's expected, will be fixed in Task 4)

- [ ] **Step 7: Commit**

```bash
git add src/open_legis/scraper/rtf_parser.py tests/test_rtf_parser_sections.py
git commit -m "feat(scraper): track official/unofficial section and category per material"
```

---

## Task 4: Batch — emit unofficial JSON fixtures

**Files:**
- Modify: `src/open_legis/scraper/batch.py`
- Create: `tests/test_scraper_batch.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_scraper_batch.py`:

```python
"""Tests for batch scraper: unofficial JSON fixture emission."""
import json
from pathlib import Path
from unittest.mock import patch

from open_legis.scraper.batch import process_issue_local
from open_legis.scraper.dv_client import DvIssue


_LONG_BODY = " думи за пълнеж" * 8  # > 80 chars


def _make_fake_materials():
    return [
        ("Закон за нещо важно" + _LONG_BODY, "Текст на закона" + _LONG_BODY, "official", None),
        ("Съобщение от съда за дело 123" + _LONG_BODY, "Подробности за делото" + _LONG_BODY, "unofficial", "Съобщения"),
    ]


def test_process_issue_local_emits_unofficial_json(tmp_path):
    issue = DvIssue(idObj=1, broy=36, year=2026, date="2026-04-17")
    out_root = tmp_path / "fixtures"
    local_rtf = tmp_path / "dv-36-26.rtf"
    local_rtf.write_bytes(b"fake rtf")

    with patch("open_legis.scraper.batch.parse_local_issue", return_value=_make_fake_materials()):
        with patch("open_legis.scraper.batch.convert_material") as mock_convert:
            mock_convert.return_value = ("dv-36-26-1", "<xml/>")
            saved, skipped, logs = process_issue_local(
                issue_tuple=(1, 36, 2026, "2026-04-17"),
                local_path_str=str(local_rtf),
                allowed_types={"zakon", "zid", "kodeks", "naredba", "postanovlenie",
                               "pravilnik", "reshenie", "ukaz", "ratifikatsiya",
                               "byudjet", "konstitutsiya"},
                out_root_str=str(out_root),
                resume=False,
            )

    json_files = list((out_root / "dv-unofficial" / "2026").glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    assert data["section"] == "unofficial"
    assert data["category"] == "Съобщения"
    assert data["dv_year"] == 2026
    assert data["dv_broy"] == 36


def test_process_issue_local_no_unofficial_json_when_all_official(tmp_path):
    issue_tuple = (1, 36, 2026, "2026-04-17")
    out_root = tmp_path / "fixtures"
    local_rtf = tmp_path / "dv-36-26.rtf"
    local_rtf.write_bytes(b"fake rtf")

    official_only = [
        ("Закон за нещо" + _LONG_BODY, "Текст" + _LONG_BODY, "official", None),
    ]
    with patch("open_legis.scraper.batch.parse_local_issue", return_value=official_only):
        with patch("open_legis.scraper.batch.convert_material") as mock_convert:
            mock_convert.return_value = ("dv-36-26-1", "<xml/>")
            process_issue_local(
                issue_tuple=issue_tuple,
                local_path_str=str(local_rtf),
                allowed_types={"zakon"},
                out_root_str=str(out_root),
                resume=False,
            )

    unofficial_dir = out_root / "dv-unofficial"
    assert not unofficial_dir.exists() or not list(unofficial_dir.rglob("*.json"))
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_scraper_batch.py -v
```
Expected: `TypeError: cannot unpack non-iterable` or similar (old 2-tuple unpacking)

- [ ] **Step 3: Rewrite `process_issue_local` in batch.py**

Replace entire `src/open_legis/scraper/batch.py` content:

```python
"""Top-level worker functions for parallel scraping with ProcessPoolExecutor."""
from __future__ import annotations


def process_issue_local(
    issue_tuple: tuple,
    local_path_str: str,
    allowed_types: set[str],
    out_root_str: str,
    resume: bool,
) -> tuple[int, int, list[str]]:
    """Parse one DV issue from a local RTF file and write AKN + unofficial JSON fixtures."""
    import json
    from pathlib import Path

    from open_legis.scraper.dv_client import DvIssue
    from open_legis.scraper.rtf_parser import parse_local_issue
    from open_legis.scraper.dv_to_akn import detect_act_type, convert_material

    idObj, broy, year, date = issue_tuple
    issue = DvIssue(idObj=idObj, broy=broy, year=year, date=date)
    local_path = Path(local_path_str)
    out_root = Path(out_root_str)

    logs: list[str] = []
    saved = skipped = 0

    try:
        raw_materials = parse_local_issue(local_path)
    except Exception as exc:
        return 0, 0, [f"  ERROR parsing {local_path.name}: {exc}"]

    if not raw_materials:
        return 0, 0, []

    # Separate official and unofficial, dedup each independently
    seen_official: dict[tuple[str, str], tuple[int, str]] = {}
    seen_unofficial: dict[str, tuple[int, str, str | None]] = {}

    for position, (title, body, section, category) in enumerate(raw_materials, start=1):
        if not title:
            continue
        if section == "unofficial":
            key = title.strip().lower()[:120]
            if key not in seen_unofficial or len(body) > len(seen_unofficial[key][1]):
                seen_unofficial[key] = (position, body, category)
        else:
            act_type, _ = detect_act_type(title)
            if act_type not in allowed_types:
                continue
            key = (act_type, title.strip().lower()[:120])
            if key not in seen_official or len(body) > len(seen_official[key][1]):
                seen_official[key] = (position, body)

    # Write official AKN fixtures
    for (act_type, _), (position, body) in seen_official.items():
        title = raw_materials[position - 1][0]
        try:
            slug, xml = convert_material(
                title=title, body=body, idMat=0,
                issue=issue, position=position,
            )
        except Exception as exc:
            logs.append(f"  ERROR converting {title[:50]!r}: {exc}")
            continue

        expr_dir = out_root / act_type / str(issue.year) / slug / "expressions"
        akn_path = expr_dir / f"{issue.date}.bul.xml"

        if resume and akn_path.exists():
            skipped += 1
            continue

        expr_dir.mkdir(parents=True, exist_ok=True)
        akn_path.write_text(xml, encoding="utf-8")
        logs.append(f"  + {act_type}: {title[:65]}")
        saved += 1

    # Write unofficial JSON fixtures
    for _key, (position, body, category) in seen_unofficial.items():
        title = raw_materials[position - 1][0]
        unofficial_dir = out_root / "dv-unofficial" / str(issue.year)
        json_path = unofficial_dir / f"{issue.broy:03d}-{position}.json"

        if resume and json_path.exists():
            skipped += 1
            continue

        unofficial_dir.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps({
                "dv_year": issue.year,
                "dv_broy": issue.broy,
                "dv_position": position,
                "section": "unofficial",
                "category": category,
                "title": title,
                "body": body,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logs.append(f"  + unofficial [{category or '?'}]: {title[:65]}")

    return saved, skipped, logs
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_scraper_batch.py -v
```
Expected: 2 tests PASS

- [ ] **Step 5: Run full suite — no regressions**

```bash
uv run pytest tests/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add src/open_legis/scraper/batch.py tests/test_scraper_batch.py
git commit -m "feat(scraper): emit unofficial JSON fixtures alongside AKN fixtures"
```

---

## Task 5: Loader — populate dv_item

**Files:**
- Modify: `src/open_legis/loader/cli.py`
- Create: `tests/test_dv_item_loader.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_dv_item_loader.py`:

```python
"""Integration tests for dv_item population in the loader."""
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine


@pytest.fixture
def fresh_db(pg_url, tmp_path, monkeypatch):
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
    yield eng
    m.Base.metadata.drop_all(eng)
    eng.dispose()


def _write_minimal_fixture(root: Path, act_type: str = "zakon") -> None:
    """Write a minimal AKN fixture to tmp_path."""
    from tests.test_loader_integration import _write_fixture  # reuse helper if it exists
    slug = "dv-99-25-1"
    expr_dir = root / act_type / "2025" / slug / "expressions"
    expr_dir.mkdir(parents=True)
    akn = expr_dir / "2025-12-15.bul.xml"
    akn.write_text(
        '<?xml version="1.0"?>'
        '<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">'
        '<act name="zakon"><meta><identification source="#source">'
        '<FRBRWork><FRBRthis value="/eli/bg/zakon/2025/dv-99-25-1"/>'
        '<FRBRuri value="/eli/bg/zakon/2025/dv-99-25-1"/>'
        '<FRBRdate date="2025-12-01" name="Generation"/>'
        '<FRBRauthor href="#issuer"/>'
        '<FRBRcountry value="bg"/>'
        '</FRBRWork>'
        '<FRBRExpression><FRBRthis value="/eli/bg/zakon/2025/dv-99-25-1/bul@2025-12-15"/>'
        '<FRBRuri value="/eli/bg/zakon/2025/dv-99-25-1/bul@2025-12-15"/>'
        '<FRBRdate date="2025-12-15" name="Generation"/>'
        '<FRBRauthor href="#issuer"/>'
        '<FRBRlanguage language="bul"/>'
        '</FRBRExpression>'
        '<FRBRManifestation><FRBRthis value="/eli/bg/zakon/2025/dv-99-25-1/bul@2025-12-15/xml"/>'
        '<FRBRuri value="/eli/bg/zakon/2025/dv-99-25-1/bul@2025-12-15/xml"/>'
        '<FRBRdate date="2025-12-15" name="Generation"/>'
        '<FRBRauthor href="#issuer"/>'
        '</FRBRManifestation>'
        '</identification>'
        '<publication date="2025-12-15" name="Official Gazette" number="99" showAs="ДВ бр. 99/2025"/>'
        '<references source="#source">'
        '<TLCOrganization eId="issuer" href="/ontology/organization/bg/ns" showAs="Народното събрание"/>'
        '</references>'
        '</meta>'
        '<body><section eId="sec_1"><content><p>Текст.</p></content></section></body>'
        '</act></akomaNtoso>',
        encoding="utf-8",
    )


def test_load_creates_dv_item_for_work(fresh_db, tmp_path):
    _write_minimal_fixture(tmp_path)
    load_directory(tmp_path, fresh_db)

    with Session(fresh_db) as s:
        items = s.scalars(select(m.DvItem)).all()
    assert len(items) == 1
    assert items[0].section == "official"
    assert items[0].work_id is not None


def test_load_unofficial_json_creates_dv_item(fresh_db, tmp_path):
    unofficial_dir = tmp_path / "dv-unofficial" / "2025"
    unofficial_dir.mkdir(parents=True)
    (unofficial_dir / "099-50.json").write_text(json.dumps({
        "dv_year": 2025, "dv_broy": 99, "dv_position": 50,
        "section": "unofficial", "category": "Съобщения",
        "title": "Съобщение за дело номер 123",
        "body": "Подробен текст на съобщението.",
    }), encoding="utf-8")

    load_directory(tmp_path, fresh_db)

    with Session(fresh_db) as s:
        items = s.scalars(
            select(m.DvItem).where(m.DvItem.section == "unofficial")
        ).all()
    assert len(items) == 1
    assert items[0].category == "Съобщения"
    assert items[0].body == "Подробен текст на съобщението."
    assert items[0].work_id is None


def test_load_idempotent_dv_items(fresh_db, tmp_path):
    _write_minimal_fixture(tmp_path)
    load_directory(tmp_path, fresh_db)
    load_directory(tmp_path, fresh_db)  # second load

    with Session(fresh_db) as s:
        count = s.scalars(select(m.DvItem)).all()
    assert len(count) == 1  # no duplicates
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
DATABASE_URL=postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis uv run pytest tests/test_dv_item_loader.py -v
```
Expected: tests fail (no dv_item rows created)

- [ ] **Step 3: Add issuer→category mapping and helper functions to `loader/cli.py`**

Add after the imports at the top of `src/open_legis/loader/cli.py`:

```python
import json as _json

_ISSUER_CATEGORY: dict[str, str] = {
    "ns": "НАРОДНО СЪБРАНИЕ",
    "president": "ПРЕЗИДЕНТ НА РЕПУБЛИКАТА",
    "ms": "МИНИСТЕРСКИ СЪВЕТ",
    "ks": "КОНСТИТУЦИОНЕН СЪД",
    "vas": "ВЪРХОВЕН АДМИНИСТРАТИВЕН СЪД",
    "vss": "МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА",
    "bnb": "МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА",
    "ministry": "МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА",
    "commission": "МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА",
    "agency": "МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА",
    "court": "МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА",
    "municipality": "МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА",
    "other": "МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА",
}
```

Add these two functions before `_recompute_is_latest`:

```python
def _upsert_dv_items_official(session: Session, works: list[m.Work]) -> int:
    count = 0
    for work in works:
        issuer_val = work.issuer.value if work.issuer else "other"
        category = _ISSUER_CATEGORY.get(issuer_val, "МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА")
        existing = session.scalars(
            select(m.DvItem).where(
                m.DvItem.dv_year == work.dv_year,
                m.DvItem.dv_broy == work.dv_broy,
                m.DvItem.dv_position == work.dv_position,
            )
        ).one_or_none()
        if existing is None:
            session.add(m.DvItem(
                dv_year=work.dv_year,
                dv_broy=work.dv_broy,
                dv_position=work.dv_position,
                section="official",
                category=category,
                title=work.title,
                body=None,
                work_id=work.id,
            ))
            count += 1
        else:
            existing.work_id = work.id
            existing.category = category
    return count


def _load_unofficial_fixtures(root: Path, session: Session) -> int:
    unofficial_dir = Path(root) / "dv-unofficial"
    if not unofficial_dir.exists():
        return 0
    count = 0
    for json_path in sorted(unofficial_dir.rglob("*.json")):
        try:
            data = _json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  SKIP {json_path}: {exc}", flush=True)
            continue
        existing = session.scalars(
            select(m.DvItem).where(
                m.DvItem.dv_year == data["dv_year"],
                m.DvItem.dv_broy == data["dv_broy"],
                m.DvItem.dv_position == data["dv_position"],
            )
        ).one_or_none()
        if existing is None:
            session.add(m.DvItem(
                dv_year=data["dv_year"],
                dv_broy=data["dv_broy"],
                dv_position=data["dv_position"],
                section=data.get("section", "unofficial"),
                category=data.get("category"),
                title=data["title"],
                body=data.get("body"),
                work_id=None,
            ))
            count += 1
    return count
```

- [ ] **Step 4: Call both passes from `load_directory`**

In `load_directory`, after `session.commit()` (around line 55), add:

```python
    # Pass 2: create dv_item rows for all loaded Works
    with Session(engine) as session:
        works = session.scalars(select(m.Work)).all()
        official_count = _upsert_dv_items_official(session, list(works))
        unofficial_count = _load_unofficial_fixtures(root, session)
        session.commit()
    print(f"DV items: {official_count} official, {unofficial_count} unofficial", flush=True)
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
DATABASE_URL=postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis uv run pytest tests/test_dv_item_loader.py -v
```
Expected: 3 tests PASS

- [ ] **Step 6: Run full suite**

```bash
uv run pytest tests/ -x -q
```

- [ ] **Step 7: Commit**

```bash
git add src/open_legis/loader/cli.py tests/test_dv_item_loader.py
git commit -m "feat(loader): populate dv_item for official acts and unofficial JSON fixtures"
```

---

## Task 6: UI — tabbed DV issue view

**Files:**
- Modify: `src/open_legis/api/routes_ui.py`
- Modify: `src/open_legis/api/templates/dv_issue.html`
- Create: `tests/test_api_dv_issue.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_api_dv_issue.py`:

```python
"""Tests for the DV issue view with sections and tabs."""
import pytest
from fastapi.testclient import TestClient


def test_dv_issue_shows_official_tab(client):
    resp = client.get("/dv/2025/99")
    # 404 if no data loaded — route must handle gracefully
    assert resp.status_code in (200, 404)


def test_dv_issue_tabs_present_when_data_exists(client, pg_url, tmp_path, monkeypatch):
    """Load a fixture + unofficial item, verify both tabs appear."""
    import json
    from pathlib import Path
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

    # Write minimal AKN fixture
    slug = "dv-99-25-1"
    expr_dir = tmp_path / "zakon" / "2025" / slug / "expressions"
    expr_dir.mkdir(parents=True)
    (expr_dir / "2025-12-15.bul.xml").write_text(
        '<?xml version="1.0"?>'
        '<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">'
        '<act name="zakon"><meta><identification source="#source">'
        '<FRBRWork><FRBRthis value="/eli/bg/zakon/2025/dv-99-25-1"/>'
        '<FRBRuri value="/eli/bg/zakon/2025/dv-99-25-1"/>'
        '<FRBRdate date="2025-12-01" name="Generation"/><FRBRauthor href="#issuer"/>'
        '<FRBRcountry value="bg"/></FRBRWork>'
        '<FRBRExpression><FRBRthis value="/eli/bg/zakon/2025/dv-99-25-1/bul@2025-12-15"/>'
        '<FRBRuri value="/eli/bg/zakon/2025/dv-99-25-1/bul@2025-12-15"/>'
        '<FRBRdate date="2025-12-15" name="Generation"/><FRBRauthor href="#issuer"/>'
        '<FRBRlanguage language="bul"/></FRBRExpression>'
        '<FRBRManifestation>'
        '<FRBRthis value="/eli/bg/zakon/2025/dv-99-25-1/bul@2025-12-15/xml"/>'
        '<FRBRuri value="/eli/bg/zakon/2025/dv-99-25-1/bul@2025-12-15/xml"/>'
        '<FRBRdate date="2025-12-15" name="Generation"/><FRBRauthor href="#issuer"/>'
        '</FRBRManifestation></identification>'
        '<publication date="2025-12-15" name="Official Gazette" number="99" showAs="ДВ бр. 99/2025"/>'
        '<references source="#source">'
        '<TLCOrganization eId="issuer" href="/ontology/organization/bg/ns" showAs="Народното събрание"/>'
        '</references></meta>'
        '<body><section eId="sec_1"><content><p>Текст.</p></content></section></body>'
        '</act></akomaNtoso>',
        encoding="utf-8",
    )

    # Write unofficial JSON
    unoff_dir = tmp_path / "dv-unofficial" / "2025"
    unoff_dir.mkdir(parents=True)
    (unoff_dir / "099-50.json").write_text(json.dumps({
        "dv_year": 2025, "dv_broy": 99, "dv_position": 50,
        "section": "unofficial", "category": "Съобщения",
        "title": "Съобщение за дело номер 123",
        "body": "Подробен текст.",
    }), encoding="utf-8")

    load_directory(tmp_path, eng)

    # Now query via test client
    from open_legis.api.app import create_app
    app = create_app()
    from sqlalchemy.orm import sessionmaker
    Sess = sessionmaker(bind=eng)
    from open_legis.api.db import get_session
    app.dependency_overrides[get_session] = lambda: Sess().__enter__()
    tc = TestClient(app)

    resp = tc.get("/dv/2025/99")
    assert resp.status_code == 200
    html = resp.text
    assert "Официален раздел" in html
    assert "Неофициален раздел" in html
    assert "Народно събрание" in html or "НАРОДНО СЪБРАНИЕ" in html
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run pytest tests/test_api_dv_issue.py::test_dv_issue_tabs_present_when_data_exists -v
```
Expected: FAIL (template doesn't have tabs yet)

- [ ] **Step 3: Update `dv_issue` route in routes_ui.py**

Replace the `dv_issue` function body (lines ~599–659) in `src/open_legis/api/routes_ui.py`:

```python
@router.get("/dv/{year}/{broy}", response_class=HTMLResponse)
def dv_issue(
    request: Request,
    year: int,
    broy: int,
    s: Session = Depends(get_session),
) -> HTMLResponse:
    from collections import defaultdict

    dv_items = s.scalars(
        select(m.DvItem)
        .where(m.DvItem.dv_year == year, m.DvItem.dv_broy == broy)
        .order_by(m.DvItem.dv_position)
    ).all()

    if not dv_items:
        raise HTTPException(status_code=404, detail="Брой не е намерен")

    # Eagerly load work for official items
    for item in dv_items:
        _ = item.work  # touch relationship

    _SECTION_LABELS = {
        "official": "Официален раздел",
        "unofficial": "Неофициален раздел",
    }
    _SECTION_ORDER = ["official", "unofficial"]

    # Group: section → category → list of item dicts
    raw: dict[str, dict[str | None, list[dict]]] = {}
    for item in dv_items:
        sec = raw.setdefault(item.section, {})
        cat_items = sec.setdefault(item.category, [])
        cat_items.append({
            "title": item.title,
            "body": item.body,
            "work_uri": item.work.eli_uri if item.work else None,
            "act_type": item.work.act_type.value if item.work else None,
            "adoption_date": item.work.adoption_date.isoformat() if item.work and item.work.adoption_date else None,
            "position": item.dv_position,
        })

    sections = [
        {
            "key": sec_key,
            "label": _SECTION_LABELS.get(sec_key, sec_key),
            "groups": [
                {"category": cat, "items": items}
                for cat, items in raw[sec_key].items()
            ],
        }
        for sec_key in _SECTION_ORDER
        if sec_key in raw
    ]

    official_count = sum(1 for i in dv_items if i.section == "official")
    unofficial_count = sum(1 for i in dv_items if i.section == "unofficial")

    # Prev/next issues
    prev_issue = s.execute(
        select(m.Work.dv_broy, m.Work.dv_year)
        .where(
            (m.Work.dv_year == year) & (m.Work.dv_broy < broy)
            | (m.Work.dv_year < year)
        )
        .order_by(m.Work.dv_year.desc(), m.Work.dv_broy.desc())
        .limit(1)
    ).first()
    next_issue = s.execute(
        select(m.Work.dv_broy, m.Work.dv_year)
        .where(
            (m.Work.dv_year == year) & (m.Work.dv_broy > broy)
            | (m.Work.dv_year > year)
        )
        .order_by(m.Work.dv_year.asc(), m.Work.dv_broy.asc())
        .limit(1)
    ).first()

    id_obj = _DV_ID_BY_ISSUE.get((year, broy))
    dv_source_url = f"{_DV_BASE}/showMaterialFiles.faces?idObj={id_obj}" if id_obj else None

    return templates.TemplateResponse(
        request,
        "dv_issue.html",
        _ctx(
            year=year,
            broy=broy,
            sections=sections,
            official_count=official_count,
            unofficial_count=unofficial_count,
            prev_issue={"year": prev_issue[1], "broy": prev_issue[0]} if prev_issue else None,
            next_issue={"year": next_issue[1], "broy": next_issue[0]} if next_issue else None,
            dv_source_url=dv_source_url,
        ),
    )
```

Also add `from sqlalchemy import select` at the top of the file if not present (check existing imports), and add `DvItem` to the model import:

```python
from open_legis.model import schema as m  # already there — just confirming DvItem is on m
```

- [ ] **Step 4: Rewrite `dv_issue.html`**

Replace entire `src/open_legis/api/templates/dv_issue.html`:

```html
{% extends "base.html" %}

{% block title %}ДВ бр. {{ broy }}/{{ year }}{% endblock %}

{% block content %}

<!-- Breadcrumb + nav -->
<div class="flex items-center justify-between mb-6">
  <nav class="flex items-center gap-2 text-sm text-gray-500">
    <a href="/dv" class="hover:text-blue-600">Държавен вестник</a>
    <span>/</span>
    <a href="/dv?year={{ year }}" class="hover:text-blue-600">{{ year }}</a>
    <span>/</span>
    <span class="text-gray-800 font-medium">бр. {{ broy }}</span>
  </nav>
  <div class="flex items-center gap-3 text-sm">
    {% if prev_issue %}
    <a href="/dv/{{ prev_issue.year }}/{{ prev_issue.broy }}"
       class="flex items-center gap-1 px-3 py-1.5 rounded border border-gray-200 text-gray-600 hover:border-blue-400 hover:text-blue-600 transition-colors">
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
      </svg>
      ДВ {{ prev_issue.broy }}/{{ prev_issue.year }}
    </a>
    {% endif %}
    {% if next_issue %}
    <a href="/dv/{{ next_issue.year }}/{{ next_issue.broy }}"
       class="flex items-center gap-1 px-3 py-1.5 rounded border border-gray-200 text-gray-600 hover:border-blue-400 hover:text-blue-600 transition-colors">
      ДВ {{ next_issue.broy }}/{{ next_issue.year }}
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
      </svg>
    </a>
    {% endif %}
  </div>
</div>

<!-- Header -->
<div class="mb-6 flex items-start justify-between gap-4">
  <div>
    <h1 class="text-2xl font-bold text-gray-800">
      Държавен вестник, бр. {{ broy }} от {{ year }} г.
    </h1>
    <p class="text-gray-500 text-sm mt-1">
      {{ official_count }} акта
      {% if unofficial_count %} · {{ unofficial_count }} известия{% endif %}
    </p>
  </div>
  {% if dv_source_url %}
  <a href="{{ dv_source_url }}" target="_blank" rel="noopener"
     class="shrink-0 flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800 border border-blue-200 hover:border-blue-400 rounded-lg px-3 py-1.5 transition-colors">
    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
        d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
    </svg>
    Оригинал в ДВ
  </a>
  {% endif %}
</div>

<!-- Tabs (only if more than one section) -->
{% if sections | length > 1 %}
<div class="flex gap-1 mb-4 border-b border-gray-200" id="dv-tabs">
  {% for sec in sections %}
  <button
    onclick="dvShowTab('{{ sec.key }}')"
    id="tab-btn-{{ sec.key }}"
    class="px-4 py-2 text-sm font-medium rounded-t-lg border border-b-0 transition-colors
           {% if loop.first %}bg-white border-gray-200 text-blue-700{% else %}bg-gray-50 border-transparent text-gray-500 hover:text-gray-700{% endif %}"
  >
    {{ sec.label }}
  </button>
  {% endfor %}
</div>
{% endif %}

<!-- Section panels -->
{% for sec in sections %}
<div id="tab-panel-{{ sec.key }}" class="{% if not loop.first %}hidden{% endif %}">
  {% for group in sec.groups %}
  <!-- Sub-section group -->
  {% if group.category %}
  <div class="mt-4 mb-2">
    <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 px-1">
      {{ group.category }}
    </h2>
  </div>
  {% endif %}
  <div class="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100 mb-4">
    {% for item in group.items %}
    {% if item.work_uri %}
    <!-- Official act — link to act page -->
    <a href="/ui{{ item.work_uri }}"
       class="flex items-start gap-4 px-5 py-4 hover:bg-gray-50 transition-colors group">
      <span class="text-xs text-gray-300 font-mono w-6 shrink-0 mt-0.5 text-right">{{ item.position }}</span>
      <div class="min-w-0 flex-1">
        <p class="text-sm text-gray-800 group-hover:text-blue-700 leading-snug">{{ item.title | fix_title }}</p>
        <div class="flex items-center gap-2 mt-1">
          {% if item.act_type %}
          <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium
            {% if item.act_type == 'zakon' %}bg-blue-50 text-blue-700
            {% elif item.act_type == 'zid' %}bg-rose-50 text-rose-700
            {% elif item.act_type == 'kodeks' %}bg-purple-50 text-purple-700
            {% elif item.act_type == 'naredba' %}bg-green-50 text-green-700
            {% elif item.act_type == 'postanovlenie' %}bg-yellow-50 text-yellow-700
            {% elif item.act_type == 'pravilnik' %}bg-orange-50 text-orange-700
            {% elif item.act_type == 'reshenie' %}bg-teal-50 text-teal-700
            {% elif item.act_type == 'ukaz' %}bg-gray-100 text-gray-600
            {% else %}bg-gray-100 text-gray-600{% endif %}">
            {{ type_labels.get(item.act_type, item.act_type) }}
          </span>
          {% endif %}
          {% if item.adoption_date %}
          <span class="text-xs text-gray-400">{{ item.adoption_date }}</span>
          {% endif %}
        </div>
      </div>
      <svg class="w-4 h-4 text-gray-300 shrink-0 mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
      </svg>
    </a>
    {% else %}
    <!-- Unofficial item — inline expand -->
    <details class="group/det px-5 py-4 hover:bg-gray-50 transition-colors">
      <summary class="flex items-start gap-4 cursor-pointer list-none">
        <span class="text-xs text-gray-300 font-mono w-6 shrink-0 mt-0.5 text-right">{{ item.position }}</span>
        <p class="text-sm text-gray-700 leading-snug flex-1">{{ item.title | fix_title }}</p>
        <svg class="w-4 h-4 text-gray-400 shrink-0 mt-0.5 transition-transform group-open/det:rotate-90"
             fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
        </svg>
      </summary>
      {% if item.body %}
      <div class="mt-3 ml-10 text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{{ item.body }}</div>
      {% endif %}
    </details>
    {% endif %}
    {% endfor %}
  </div>
  {% endfor %}
</div>
{% endfor %}

{% if sections | length > 1 %}
<script>
function dvShowTab(key) {
  document.querySelectorAll('[id^="tab-panel-"]').forEach(p => p.classList.add('hidden'));
  document.querySelectorAll('[id^="tab-btn-"]').forEach(b => {
    b.classList.remove('bg-white', 'border-gray-200', 'text-blue-700');
    b.classList.add('bg-gray-50', 'border-transparent', 'text-gray-500');
  });
  document.getElementById('tab-panel-' + key).classList.remove('hidden');
  var btn = document.getElementById('tab-btn-' + key);
  btn.classList.remove('bg-gray-50', 'border-transparent', 'text-gray-500');
  btn.classList.add('bg-white', 'border-gray-200', 'text-blue-700');
}
</script>
{% endif %}

{% endblock %}
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/test_api_dv_issue.py -v
```
Expected: 2 tests PASS

- [ ] **Step 6: Run full suite**

```bash
uv run pytest tests/ -x -q
```

- [ ] **Step 7: Commit**

```bash
git add src/open_legis/api/routes_ui.py src/open_legis/api/templates/dv_issue.html tests/test_api_dv_issue.py
git commit -m "feat(ui): tabbed DV issue view with official/unofficial sections and sub-section groups"
```

---

## Task 7: Push and verify

- [ ] **Step 1: Push to origin**

```bash
git push origin main
```

- [ ] **Step 2: On Mac — pull and run re-scrape**

```bash
git pull origin main
uv run open-legis scrape-dv-batch --workers 8
DATABASE_URL=... uv run open-legis load
```

- [ ] **Step 3: Spot-check the UI**

Open `http://localhost:8000/dv/2025/99` (or any issue known to have unofficial content). Verify:
- Two tabs appear when unofficial items exist
- Official tab shows sub-section groups (НАРОДНО СЪБРАНИЕ, МИНИСТЕРСКИ СЪВЕТ, etc.)
- Unofficial tab shows expandable items with body text
- Clicking a tab switches the panel
- Official items link to act pages correctly

---

## Self-Review Notes

- Migration `0011` depends on `0010` — verify `down_revision = "0010"` matches actual latest
- `_upsert_dv_items_official` runs a per-Work SELECT — acceptable for load (not hot path); could be batched later
- `parse_pdf` return type annotation updated but PDF files pre-2003 won't have section markers — all materials default to `section="official"`, `category=None` (correct behaviour)
- `dv_issue` route still queries `m.Work` for prev/next navigation — that's fine, those queries are issue-level not item-level
- The `details/summary` expand for unofficial items uses native HTML — no JS required, works with htmx
