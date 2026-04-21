"""Convert raw DV text (from showMaterialDV.jsp) to AKN XML."""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from typing import Optional

# --- Act type detection -------------------------------------------------------

_TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("КОДЕКС", "kodeks"),
    ("Кодекс", "kodeks"),
    ("Закон за ратифициране", "zakon"),
    ("Закон за изменение и допълнение", "zakon"),
    ("Закон за допълнение", "zakon"),
    ("Закон за изменение", "zakon"),
    ("ЗАКОН", "zakon"),
    ("Закон", "zakon"),
    ("НАРЕДБА", "naredba"),
    ("Наредба", "naredba"),
    ("ПОСТАНОВЛЕНИЕ", "postanovlenie"),
    ("Постановление", "postanovlenie"),
    ("ПРАВИЛНИК", "pravilnik"),
    ("Правилник", "pravilnik"),
    # Parliamentary decisions (Решение на/за Народното събрание)
    ("Решение за", "reshenie_ns"),
    ("Решение на Народното събрание", "reshenie_ns"),
    ("УКАЗ", "ukaz"),
    ("Указ", "ukaz"),
    # Court/constitutional decisions — not legislative acts
    ("Решение № ", "_court"),
    ("Определение № ", "_court"),
    # Non-legislative documents
    ("Инструкция", "_other"),
    ("Споразумение", "_other"),
]

# Act types we care about for legislative data
LEGISLATIVE_TYPES = {"zakon", "kodeks", "naredba", "postanovlenie", "pravilnik", "reshenie_ns"}

_ISSUING_BODY: dict[str, str] = {
    "zakon": "Народно събрание",
    "kodeks": "Народно събрание",
    "naredba": "Министерски съвет",
    "postanovlenie": "Министерски съвет",
    "pravilnik": "Министерски съвет",
    "reshenie_ns": "Народно събрание",
    "ukaz": "Президент на Републиката",
}


def detect_act_type(title: str) -> str:
    # Check if the title STARTS with the keyword (word boundary check)
    # to avoid "Постановление ... за изменение на Закона ..." matching "Закон"
    for keyword, act_type in _TYPE_KEYWORDS:
        if title.startswith(keyword):
            return act_type
    # Fallback: substring match for all-caps variants (titles scraped in caps)
    for keyword, act_type in _TYPE_KEYWORDS:
        if keyword in title:
            return act_type
    return "_other"


# --- Slug generation ----------------------------------------------------------

def make_slug(broy: int, year: int, position: int = 1) -> str:
    """Generate a unique slug per law within an issue: dv-{broy}-{yy}-{pos}."""
    return f"dv-{broy}-{year % 100:02d}-{position}"


# --- Text parsing -------------------------------------------------------------

@dataclass
class ParsedSection:
    e_id: str
    tag: str  # "hcontainer", "article", "paragraph"
    num: str
    name: Optional[str]  # "modification" for § in ZID
    paragraphs: list[str]


def parse_body_text(text: str, act_type: str) -> list[ParsedSection]:
    """Parse DV body text into structured sections."""
    # Detect ZID (has §-paragraph structure)
    has_paragraphs = bool(re.search(r"§\s*\d+\.", text))

    if has_paragraphs:
        return _parse_zid(text)
    else:
        return _parse_articles(text)


def _clean_text(text: str) -> str:
    """Remove the presidential decree preamble and signature block."""
    # Remove everything before the main law title (ЗАКОН/НАРЕДБА/etc.)
    # The preamble starts with УКАЗ №
    # Find the main act title line
    for marker in ("ЗАКОН", "КОДЕКС", "НАРЕДБА", "ПОСТАНОВЛЕНИЕ", "ПРАВИЛНИК"):
        m = re.search(rf"(?m)^{marker}\b", text)
        if m:
            text = text[m.start():]
            break

    # Remove signature/ending
    for end_marker in (
        "Законът е приет от",
        "Постановлението е прието от",
        "Наредбата е приета от",
        "Правилникът е приет от",
        "Председател на Народното събрание",
        "Министър-председател:",
    ):
        idx = text.find(end_marker)
        if idx >= 0:
            text = text[:idx]
            break

    return text.strip()


def _parse_zid(text: str) -> list[ParsedSection]:
    """Parse a ZID (amendment law) with § N. markers."""
    text = _clean_text(text)

    # Split on § N. boundaries (each § starts on its own line ideally)
    # Pattern: § followed by digits and dot
    splits = re.split(r"(?m)(?=§\s*\d+\.)", text)
    sections: list[ParsedSection] = []
    seq = 0
    for chunk in splits:
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"(§\s*\d+[а-я]?)\.", chunk)
        if not m:
            # Could be preface text
            continue
        num = m.group(1).replace("  ", " ").strip()  # "§ 1"
        num_full = num + "."  # "§ 1."
        body = chunk[m.end():].strip()

        # Split body into paragraphs
        paras = [p.strip() for p in body.split("\n") if p.strip()]

        seq += 1
        e_id = f"par_{seq}"
        sections.append(
            ParsedSection(
                e_id=e_id,
                tag="hcontainer",
                num=num_full,
                name="modification",
                paragraphs=paras,
            )
        )
    return sections


def _parse_articles(text: str) -> list[ParsedSection]:
    """Parse a standalone law with Чл. N. markers."""
    text = _clean_text(text)

    splits = re.split(r"(?m)(?=Чл\.\s*\d+\.)", text)
    sections: list[ParsedSection] = []
    seq = 0
    for chunk in splits:
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"(Чл\.\s*\d+[а-я]?)\.", chunk)
        if not m:
            continue
        num = m.group(0)  # "Чл. 1."
        body = chunk[m.end():].strip()
        paras = [p.strip() for p in body.split("\n") if p.strip()]
        seq += 1
        e_id = f"art_{seq}"
        sections.append(
            ParsedSection(
                e_id=e_id,
                tag="article",
                num=num,
                name=None,
                paragraphs=paras,
            )
        )
    return sections


# --- AKN XML builder ----------------------------------------------------------

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def build_akn_xml(
    *,
    title: str,
    act_type: str,
    slug: str,
    dv_year: int,
    dv_broy: int,
    dv_position: int,
    expression_date: str,  # YYYY-MM-DD
    adoption_date: str,  # YYYY-MM-DD
    language: str = "bul",
    sections: list[ParsedSection],
    publication_history: str = "",
) -> str:
    """Build a minimal AKN XML string."""
    eli = f"/eli/bg/{act_type}/{dv_year}/{slug}"
    akn_work = f"/akn/bg/act/{dv_year}/{slug}"
    akn_expr = f"{akn_work}/{language}@{expression_date}"
    issuing_body = _ISSUING_BODY.get(act_type, "Народно събрание")

    def x(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    body_lines: list[str] = []
    for sec in sections:
        attrs = f'eId="{sec.e_id}"'
        if sec.name:
            attrs += f' name="{sec.name}"'
        body_lines.append(f'      <{sec.tag} {attrs}>')
        body_lines.append(f"        <num>{x(sec.num)}</num>")
        body_lines.append("        <content>")
        for para in sec.paragraphs:
            body_lines.append(f"          <p>{x(para)}</p>")
        body_lines.append("        </content>")
        body_lines.append(f"      </{sec.tag}>")

    body_str = "\n".join(body_lines)

    preface_parts = [f"<p>{x(title)}</p>"]
    if publication_history:
        preface_parts.append(f"<p>{x(publication_history)}</p>")

    preface_str = "\n      ".join(preface_parts)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<akomaNtoso xmlns="{_AKN_NS}">',
        "  <act contains=\"originalVersion\">",
        "    <meta>",
        "      <identification source=\"#openlegis\">",
        "        <FRBRWork>",
        f"          <FRBRthis value=\"{akn_work}/main\"/>",
        f"          <FRBRuri value=\"{akn_work}\"/>",
        f"          <FRBRalias value=\"{x(title)}\" name=\"short\"/>",
        f"          <FRBRalias value=\"{x(title)}\" name=\"eli\" other=\"{eli}\"/>",
        f"          <FRBRdate date=\"{adoption_date}\" name=\"Generation\"/>",
        "          <FRBRauthor href=\"#parliament\"/>",
        "          <FRBRcountry value=\"bg\"/>",
        f"          <FRBRnumber value=\"{dv_position}\"/>",
        "        </FRBRWork>",
        "        <FRBRExpression>",
        f"          <FRBRthis value=\"{akn_expr}/main\"/>",
        f"          <FRBRuri value=\"{akn_expr}\"/>",
        f"          <FRBRdate date=\"{expression_date}\" name=\"Generation\"/>",
        "          <FRBRauthor href=\"#parliament\"/>",
        f"          <FRBRlanguage language=\"{language}\"/>",
        "        </FRBRExpression>",
        "        <FRBRManifestation>",
        f"          <FRBRthis value=\"{akn_expr}/main.xml\"/>",
        f"          <FRBRuri value=\"{akn_expr}.xml\"/>",
        f"          <FRBRdate date=\"{expression_date}\" name=\"Generation\"/>",
        "          <FRBRauthor href=\"#parliament\"/>",
        "          <FRBRformat value=\"application/akn+xml\"/>",
        "        </FRBRManifestation>",
        "      </identification>",
        f"      <publication date=\"{expression_date}\" name=\"Държавен вестник\" number=\"{dv_broy}\" showAs=\"ДВ\"/>",
        "      <references source=\"#openlegis\">",
        f"        <TLCOrganization eId=\"parliament\" href=\"/ontology/organization/bg/NarodnoSabranie\" showAs=\"{x(issuing_body)}\"/>",
        "        <TLCPerson eId=\"openlegis\" href=\"/ontology/person/openlegis\" showAs=\"open-legis\"/>",
        "      </references>",
        "    </meta>",
        "    <preface>",
    ]
    for pf in preface_parts:
        lines.append(f"      {pf}")
    lines += [
        "    </preface>",
        "    <body>",
    ]
    lines.extend(body_lines)
    lines += [
        "    </body>",
        "  </act>",
        "</akomaNtoso>",
        "",
    ]
    return "\n".join(lines)


# --- High-level convert -------------------------------------------------------

def convert_material(
    *,
    title: str,
    body: str,
    idMat: int,
    issue: "DvIssue",  # type: ignore[name-defined]
    position: int = 1,
) -> tuple[str, str]:
    """Return (slug, akn_xml) for a scraped DV material.

    slug: e.g. 'dv-30-26'
    akn_xml: full AKN XML string
    """
    from open_legis.scraper.dv_client import DvIssue as _DvIssue  # noqa: F401

    act_type = detect_act_type(title)
    slug = make_slug(issue.broy, issue.year, position)

    # Extract publication history from body (inside parentheses after title)
    pub_history = ""
    ph_m = re.search(r"\(обн\.,.*?\)", body)
    if ph_m:
        pub_history = ph_m.group(0)

    sections = parse_body_text(body, act_type)

    xml = build_akn_xml(
        title=title,
        act_type=act_type,
        slug=slug,
        dv_year=issue.year,
        dv_broy=issue.broy,
        dv_position=position,
        expression_date=issue.date,
        adoption_date=issue.date,
        sections=sections,
        publication_history=pub_history,
    )
    return slug, xml
