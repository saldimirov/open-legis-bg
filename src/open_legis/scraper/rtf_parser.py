"""Parse a DV issue file (RTF or PDF) into individual materials.

RTF structure (newer issues, ~2003+):
  - Mixed-case TOC lines: "Title text \\t page_number"
  - Section headers: "ОФИЦИАЛЕН РАЗДЕЛ", "НАРОДНО СЪБРАНИЕ", etc.
  - Act headings in ALL CAPS: "ЗАКОН", "ПОСТАНОВЛЕНИЕ № X от ...", "УКАЗ № X", etc.
  - Act body: plain text paragraphs

PDF structure (older issues, 1989–~2002):
  - No reliable TOC; acts separated by ALL-CAPS headings in body text
  - Same split strategy, no TOC-title matching available

Strategy:
  1. Extract TOC titles (RTF only; mixed-case, more descriptive)
  2. Split body on ALL-CAPS act headings
  3. Match each body chunk to its TOC title by act number / type prefix
"""
from __future__ import annotations

import re
from pathlib import Path

from striprtf.striprtf import rtf_to_text

# Act type keywords as they appear in ALL-CAPS headings
_CAPS_ACT = re.compile(
    r"^(ЗАКОН|НАРЕДБА|КОДЕКС|ПОСТАНОВЛЕНИЕ|ПРАВИЛНИК|РЕШЕНИЕ|УКАЗ"
    r"|ИНСТРУКЦИЯ|ТАРИФА|КОНВЕНЦИЯ|ДОГОВОР|ИЗМЕНЕНИЕ)\b",
    re.MULTILINE,
)

# Section/institution headers to skip (not acts)
_SKIP_HEADERS = re.compile(
    r"^(ОФИЦИАЛЕН РАЗДЕЛ|НЕОФИЦИАЛЕН РАЗДЕЛ|НАРОДНО СЪБРАНИЕ|ПРЕЗИДЕНТ НА"
    r"|КОНСТИТУЦИОНЕН СЪД|МИНИСТЕРСКИ СЪВЕТ|МИНИСТЕРСТВО|АГЕНЦИЯ|КОМИСИЯ"
    r"|ПРОКУРАТУР|ПОКАНИ|ОБЯВИ|ИЗВЛЕЧЕНИЯ|СЪОБЩЕНИЯ|ДЪРЖАВНИ ВЕДОМСТВА"
    r"|ОБЩИНИ И СЪДИЛИЩА)\b",
)

_TOC_LINE = re.compile(r"^(.{10,}?)\s*\t\s*(\d+)\s*$")

_DV_HEADER_LINE2 = re.compile(r"брой:\s*\d+.*стр\.\s*\d+", re.IGNORECASE)
_WORD_BLOCK_START = re.compile(r"^\d+x\d+$")


def _strip_dv_page_headers(lines: list[str]) -> list[str]:
    """Remove DV page-break header lines (Държавен вестник + issue/page line)."""
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
    """Remove legacy Microsoft Word document-property blocks embedded in HTML."""
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
    """Apply all body-text cleaning passes in order."""
    lines = _strip_dv_page_headers(lines)
    lines = _strip_word_metadata(lines)
    return lines


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return rtf_to_text(raw.decode(enc, errors="replace"))
        except Exception:
            continue
    return ""


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_rtf(path: Path) -> list[tuple[str, str, str, str | None]]:
    """Return list of (title, body, section, category) for each legislative act in the RTF file."""
    text = _read_text(path)
    if not text:
        return []

    lines = _clean_body(text.splitlines())

    # Phase 1: extract TOC titles
    toc_titles: list[str] = []
    for line in lines[:400]:
        m = _TOC_LINE.match(line)
        if m:
            title = _clean(m.group(1))
            if len(title) > 10:
                toc_titles.append(title)

    # Phase 2: find body start at first section header
    body_start = 0
    for i, line in enumerate(lines):
        if re.match(r"^ОФИЦИАЛЕН РАЗДЕЛ|^НЕОФИЦИАЛЕН РАЗДЕЛ", line.strip()):
            body_start = i
            break

    return _split_acts(lines[body_start:], toc_titles)


def _split_acts(
    body_lines: list[str], toc_titles: list[str]
) -> list[tuple[str, str, str, str | None]]:
    """Split body lines on ALL-CAPS act headings.

    Returns list of (title, body, section, category) where:
      - section is "official" or "unofficial"
      - category is None for official items; a title-cased sub-heading string
        (e.g. "Съобщения") for unofficial items when detected
    """
    # --- Pass 1: collect unofficial items (blank-line splitting) ---
    #
    # We also track section state so we know which lines belong where.
    # Official items are processed in a separate pass below using the original
    # heading-accumulation + TOC-matching logic.

    current_section: str = "official"
    current_category: str | None = None
    unofficial_items: list[tuple[str, str, str, str | None]] = []
    unofficial_block: list[str] = []

    def _flush_unofficial_block() -> None:
        """Emit an unofficial item from the current buffer if long enough."""
        block = [ln for ln in unofficial_block if ln]  # drop any embedded empties
        if not block:
            return
        total = " ".join(block)
        if len(total) >= 80:
            title = block[0]
            body = " ".join(block[1:]) if len(block) > 1 else block[0]
            unofficial_items.append((title, body, "unofficial", current_category))
        unofficial_block.clear()

    i = 0
    while i < len(body_lines):
        line = body_lines[i].strip()

        if line == "ОФИЦИАЛЕН РАЗДЕЛ":
            current_section = "official"
            current_category = None
            i += 1
            continue

        if line == "НЕОФИЦИАЛЕН РАЗДЕЛ":
            _flush_unofficial_block()
            current_section = "unofficial"
            current_category = None
            i += 1
            continue

        if current_section == "unofficial":
            if not line:
                _flush_unofficial_block()
            elif _SKIP_HEADERS.match(line):
                # Category sub-heading (e.g. СЪОБЩЕНИЯ, ПОКАНИ, ОБЯВЛЕНИЯ)
                _flush_unofficial_block()
                current_category = line.title()
            else:
                unofficial_block.append(line)
            i += 1
            continue

        # Official section — nothing to do here; handled in pass 2
        i += 1

    _flush_unofficial_block()  # trailing block

    # --- Pass 2: collect official items using original heading-accumulation logic ---
    #
    # We build a flat buffer of official-section lines and track split positions
    # within that buffer, so TOC matching and body extraction work identically to
    # the original implementation.

    official_line_buf: list[str] = []
    official_splits: list[tuple[int, str]] = []

    current_section2: str = "official"
    i = 0
    while i < len(body_lines):
        line = body_lines[i].strip()

        if line == "ОФИЦИАЛЕН РАЗДЕЛ":
            current_section2 = "official"
            i += 1
            continue
        if line == "НЕОФИЦИАЛЕН РАЗДЕЛ":
            current_section2 = "unofficial"
            i += 1
            continue

        if current_section2 != "official":
            i += 1
            continue

        if _SKIP_HEADERS.match(line):
            i += 1
            continue

        if _CAPS_ACT.match(line):
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
            official_splits.append((len(official_line_buf), " ".join(heading_parts)))
            for k in range(i, j):
                official_line_buf.append(body_lines[k])
            i = j
        else:
            official_line_buf.append(body_lines[i])
            i += 1

    if not official_splits:
        return unofficial_items

    raw_official: list[tuple[str, str]] = []
    for idx, (line_idx, caps_heading) in enumerate(official_splits):
        end_line = official_splits[idx + 1][0] if idx + 1 < len(official_splits) else len(official_line_buf)
        body_chunk = _clean("\n".join(official_line_buf[line_idx:end_line]))

        title = _match_toc_title(caps_heading, toc_titles) or _normalise_heading(caps_heading)

        body = body_chunk
        if body.startswith(caps_heading):
            stripped = body[len(caps_heading):].lstrip(" \n")
            body = stripped if stripped else body_chunk
        elif body.lower().startswith(title[:30].lower()):
            stripped = body[len(title):].lstrip(" \n")
            body = stripped if stripped else body_chunk

        raw_official.append((title, body))

    # Merge consecutive chunks with the same title — repeated headings inside a doc body
    merged_official: list[tuple[str, str]] = []
    for title, body in raw_official:
        if merged_official and merged_official[-1][0] == title:
            merged_official[-1] = (title, (merged_official[-1][1] + " " + body).strip())
        else:
            merged_official.append((title, body))

    # Drop fragments with very little body text (< 80 chars) — likely split artifacts
    official_materials: list[tuple[str, str, str, str | None]] = [
        (t, b, "official", None) for t, b in merged_official if len(b) >= 80
    ]

    return official_materials + unofficial_items


def _normalise_heading(caps: str) -> str:
    """Convert ALL-CAPS heading to title-case for use as title."""
    # Keep number/date parts, title-case the type word
    parts = caps.split(None, 1)
    if not parts:
        return caps
    type_word = parts[0].capitalize()
    rest = parts[1] if len(parts) > 1 else ""
    return f"{type_word} {rest}".strip()


def parse_pdf(path: Path) -> list[tuple[str, str, str, str | None]]:
    """Return list of (title, body, section, category) for each legislative act in the PDF file.

    PDF materials default to section="official" and category=None since pre-2003 RTFs
    won't have section markers.

    Returns an empty list when the PDF uses an undecodable custom font encoding
    (typically pre-2000 issues) — caller should fall back to HTTP in that case.
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        return []

    try:
        doc = fitz.open(str(path))
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    except Exception:
        return []

    if not text:
        return []

    # Pre-2000 PDFs use undecodable custom font encoding — detect and bail out
    cyrillic = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    if cyrillic < 50:
        return []

    return _split_acts(text.splitlines(), toc_titles=[])


def parse_local_issue(path: Path) -> list[tuple[str, str, str, str | None]]:
    """Dispatch to RTF or PDF parser based on file extension."""
    if path.suffix.lower() == ".rtf":
        return parse_rtf(path)
    elif path.suffix.lower() == ".pdf":
        return parse_pdf(path)
    return []


def _match_toc_title(caps_heading: str, toc_titles: list[str]) -> str | None:
    """Find the TOC title that best matches the ALL-CAPS heading."""
    if not toc_titles:
        return None

    # Extract number from heading e.g. "ПОСТАНОВЛЕНИЕ № 12" → "12"
    num_m = re.search(r"№\s*(\d+)", caps_heading)
    heading_num = num_m.group(1) if num_m else None

    # Extract type prefix (first word, normalised)
    caps_type = caps_heading.split()[0].capitalize()

    for t in toc_titles:
        # Match by type + number
        if heading_num and f"№ {heading_num}" in t and t.lower().startswith(caps_type.lower()):
            return t
        # Match by type prefix only (for ЗАКОН ЗА... which has no number)
        if not heading_num and t.lower().startswith(caps_type.lower()):
            # Additional check: first few words of caps match toc
            caps_words = set(caps_heading.lower().split()[:5])
            toc_words = set(t.lower().split()[:5])
            if len(caps_words & toc_words) >= 2:
                return t

    return None
