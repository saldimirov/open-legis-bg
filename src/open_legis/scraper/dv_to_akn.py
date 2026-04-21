"""Convert raw DV text (from showMaterialDV.jsp) to AKN XML."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# --- Act type detection -------------------------------------------------------

_TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("КОДЕКС", "kodeks"),
    ("Кодекс", "kodeks"),
    ("Закон за ратифициране", "ratifikatsiya"),
    ("Закон за изменение и допълнение", "zid"),
    ("Закон за допълнение", "zid"),
    ("Закон за изменение", "zid"),
    ("Закон за държавния бюджет", "byudjet"),
    ("Закон за бюджета на", "byudjet"),
    ("Закон за събирането на приходи и извършването на разходи", "byudjet"),
    ("Закон за прилагане на разпоредби на Закона за държавния бюджет", "byudjet"),
    ("ЗАКОН", "zakon"),
    ("Закон", "zakon"),
    ("НАРЕДБА", "naredba"),
    ("Наредба", "naredba"),
    ("ПОСТАНОВЛЕНИЕ", "postanovlenie"),
    ("Постановление", "postanovlenie"),
    ("ПРАВИЛНИК", "pravilnik"),
    ("Правилник", "pravilnik"),
    ("Решение за", "reshenie_ns"),
    ("Решение на Народното събрание", "reshenie_ns"),
    ("УКАЗ", "ukaz"),
    ("Указ", "ukaz"),
    ("Решение № ", "_court"),
    ("Определение № ", "_court"),
    ("Инструкция", "_other"),
    ("Споразумение", "_other"),
]

LEGISLATIVE_TYPES = {"zakon", "zid", "byudjet", "kodeks", "naredba", "postanovlenie", "pravilnik", "reshenie_ns", "ratifikatsiya"}

_ISSUING_BODY: dict[str, str] = {
    "zakon": "Народно събрание",
    "zid": "Народно събрание",
    "byudjet": "Народно събрание",
    "kodeks": "Народно събрание",
    "naredba": "Министерски съвет",
    "postanovlenie": "Министерски съвет",
    "pravilnik": "Министерски съвет",
    "reshenie_ns": "Народно събрание",
    "ratifikatsiya": "Народно събрание",
    "ukaz": "Президент на Републиката",
}


def detect_act_type(title: str) -> str:
    for keyword, act_type in _TYPE_KEYWORDS:
        if title.startswith(keyword):
            return act_type
    for keyword, act_type in _TYPE_KEYWORDS:
        if keyword in title:
            return act_type
    return "_other"


# --- Slug generation ----------------------------------------------------------

def make_slug(broy: int, year: int, position: int = 1) -> str:
    return f"dv-{broy}-{year % 100:02d}-{position}"


# --- Text parsing -------------------------------------------------------------

@dataclass
class ParsedSection:
    e_id: str
    tag: str          # "hcontainer", "article"
    num: str
    name: Optional[str]   # AKN name attr: "chapter", "section", "modification", etc.
    heading: Optional[str]
    paragraphs: list[str]
    children: list["ParsedSection"] = field(default_factory=list)


# Structural boundary patterns (match at start of a stripped line)
_CHAPTER_RE = re.compile(r"^(Глава\s+\S+)$")
_SECTION_RE = re.compile(r"^(Раздел\s+\S+)$")
_SPECIAL_RE = re.compile(
    r"^(ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ|ЗАКЛЮЧИТЕЛНА РАЗПОРЕДБА"
    r"|ПРЕХОДНИ РАЗПОРЕДБИ|ПРЕХОДНА РАЗПОРЕДБА"
    r"|ДОПЪЛНИТЕЛНИ РАЗПОРЕДБИ|ДОПЪЛНИТЕЛНА РАЗПОРЕДБА"
    r"|ПРЕХОДНИ И ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ|ДОПЪЛНИТЕЛНИ И ПРЕХОДНИ РАЗПОРЕДБИ"
    r"|Заключителни разпоредби|Заключителна разпоредба"
    r"|Преходни разпоредби|Преходна разпоредба"
    r"|Допълнителни разпоредби|Допълнителна разпоредба"
    r"|Преходни и заключителни разпоредби|Допълнителни и преходни разпоредби)$"
)
_ARTICLE_RE = re.compile(r"^(Чл\.\s*\d+[а-я]?)\.")
_PAR_RE = re.compile(r"^(§\s*\d+[а-я]?)\.")

# Sub-article structure patterns
_NUMBERED_PARA_RE = re.compile(r"^\((\d+[а-я]?)\)\s*(.*)")   # (1), (2а) …
_POINT_RE = re.compile(r"^(\d+)\.\s+(.*)")                    # 1. …  (only when ≥ 1 space after dot)
_LETTER_RE = re.compile(r"^([а-я])\)\s+(.*)")                 # а) …

_SPECIAL_NAME = {
    "ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ": "final-provisions",
    "ЗАКЛЮЧИТЕЛНА РАЗПОРЕДБА": "final-provisions",
    "ПРЕХОДНИ РАЗПОРЕДБИ": "transitional-provisions",
    "ПРЕХОДНА РАЗПОРЕДБА": "transitional-provisions",
    "ДОПЪЛНИТЕЛНИ РАЗПОРЕДБИ": "additional-provisions",
    "ДОПЪЛНИТЕЛНА РАЗПОРЕДБА": "additional-provisions",
    "ПРЕХОДНИ И ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ": "transitional-provisions",
    "ДОПЪЛНИТЕЛНИ И ПРЕХОДНИ РАЗПОРЕДБИ": "additional-provisions",
    "Заключителни разпоредби": "final-provisions",
    "Заключителна разпоредба": "final-provisions",
    "Преходни разпоредби": "transitional-provisions",
    "Преходна разпоредба": "transitional-provisions",
    "Допълнителни разпоредби": "additional-provisions",
    "Допълнителна разпоредба": "additional-provisions",
    "Преходни и заключителни разпоредби": "transitional-provisions",
    "Допълнителни и преходни разпоредби": "additional-provisions",
}
_SPECIAL_EID = {
    "final-provisions": "sec_final",
    "transitional-provisions": "sec_trans",
    "additional-provisions": "sec_add",
}


def parse_body_text(text: str, act_type: str) -> list[ParsedSection]:
    if act_type == "zid":
        return _parse_zid(text)
    return _parse_structured(text)


def _clean_text(text: str) -> str:
    for marker in ("ЗАКОН", "КОДЕКС", "НАРЕДБА", "ПОСТАНОВЛЕНИЕ", "ПРАВИЛНИК"):
        m = re.search(rf"(?m)^{marker}\b", text)
        if m:
            text = text[m.start():]
            break
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


def _is_boundary(line: str) -> bool:
    return bool(
        _CHAPTER_RE.match(line)
        or _SECTION_RE.match(line)
        or _SPECIAL_RE.match(line)
        or _ARTICLE_RE.match(line)
        or _PAR_RE.match(line)
    )


def _parse_zid(text: str) -> list[ParsedSection]:
    text = _clean_text(text)
    splits = re.split(r"(?m)(?=§\s*\d+\.)", text)
    sections: list[ParsedSection] = []
    seq = 0
    for chunk in splits:
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"(§\s*\d+[а-я]?)\.", chunk)
        if not m:
            continue
        num = m.group(1).replace("  ", " ").strip() + "."
        body = chunk[m.end():].strip()
        paras = [p.strip() for p in body.split("\n") if p.strip()]
        seq += 1
        sections.append(ParsedSection(
            e_id=f"par_{seq}",
            tag="hcontainer",
            num=num,
            name="modification",
            heading=None,
            paragraphs=paras,
        ))
    return sections


def _parse_article_body(
    lines: list[str], base_e_id: str
) -> tuple[list[str], list[ParsedSection]]:
    """Split article lines into intro text + structured paragraph/point children.

    Returns (intro_lines, children).  If no (N) paragraphs found, returns
    (lines, []) so the caller falls back to a plain content block.
    """
    if not lines:
        return [], []

    # Quick check: does this article have any (N) numbered paragraphs?
    has_numbered = any(_NUMBERED_PARA_RE.match(l) for l in lines)
    if not has_numbered:
        # Check if it has numbered points only (no paragraphs)
        has_points = any(_POINT_RE.match(l) for l in lines)
        if not has_points:
            return lines, []
        # Points without paragraphs — treat intro + points as flat
        # intro = lines up to first point, then points as `point` children
        intro: list[str] = []
        children: list[ParsedSection] = []
        p_seq = 0
        i = 0
        while i < len(lines):
            m = _POINT_RE.match(lines[i])
            if m:
                p_seq += 1
                p_num = m.group(1) + "."
                p_text = m.group(2)
                # Accumulate continuation lines (letters)
                j = i + 1
                sub_children: list[ParsedSection] = []
                l_seq = 0
                while j < len(lines) and not _POINT_RE.match(lines[j]) and not _NUMBERED_PARA_RE.match(lines[j]):
                    lm = _LETTER_RE.match(lines[j])
                    if lm:
                        l_seq += 1
                        sub_children.append(ParsedSection(
                            e_id=f"{base_e_id}__pt_{p_seq}__l_{l_seq}",
                            tag="point",
                            num=lm.group(1) + ")",
                            name=None,
                            heading=None,
                            paragraphs=[lm.group(2)],
                        ))
                    else:
                        if sub_children:
                            sub_children[-1].paragraphs.append(lines[j])
                        else:
                            p_text = (p_text + " " + lines[j]).strip() if p_text else lines[j]
                    j += 1
                point = ParsedSection(
                    e_id=f"{base_e_id}__pt_{p_seq}",
                    tag="point",
                    num=p_num,
                    name=None,
                    heading=None,
                    paragraphs=[p_text] if p_text else [],
                    children=sub_children,
                )
                children.append(point)
                i = j
            else:
                intro.append(lines[i])
                i += 1
        return intro, children

    # --- Articles with (N) numbered paragraphs ---
    intro = []
    children = []
    par_seq = 0
    i = 0
    # Collect intro (lines before first numbered paragraph)
    while i < len(lines) and not _NUMBERED_PARA_RE.match(lines[i]):
        intro.append(lines[i])
        i += 1

    while i < len(lines):
        m = _NUMBERED_PARA_RE.match(lines[i])
        if not m:
            i += 1
            continue
        par_seq += 1
        par_num = f"({m.group(1)})"
        par_text = m.group(2)  # rest of the line after (N)
        i += 1

        # Collect lines belonging to this paragraph
        par_lines: list[str] = [par_text] if par_text else []
        while i < len(lines) and not _NUMBERED_PARA_RE.match(lines[i]):
            par_lines.append(lines[i])
            i += 1

        par_e_id = f"{base_e_id}__al_{par_seq}"

        # Check if paragraph has numbered points
        has_par_points = any(_POINT_RE.match(l) for l in par_lines)
        if not has_par_points:
            children.append(ParsedSection(
                e_id=par_e_id,
                tag="paragraph",
                num=par_num,
                name=None,
                heading=None,
                paragraphs=[l for l in par_lines if l],
            ))
            continue

        # Paragraph with points
        par_intro: list[str] = []
        point_children: list[ParsedSection] = []
        p_seq = 0
        j = 0
        while j < len(par_lines) and not _POINT_RE.match(par_lines[j]):
            par_intro.append(par_lines[j])
            j += 1
        while j < len(par_lines):
            pm = _POINT_RE.match(par_lines[j])
            if pm:
                p_seq += 1
                pt_num = pm.group(1) + "."
                pt_text = pm.group(2)
                k = j + 1
                sub_children: list[ParsedSection] = []
                l_seq = 0
                while k < len(par_lines) and not _POINT_RE.match(par_lines[k]):
                    lm = _LETTER_RE.match(par_lines[k])
                    if lm:
                        l_seq += 1
                        sub_children.append(ParsedSection(
                            e_id=f"{par_e_id}__pt_{p_seq}__l_{l_seq}",
                            tag="point",
                            num=lm.group(1) + ")",
                            name=None,
                            heading=None,
                            paragraphs=[lm.group(2)],
                        ))
                    else:
                        if sub_children:
                            sub_children[-1].paragraphs.append(par_lines[k])
                        else:
                            pt_text = (pt_text + " " + par_lines[k]).strip() if pt_text else par_lines[k]
                    k += 1
                point_children.append(ParsedSection(
                    e_id=f"{par_e_id}__pt_{p_seq}",
                    tag="point",
                    num=pt_num,
                    name=None,
                    heading=None,
                    paragraphs=[pt_text] if pt_text else [],
                    children=sub_children,
                ))
                j = k
            else:
                j += 1

        children.append(ParsedSection(
            e_id=par_e_id,
            tag="paragraph",
            num=par_num,
            name=None,
            heading=None,
            paragraphs=[l for l in par_intro if l],
            children=point_children,
        ))

    return intro, children


def _parse_structured(text: str) -> list[ParsedSection]:
    """Parse a standalone law preserving chapter/section/special-section hierarchy."""
    text = _clean_text(text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    root: list[ParsedSection] = []
    current_chapter: Optional[ParsedSection] = None
    current_section: Optional[ParsedSection] = None
    current_special: Optional[ParsedSection] = None

    chap_seq = section_seq = art_seq = par_seq = 0
    _special_eid_counts: dict[str, int] = {}

    def _current_container() -> Optional[ParsedSection]:
        if current_special:
            return current_special
        if current_section:
            return current_section
        if current_chapter:
            return current_chapter
        return None

    def _add(sec: ParsedSection) -> None:
        c = _current_container()
        if c is not None:
            c.children.append(sec)
        else:
            root.append(sec)

    i = 0
    while i < len(lines):
        line = lines[i]

        # --- Chapter ---
        m = _CHAPTER_RE.match(line)
        if m:
            chap_seq += 1
            section_seq = 0
            # Collect heading lines (until next boundary)
            j = i + 1
            heading_parts: list[str] = []
            while j < len(lines) and not _is_boundary(lines[j]):
                heading_parts.append(lines[j])
                j += 1
            current_chapter = ParsedSection(
                e_id=f"chap_{chap_seq}",
                tag="chapter",
                num=m.group(1),
                name=None,
                heading=" ".join(heading_parts) or None,
                paragraphs=[],
            )
            current_section = None
            current_special = None
            root.append(current_chapter)
            i = j
            continue

        # --- Section ---
        m = _SECTION_RE.match(line)
        if m:
            section_seq += 1
            j = i + 1
            heading_parts = []
            while j < len(lines) and not _is_boundary(lines[j]):
                heading_parts.append(lines[j])
                j += 1
            prefix = f"chap_{chap_seq}__" if current_chapter else ""
            current_section = ParsedSection(
                e_id=f"{prefix}sec_{section_seq}",
                tag="section",
                num=m.group(1),
                name=None,
                heading=" ".join(heading_parts) or None,
                paragraphs=[],
            )
            current_special = None
            if current_chapter:
                current_chapter.children.append(current_section)
            else:
                root.append(current_section)
            i = j
            continue

        # --- Special section (ЗАКЛЮЧИТЕЛНИ / ПРЕХОДНИ / ДОПЪЛНИТЕЛНИ) ---
        m = _SPECIAL_RE.match(line)
        if m:
            par_seq = 0
            label = m.group(1)
            sname = _SPECIAL_NAME.get(label, "special")
            base_eid = _SPECIAL_EID.get(sname, "sec_special")
            _special_eid_counts[base_eid] = _special_eid_counts.get(base_eid, 0) + 1
            eid = base_eid if _special_eid_counts[base_eid] == 1 else f"{base_eid}_{_special_eid_counts[base_eid]}"
            current_special = ParsedSection(
                e_id=eid,
                tag="hcontainer",
                num=label,
                name=sname,
                heading=None,
                paragraphs=[],
            )
            current_chapter = None
            current_section = None
            root.append(current_special)
            i += 1
            continue

        # --- Article (Чл. N.) ---
        m = _ARTICLE_RE.match(line)
        if m:
            art_seq += 1
            num = line[: line.index(".", line.index(".") + 1) + 1] if line.count(".") >= 2 else m.group(1) + "."
            # Use the full match including the dot
            num = re.match(r"(Чл\.\s*\d+[а-я]?\.)", line).group(1)  # type: ignore[union-attr]
            body = line[len(num):].strip()
            j = i + 1
            paras = [body] if body else []
            while j < len(lines) and not _is_boundary(lines[j]):
                paras.append(lines[j])
                j += 1
            container = _current_container()
            prefix = f"{container.e_id}__" if container else ""
            art_e_id = f"{prefix}art_{art_seq}"
            intro, sub_children = _parse_article_body([p for p in paras if p], art_e_id)
            art = ParsedSection(
                e_id=art_e_id,
                tag="article",
                num=num,
                name=None,
                heading=None,
                paragraphs=intro,
                children=sub_children,
            )
            _add(art)
            i = j
            continue

        # --- § item — always belongs to closing provisions, never mid-chapter ---
        # If the ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ heading was absent or didn't match
        # (wrong casing, missing line, etc.) we synthesise it here so § items
        # are never attached to whatever chapter happened to be open last.
        m = _PAR_RE.match(line)
        if m:
            if current_special is None:
                base_eid = "sec_final"
                _special_eid_counts[base_eid] = _special_eid_counts.get(base_eid, 0) + 1
                eid = base_eid if _special_eid_counts[base_eid] == 1 else f"{base_eid}_{_special_eid_counts[base_eid]}"
                current_special = ParsedSection(
                    e_id=eid,
                    tag="hcontainer",
                    num="ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ",
                    name="final-provisions",
                    heading=None,
                    paragraphs=[],
                )
                current_chapter = None
                current_section = None
                root.append(current_special)
            par_seq += 1
            num = m.group(1).replace("  ", " ").strip() + "."
            body = line[m.end():].strip()
            j = i + 1
            paras = [body] if body else []
            while j < len(lines) and not _is_boundary(lines[j]):
                paras.append(lines[j])
                j += 1
            par = ParsedSection(
                e_id=f"{current_special.e_id}__par_{par_seq}",
                tag="hcontainer",
                num=num,
                name="modification",
                heading=None,
                paragraphs=[p for p in paras if p],
            )
            current_special.children.append(par)
            i = j
            continue

        i += 1

    return root


# --- AKN XML builder ----------------------------------------------------------

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def _x(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_section(sec: ParsedSection, depth: int = 3) -> list[str]:
    pad = "  " * depth
    lines: list[str] = []
    attrs = f'eId="{sec.e_id}"'
    if sec.name:
        attrs += f' name="{sec.name}"'
    lines.append(f"{pad}<{sec.tag} {attrs}>")
    lines.append(f"{pad}  <num>{_x(sec.num)}</num>")
    if sec.heading:
        lines.append(f"{pad}  <heading>{_x(sec.heading)}</heading>")
    if sec.children:
        if sec.paragraphs:
            lines.append(f"{pad}  <intro>")
            for para in sec.paragraphs:
                lines.append(f"{pad}    <p>{_x(para)}</p>")
            lines.append(f"{pad}  </intro>")
        for child in sec.children:
            lines.extend(_render_section(child, depth + 1))
    else:
        lines.append(f"{pad}  <content>")
        for para in sec.paragraphs:
            lines.append(f"{pad}    <p>{_x(para)}</p>")
        lines.append(f"{pad}  </content>")
    lines.append(f"{pad}</{sec.tag}>")
    return lines


def build_akn_xml(
    *,
    title: str,
    act_type: str,
    slug: str,
    dv_year: int,
    dv_broy: int,
    dv_position: int,
    expression_date: str,
    adoption_date: str,
    language: str = "bul",
    sections: list[ParsedSection],
    publication_history: str = "",
) -> str:
    eli = f"/eli/bg/{act_type}/{dv_year}/{slug}"
    akn_work = f"/akn/bg/act/{dv_year}/{slug}"
    akn_expr = f"{akn_work}/{language}@{expression_date}"
    issuing_body = _ISSUING_BODY.get(act_type, "Народно събрание")

    body_lines: list[str] = []
    for sec in sections:
        body_lines.extend(_render_section(sec, depth=3))

    preface_parts = [f"<p>{_x(title)}</p>"]
    if publication_history:
        preface_parts.append(f"<p>{_x(publication_history)}</p>")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<akomaNtoso xmlns="{_AKN_NS}">',
        '  <act contains="originalVersion">',
        "    <meta>",
        '      <identification source="#openlegis">',
        "        <FRBRWork>",
        f'          <FRBRthis value="{akn_work}/main"/>',
        f'          <FRBRuri value="{akn_work}"/>',
        f'          <FRBRalias value="{_x(title)}" name="short"/>',
        f'          <FRBRalias value="{_x(title)}" name="eli" other="{eli}"/>',
        f'          <FRBRdate date="{adoption_date}" name="Generation"/>',
        '          <FRBRauthor href="#parliament"/>',
        '          <FRBRcountry value="bg"/>',
        f'          <FRBRnumber value="{dv_position}"/>',
        "        </FRBRWork>",
        "        <FRBRExpression>",
        f'          <FRBRthis value="{akn_expr}/main"/>',
        f'          <FRBRuri value="{akn_expr}"/>',
        f'          <FRBRdate date="{expression_date}" name="Generation"/>',
        '          <FRBRauthor href="#parliament"/>',
        f'          <FRBRlanguage language="{language}"/>',
        "        </FRBRExpression>",
        "        <FRBRManifestation>",
        f'          <FRBRthis value="{akn_expr}/main.xml"/>',
        f'          <FRBRuri value="{akn_expr}.xml"/>',
        f'          <FRBRdate date="{expression_date}" name="Generation"/>',
        '          <FRBRauthor href="#parliament"/>',
        '          <FRBRformat value="application/akn+xml"/>',
        "        </FRBRManifestation>",
        "      </identification>",
        f'      <publication date="{expression_date}" name="Държавен вестник" number="{dv_broy}" showAs="ДВ"/>',
        '      <references source="#openlegis">',
        f'        <TLCOrganization eId="parliament" href="/ontology/organization/bg/NarodnoSabranie" showAs="{_x(issuing_body)}"/>',
        '        <TLCPerson eId="openlegis" href="/ontology/person/openlegis" showAs="open-legis"/>',
        "      </references>",
        "    </meta>",
        "    <preface>",
    ]
    for pf in preface_parts:
        lines.append(f"      {pf}")
    lines += ["    </preface>", "    <body>"]
    lines.extend(body_lines)
    lines += ["    </body>", "  </act>", "</akomaNtoso>", ""]
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
    from open_legis.scraper.dv_client import DvIssue as _DvIssue  # noqa: F401

    act_type = detect_act_type(title)
    slug = make_slug(issue.broy, issue.year, position)

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
