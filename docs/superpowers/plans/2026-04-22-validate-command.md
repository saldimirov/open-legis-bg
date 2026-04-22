# Validate Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `open-legis validate` command that checks the full data pipeline (mirror → fixtures → DB) for coverage gaps, structural problems, misclassifications, fragments, and ELI consistency.

**Architecture:** New `src/open_legis/validate/` module with one file per layer, each returning a typed `LayerResult`. The CLI command in `cli.py` orchestrates all layers and renders a terminal report (or JSON file). Each layer is independently testable and can be run in isolation via `--layer`.

**Tech Stack:** Python stdlib (`json`, `re`, `difflib`, `dataclasses`), `lxml` (already in deps), `sqlalchemy` (raw `text()` queries), `typer` (CLI).

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/open_legis/validate/__init__.py` | `Issue` + `LayerResult` dataclasses |
| Create | `src/open_legis/validate/mirror.py` | Layer 1 — index vs local_dv |
| Create | `src/open_legis/validate/fixtures.py` | Layer 2 — XML validity + path structure |
| Create | `src/open_legis/validate/classify.py` | Layer 3 — act-type classification |
| Create | `src/open_legis/validate/db.py` | Layer 4 — DB coverage + dupe/fragment |
| Create | `src/open_legis/validate/eli.py` | Layer 5 — ELI analysis (informational) |
| Create | `src/open_legis/validate/report.py` | Terminal + JSON output |
| Modify | `src/open_legis/cli.py` | Add `validate` command |
| Create | `tests/test_validate_mirror.py` | Layer 1 tests |
| Create | `tests/test_validate_fixtures.py` | Layer 2 tests |
| Create | `tests/test_validate_classify.py` | Layer 3 tests |
| Create | `tests/test_validate_db.py` | Layer 4 tests |
| Create | `tests/test_validate_eli.py` | Layer 5 tests |
| Create | `tests/data/validate_valid.xml` | Correct AKN fixture for tests |

---

## Task 1: Data model + report module

**Files:**
- Create: `src/open_legis/validate/__init__.py`
- Create: `src/open_legis/validate/report.py`

- [ ] **Step 1: Write the failing import test**

```python
# tests/test_validate_mirror.py  (create this file now — will grow in later tasks)
from open_legis.validate import Issue, LayerResult


def test_issue_creation():
    issue = Issue(severity="error", code="MISSING_FILE", message="not found")
    assert issue.severity == "error"
    assert issue.code == "MISSING_FILE"
    assert issue.path is None


def test_layer_result_error_count():
    result = LayerResult(
        name="mirror",
        issues=[
            Issue("error", "MISSING_FILE", "gone"),
            Issue("warn", "TOO_SMALL", "tiny"),
        ],
        stats={"checked": 2},
    )
    errors = [i for i in result.issues if i.severity == "error"]
    assert len(errors) == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/loki/projects/gov/open-legis
uv run pytest tests/test_validate_mirror.py::test_issue_creation -v
```
Expected: `ModuleNotFoundError: No module named 'open_legis.validate'`

- [ ] **Step 3: Create the data model**

```python
# src/open_legis/validate/__init__.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Issue:
    severity: Literal["error", "warn", "info"]
    code: str
    message: str
    path: str | None = None
    detail: str | None = None


@dataclass
class LayerResult:
    name: str
    issues: list[Issue] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
```

- [ ] **Step 4: Create the report module**

```python
# src/open_legis/validate/report.py
from __future__ import annotations

import datetime
import json
from dataclasses import asdict

from open_legis.validate import LayerResult

_SEVERITY_PREFIX = {"error": "  ✗", "warn": "  !", "info": "  ·"}


def print_report(results: list[LayerResult], verbose: bool = False) -> int:
    """Print terminal report. Returns error count."""
    total_errors = 0
    total_warnings = 0

    for result in results:
        errors = [i for i in result.issues if i.severity == "error"]
        warnings = [i for i in result.issues if i.severity == "warn"]
        total_errors += len(errors)
        total_warnings += len(warnings)

        stats_str = "  ".join(f"{k}={v}" for k, v in result.stats.items())
        status = "OK" if not errors else f"{len(errors)} errors"
        print(f"\n── {result.name.upper()} ── {status}  {stats_str}")

        to_show = result.issues if verbose else result.issues[:20]
        for issue in to_show:
            line = f"{_SEVERITY_PREFIX[issue.severity]} [{issue.code}] {issue.message}"
            if issue.path:
                line += f"\n      {issue.path}"
            if issue.detail:
                line += f"\n      {issue.detail}"
            print(line)

        if not verbose and len(result.issues) > 20:
            print(f"  ... {len(result.issues) - 20} more (use --verbose to see all)")

    print(f"\n{'─' * 60}")
    print(f"Total: {total_errors} errors, {total_warnings} warnings")
    return total_errors


def write_json_report(results: list[LayerResult], path: str) -> None:
    report = {
        "run_at": datetime.datetime.now().isoformat(),
        "summary": {
            "errors": sum(len([i for i in r.issues if i.severity == "error"]) for r in results),
            "warnings": sum(len([i for i in r.issues if i.severity == "warn"]) for r in results),
            "layers_run": len(results),
        },
        "layers": [
            {
                "name": r.name,
                "stats": r.stats,
                "issues": [asdict(i) for i in r.issues],
            }
            for r in results
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_validate_mirror.py::test_issue_creation tests/test_validate_mirror.py::test_layer_result_error_count -v
```
Expected: both PASS

- [ ] **Step 6: Commit**

```bash
git add src/open_legis/validate/__init__.py src/open_legis/validate/report.py tests/test_validate_mirror.py
git commit -m "feat(validate): data model and report module"
```

---

## Task 2: Layer 1 — Mirror Coverage

**Files:**
- Create: `src/open_legis/validate/mirror.py`
- Modify: `tests/test_validate_mirror.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_validate_mirror.py`:

```python
import json
from pathlib import Path

from open_legis.validate.mirror import check_mirror


def _write_index(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries))


def test_mirror_all_present(tmp_path):
    idx = tmp_path / "index.json"
    mirror = tmp_path / "mirror"
    (mirror / "2024").mkdir(parents=True)
    (mirror / "2024" / "001-1234.rtf").write_bytes(b"x" * 2048)
    _write_index(idx, [{"year": 2024, "broy": 1, "idObj": 1234}])

    result = check_mirror(idx, mirror)
    assert result.stats["checked"] == 1
    assert result.stats["missing"] == 0
    assert result.stats["too_small"] == 0
    assert result.issues == []


def test_mirror_missing_file(tmp_path):
    idx = tmp_path / "index.json"
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    _write_index(idx, [{"year": 2024, "broy": 1, "idObj": 1234}])

    result = check_mirror(idx, mirror)
    assert result.stats["missing"] == 1
    assert any(i.code == "MISSING_FILE" and i.severity == "error" for i in result.issues)


def test_mirror_too_small(tmp_path):
    idx = tmp_path / "index.json"
    mirror = tmp_path / "mirror"
    (mirror / "2024").mkdir(parents=True)
    (mirror / "2024" / "001-1234.rtf").write_bytes(b"x" * 100)
    _write_index(idx, [{"year": 2024, "broy": 1, "idObj": 1234}])

    result = check_mirror(idx, mirror)
    assert result.stats["too_small"] == 1
    assert any(i.code == "TOO_SMALL" and i.severity == "warn" for i in result.issues)


def test_mirror_pdf_accepted(tmp_path):
    idx = tmp_path / "index.json"
    mirror = tmp_path / "mirror"
    (mirror / "1995").mkdir(parents=True)
    (mirror / "1995" / "005-9999.pdf").write_bytes(b"x" * 2048)
    _write_index(idx, [{"year": 1995, "broy": 5, "idObj": 9999}])

    result = check_mirror(idx, mirror)
    assert result.stats["missing"] == 0


def test_mirror_multiple_entries(tmp_path):
    idx = tmp_path / "index.json"
    mirror = tmp_path / "mirror"
    (mirror / "2024").mkdir(parents=True)
    (mirror / "2024" / "001-1111.rtf").write_bytes(b"x" * 2048)
    # 002-2222 intentionally missing
    _write_index(idx, [
        {"year": 2024, "broy": 1, "idObj": 1111},
        {"year": 2024, "broy": 2, "idObj": 2222},
    ])

    result = check_mirror(idx, mirror)
    assert result.stats["checked"] == 2
    assert result.stats["missing"] == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_validate_mirror.py -k "mirror" -v
```
Expected: `ImportError: cannot import name 'check_mirror'`

- [ ] **Step 3: Implement mirror layer**

```python
# src/open_legis/validate/mirror.py
from __future__ import annotations

import json
from pathlib import Path

from open_legis.validate import Issue, LayerResult

_MIN_SIZE = 1024


def check_mirror(index_path: Path, mirror_root: Path) -> LayerResult:
    entries = json.loads(index_path.read_text(encoding="utf-8"))
    issues: list[Issue] = []
    checked = 0

    for entry in entries:
        year = entry["year"]
        broy = entry["broy"]
        idobj = entry["idObj"]
        stem = f"{broy:03d}-{idobj}"

        rtf = mirror_root / str(year) / f"{stem}.rtf"
        pdf = mirror_root / str(year) / f"{stem}.pdf"

        if rtf.exists():
            found = rtf
        elif pdf.exists():
            found = pdf
        else:
            issues.append(Issue(
                severity="error",
                code="MISSING_FILE",
                message=f"DV {year} broy {broy} (idObj={idobj}) not in mirror",
                path=str(mirror_root / str(year) / stem),
                detail=f"Expected {rtf} or {pdf}",
            ))
            checked += 1
            continue

        if found.stat().st_size < _MIN_SIZE:
            issues.append(Issue(
                severity="warn",
                code="TOO_SMALL",
                message=f"DV {year} broy {broy}: {found.name} is {found.stat().st_size} bytes (< {_MIN_SIZE})",
                path=str(found),
            ))
        checked += 1

    missing = sum(1 for i in issues if i.code == "MISSING_FILE")
    too_small = sum(1 for i in issues if i.code == "TOO_SMALL")
    return LayerResult(
        name="mirror",
        issues=issues,
        stats={"checked": checked, "missing": missing, "too_small": too_small},
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_validate_mirror.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/open_legis/validate/mirror.py tests/test_validate_mirror.py
git commit -m "feat(validate): layer 1 — mirror coverage check"
```

---

## Task 3: Layer 2 — Fixture Structure

**Files:**
- Create: `src/open_legis/validate/fixtures.py`
- Create: `tests/test_validate_fixtures.py`
- Create: `tests/data/validate_valid.xml`

- [ ] **Step 1: Create the valid test fixture XML**

```xml
<!-- tests/data/validate_valid.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <act contains="originalVersion">
    <meta>
      <identification source="#openlegis">
        <FRBRWork>
          <FRBRthis value="/akn/bg/act/2024/dv-26-24-1/main"/>
          <FRBRuri value="/akn/bg/act/2024/dv-26-24-1"/>
          <FRBRalias value="Закон за тест" name="short"/>
          <FRBRalias value="Закон за тест" name="eli" other="/eli/bg/zakon/2024/dv-26-24-1"/>
          <FRBRdate date="2024-03-30" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRcountry value="bg"/>
          <FRBRnumber value="1"/>
        </FRBRWork>
        <FRBRExpression>
          <FRBRthis value="/akn/bg/act/2024/dv-26-24-1/bul@2024-03-30/main"/>
          <FRBRuri value="/akn/bg/act/2024/dv-26-24-1/bul@2024-03-30"/>
          <FRBRdate date="2024-03-30" name="Generation"/>
          <FRBRauthor href="#parliament"/>
          <FRBRlanguage language="bul"/>
        </FRBRExpression>
      </identification>
      <publication date="2024-03-30" name="Държавен вестник" number="26" showAs="ДВ"/>
    </meta>
    <body>
      <article eId="art_1">
        <num>Чл. 1.</num>
        <content><p>Тест.</p></content>
      </article>
    </body>
  </act>
</akomaNtoso>
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_validate_fixtures.py
from pathlib import Path
import pytest
from open_legis.validate.fixtures import check_fixtures

_VALID_XML = Path("tests/data/validate_valid.xml").read_text(encoding="utf-8")


def _place(root: Path, act_type: str, year: str, slug: str, date: str, xml: str) -> Path:
    p = root / act_type / year / slug / "expressions" / f"{date}.bul.xml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(xml, encoding="utf-8")
    return p


def test_valid_fixture_no_errors(tmp_path):
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", _VALID_XML)
    result = check_fixtures(tmp_path)
    assert result.stats["checked"] == 1
    assert not any(i.severity == "error" for i in result.issues)


def test_malformed_xml(tmp_path):
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", "not < xml >>")
    result = check_fixtures(tmp_path)
    assert any(i.code == "MALFORMED_XML" for i in result.issues)


def test_empty_body_flagged(tmp_path):
    xml = _VALID_XML.replace(
        "<body>\n      <article eId=\"art_1\">\n        <num>Чл. 1.</num>\n        <content><p>Тест.</p></content>\n      </article>\n    </body>",
        "<body></body>",
    )
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", xml)
    result = check_fixtures(tmp_path)
    assert any(i.code == "EMPTY_BODY" for i in result.issues)


def test_missing_title_warned(tmp_path):
    xml = _VALID_XML.replace(
        '<FRBRalias value="Закон за тест" name="short"/>\n          ',
        "",
    )
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", xml)
    result = check_fixtures(tmp_path)
    assert any(i.code == "MISSING_TITLE" for i in result.issues)


def test_eli_mismatch_warned(tmp_path):
    xml = _VALID_XML.replace(
        'other="/eli/bg/zakon/2024/dv-26-24-1"',
        'other="/eli/bg/zakon/2024/dv-99-24-1"',
    )
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", xml)
    result = check_fixtures(tmp_path)
    assert any(i.code == "ELI_MISMATCH" for i in result.issues)


def test_multiple_files_counted(tmp_path):
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", _VALID_XML)
    xml2 = _VALID_XML.replace("dv-26-24-1", "dv-27-24-1").replace("26-24-1", "27-24-1")
    _place(tmp_path, "zakon", "2024", "dv-27-24-1", "2024-04-02", xml2)
    result = check_fixtures(tmp_path)
    assert result.stats["checked"] == 2
```

- [ ] **Step 3: Run to confirm failure**

```bash
uv run pytest tests/test_validate_fixtures.py -v
```
Expected: `ImportError: cannot import name 'check_fixtures'`

- [ ] **Step 4: Implement fixture layer**

```python
# src/open_legis/validate/fixtures.py
from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from open_legis.validate import Issue, LayerResult

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NS = {"akn": _AKN_NS}
# {act_type}/{year}/{slug}/expressions/{date}.bul.xml
_PATH_RE = re.compile(
    r"^(?P<act_type>[^/]+)/(?P<year>\d{4})/(?P<slug>[^/]+)"
    r"/expressions/(?P<date>\d{4}-\d{2}-\d{2})\.bul\.xml$"
)


def check_fixtures(fixtures_root: Path) -> LayerResult:
    issues: list[Issue] = []
    files = sorted(fixtures_root.rglob("*.bul.xml"))
    checked = 0

    for f in files:
        rel = f.relative_to(fixtures_root).as_posix()
        checked += 1

        try:
            tree = etree.parse(str(f))
        except etree.XMLSyntaxError as exc:
            issues.append(Issue("error", "MALFORMED_XML",
                f"Not valid XML: {exc}", rel))
            continue

        root = tree.getroot()

        # Title: warn if name="short" absent (some older fixtures may only have name="eli")
        if not root.xpath("//akn:FRBRalias[@name='short']", namespaces=_NS):
            issues.append(Issue("warn", "MISSING_TITLE",
                "FRBRalias name='short' absent — title not machine-readable", rel))

        # Body must have at least one child
        body = root.find(f"{{{_AKN_NS}}}act/{{{_AKN_NS}}}body")
        if body is None or len(body) == 0:
            issues.append(Issue("error", "EMPTY_BODY",
                "<body> is absent or has no child elements", rel))

        # Path structure
        m = _PATH_RE.match(rel)
        if not m:
            issues.append(Issue("warn", "BAD_PATH",
                f"Path doesn't match {{act_type}}/{{year}}/{{slug}}/expressions/{{date}}.bul.xml",
                rel))
            continue

        path_act_type = m.group("act_type")
        path_year = m.group("year")
        path_slug = m.group("slug")

        # ELI in XML must match path
        eli_nodes = root.xpath("//akn:FRBRalias[@name='eli']", namespaces=_NS)
        if eli_nodes:
            eli_other = eli_nodes[0].get("other", "")
            expected = f"/eli/bg/{path_act_type}/{path_year}/{path_slug}"
            if eli_other != expected:
                issues.append(Issue("warn", "ELI_MISMATCH",
                    f"ELI in XML ({eli_other!r}) doesn't match path ({expected!r})", rel))

    counts = {
        "checked": checked,
        "malformed": sum(1 for i in issues if i.code == "MALFORMED_XML"),
        "empty_body": sum(1 for i in issues if i.code == "EMPTY_BODY"),
        "eli_mismatch": sum(1 for i in issues if i.code == "ELI_MISMATCH"),
    }
    return LayerResult(name="fixtures", issues=issues, stats=counts)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_validate_fixtures.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/open_legis/validate/fixtures.py tests/test_validate_fixtures.py tests/data/validate_valid.xml
git commit -m "feat(validate): layer 2 — fixture structure check"
```

---

## Task 4: Layer 3 — Classification Sanity

**Files:**
- Create: `src/open_legis/validate/classify.py`
- Create: `tests/test_validate_classify.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_validate_classify.py
from pathlib import Path
import pytest
from open_legis.validate.classify import check_classification

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"

_VALID_XML = Path("tests/data/validate_valid.xml").read_text(encoding="utf-8")


def _place(root: Path, act_type: str, slug: str, title: str) -> Path:
    xml = _VALID_XML.replace(
        'value="Закон за тест" name="short"',
        f'value="{title}" name="short"',
    ).replace(
        'other="/eli/bg/zakon/2024/dv-26-24-1"',
        f'other="/eli/bg/{act_type}/2024/{slug}"',
    )
    p = root / act_type / "2024" / slug / "expressions" / "2024-03-30.bul.xml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(xml, encoding="utf-8")
    return p


def test_correct_type_no_issues(tmp_path):
    _place(tmp_path, "zakon", "dv-26-24-1", "Закон за тест")
    result = check_classification(tmp_path)
    assert not any(i.code == "TYPE_MISMATCH" for i in result.issues)


def test_type_mismatch_detected(tmp_path):
    # File is in zakon/ but title is a Решение
    _place(tmp_path, "zakon", "dv-26-24-1", "Решение за нещо")
    result = check_classification(tmp_path)
    assert any(i.code == "TYPE_MISMATCH" and i.severity == "error" for i in result.issues)


def test_reshenie_subtype_mismatch(tmp_path):
    # File is in reshenie_ns/ but title is a KEVR decision
    _place(tmp_path, "reshenie_ns", "dv-80-16-8",
           "Решение № 689-ЖЗ от 26 септември 2016 г.")
    result = check_classification(tmp_path)
    assert any(i.code == "TYPE_MISMATCH" and "reshenie_kevr" in i.message for i in result.issues)


def test_undetected_title_warned(tmp_path):
    _place(tmp_path, "zakon", "dv-26-24-1", "Инструкция за нещо непознато")
    result = check_classification(tmp_path)
    assert any(i.code == "UNDETECTED" and i.severity == "warn" for i in result.issues)


def test_postanovlenie_correct(tmp_path):
    _place(tmp_path, "postanovlenie", "dv-68-12-1",
           "Постановление № 193 ОТ 28 АВГУСТ 2012 Г. за определяне")
    result = check_classification(tmp_path)
    assert not any(i.code == "TYPE_MISMATCH" for i in result.issues)
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_validate_classify.py -v
```
Expected: `ImportError: cannot import name 'check_classification'`

- [ ] **Step 3: Implement classify layer**

```python
# src/open_legis/validate/classify.py
from __future__ import annotations

from pathlib import Path

from lxml import etree

from open_legis.scraper.dv_to_akn import detect_act_type
from open_legis.validate import Issue, LayerResult

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NS = {"akn": _AKN_NS}


def check_classification(fixtures_root: Path) -> LayerResult:
    issues: list[Issue] = []
    checked = 0

    for f in sorted(fixtures_root.rglob("*.bul.xml")):
        rel = f.relative_to(fixtures_root).as_posix()
        parts = rel.split("/")
        if len(parts) < 4:
            continue
        dir_act_type = parts[0]

        try:
            tree = etree.parse(str(f))
        except etree.XMLSyntaxError:
            continue  # already flagged by Layer 2

        short_nodes = tree.xpath("//akn:FRBRalias[@name='short']", namespaces=_NS)
        if not short_nodes:
            continue  # already flagged by Layer 2 as MISSING_TITLE

        title = short_nodes[0].get("value", "")
        detected = detect_act_type(title)
        checked += 1

        if detected == "_other":
            issues.append(Issue(
                severity="warn",
                code="UNDETECTED",
                message=f"Could not classify title: {title[:80]!r}",
                path=rel,
            ))
            continue

        if detected != dir_act_type:
            issues.append(Issue(
                severity="error",
                code="TYPE_MISMATCH",
                message=(
                    f"Directory={dir_act_type!r} but title detects as {detected!r}: "
                    f"{title[:80]!r}"
                ),
                path=rel,
                detail=f"expected={dir_act_type}, detected={detected}",
            ))

    return LayerResult(
        name="classify",
        issues=issues,
        stats={
            "checked": checked,
            "mismatches": sum(1 for i in issues if i.code == "TYPE_MISMATCH"),
            "undetected": sum(1 for i in issues if i.code == "UNDETECTED"),
        },
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_validate_classify.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/open_legis/validate/classify.py tests/test_validate_classify.py
git commit -m "feat(validate): layer 3 — act-type classification sanity"
```

---

## Task 5: Layer 4a — DB Coverage

**Files:**
- Create: `src/open_legis/validate/db.py`
- Create: `tests/test_validate_db.py`

- [ ] **Step 1: Write failing tests**

These use `testcontainers` (same as other DB tests in this project).

```python
# tests/test_validate_db.py
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine
from open_legis.validate.db import check_db


@pytest.fixture
def loaded_db(pg_url, tmp_path):
    """Fresh DB loaded with the minimal test fixture."""
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
    dest = tmp_path / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    (dest / "2000-01-01.bul.xml").write_text(
        Path("tests/data/minimal_act.xml").read_text()
    )
    load_directory(tmp_path / "akn", engine=eng)
    return eng, tmp_path / "akn"


def test_loaded_work_no_errors(loaded_db):
    eng, fixtures_root = loaded_db
    with Session(eng) as session:
        result = check_db(fixtures_root, session)
    assert not any(i.code == "TYPE_NOT_IN_DB" for i in result.issues)
    assert not any(i.code == "FIXTURE_NOT_LOADED" for i in result.issues)


def test_type_not_in_db_detected(loaded_db):
    eng, fixtures_root = loaded_db
    # Add a reshenie_kevr fixture that is NOT loaded into DB
    extra = fixtures_root / "reshenie_kevr" / "2016" / "dv-80-16-8" / "expressions"
    extra.mkdir(parents=True)
    (extra / "2016-10-11.bul.xml").write_text(
        Path("tests/data/validate_valid.xml").read_text()
        .replace("zakon", "reshenie_kevr")
        .replace("dv-26-24-1", "dv-80-16-8")
        .replace("2024", "2016")
        .replace("2024-03-30", "2016-10-11")
    )
    with Session(eng) as session:
        result = check_db(fixtures_root, session)
    assert any(i.code == "TYPE_NOT_IN_DB" and "reshenie_kevr" in i.message for i in result.issues)


def test_zero_elements_flagged(loaded_db):
    eng, fixtures_root = loaded_db
    # Manually clear elements for the loaded work
    with Session(eng) as session:
        session.execute(text("DELETE FROM element"))
        session.commit()
    with Session(eng) as session:
        result = check_db(fixtures_root, session)
    assert any(i.code == "ZERO_ELEMENTS" for i in result.issues)
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_validate_db.py::test_loaded_work_no_errors -v
```
Expected: `ImportError: cannot import name 'check_db'`

- [ ] **Step 3: Implement DB coverage layer**

```python
# src/open_legis/validate/db.py
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from open_legis.validate import Issue, LayerResult


def check_db(fixtures_root: Path, session: Session) -> LayerResult:
    issues: list[Issue] = []

    # --- 4a: Coverage ---

    # Count fixture XML files per act_type
    fixture_counts: dict[str, int] = {}
    for f in fixtures_root.rglob("*.bul.xml"):
        parts = f.relative_to(fixtures_root).parts
        if len(parts) < 4:
            continue
        act_type = parts[0]
        fixture_counts[act_type] = fixture_counts.get(act_type, 0) + 1

    # DB counts per act_type (lower-case to match fixture dir names)
    db_rows = session.execute(text(
        "SELECT lower(act_type::text), COUNT(*) FROM work GROUP BY act_type"
    )).fetchall()
    db_counts: dict[str, int] = {r[0]: r[1] for r in db_rows}

    for act_type, fx_count in sorted(fixture_counts.items()):
        db_count = db_counts.get(act_type, 0)
        if db_count == 0:
            issues.append(Issue(
                severity="error",
                code="TYPE_NOT_IN_DB",
                message=f"{act_type}: {fx_count} fixtures present but 0 DB rows",
                path=act_type,
                detail="All fixtures of this type failed to load",
            ))
        elif db_count < fx_count:
            issues.append(Issue(
                severity="warn",
                code="COVERAGE_GAP",
                message=f"{act_type}: {fx_count} fixtures but only {db_count} DB rows ({fx_count - db_count} missing)",
                path=act_type,
            ))

    # Works with 0 elements
    zero_elem_rows = session.execute(text("""
        SELECT w.eli_uri
        FROM work w
        JOIN expression e ON e.work_id = w.id AND e.is_latest = true
        LEFT JOIN element el ON el.expression_id = e.id
        GROUP BY w.id, w.eli_uri
        HAVING COUNT(el.id) = 0
    """)).fetchall()
    for row in zero_elem_rows:
        issues.append(Issue(
            severity="warn",
            code="ZERO_ELEMENTS",
            message=f"Work has no parsed elements: {row[0]}",
            path=row[0],
        ))

    return LayerResult(
        name="db",
        issues=issues,
        stats={
            "fixture_types": len(fixture_counts),
            "db_types": len(db_counts),
            "type_not_in_db": sum(1 for i in issues if i.code == "TYPE_NOT_IN_DB"),
            "coverage_gaps": sum(1 for i in issues if i.code == "COVERAGE_GAP"),
            "zero_elements": len(zero_elem_rows),
        },
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_validate_db.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/open_legis/validate/db.py tests/test_validate_db.py
git commit -m "feat(validate): layer 4a — DB coverage check"
```

---

## Task 6: Layer 4b — Duplicate / Fragment Detection

**Files:**
- Modify: `src/open_legis/validate/db.py`
- Modify: `tests/test_validate_db.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_validate_db.py`:

```python
from open_legis.validate.db import check_db, _title_similarity


def test_title_similarity_same():
    assert _title_similarity("Закон за тест", "Закон за тест") == 1.0


def test_title_similarity_different():
    assert _title_similarity("Закон за тест", "Постановление за нещо") < 0.4


def test_probable_fragment_detected(loaded_db):
    """Two works in the same issue with near-identical titles should be flagged."""
    eng, fixtures_root = loaded_db
    with Session(eng) as session:
        # Insert a second work in the same DV issue as the loaded 'test' work,
        # with a very similar title.
        session.execute(text("""
            INSERT INTO work (id, eli_uri, act_type, title, dv_broy, dv_year, dv_position, status)
            VALUES (
                gen_random_uuid(),
                '/eli/bg/zakon/2000/test-fragment',
                'ZAKON',
                'Test Act (continued)',
                1, 2000, 2,
                'in_force'
            )
        """))
        session.commit()
    with Session(eng) as session:
        result = check_db(fixtures_root, session)
    assert any(i.code == "PROBABLE_FRAGMENT" for i in result.issues)


def test_issue_overcount_flagged(loaded_db):
    """More than threshold zakoni in a single issue should warn."""
    eng, _ = loaded_db
    with Session(eng) as session:
        for pos in range(2, 8):  # add 6 more, total=7, threshold=3
            session.execute(text(f"""
                INSERT INTO work (id, eli_uri, act_type, title, dv_broy, dv_year, dv_position, status)
                VALUES (
                    gen_random_uuid(),
                    '/eli/bg/zakon/2000/extra-{pos}',
                    'ZAKON',
                    'Completely Different Law {pos}',
                    1, 2000, {pos},
                    'in_force'
                )
            """))
        session.commit()
    # Use a fresh fixtures_root (just needs to exist; overcount is DB-only check)
    from pathlib import Path
    with Session(eng) as session:
        result = check_db(Path("fixtures/akn"), session)
    assert any(i.code == "ISSUE_OVERCOUNT" for i in result.issues)
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_validate_db.py::test_probable_fragment_detected tests/test_validate_db.py::test_title_similarity_same -v
```
Expected: `ImportError: cannot import name '_title_similarity'`

- [ ] **Step 3: Extend `db.py` with fragment detection**

Add after the existing `check_db` function and imports:

```python
# Add to top of src/open_legis/validate/db.py:
from difflib import SequenceMatcher

# Add this constant after imports:
_ISSUE_THRESHOLDS: dict[str, int] = {
    "zakon": 3, "kodeks": 3, "byudjet": 3, "konstitutsiya": 1,
    "naredba": 8, "pravilnik": 8, "postanovlenie": 8, "zid": 8, "ratifikatsiya": 8,
    "reshenie_ns": 15, "reshenie_ms": 15, "reshenie_kevr": 15,
    "reshenie_kfn": 15, "reshenie_nhif": 15,
}


def _title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a[:120], b[:120]).ratio()
```

Then add a call to `_check_duplicates(session, issues)` at the end of `check_db`, and implement:

```python
def _check_duplicates(session: Session, issues: list[Issue]) -> dict[str, int]:
    groups = session.execute(text("""
        SELECT
            lower(act_type::text),
            dv_broy,
            dv_year,
            COUNT(*)                                    AS cnt,
            array_agg(eli_uri   ORDER BY dv_position)  AS uris,
            array_agg(title     ORDER BY dv_position)  AS titles,
            array_agg(dv_position ORDER BY dv_position) AS positions
        FROM work
        GROUP BY act_type, dv_broy, dv_year
        HAVING COUNT(*) > 1
    """)).fetchall()

    overcounts = 0
    fragments = 0
    pos_gaps = 0

    for row in groups:
        act_type, broy, year, cnt, uris, titles, positions = row
        threshold = _ISSUE_THRESHOLDS.get(act_type, 8)

        if cnt > threshold:
            issues.append(Issue(
                severity="warn",
                code="ISSUE_OVERCOUNT",
                message=f"{act_type} DV {broy}/{year}: {cnt} acts (threshold={threshold})",
                path=f"dv-{broy}-{year % 100:02d}",
                detail=f"URIs: {', '.join(uris[:5])}",
            ))
            overcounts += 1

        # Fragment check: any pair of titles with high similarity
        for i in range(len(titles)):
            for j in range(i + 1, len(titles)):
                sim = _title_similarity(titles[i], titles[j])
                if sim > 0.6:
                    issues.append(Issue(
                        severity="error",
                        code="PROBABLE_FRAGMENT",
                        message=(
                            f"{act_type} DV {broy}/{year}: similar titles at "
                            f"pos {positions[i]}&{positions[j]} — likely parser split"
                        ),
                        path=uris[i],
                        detail=(
                            f"similarity={sim:.2f}\n"
                            f"      A: {titles[i][:80]}\n"
                            f"      B: {titles[j][:80]}"
                        ),
                    ))
                    fragments += 1

        # Position gap: if all positions are even and avg gap > 3 → page numbers not counters
        if len(positions) >= 3:
            gaps = [positions[k + 1] - positions[k] for k in range(len(positions) - 1)]
            avg_gap = sum(gaps) / len(gaps)
            if avg_gap > 3 and all(p % 2 == 0 for p in positions):
                issues.append(Issue(
                    severity="warn",
                    code="POSITION_GAPS",
                    message=(
                        f"{act_type} DV {broy}/{year}: positions {positions} "
                        f"look like page numbers (avg gap={avg_gap:.1f})"
                    ),
                    path=f"dv-{broy}-{year % 100:02d}",
                ))
                pos_gaps += 1

    return {"overcounts": overcounts, "fragments": fragments, "position_gaps": pos_gaps}
```

Update `check_db` to call this and merge the stats:

```python
# At the end of check_db, replace the return with:
    dup_stats = _check_duplicates(session, issues)
    return LayerResult(
        name="db",
        issues=issues,
        stats={
            "fixture_types": len(fixture_counts),
            "db_types": len(db_counts),
            "type_not_in_db": sum(1 for i in issues if i.code == "TYPE_NOT_IN_DB"),
            "coverage_gaps": sum(1 for i in issues if i.code == "COVERAGE_GAP"),
            "zero_elements": len(zero_elem_rows),
            **dup_stats,
        },
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_validate_db.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/open_legis/validate/db.py tests/test_validate_db.py
git commit -m "feat(validate): layer 4b — duplicate and fragment detection"
```

---

## Task 7: Layer 5 — ELI Analysis

**Files:**
- Create: `src/open_legis/validate/eli.py`
- Create: `tests/test_validate_eli.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_validate_eli.py
from pathlib import Path
from open_legis.validate.eli import check_eli

_VALID_XML = Path("tests/data/validate_valid.xml").read_text(encoding="utf-8")


def _place(root: Path, act_type: str, year: str, slug: str, date: str, xml: str) -> None:
    p = root / act_type / year / slug / "expressions" / f"{date}.bul.xml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(xml, encoding="utf-8")


def test_standard_slug_counted(tmp_path):
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", _VALID_XML)
    result = check_eli(tmp_path)
    assert result.stats["standard"] == 1
    assert result.stats["nonstandard"] == 0


def test_nonstandard_slug_flagged(tmp_path):
    xml = _VALID_XML.replace("dv-26-24-1", "custom-slug")
    _place(tmp_path, "zakon", "2024", "custom-slug", "2024-03-30", xml)
    result = check_eli(tmp_path)
    assert result.stats["nonstandard"] == 1
    assert any(i.code == "NONSTANDARD_SLUG" and i.severity == "info" for i in result.issues)


def test_postanovlenie_number_detected(tmp_path):
    xml = _VALID_XML.replace(
        'value="Закон за тест" name="short"',
        'value="Постановление № 193 ОТ 28 АВГУСТ 2012 Г." name="short"',
    ).replace("zakon", "postanovlenie").replace("dv-26-24-1", "dv-68-12-1")
    _place(tmp_path, "postanovlenie", "2024", "dv-68-12-1", "2024-03-30", xml)
    result = check_eli(tmp_path)
    assert result.stats.get("postanovlenie_with_number", 0) == 1


def test_recommendation_always_present(tmp_path):
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", _VALID_XML)
    result = check_eli(tmp_path)
    assert any(i.code == "ELI_RECOMMENDATION" for i in result.issues)
    assert all(i.severity == "info" for i in result.issues)
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_validate_eli.py -v
```
Expected: `ImportError: cannot import name 'check_eli'`

- [ ] **Step 3: Implement ELI layer**

```python
# src/open_legis/validate/eli.py
from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from open_legis.validate import Issue, LayerResult

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NS = {"akn": _AKN_NS}
_SLUG_RE = re.compile(r"^dv-\d+-\d{2}-\d+$")

_NUMBER_PATTERNS: dict[str, re.Pattern[str]] = {
    "postanovlenie": re.compile(r"Постановление\s+№\s+\d+", re.IGNORECASE),
    "naredba": re.compile(r"Наредба\s+№\s+[\w\-/]+", re.IGNORECASE),
    "pravilnik": re.compile(r"Правилник\s+№\s+[\w\-/]+", re.IGNORECASE),
    "reshenie_kevr": re.compile(r"Решение\s+№\s+[\w\-]+"),
    "reshenie_kfn": re.compile(r"Решение\s+№\s+[\w\-]+"),
    "reshenie_nhif": re.compile(r"Решение\s+№\s+[\w\-]+"),
}


def check_eli(fixtures_root: Path) -> LayerResult:
    issues: list[Issue] = []
    slug_counts: dict[str, int] = {"standard": 0, "nonstandard": 0}
    number_stats: dict[str, dict[str, int]] = {}

    for f in sorted(fixtures_root.rglob("*.bul.xml")):
        parts = f.relative_to(fixtures_root).parts
        if len(parts) < 3:
            continue
        act_type, _year, slug = parts[0], parts[1], parts[2]
        rel = f.relative_to(fixtures_root).as_posix()

        if _SLUG_RE.match(slug):
            slug_counts["standard"] += 1
        else:
            slug_counts["nonstandard"] += 1
            issues.append(Issue(
                severity="info",
                code="NONSTANDARD_SLUG",
                message=f"Slug {slug!r} doesn't follow dv-N-NN-N pattern",
                path=rel,
            ))

        if act_type not in _NUMBER_PATTERNS:
            continue

        if act_type not in number_stats:
            number_stats[act_type] = {"total": 0, "has_number": 0}
        number_stats[act_type]["total"] += 1

        try:
            tree = etree.parse(str(f))
            aliases = tree.xpath("//akn:FRBRalias[@name='short']", namespaces=_NS)
            if aliases:
                title = aliases[0].get("value", "")
                if _NUMBER_PATTERNS[act_type].search(title):
                    number_stats[act_type]["has_number"] += 1
        except etree.XMLSyntaxError:
            pass

    # Emit a summary info issue per type with parseable numbers
    for act_type, stats in number_stats.items():
        if stats["total"] == 0:
            continue
        pct = stats["has_number"] / stats["total"] * 100
        issues.append(Issue(
            severity="info",
            code="NUMBER_COVERAGE",
            message=(
                f"{act_type}: {stats['has_number']}/{stats['total']} ({pct:.0f}%) "
                f"have parseable official numbers"
            ),
            path=act_type,
            detail="Populate work.number for human-readable display; keep current slugs",
        ))

    issues.append(Issue(
        severity="info",
        code="ELI_RECOMMENDATION",
        message="Current dv-N-NN-N slugs are stable — do not change after launch",
        detail=(
            "Recommended: populate work.number (already in schema) for acts with "
            "official numbers; no URI changes needed"
        ),
    ))

    extra_stats = {
        f"{k}_with_number": v["has_number"] for k, v in number_stats.items()
    }
    return LayerResult(
        name="eli",
        issues=issues,
        stats={**slug_counts, **extra_stats},
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_validate_eli.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/open_legis/validate/eli.py tests/test_validate_eli.py
git commit -m "feat(validate): layer 5 — ELI structure analysis"
```

---

## Task 8: CLI command wiring

**Files:**
- Modify: `src/open_legis/cli.py`
- Create: `tests/test_validate_cli.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/test_validate_cli.py
import json
from pathlib import Path

from typer.testing import CliRunner

from open_legis.cli import app

runner = CliRunner()

_VALID_XML = Path("tests/data/validate_valid.xml").read_text(encoding="utf-8")
_VALID_INDEX = json.dumps([{"year": 2024, "broy": 26, "idObj": 9999}])


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create minimal valid mirror + fixture tree."""
    mirror = tmp_path / "mirror"
    (mirror / "2024").mkdir(parents=True)
    (mirror / "2024" / "026-9999.rtf").write_bytes(b"x" * 2048)

    idx = tmp_path / ".dv-index.json"
    idx.write_text(_VALID_INDEX)

    fixtures = tmp_path / "akn"
    p = fixtures / "zakon" / "2024" / "dv-26-24-1" / "expressions" / "2024-03-30.bul.xml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_VALID_XML)

    return fixtures, mirror, idx


def test_validate_mirror_layer_only(tmp_path):
    fixtures, mirror, idx = _setup(tmp_path)
    result = runner.invoke(app, [
        "validate",
        "--fixtures", str(fixtures),
        "--mirror", str(mirror),
        "--index-file", str(idx),
        "--layer", "mirror",
    ])
    assert result.exit_code == 0
    assert "MIRROR" in result.output


def test_validate_fixtures_layer_only(tmp_path):
    fixtures, mirror, idx = _setup(tmp_path)
    result = runner.invoke(app, [
        "validate",
        "--fixtures", str(fixtures),
        "--mirror", str(mirror),
        "--index-file", str(idx),
        "--layer", "fixtures",
    ])
    assert result.exit_code == 0
    assert "FIXTURES" in result.output


def test_validate_json_output(tmp_path):
    fixtures, mirror, idx = _setup(tmp_path)
    out_json = tmp_path / "report.json"
    runner.invoke(app, [
        "validate",
        "--fixtures", str(fixtures),
        "--mirror", str(mirror),
        "--index-file", str(idx),
        "--layer", "mirror",
        "--json", str(out_json),
    ])
    assert out_json.exists()
    data = json.loads(out_json.read_text())
    assert "layers" in data
    assert data["layers"][0]["name"] == "mirror"


def test_validate_exits_1_on_error(tmp_path):
    """Missing mirror file should cause exit code 1."""
    fixtures, mirror, idx = _setup(tmp_path)
    # Write index entry that has no matching file
    idx.write_text(json.dumps([
        {"year": 2024, "broy": 26, "idObj": 9999},
        {"year": 2024, "broy": 99, "idObj": 8888},  # missing
    ]))
    result = runner.invoke(app, [
        "validate",
        "--fixtures", str(fixtures),
        "--mirror", str(mirror),
        "--index-file", str(idx),
        "--layer", "mirror",
    ])
    assert result.exit_code == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_validate_cli.py::test_validate_mirror_layer_only -v
```
Expected: error — `No such command 'validate'`

- [ ] **Step 3: Add `validate` command to `cli.py`**

Add this import block near the other imports at top of `src/open_legis/cli.py`:

```python
# (no new top-level imports needed — all imports are inside the command)
```

Add this command after the existing `cache-dv` command:

```python
@app.command("validate")
def validate(
    fixtures: str = typer.Option("fixtures/akn", "--fixtures", help="AKN fixtures root"),
    mirror: str = typer.Option("local_dv", "--mirror", help="Local DV mirror directory"),
    index_file: str = typer.Option(".dv-index.json", "--index-file", help="DV issue index"),
    layer: Optional[str] = typer.Option(
        None, "--layer",
        help="Run only one layer: mirror|fixtures|classify|db|eli (default: all)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all issues"),
    json_out: Optional[str] = typer.Option(None, "--json", help="Write JSON report to file"),
) -> None:
    """Validate the data pipeline: mirror → fixtures → DB."""
    from pathlib import Path

    from open_legis.validate.mirror import check_mirror
    from open_legis.validate.fixtures import check_fixtures
    from open_legis.validate.classify import check_classification
    from open_legis.validate.db import check_db
    from open_legis.validate.eli import check_eli
    from open_legis.validate.report import print_report, write_json_report

    fixtures_path = Path(fixtures)
    mirror_path = Path(mirror)
    index_path = Path(index_file)

    results = []

    def _run(name: str, fn, *args):
        if layer is None or layer == name:
            typer.echo(f"Running {name}...")
            results.append(fn(*args))

    _run("mirror", check_mirror, index_path, mirror_path)
    _run("fixtures", check_fixtures, fixtures_path)
    _run("classify", check_classification, fixtures_path)

    if layer is None or layer == "db":
        typer.echo("Running db...")
        from open_legis.model.db import make_engine
        from open_legis.settings import Settings
        from sqlalchemy.orm import Session

        engine = make_engine(Settings().database_url)
        with Session(engine) as session:
            results.append(check_db(fixtures_path, session))

    _run("eli", check_eli, fixtures_path)

    if json_out:
        write_json_report(results, json_out)
        typer.echo(f"Report written to {json_out}")

    error_count = print_report(results, verbose=verbose)
    raise typer.Exit(code=1 if error_count > 0 else 0)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_validate_cli.py -v
```
Expected: all PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
uv run pytest tests/ -x -q
```
Expected: all existing tests PASS

- [ ] **Step 6: Smoke-test against real data**

```bash
DATABASE_URL=postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis \
  uv run open-legis validate --layer mirror -v
```
Expected: `MIRROR ── OK  checked=4070 missing=0 too_small=...`

```bash
DATABASE_URL=postgresql+psycopg://openlegis:openlegis@localhost:5432/openlegis \
  uv run open-legis validate --layer db --verbose 2>&1 | head -60
```
Expected: `TYPE_NOT_IN_DB` errors for `reshenie_kevr`, `reshenie_kfn`, `reshenie_nhif` and `COVERAGE_GAP` warnings for `zakon`, `zid`, `reshenie_ms`.

- [ ] **Step 7: Commit**

```bash
git add src/open_legis/cli.py tests/test_validate_cli.py
git commit -m "feat(validate): wire up CLI command — open-legis validate"
```

---

## Self-Review

**Spec coverage:**
- Layer 1 (mirror coverage) → Tasks 2 ✓
- Layer 2 (fixture structure) → Task 3 ✓
- Layer 3 (classification) → Task 4 ✓
- Layer 4a (DB coverage) → Task 5 ✓
- Layer 4b (dupe/fragment) → Task 6 ✓
- Layer 5 (ELI analysis) → Task 7 ✓
- CLI command with `--layer`, `--verbose`, `--json`, exit codes → Task 8 ✓
- JSON report structure (`run_at`, `summary`, `layers[].stats`, `layers[].issues`) → Task 1 (report.py) ✓
- `RESHENIE_WRONG_BODY` — absorbed into `TYPE_MISMATCH` (detect_act_type handles all reshenie subtypes; separate code adds no value) ✓

**Placeholder scan:** No TBDs, TODOs, or "similar to task N" references found.

**Type consistency:**
- `Issue`, `LayerResult` defined in Task 1, used identically in all layers ✓
- `check_mirror` / `check_fixtures` / `check_classification` / `check_db` / `check_eli` all return `LayerResult` ✓
- `_title_similarity` defined and exported in Task 6, tested in same task ✓
- `print_report` returns `int` (error count), used as exit code in Task 8 ✓
