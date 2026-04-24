"""Tokenizer for Bulgarian legal text from dv.parliament.bg."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import auto, Enum


class TK(Enum):
    CHAPTER = auto()        # Глава I / ГЛАВА I
    SECTION = auto()        # Раздел I / РАЗДЕЛ I
    SPECIAL = auto()        # ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ etc.
    ARTICLE = auto()        # Чл. 1.
    PAR_ITEM = auto()       # § 1.  (modification / provision item)
    NUMBERED_PARA = auto()  # (1), (2а)
    POINT = auto()          # 1.  (with trailing space + text)
    LETTER = auto()         # а) text
    TEXT = auto()


@dataclass
class Token:
    kind: TK
    num: str            # structural marker ("Глава I", "§ 3.", "(1)", "1.", ...)
    rest: str           # text following the marker on the same line
    raw: str            # original line (for diagnostics)
    special_name: str = field(default="")  # AKN name attr (SPECIAL tokens only)
    special_eid: str = field(default="")   # base eId prefix (SPECIAL tokens only)


# ── Patterns ──────────────────────────────────────────────────────────────────

_CHAPTER_RE = re.compile(r"^(Глава\s+\S+)$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^(Раздел\s+\S+)$", re.IGNORECASE)
_ARTICLE_RE = re.compile(r"^(Чл\.\s*\d+[а-яА-Я]?)\.(?:\s+(.*))?$")
_PAR_ITEM_RE = re.compile(r"^(§\s*\d+[а-яА-Я]?)\.(?:\s+(.*))?$")
_NUMBERED_PARA_RE = re.compile(r"^\((\d+[а-яА-Я]?)\)\s*(.*)")
_POINT_RE = re.compile(r"^(\d+)\.\s+(.*)")       # space required after dot
_LETTER_RE = re.compile(r"^([а-я])\)\s+(.*)")    # Cyrillic letter only

# Special-section headings: (compiled pattern, akn_name, base_eid)
# Most-specific combined forms must come before individual forms.
_SPECIAL_TABLE: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"^ПРЕХОДНИ И ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ$", re.I),    "transitional-provisions", "sec_trans"),
    (re.compile(r"^ДОПЪЛНИТЕЛНИ И ПРЕХОДНИ РАЗПОРЕДБИ$", re.I),    "additional-provisions",   "sec_add"),
    (re.compile(r"^ДОПЪЛНИТЕЛНИ И ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ$", re.I), "additional-provisions",   "sec_add"),
    (re.compile(r"^ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ$", re.I),               "final-provisions",        "sec_final"),
    (re.compile(r"^ЗАКЛЮЧИТЕЛНА РАЗПОРЕДБА$", re.I),               "final-provisions",        "sec_final"),
    (re.compile(r"^ПРЕХОДНИ РАЗПОРЕДБИ$", re.I),                   "transitional-provisions", "sec_trans"),
    (re.compile(r"^ПРЕХОДНА РАЗПОРЕДБА$", re.I),                   "transitional-provisions", "sec_trans"),
    (re.compile(r"^ДОПЪЛНИТЕЛНИ РАЗПОРЕДБИ$", re.I),               "additional-provisions",   "sec_add"),
    (re.compile(r"^ДОПЪЛНИТЕЛНА РАЗПОРЕДБА$", re.I),               "additional-provisions",   "sec_add"),
]

_END_MARKERS = (
    "Законът е приет от",
    "Постановлението е прието от",
    "Наредбата е приета от",
    "Правилникът е приет от",
    "Председател на Народното събрание",
    "Министър-председател:",
)
_START_MARKERS = ("ЗАКОН", "КОДЕКС", "НАРЕДБА", "ПОСТАНОВЛЕНИЕ", "ПРАВИЛНИК")
_COLLAPSED_THRESHOLD = 200
_XML_INVALID_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_text(text: str) -> str:
    """Strip boilerplate from DV source text; inject newlines if RTF-collapsed."""
    text = _XML_INVALID_CHARS.sub("", text)

    newline_ratio = text.count("\n") / max(len(text), 1)
    collapsed = newline_ratio < 1 / _COLLAPSED_THRESHOLD

    for marker in _START_MARKERS:
        pat = rf"{marker}\b" if collapsed else rf"(?m)^{marker}\b"
        m = re.search(pat, text)
        if m:
            text = text[m.start():]
            break
    else:
        if collapsed:
            m = re.search(r"Чл\.\s+1\.", text)
            if m:
                text = text[m.start():]

    for marker in _END_MARKERS:
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx]
            break

    if collapsed:
        text = _inject_newlines(text)

    return text.strip()


def _inject_newlines(text: str) -> str:
    text = re.sub(r"(?<!\n)(Чл\.\s+\d+[а-яА-Я]?\.)", r"\n\1", text)
    text = re.sub(r"(?<!\n)(\(\d+\)\s)", r"\n\1", text)
    text = re.sub(r"(?<!\n)(§\s*\d+\.)", r"\n\1", text)
    for pat in (r"(ГЛАВА\s+[ИВХЛЦМДЕЖ\d]+)", r"(РАЗДЕЛ\s+[ИВХЛЦМДЕЖ\d]+)"):
        text = re.sub(rf"(?<!\n)({pat})", r"\n\1", text)
    return text


def tokenize(text: str) -> list[Token]:
    """Convert cleaned text lines to a token stream."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [_tok(line) for line in lines]


def _tok(line: str) -> Token:
    # 1. Special headings (check before chapter/section to avoid false matches)
    for pat, name, eid in _SPECIAL_TABLE:
        if pat.match(line):
            return Token(TK.SPECIAL, num=line, rest="", raw=line,
                         special_name=name, special_eid=eid)

    # 2. Chapter
    m = _CHAPTER_RE.match(line)
    if m:
        return Token(TK.CHAPTER, num=m.group(1), rest="", raw=line)

    # 3. Section
    m = _SECTION_RE.match(line)
    if m:
        return Token(TK.SECTION, num=m.group(1), rest="", raw=line)

    # 4. Article
    m = _ARTICLE_RE.match(line)
    if m:
        return Token(TK.ARTICLE, num=m.group(1) + ".", rest=(m.group(2) or "").strip(), raw=line)

    # 5. § item
    m = _PAR_ITEM_RE.match(line)
    if m:
        num = m.group(1).replace("  ", " ").strip() + "."
        return Token(TK.PAR_ITEM, num=num, rest=(m.group(2) or "").strip(), raw=line)

    # 6. Numbered paragraph (1), (1а)
    m = _NUMBERED_PARA_RE.match(line)
    if m:
        return Token(TK.NUMBERED_PARA, num=f"({m.group(1)})", rest=m.group(2).strip(), raw=line)

    # 7. Numbered point  1. text
    m = _POINT_RE.match(line)
    if m:
        return Token(TK.POINT, num=m.group(1) + ".", rest=m.group(2).strip(), raw=line)

    # 8. Letter  а) text
    m = _LETTER_RE.match(line)
    if m:
        return Token(TK.LETTER, num=m.group(1) + ")", rest=m.group(2).strip(), raw=line)

    return Token(TK.TEXT, num="", rest=line, raw=line)
