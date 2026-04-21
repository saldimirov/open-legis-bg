"""Parse a DV RTF issue file into individual materials.

DV RTF structure:
  - Mixed-case TOC lines: "Title text \\t page_number"
  - Section headers: "ОФИЦИАЛЕН РАЗДЕЛ", "НАРОДНО СЪБРАНИЕ", etc.
  - Act headings in ALL CAPS: "ЗАКОН", "ПОСТАНОВЛЕНИЕ № X от ...", "УКАЗ № X", etc.
  - Act body: plain text paragraphs

Strategy:
  1. Extract TOC titles (mixed-case, more descriptive)
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


def parse_rtf(path: Path) -> list[tuple[str, str]]:
    """Return list of (title, body) for each legislative act in the RTF file."""
    text = _read_text(path)
    if not text:
        return []

    lines = text.splitlines()

    # --- Phase 1: extract TOC titles for lookup ---
    toc_titles: list[str] = []
    for line in lines[:400]:
        m = _TOC_LINE.match(line)
        if m:
            title = _clean(m.group(1))
            if len(title) > 10:
                toc_titles.append(title)

    # --- Phase 2: find body start (first section header) ---
    body_start = 0
    for i, line in enumerate(lines):
        if re.match(r"^ОФИЦИАЛЕН РАЗДЕЛ|^НЕОФИЦИАЛЕН РАЗДЕЛ", line.strip()):
            body_start = i
            break

    body_lines = lines[body_start:]

    # --- Phase 3: split on ALL-CAPS act headings ---
    # Collect (line_index, heading) pairs
    splits: list[tuple[int, str]] = []
    i = 0
    while i < len(body_lines):
        line = body_lines[i].strip()
        if _CAPS_ACT.match(line) and not _SKIP_HEADERS.match(line):
            # Collect heading: first CAPS line + following "за ..." subject lines
            heading_parts = [line]
            j = i + 1
            while j < len(body_lines):
                next_line = body_lines[j].strip()
                if not next_line:
                    break
                # Subject lines start with lowercase (за/относно/и/на) or continuation
                if re.match(r"^(за |относно |и |на |от )", next_line, re.IGNORECASE):
                    heading_parts.append(next_line)
                    j += 1
                else:
                    break
            heading = " ".join(heading_parts)
            splits.append((i, heading))
            i = j
        else:
            i += 1

    if not splits:
        return []

    # --- Phase 4: build (title, body) pairs ---
    materials: list[tuple[str, str]] = []
    for idx, (line_idx, caps_heading) in enumerate(splits):
        end_line = splits[idx + 1][0] if idx + 1 < len(splits) else len(body_lines)
        body_chunk = _clean("\n".join(body_lines[line_idx:end_line]))

        # Try to match to a TOC title for a better (more descriptive) title
        # Match by: same act number, or same prefix words
        title = _match_toc_title(caps_heading, toc_titles) or _normalise_heading(caps_heading)

        # Strip the heading from the body chunk start
        body = body_chunk
        if body.startswith(caps_heading):
            body = body[len(caps_heading):].lstrip(" \n")
        elif body.lower().startswith(title[:30].lower()):
            body = body[len(title):].lstrip(" \n")

        materials.append((title, body))

    return materials


def _normalise_heading(caps: str) -> str:
    """Convert ALL-CAPS heading to title-case for use as title."""
    # Keep number/date parts, title-case the type word
    parts = caps.split(None, 1)
    if not parts:
        return caps
    type_word = parts[0].capitalize()
    rest = parts[1] if len(parts) > 1 else ""
    return f"{type_word} {rest}".strip()


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
