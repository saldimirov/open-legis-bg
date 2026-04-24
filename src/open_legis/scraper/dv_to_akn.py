"""Convert raw DV text (from showMaterialDV.jsp) to AKN XML."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# --- Act type detection -------------------------------------------------------

_TYPE_KEYWORDS: list[tuple[str, str]] = [
    # Exclude maritime IMO codes and professional/conduct codes before generic kodeks match
    ("КОДЕКС ЗА БЕЗОПАСНОСТ", "_other"),
    ("КОДЕКС ЗА РАЗШИРЕНИ", "_other"),
    ("КОДЕКС ЗА УПРАВЛЕНИЕ", "_other"),
    ("КОДЕКС ЗА ПРЕВОЗ", "_other"),
    ("КОДЕКС ЗА КОНСТРУКЦИЯТА", "_other"),
    ("КОДЕКС ЗА ОДОБРЕНИЕ", "_other"),
    ("КОДЕКС ЗА НИВАТА", "_other"),
    ("КОДЕКС ЗА СИГУРНОСТ", "_other"),
    ("КОДЕКС ЗА ПРИЛАГАНЕ", "_other"),
    ("КОДЕКС НА ПОВЕДЕНИЕ", "_other"),
    ("КОДЕКС ОТ 20", "_other"),  # "Кодекс от 2008 г."
    ("КОДЕКС ЗА NOх", "_other"),
    ("Кодекс за безопасност", "_other"),
    ("Кодекс за разширени", "_other"),
    ("Кодекс за управление на безопасността", "_other"),
    ("Кодекс за превоз", "_other"),
    ("Кодекс за конструкцията", "_other"),
    ("Кодекс за одобрение", "_other"),
    ("Кодекс за нивата", "_other"),
    ("Кодекс за сигурност на корабите", "_other"),
    ("Кодекс за прилагане на задължителните", "_other"),
    ("Кодекс за разследване на морски", "_other"),
    ("Кодекс за устойчивост", "_other"),
    ("Кодекс за добра", "_other"),
    ("Кодекс за поведение", "_other"),
    ("Кодекс за признатите", "_other"),
    ("Кодекс за признати", "_other"),
    ("Кодекс за професионална", "_other"),
    ("Кодекс ЗА ПОВЕДЕНИЕ", "_other"),
    ("Кодекс ЗА БЕЗОПАСНОСТ", "_other"),
    ("Кодекс ЗА РАЗШИРЕНИ", "_other"),
    ("Кодекс НА ПОВЕДЕНИЕ", "_other"),
    ("КОДЕКС", "kodeks"),
    ("Кодекс", "kodeks"),
    ("Закон за ратифициране", "ratifikatsiya"),
    ("Закон за изменение и допълнение", "zid"),
    ("Закон за допълнение", "zid"),
    ("Закон за изменение", "zid"),
    ("Закон за отмяна", "zid"),
    ("Поправка", "zid"),
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
    # Regulatory decisions — matched before the generic _court catch below
    ("Решение № РД-НС-04", "reshenie_nhif"),   # НЗОК (health insurance fund)
    ("Решение № РД-НС-", "reshenie_nhif"),
    ("Решение № ТПрГ", "reshenie_kevr"),        # КЕВР energy price regulation
    ("Решение № ", "_court"),
    ("Определение № ", "_court"),
    ("Инструкция", "_other"),
    ("Споразумение", "_other"),
]

LEGISLATIVE_TYPES = {
    "zakon", "zid", "byudjet", "kodeks", "naredba", "postanovlenie", "pravilnik",
    "reshenie_ns", "reshenie_ks", "reshenie_ms", "reshenie_kevr", "reshenie_kfn", "reshenie_nhif",
    "ratifikatsiya",
}

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
    "reshenie_ms": "Министерски съвет",
    "reshenie_kevr": "Комисия за енергийно и водно регулиране",
    "reshenie_kfn": "Комисия за финансов надзор",
    "reshenie_nhif": "Национална здравноосигурителна каса",
}

# Regex for decision number suffixes/prefixes that indicate the issuing body
_RESHENIE_SUFFIX_RE = re.compile(
    r"^Решение\s+№\s+(?:ТПрГ|ТПГ)\b"
    r"|^Решение\s+№\s+\S*-(?P<suffix>ОЗ|ЖЗ|ОЕ|ЕС|ЕО)\b"  # КЕВР electricity/gas
    r"|^Решение\s+№\s+\S*-(?P<kfn>НИФ|ИП|УД|ДСИЦ|ПД|ОЗО|ЛУАИФ)\b"  # КФН financial
    r"|^Решение\s+№\s+(?P<nhif>РД-НС-\d+)"                            # НЗОК health
)

# Keywords in concession/MS decision titles
_MS_DECISION_RE = re.compile(
    r"за предоставяне на концесия|"
    r"за продължаване срока на разрешение|"
    r"за даване на разрешение за прехвърляне|"
    r"за удължаване срока на|"
    r"за прекратяване на концесия",
    re.IGNORECASE,
)


def detect_act_type(title: str) -> str:
    # Normalise non-breaking spaces for consistent keyword matching
    norm = title.replace(" ", " ").replace(" ", " ")
    # For "Решение №" run suffix regex BEFORE the generic _court catch in keywords
    if "№" in title:
        m = _RESHENIE_SUFFIX_RE.match(norm)
        if m:
            if m.group("nhif"):
                return "reshenie_nhif"
            return "reshenie_kevr" if m.group("suffix") else "reshenie_kfn"
        if _MS_DECISION_RE.search(norm):
            return "reshenie_ms"
    for keyword, act_type in _TYPE_KEYWORDS:
        if norm.startswith(keyword):
            return act_type
    # Second pass: substring match, but skip kodeks and _other (too broad)
    for keyword, act_type in _TYPE_KEYWORDS:
        if act_type in ("kodeks", "_other"):
            continue
        if keyword in norm:
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




def parse_body_text(text: str, act_type: str) -> list[ParsedSection]:
    from open_legis.scraper.lexer import clean_text, tokenize
    cleaned = clean_text(text)
    tokens = tokenize(cleaned)
    return _build_tree(tokens)


def _build_tree(tokens: list) -> list[ParsedSection]:
    """Stack-based tree builder — token stream → ParsedSection tree.

    Separates tokenization from tree-building so errors in one phase
    cannot corrupt the other.  Each structural level is handled by
    popping the stack to the appropriate parent rather than tracking
    mutable current_* variables.
    """
    from open_legis.scraper.lexer import TK

    _c: dict[str, int] = {}   # sequence counters keyed by level name

    def _next(key: str) -> int:
        _c[key] = _c.get(key, 0) + 1
        return _c[key]

    def _reset(*keys: str) -> None:
        for k in keys:
            _c[k] = 0

    # Stack entries: (ParsedSection, TK) — TK is the kind of that node
    stack: list[tuple[ParsedSection, object]] = []

    def _parent() -> Optional[ParsedSection]:
        return stack[-1][0] if stack else None

    def _parent_kind():
        return stack[-1][1] if stack else None

    def _kinds() -> set:
        return {k for _, k in stack}

    def _pop_to(target: set) -> None:
        """Pop stack until top is one of target kinds (or empty)."""
        while stack and stack[-1][1] not in target:
            stack.pop()

    def _append_text(text: str) -> None:
        p = _parent()
        if p is None:
            return
        # Continuation text goes to last child if children exist, else to intro
        if p.children:
            p.children[-1].paragraphs.append(text)
        else:
            p.paragraphs.append(text)

    root: list[ParsedSection] = []
    special_counts: dict[str, int] = {}

    # Deferred heading state: TEXT tokens after CHAPTER/SECTION become the heading
    heading_node: Optional[ParsedSection] = None
    heading_lines: list[str] = []

    def _flush_heading() -> None:
        nonlocal heading_node, heading_lines
        if heading_node is not None and heading_lines:
            heading_node.heading = " ".join(heading_lines)
        heading_node = None
        heading_lines.clear()

    def _make_special(base: str, label: str, sname: str) -> ParsedSection:
        special_counts[base] = special_counts.get(base, 0) + 1
        cnt = special_counts[base]
        eid = base if cnt == 1 else f"{base}_{cnt}"
        return ParsedSection(
            e_id=eid, tag="hcontainer",
            num=label, name=sname,
            heading=None, paragraphs=[],
        )

    for tok in tokens:
        if tok.kind == TK.CHAPTER:
            _flush_heading()
            stack.clear()
            _reset("section", "paragraph", "point", "letter", "par_item")
            n = _next("chapter")
            sec = ParsedSection(
                e_id=f"chap_{n}", tag="chapter",
                num=tok.num, name=None, heading=None, paragraphs=[],
            )
            root.append(sec)
            stack.append((sec, TK.CHAPTER))
            heading_node = sec
            heading_lines = []

        elif tok.kind == TK.SECTION:
            _flush_heading()
            _pop_to({TK.CHAPTER})
            _reset("article", "paragraph", "point", "letter")
            n = _next("section")
            chap_n = _c.get("chapter", 0)
            prefix = f"chap_{chap_n}__" if _parent_kind() == TK.CHAPTER else ""
            sec = ParsedSection(
                e_id=f"{prefix}sec_{n}", tag="section",
                num=tok.num, name=None, heading=None, paragraphs=[],
            )
            p = _parent()
            (p.children if p else root).append(sec)
            stack.append((sec, TK.SECTION))
            heading_node = sec
            heading_lines = []

        elif tok.kind == TK.SPECIAL:
            _flush_heading()
            stack.clear()
            _reset("article", "paragraph", "point", "letter", "par_item")
            sec = _make_special(tok.special_eid, tok.num, tok.special_name)
            root.append(sec)
            stack.append((sec, TK.SPECIAL))

        elif tok.kind == TK.ARTICLE:
            _flush_heading()
            _pop_to({TK.CHAPTER, TK.SECTION, TK.SPECIAL})
            _reset("paragraph", "point", "letter")
            n = _next("article")
            p = _parent()
            prefix = f"{p.e_id}__" if p else ""
            art = ParsedSection(
                e_id=f"{prefix}art_{n}", tag="article",
                num=tok.num, name=None, heading=None,
                paragraphs=[tok.rest] if tok.rest else [],
            )
            (p.children if p else root).append(art)
            stack.append((art, TK.ARTICLE))

        elif tok.kind == TK.PAR_ITEM:
            _flush_heading()
            # Always under a SPECIAL — synthesise if missing
            if TK.SPECIAL not in _kinds():
                sec = _make_special("sec_final", "ЗАКЛЮЧИТЕЛНИ РАЗПОРЕДБИ", "final-provisions")
                root.append(sec)
                stack.clear()
                stack.append((sec, TK.SPECIAL))
                _reset("par_item")
            else:
                _pop_to({TK.SPECIAL})
            n = _next("par_item")
            spec = stack[-1][0]
            par = ParsedSection(
                e_id=f"{spec.e_id}__par_{n}", tag="hcontainer",
                num=tok.num, name="modification", heading=None,
                paragraphs=[tok.rest] if tok.rest else [],
            )
            spec.children.append(par)
            stack.append((par, TK.PAR_ITEM))

        elif tok.kind == TK.NUMBERED_PARA:
            _flush_heading()
            valid = {TK.ARTICLE, TK.PAR_ITEM}
            if not _kinds() & valid:
                _append_text(tok.num + " " + tok.rest)
                continue
            _pop_to(valid)
            _reset("point", "letter")
            n = _next("paragraph")
            p = stack[-1][0]
            al = ParsedSection(
                e_id=f"{p.e_id}__al_{n}", tag="paragraph",
                num=tok.num, name=None, heading=None,
                paragraphs=[tok.rest] if tok.rest else [],
            )
            p.children.append(al)
            stack.append((al, TK.NUMBERED_PARA))

        elif tok.kind == TK.POINT:
            _flush_heading()
            valid = {TK.ARTICLE, TK.NUMBERED_PARA, TK.PAR_ITEM}
            if not _kinds() & valid:
                _append_text(tok.num + " " + tok.rest)
                continue
            _pop_to(valid)
            _reset("letter")
            n = _next("point")
            p = stack[-1][0]
            pt = ParsedSection(
                e_id=f"{p.e_id}__pt_{n}", tag="point",
                num=tok.num, name=None, heading=None,
                paragraphs=[tok.rest] if tok.rest else [],
            )
            p.children.append(pt)
            stack.append((pt, TK.POINT))

        elif tok.kind == TK.LETTER:
            _flush_heading()
            valid = {TK.POINT, TK.NUMBERED_PARA, TK.ARTICLE}
            if not _kinds() & valid:
                _append_text(tok.num + " " + tok.rest)
                continue
            _pop_to(valid)
            n = _next("letter")
            p = stack[-1][0]
            lt = ParsedSection(
                e_id=f"{p.e_id}__l_{n}", tag="point",
                num=tok.num, name=None, heading=None,
                paragraphs=[tok.rest] if tok.rest else [],
            )
            p.children.append(lt)
            stack.append((lt, TK.LETTER))

        elif tok.kind == TK.TEXT:
            if heading_node is not None:
                heading_lines.append(tok.rest)
                continue
            _flush_heading()
            _append_text(tok.rest)

    _flush_heading()

    # Fallback: pure prose (reshenie_ns, court decisions, etc.)
    if not root:
        prose = [t.rest for t in tokens if t.kind == TK.TEXT and t.rest]
        if prose:
            root.append(ParsedSection(
                e_id="sec_1", tag="section",
                num=None, name=None, heading=None,
                paragraphs=prose,
            ))

    return root


# --- AKN XML builder ----------------------------------------------------------

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


_XML_INVALID_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _x(s: str) -> str:
    s = _XML_INVALID_CHARS.sub("", s)
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
    if sec.num is not None:
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
