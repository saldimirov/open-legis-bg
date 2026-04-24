import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lxml import etree

NS = {"akn": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}

_ELEMENT_TYPE_BY_LOCAL = {
    "part": "part",
    "title": "title",
    "chapter": "chapter",
    "section": "section",
    "article": "article",
    "paragraph": "paragraph",
    "point": "point",
    "subparagraph": "paragraph",
    "indent": "letter",
    "hcontainer": "hcontainer",
}


@dataclass
class ParsedWork:
    eli_uri: str
    title: str
    act_type: str
    dv_broy: int
    dv_year: int
    dv_position: int
    adoption_date: Optional[dt.date]
    issuing_body: Optional[str]
    issuer: Optional[str] = None


@dataclass
class ParsedExpression:
    expression_date: dt.date
    language: str
    source_file: str
    akn_xml: str = ""


@dataclass
class ParsedElement:
    e_id: str
    parent_e_id: Optional[str]
    element_type: str
    num: Optional[str]
    heading: Optional[str]
    text: Optional[str]
    sequence: int


@dataclass
class ParsedAkn:
    work: ParsedWork
    expression: ParsedExpression
    elements: list[ParsedElement] = field(default_factory=list)


def _text_of(el: etree._Element, local: str) -> Optional[str]:
    child = el.find(f"akn:{local}", NS)
    if child is None:
        return None
    return "".join(child.itertext()).strip() or None


def _find_first(root: etree._Element, xpath: str) -> Optional[etree._Element]:
    results = root.xpath(xpath, namespaces=NS)
    return results[0] if results else None


def parse_akn_file(path: Path) -> ParsedAkn:
    akn_xml = path.read_text(encoding="utf-8")
    root = etree.fromstring(akn_xml.encode())

    # Work metadata
    eli_alias = _find_first(
        root,
        "//akn:identification/akn:FRBRWork/akn:FRBRalias[@name='eli']",
    )
    if eli_alias is None:
        raise ValueError(f"{path}: missing FRBRalias[name=eli]")
    eli_uri = eli_alias.get("other") or eli_alias.get("value")
    if not eli_uri:
        raise ValueError(f"{path}: FRBRalias has no value")

    # Title: use the 'value' attribute of the eli alias (which holds the human title)
    title_s = eli_alias.get("value") or _eli_to_title(eli_uri)

    pub = _find_first(root, "//akn:publication")
    if pub is None:
        raise ValueError(f"{path}: missing <publication>")
    try:
        dv_year = int(pub.get("date", "")[:4])
    except ValueError as exc:
        raise ValueError(f"{path}: bad publication date: {pub.get('date')!r}") from exc
    dv_broy = int(pub.get("number") or "0")
    frbr_num_el = _find_first(root, "//akn:FRBRWork/akn:FRBRnumber")
    dv_position = int((frbr_num_el.get("value") if frbr_num_el is not None else "1") or "1")

    gen_date_el = _find_first(
        root, "//akn:FRBRWork/akn:FRBRdate[@name='Generation']"
    )
    adoption_date = (
        dt.date.fromisoformat(gen_date_el.get("date"))
        if gen_date_el is not None and gen_date_el.get("date")
        else None
    )

    issuer_el = _find_first(root, "//akn:references/akn:TLCOrganization")
    issuing_body = issuer_el.get("showAs") if issuer_el is not None else None
    issuer: Optional[str] = None
    if issuer_el is not None:
        href = issuer_el.get("href", "")
        slug = href.rsplit("/", 1)[-1] if "/" in href else ""
        if slug and slug not in ("NarodnoSabranie",):  # skip old-style hrefs
            issuer = slug

    act_type = _eli_act_type(eli_uri)

    work = ParsedWork(
        eli_uri=eli_uri,
        title=title_s,
        act_type=act_type,
        dv_broy=dv_broy,
        dv_year=dv_year,
        dv_position=dv_position,
        adoption_date=adoption_date,
        issuing_body=issuing_body,
        issuer=issuer,
    )

    # Expression metadata
    expr_date_el = _find_first(
        root, "//akn:FRBRExpression/akn:FRBRdate[@name='Generation']"
    )
    if expr_date_el is None or not expr_date_el.get("date"):
        raise ValueError(f"{path}: missing FRBRExpression/FRBRdate")
    expr_date = dt.date.fromisoformat(expr_date_el.get("date"))
    lang_el = _find_first(root, "//akn:FRBRExpression/akn:FRBRlanguage")
    language = lang_el.get("language") if lang_el is not None else "bul"

    expression = ParsedExpression(
        expression_date=expr_date,
        language=language,
        source_file=str(path),
        akn_xml=akn_xml,
    )

    body = _find_first(root, "//akn:body")
    if body is None:
        raise ValueError(f"{path}: missing <body>")

    elements: list[ParsedElement] = []
    _walk(body, parent_e_id=None, out=elements, counter=[0])

    return ParsedAkn(work=work, expression=expression, elements=elements)


def _walk(
    node: etree._Element,
    parent_e_id: Optional[str],
    out: list[ParsedElement],
    counter: list[int],
) -> None:
    for child in node:
        if not isinstance(child.tag, str):
            continue
        local = etree.QName(child.tag).localname
        if local not in _ELEMENT_TYPE_BY_LOCAL:
            _walk(child, parent_e_id, out, counter)
            continue
        e_id = child.get("eId")
        if not e_id:
            continue
        num = _text_of(child, "num")
        heading = _text_of(child, "heading")
        text = _collect_leaf_text(child)
        out.append(
            ParsedElement(
                e_id=e_id,
                parent_e_id=parent_e_id,
                element_type=_ELEMENT_TYPE_BY_LOCAL[local],
                num=num,
                heading=heading,
                text=text,
                sequence=counter[0],
            )
        )
        counter[0] += 1
        _walk(child, parent_e_id=e_id, out=out, counter=counter)


def _collect_leaf_text(el: etree._Element) -> Optional[str]:
    parts: list[str] = []
    for content in el.xpath("./akn:content | ./akn:intro", namespaces=NS):
        parts.append("".join(content.itertext()).strip())
    text = "\n".join(p for p in parts if p)
    return text or None


def _eli_to_title(eli: str) -> str:
    return eli.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()


# Remap old compound reshenie_* slugs to the flat "reshenie" type
_ACT_TYPE_REMAP: dict[str, str] = {
    "reshenie_ks":   "reshenie",
    "reshenie_ns":   "reshenie",
    "reshenie_ms":   "reshenie",
    "reshenie_kevr": "reshenie",
    "reshenie_kfn":  "reshenie",
    "reshenie_nhif": "reshenie",
}


def _eli_act_type(eli: str) -> str:
    parts = eli.strip("/").split("/")
    if len(parts) < 3:
        raise ValueError(f"Cannot derive act_type from {eli!r}")
    raw = parts[2].replace("-", "_")
    return _ACT_TYPE_REMAP.get(raw, raw)
