"""Convert raw DV text (from showMaterialDV.jsp) to AKN XML."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# --- Act type detection -------------------------------------------------------

# Each entry: (keyword, act_type, issuer)
# issuer="_detect" means: run _detect_reshenie_issuer on the full title
_TYPE_KEYWORDS: list[tuple[str, str, str]] = [
    # Kodeks exclusions — non-Bulgarian legislative codes (IMO, EU, professional)
    ("КОДЕКС ЗА БЕЗОПАСНОСТ", "_other", "other"),
    ("КОДЕКС ЗА РАЗШИРЕНИ", "_other", "other"),
    ("КОДЕКС ЗА УПРАВЛЕНИЕ", "_other", "other"),
    ("КОДЕКС ЗА ПРЕВОЗ", "_other", "other"),
    ("КОДЕКС ЗА КОНСТРУКЦИЯТА", "_other", "other"),
    ("КОДЕКС ЗА ОДОБРЕНИЕ", "_other", "other"),
    ("КОДЕКС ЗА НИВАТА", "_other", "other"),
    ("КОДЕКС ЗА СИГУРНОСТ", "_other", "other"),
    ("КОДЕКС ЗА ПРИЛАГАНЕ", "_other", "other"),
    ("КОДЕКС НА ПОВЕДЕНИЕ", "_other", "other"),
    ("КОДЕКС ОТ 20", "_other", "other"),
    ("КОДЕКС ЗА NOх", "_other", "other"),
    ("Кодекс за безопасност", "_other", "other"),
    ("Кодекс за разширени", "_other", "other"),
    ("Кодекс за управление на безопасността", "_other", "other"),
    ("Кодекс за превоз", "_other", "other"),
    ("Кодекс за конструкцията", "_other", "other"),
    ("Кодекс за одобрение", "_other", "other"),
    ("Кодекс за нивата", "_other", "other"),
    ("Кодекс за сигурност на корабите", "_other", "other"),
    ("Кодекс за прилагане на задължителните", "_other", "other"),
    ("Кодекс за разследване на морски", "_other", "other"),
    ("Кодекс за устойчивост", "_other", "other"),
    ("Кодекс за добра", "_other", "other"),
    ("Кодекс за поведение", "_other", "other"),
    ("Кодекс за признатите", "_other", "other"),
    ("Кодекс за признати", "_other", "other"),
    ("Кодекс за професионална", "_other", "other"),
    ("Кодекс ЗА ПОВЕДЕНИЕ", "_other", "other"),
    ("Кодекс ЗА БЕЗОПАСНОСТ", "_other", "other"),
    ("Кодекс ЗА РАЗШИРЕНИ", "_other", "other"),
    ("Кодекс НА ПОВЕДЕНИЕ", "_other", "other"),
    ("КОДЕКС", "kodeks", "ns"),
    ("Кодекс", "kodeks", "ns"),
    ("кодекс", "kodeks", "ns"),   # lowercase — "Наказателен кодекс", "Морски кодекс"
    # Laws
    ("Закон за ратифициране", "ratifikatsiya", "ns"),
    ("Закон за изменение и допълнение", "zid", "ns"),
    ("Закон за допълнение", "zid", "ns"),
    ("Закон за изменение", "zid", "ns"),
    ("Закон за отмяна", "zid", "ns"),
    ("Поправка", "zid", "ns"),
    ("Закон за държавния бюджет", "byudjet", "ns"),
    ("Закон за бюджета на", "byudjet", "ns"),
    ("Закон за събирането на приходи и извършването на разходи", "byudjet", "ns"),
    ("Закон за прилагане на разпоредби на Закона за държавния бюджет", "byudjet", "ns"),
    ("ЗАКОН", "zakon", "ns"),
    ("Закон", "zakon", "ns"),
    # Constitution
    ("КОНСТИТУЦИЯ", "konstitutsiya", "ns"),
    ("Конституция", "konstitutsiya", "ns"),
    # Executive instruments
    ("НАРЕДБА", "naredba", "ms"),
    ("Наредба", "naredba", "ms"),
    ("ПОСТАНОВЛЕНИЕ", "postanovlenie", "ms"),
    ("Постановление", "postanovlenie", "ms"),
    ("ПРАВИЛНИК", "pravilnik", "ms"),
    ("Правилник", "pravilnik", "ms"),
    ("ИНСТРУКЦИЯ", "instruktsiya", "ministry"),
    ("Инструкция", "instruktsiya", "ministry"),
    ("ТАРИФА", "tarifa", "ms"),
    ("Тарифа", "tarifa", "ms"),
    ("ЗАПОВЕД", "zapoved", "ministry"),
    ("Заповед", "zapoved", "ministry"),
    # Presidential decrees
    ("УКАЗ", "ukaz", "president"),
    ("Указ", "ukaz", "president"),
    # Declarations
    ("ДЕКЛАРАЦИЯ", "deklaratsiya", "ns"),
    ("Декларация", "deklaratsiya", "ns"),
    # Treaties / international agreements
    ("ДОГОВОР", "dogovor", "ns"),
    ("Договор", "dogovor", "ns"),
    ("СПОГОДБА", "dogovor", "ns"),
    ("Спогодба", "dogovor", "ns"),
    ("КОНВЕНЦИЯ", "dogovor", "ns"),
    ("Конвенция", "dogovor", "ns"),
    ("ПРОТОКОЛ", "dogovor", "ns"),
    ("Протокол", "dogovor", "ns"),
    ("МЕМОРАНДУМ", "dogovor", "ns"),
    ("Меморандум", "dogovor", "ns"),
    # Notices
    ("СЪОБЩЕНИЕ", "saobshtenie", "ns"),
    ("Съобщение", "saobshtenie", "ns"),
    # Decisions — specific patterns first, then general catch-alls
    ("Решение на Народното събрание", "reshenie", "ns"),
    ("Решение на", "reshenie", "_detect"),   # КС, МС, ВАС, ВСС, БНБ, etc.
    ("Решение за", "reshenie", "ns"),
    ("Решение № РД-НС-04", "reshenie", "commission"),
    ("Решение № РД-НС-", "reshenie", "commission"),
    ("Решение № ТПрГ", "reshenie", "commission"),
    ("Решение № ТПГ", "reshenie", "commission"),
    ("Решение № ", "reshenie", "_detect"),
    # Court rulings
    ("ОПРЕДЕЛЕНИЕ", "opredelenie", "court"),
    ("Определение № ", "opredelenie", "_detect"),
    ("Определение", "opredelenie", "court"),
]

LEGISLATIVE_TYPES = {
    "zakon", "zid", "byudjet", "kodeks", "naredba", "postanovlenie", "pravilnik",
    "reshenie", "ukaz", "instruktsiya", "tarifa", "zapoved", "deklaratsiya",
    "opredelenie", "dogovor", "saobshtenie", "ratifikatsiya", "konstitutsiya",
}

_ISSUER_DISPLAY: dict[str, str] = {
    "ns":           "Народно събрание",
    "ms":           "Министерски съвет",
    "president":    "Президент на Републиката",
    "ministry":     "Министерство",
    "commission":   "Регулаторна комисия",
    "agency":       "Агенция",
    "court":        "Съд",
    "ks":           "Конституционен съд",
    "vas":          "Върховен административен съд",
    "vss":          "Висш съдебен съвет",
    "bnb":          "Българска народна банка",
    "municipality": "Община",
    "other":        "Друг орган",
}

# Ordered keyword → issuer table for reshenie / opredelenie with "_detect" issuer
_RESHENIE_ISSUERS: list[tuple[str, str]] = [
    ("Конституционния съд", "ks"),
    ("Конституционен съд", "ks"),
    ("Конституционния Съд", "ks"),
    ("Върховния административен съд", "vas"),
    ("Върховен административен съд", "vas"),
    (" ВАС", "vas"),
    ("Висш съдебен съвет", "vss"),
    (" ВСС", "vss"),
    ("Българска народна банка", "bnb"),
    (" БНБ", "bnb"),
    ("КЕВР", "commission"),
    ("ДКЕВР", "commission"),
    ("КФН", "commission"),
    ("НЗОК", "commission"),
    ("РД-НС-", "commission"),
    ("ТПрГ", "commission"),
    ("ТПГ", "commission"),
    ("-ОЗ-", "commission"),
    ("-ЖЗ-", "commission"),
    ("-ОЕ-", "commission"),
    ("Министерски съвет", "ms"),
    (" МС №", "ms"),
    ("Народното събрание", "ns"),
    ("Народно събрание", "ns"),
]


def _detect_reshenie_issuer(norm: str) -> str:
    for keyword, issuer_slug in _RESHENIE_ISSUERS:
        if keyword in norm:
            return issuer_slug
    return "other"


def detect_act_type(title: str) -> tuple[str, str]:
    """Return (act_type, issuer) for the given title."""
    # Normalise non-breaking spaces
    norm = title.replace(" ", " ").replace(" ", " ")
    for keyword, act_type, issuer in _TYPE_KEYWORDS:
        if norm.startswith(keyword):
            if issuer == "_detect":
                issuer = _detect_reshenie_issuer(norm)
            return act_type, issuer
    # Second pass: substring match — skip only exclusion tokens
    for keyword, act_type, issuer in _TYPE_KEYWORDS:
        if act_type == "_other":
            continue
        if keyword in norm:
            if issuer == "_detect":
                issuer = _detect_reshenie_issuer(norm)
            return act_type, issuer
    return "_other", "other"


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

    # Fallback: pure prose (reshenie, court decisions, etc.)
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
    issuer: str = "ns",
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
    issuing_body = _ISSUER_DISPLAY.get(issuer, issuer)

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
        '          <FRBRauthor href="#issuer"/>',
        '          <FRBRcountry value="bg"/>',
        f'          <FRBRnumber value="{dv_position}"/>',
        "        </FRBRWork>",
        "        <FRBRExpression>",
        f'          <FRBRthis value="{akn_expr}/main"/>',
        f'          <FRBRuri value="{akn_expr}"/>',
        f'          <FRBRdate date="{expression_date}" name="Generation"/>',
        '          <FRBRauthor href="#issuer"/>',
        f'          <FRBRlanguage language="{language}"/>',
        "        </FRBRExpression>",
        "        <FRBRManifestation>",
        f'          <FRBRthis value="{akn_expr}/main.xml"/>',
        f'          <FRBRuri value="{akn_expr}.xml"/>',
        f'          <FRBRdate date="{expression_date}" name="Generation"/>',
        '          <FRBRauthor href="#issuer"/>',
        '          <FRBRformat value="application/akn+xml"/>',
        "        </FRBRManifestation>",
        "      </identification>",
        f'      <publication date="{expression_date}" name="Държавен вестник" number="{dv_broy}" showAs="ДВ"/>',
        '      <references source="#openlegis">',
        f'        <TLCOrganization eId="issuer" href="/ontology/organization/bg/{issuer}" showAs="{_x(issuing_body)}"/>',
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

    act_type, issuer = detect_act_type(title)
    slug = make_slug(issue.broy, issue.year, position)

    pub_history = ""
    ph_m = re.search(r"\(обн\.,.*?\)", body)
    if ph_m:
        pub_history = ph_m.group(0)

    sections = parse_body_text(body, act_type)

    xml = build_akn_xml(
        title=title,
        act_type=act_type,
        issuer=issuer,
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
