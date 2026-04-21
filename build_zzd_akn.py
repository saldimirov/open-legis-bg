#!/usr/bin/env python3
"""
Build AKN 3.0 XML fixture for ЗЗД (Закон за задълженията и договорите, 1950).
Consolidated through ДВ бр. 35/2021.

Source: https://lex.bg/laws/ldoc/2121934337

Usage:
    uv run python build_zzd_akn.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent
RAW_HTML = HERE / "zzd_cp1251.html"
JSON_CACHE = HERE / "zzd_elements.json"
OUT_FILE = HERE / "fixtures/akn/zakon/1950/zzd/expressions/2021-04-27.bul.xml"

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN_PREFIX = "{" + AKN_NS + "}"


# ---------------------------------------------------------------------------
# Step 1: Fetch source HTML if not cached
# ---------------------------------------------------------------------------

def fetch_html() -> None:
    """Download lex.bg ЗЗД page in windows-1251 and save as UTF-8."""
    print("Fetching lex.bg ЗЗД …", flush=True)
    url = "https://lex.bg/laws/ldoc/2121934337"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/115.0",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    text = raw.decode("windows-1251", errors="replace")
    RAW_HTML.write_text(text, encoding="utf-8")
    print(f"  Saved {len(text):,} chars → {RAW_HTML}")


# ---------------------------------------------------------------------------
# Step 2: Parse HTML → structured elements
# ---------------------------------------------------------------------------

class _StripHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._buf: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "br":
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if self._skip == 0:
            self._buf.append(data)

    def result(self) -> str:
        t = "".join(self._buf)
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n +", "\n", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()


def _strip(html_str: str) -> str:
    p = _StripHTMLParser()
    p.feed(html_str)
    return p.result()


def parse_html_to_elements(html: str) -> list[dict]:
    """Extract headings and articles from lex.bg HTML in document order."""
    # Narrow to document section
    ds = html.find('id="DocumentTitle"')
    de_m = re.search(r'id="footer"', html)
    doc = html[ds:(de_m.start() if de_m else len(html))]

    elements: list[dict] = []

    # Headings
    for m in re.finditer(
        r'<div[^>]*class="Heading"[^>]*>\s*<p[^>]*class="Title">(.*?)</p>\s*</div>',
        doc, re.DOTALL
    ):
        text = _strip(m.group(1))
        elements.append({"type": "heading", "pos": m.start(), "text": text})

    # Articles: stack-based balanced-div extraction
    pos = 0
    while True:
        m = re.search(r'<div[^>]*class="Article"[^>]*>', doc[pos:])
        if not m:
            break
        div_start = pos + m.start()
        content_start = pos + m.end()
        depth = 1
        scan = content_start
        div_end = content_start
        while depth > 0 and scan < len(doc):
            open_m = re.search(r'<div[^>]*>', doc[scan:])
            close_m = re.search(r'</div>', doc[scan:])
            if close_m is None:
                break
            if open_m and open_m.start() < close_m.start():
                depth += 1
                scan += open_m.end()
            else:
                depth -= 1
                div_end = scan + close_m.end()
                scan += close_m.end()
        content = doc[content_start:div_end - len("</div>")]
        text = _strip(content)
        elements.append({"type": "article", "pos": div_start, "text": text})
        pos = div_start + 1

    # FinalEdictsArticle (§ paragraphs in ПЗР)
    for m in re.finditer(
        r'<div[^>]*class="FinalEdictsArticle"[^>]*>(.*?)</div>\s*(?=<br>|<div|$)',
        doc, re.DOTALL
    ):
        text = _strip(m.group(1))
        if text and re.match(r'^§\s*\d', text):
            elements.append({"type": "paragraph_s", "pos": m.start(), "text": text})

    # TransitionalFinalEdicts headings
    for m in re.finditer(
        r'<div[^>]*class="TransitionalFinalEdicts"[^>]*>(.*?)</div>',
        doc, re.DOTALL
    ):
        text = _strip(m.group(1))
        elements.append({"type": "tfe_heading", "pos": m.start(), "text": text})

    elements.sort(key=lambda x: x["pos"])
    return elements


def build_json_cache() -> None:
    """Parse HTML and save JSON cache."""
    if not RAW_HTML.exists():
        fetch_html()
    html = RAW_HTML.read_text(encoding="utf-8")
    elements = parse_html_to_elements(html)
    JSON_CACHE.write_text(json.dumps(elements, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Parsed {len(elements)} elements → {JSON_CACHE}")


# ---------------------------------------------------------------------------
# Step 3: Structure the data into AKN hierarchy
# ---------------------------------------------------------------------------

def clean_article_text(raw: str) -> str:
    """Remove stray heading text that leaked into article div after extraction."""
    # Headings that sometimes trail into article text
    # They appear on separate lines; remove them
    patterns = [
        r'\n+\s*[IVXLC]+\.\s+[А-ЯA-Z][А-ЯA-Z\s,]+$',
        r'\n+\s*[А-ЯA-Z]{2,}[А-ЯA-Z\s,]{5,}$',
        r'\n+\s*ОБЩА ЧАСТ\s*$',
        r'\n+\s*ОСОБЕНА ЧАСTТ?\s*$',
    ]
    for pat in patterns:
        raw = re.sub(pat, '', raw, flags=re.MULTILINE)
    return raw.strip()


def parse_article(raw: str) -> dict:
    """
    Parse a raw article text into:
      {"num": "Чл. N.", "heading": str|None, "paras": [str, ...]}

    Алинеи are identified by lines starting with digit in parens (1) (2) ...
    or bullet letter lines.
    """
    text = clean_article_text(raw)
    if not text:
        return {"num": "", "heading": None, "paras": []}

    # Extract article number
    num_m = re.match(r'^(Чл\.\s*\d+[а-я]?\.)(\s*)', text)
    if not num_m:
        # Not an article
        return {"num": "", "heading": None, "paras": [text] if text else []}

    num = num_m.group(1)
    rest = text[num_m.end():]

    # Check if entire article is repealed/replaced (single line)
    repealed_m = re.match(r'^\((Отм|Зал|Изм|Нов)[^)]*\)\s*$', rest.strip())
    if repealed_m:
        return {"num": num, "heading": rest.strip(), "paras": []}

    # Split into алинеи: paragraphs starting with (N) pattern
    # Split on lines that start with (digit) or "а)" "б)" etc.
    para_split = re.split(r'\n(?=\s*\(\d+\)\s)', rest)
    if len(para_split) == 1:
        # No explicit алиней numbering — check for newline-separated blocks
        lines = [l.strip() for l in rest.split('\n') if l.strip()]
        # Filter out leaked heading text (all-caps lines)
        lines = [l for l in lines if not re.match(r'^[А-ЯA-Z\s,]{10,}$', l)]
        paras = [' '.join(lines)] if lines else []
    else:
        paras = [p.strip() for p in para_split if p.strip()]
        # Filter out leaked heading text
        paras = [p for p in paras if not re.match(r'^[А-ЯA-Z\s,]{10,}$', p)]

    return {"num": num, "heading": None, "paras": paras if paras else []}


def build_structure(elements: list[dict]) -> dict:
    """
    Build the hierarchical structure:
    {
      "parts": [
        {
          "num": "ОБЩА ЧАСТ",
          "chapters": [
            {
              "num": "I. ОСНОВНИ ПРАВИЛА",
              "sections": [
                {
                  "num": "...",
                  "articles": [{"num": ..., "paras": [...]}, ...]
                }
              ],
              "articles": [...]  # articles without a section
            }
          ],
          "articles": []  # top-level articles in part
        }
      ],
      "transitional": [...]  # ПЗР paragraphs
    }
    """
    # Define the hierarchy levels:
    # Part: ОБЩА ЧАСТ, ОСОБЕНА ЧАСT, ЧАСТ ТРЕТА
    # Chapter: Roman numeral headings (I., II., ...)
    # Section: Numbered or lettered sub-headings (1., А), Б), ...)
    # Article: Чл. N.

    PART_PATTERN = re.compile(r'^(ОБЩА ЧАСT?|ОСОБЕНА ЧАСT?T?|ЧАСT\s+ТРЕТА)', re.IGNORECASE)
    CHAPTER_PATTERN = re.compile(r'^([IVXLC]+)\.\s+')
    SECTION_PATTERN = re.compile(r'^(\d+\.|[А-ЯA-Z]\))\s+')

    structure = {
        "parts": [],
        "transitional": [],
    }

    current_part = None
    current_chapter = None
    current_section = None
    in_transitional = False

    def ensure_part(text: str) -> dict:
        p = {"num": text, "chapters": [], "articles": []}
        structure["parts"].append(p)
        return p

    def ensure_chapter(part: dict, text: str) -> dict:
        ch = {"num": text, "sections": [], "articles": []}
        part["chapters"].append(ch)
        return ch

    def ensure_section(chapter: dict, text: str) -> dict:
        sec = {"num": text, "articles": []}
        chapter["sections"].append(sec)
        return sec

    def add_article(art: dict) -> None:
        nonlocal current_part
        if in_transitional:
            return  # handled separately
        if current_section is not None:
            current_section["articles"].append(art)
        elif current_chapter is not None:
            current_chapter["articles"].append(art)
        elif current_part is not None:
            current_part["articles"].append(art)
        else:
            # Before any part — create implicit part
            current_part = ensure_part("(преди ОБЩА ЧАСT)")
            current_part["articles"].append(art)

    for el in elements:
        typ = el["type"]
        text = el["text"].strip()

        if typ == "heading":
            if re.search(r'ПРЕХОДНИ\s+ПРАВИЛА|ЗАКЛЮЧИТЕЛНИ\s+РАЗПОРЕДБИ', text, re.IGNORECASE):
                in_transitional = True
                current_section = None
                current_chapter = None
                continue

            if PART_PATTERN.match(text):
                current_part = ensure_part(text)
                current_chapter = None
                current_section = None
                in_transitional = False
                continue

            if current_part is None:
                current_part = ensure_part("ОБЩА ЧАСT")

            if CHAPTER_PATTERN.match(text):
                current_chapter = ensure_chapter(current_part, text)
                current_section = None
                continue

            # Section or sub-heading
            if current_chapter is not None:
                current_section = ensure_section(current_chapter, text)
            else:
                # Create a pseudo-chapter for headings at chapter level
                current_chapter = ensure_chapter(current_part, text)
                current_section = None

        elif typ == "tfe_heading":
            if not in_transitional:
                in_transitional = True
            continue

        elif typ == "article":
            art = parse_article(text)
            if not art["num"]:
                continue
            add_article(art)

        elif typ == "paragraph_s":
            # § paragraphs in transitional provisions
            structure["transitional"].append({"text": text})

    return structure


# ---------------------------------------------------------------------------
# Step 4: Generate AKN XML
# ---------------------------------------------------------------------------

def make_elem(parent: ET.Element, tag: str, attrib: dict | None = None, text: str | None = None) -> ET.Element:
    el = ET.SubElement(parent, AKN_PREFIX + tag, attrib or {})
    if text is not None:
        el.text = text
    return el


def art_eId(num_str: str) -> str:
    """Convert 'Чл. 20а.' → 'art_20a'"""
    m = re.search(r'(\d+)([а-яa-z]?)', num_str)
    if not m:
        return "art_unknown"
    n = m.group(1)
    letter = m.group(2)
    # Transliterate Cyrillic letter suffix to Latin
    cyr_to_lat = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e"}
    letter_lat = cyr_to_lat.get(letter, letter)
    return f"art_{n}{letter_lat}"


def build_xml(structure: dict) -> ET.Element:
    # Register namespace
    ET.register_namespace("", AKN_NS)

    root = ET.Element(AKN_PREFIX + "akomaNtoso")
    act = ET.SubElement(root, AKN_PREFIX + "act", {"contains": "singleVersion"})

    # --- meta ---
    meta = make_elem(act, "meta")
    ident = make_elem(meta, "identification", {"source": "#openlegis"})

    fw = make_elem(ident, "FRBRWork")
    make_elem(fw, "FRBRthis", {"value": "/akn/bg/act/1950/zzd/main"})
    make_elem(fw, "FRBRuri", {"value": "/akn/bg/act/1950/zzd"})
    make_elem(fw, "FRBRalias", {"value": "Закон за задълженията и договорите", "name": "short"})
    make_elem(fw, "FRBRalias", {
        "value": "Закон за задълженията и договорите",
        "name": "eli",
        "other": "/eli/bg/zakon/1950/zzd",
    })
    make_elem(fw, "FRBRdate", {"date": "1950-11-22", "name": "Generation"})
    make_elem(fw, "FRBRauthor", {"href": "#parliament"})
    make_elem(fw, "FRBRcountry", {"value": "bg"})
    make_elem(fw, "FRBRnumber", {"value": "1"})

    fe = make_elem(ident, "FRBRExpression")
    make_elem(fe, "FRBRthis", {"value": "/akn/bg/act/1950/zzd/bul@2021-04-27/main"})
    make_elem(fe, "FRBRuri", {"value": "/akn/bg/act/1950/zzd/bul@2021-04-27"})
    make_elem(fe, "FRBRdate", {"date": "2021-04-27", "name": "Generation"})
    make_elem(fe, "FRBRauthor", {"href": "#parliament"})
    make_elem(fe, "FRBRlanguage", {"language": "bul"})

    fm = make_elem(ident, "FRBRManifestation")
    make_elem(fm, "FRBRthis", {"value": "/akn/bg/act/1950/zzd/bul@2021-04-27/main.xml"})
    make_elem(fm, "FRBRuri", {"value": "/akn/bg/act/1950/zzd/bul@2021-04-27.xml"})
    make_elem(fm, "FRBRdate", {"date": "2021-04-27", "name": "Generation"})
    make_elem(fm, "FRBRauthor", {"href": "#parliament"})
    make_elem(fm, "FRBRformat", {"value": "application/akn+xml"})

    make_elem(meta, "publication", {
        "date": "1950-11-22",
        "name": "Държавен вестник",
        "number": "275",
        "showAs": "ДВ",
    })

    refs = make_elem(meta, "references", {"source": "#openlegis"})
    make_elem(refs, "TLCOrganization", {
        "eId": "parliament",
        "href": "/ontology/organization/bg/NarodnoSabranie",
        "showAs": "Народно събрание",
    })
    make_elem(refs, "TLCPerson", {
        "eId": "openlegis",
        "href": "/ontology/person/openlegis",
        "showAs": "open-legis",
    })

    # --- preface ---
    preface = make_elem(act, "preface")
    make_elem(preface, "p", text="Закон за задълженията и договорите")
    make_elem(preface, "p", text=(
        "Обн. ДВ бр. 275 от 22 Ноември 1950 г. "
        "Консолидиран текст към ДВ бр. 35 от 27 Април 2021 г."
    ))

    # --- body ---
    body = make_elem(act, "body")

    # Track eId counters
    _part_counter = [0]
    _ch_counter = [0]
    _sec_counter = [0]

    def _add_articles(parent: ET.Element, articles: list[dict], parent_eid: str) -> None:
        for art_data in articles:
            num_str = art_data["num"]
            eid = art_eId(num_str)
            art_el = make_elem(parent, "article", {"eId": eid})
            make_elem(art_el, "num", text=num_str)

            heading_text = art_data.get("heading")
            paras = art_data.get("paras", [])

            if heading_text and not paras:
                # Repealed or single-note article
                make_elem(art_el, "heading", text=heading_text)
                # Add empty content so it has a leaf
                intro = make_elem(art_el, "intro")
                cont = make_elem(intro, "content")
                make_elem(cont, "p", text=heading_text)
            elif not paras:
                # Article with no text
                intro = make_elem(art_el, "intro")
                cont = make_elem(intro, "content")
                make_elem(cont, "p", text="(текст липсва)")
            elif len(paras) == 1:
                cont = make_elem(art_el, "content")
                make_elem(cont, "p", text=paras[0])
            else:
                for i, para_text in enumerate(paras, 1):
                    para_eid = f"{eid}__para_{i}"
                    para_el = make_elem(art_el, "paragraph", {"eId": para_eid})
                    # Extract para num if present
                    pnum_m = re.match(r'^(\(\d+\))\s*', para_text)
                    if pnum_m:
                        make_elem(para_el, "num", text=pnum_m.group(1))
                        para_text = para_text[pnum_m.end():]
                    cont = make_elem(para_el, "content")
                    make_elem(cont, "p", text=para_text.strip())

    def _add_section(parent: ET.Element, sec: dict, sec_eid: str) -> None:
        sec_el = make_elem(parent, "section", {"eId": sec_eid})
        make_elem(sec_el, "num", text=sec["num"])
        _add_articles(sec_el, sec["articles"], sec_eid)

    def _add_chapter(part_el: ET.Element, ch: dict, ch_eid: str) -> None:
        ch_el = make_elem(part_el, "chapter", {"eId": ch_eid})
        make_elem(ch_el, "num", text=ch["num"])

        # Articles directly in chapter (no section)
        if ch["articles"] and not ch["sections"]:
            _add_articles(ch_el, ch["articles"], ch_eid)
        elif ch["sections"]:
            for j, sec in enumerate(ch["sections"], 1):
                sec_eid = f"{ch_eid}__section_{j}"
                _add_section(ch_el, sec, sec_eid)
            # Articles after sections (unlikely but handle)
            if ch["articles"]:
                _add_articles(ch_el, ch["articles"], ch_eid)
        else:
            # Empty chapter
            pass

    for i, part in enumerate(structure["parts"], 1):
        part_eid = f"part_{i}"
        part_el = make_elem(body, "part", {"eId": part_eid})
        make_elem(part_el, "num", text=part["num"])

        # Top-level articles in part
        if part["articles"]:
            _add_articles(part_el, part["articles"], part_eid)

        for j, ch in enumerate(part["chapters"], 1):
            ch_eid = f"{part_eid}__chapter_{j}"
            _add_chapter(part_el, ch, ch_eid)

    # Transitional provisions
    if structure["transitional"]:
        trans = make_elem(body, "hcontainer", {
            "eId": "transitional",
            "name": "transitional",
        })
        make_elem(trans, "heading", text="ПРЕХОДНИ ПРАВИЛА")
        for k, para in enumerate(structure["transitional"], 1):
            p_el = make_elem(trans, "paragraph", {"eId": f"transitional__para_{k}"})
            cont = make_elem(p_el, "content")
            make_elem(cont, "p", text=para["text"])

    return root


# ---------------------------------------------------------------------------
# Step 5: Serialize to file
# ---------------------------------------------------------------------------

def pretty_xml(root: ET.Element) -> str:
    raw = ET.tostring(root, encoding="unicode", xml_declaration=False)
    # Use minidom for pretty printing
    dom = minidom.parseString(f'<?xml version="1.0" encoding="UTF-8"?>{raw}')
    pretty = dom.toprettyxml(indent="  ", encoding=None)
    # minidom adds extra xml declaration; remove it and re-add clean one
    lines = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines = lines[1:]
    result = '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(lines)
    # Clean up excessive blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip() + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== build_zzd_akn.py ===\n")

    # 1. Ensure we have HTML
    if not RAW_HTML.exists():
        fetch_html()

    # 2. Ensure we have JSON cache
    if not JSON_CACHE.exists():
        build_json_cache()
    else:
        print(f"Using cached JSON: {JSON_CACHE}")

    # 3. Load elements
    elements = json.loads(JSON_CACHE.read_text(encoding="utf-8"))
    print(f"Loaded {len(elements)} elements from JSON")

    # 4. Build structure
    print("Building hierarchy …")
    structure = build_structure(elements)
    total_arts = sum(
        len(ch.get("articles", []))
        + sum(len(s["articles"]) for s in ch.get("sections", []))
        for part in structure["parts"]
        for ch in part.get("chapters", [])
    ) + sum(len(part.get("articles", [])) for part in structure["parts"])
    print(f"  Parts: {len(structure['parts'])}")
    print(f"  Articles: {total_arts}")
    print(f"  ПЗР paragraphs: {len(structure['transitional'])}")

    # 5. Generate XML
    print("Generating XML …")
    root = build_xml(structure)

    # 6. Write output
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    xml_text = pretty_xml(root)
    OUT_FILE.write_text(xml_text, encoding="utf-8")
    print(f"Written: {OUT_FILE}")
    print(f"  Size: {OUT_FILE.stat().st_size:,} bytes")

    # 7. Quick sanity check
    from open_legis.loader.akn_parser import parse_akn_file
    from open_legis.loader.validators import validate_parsed
    parsed = parse_akn_file(OUT_FILE)
    validate_parsed(parsed, source_path=OUT_FILE)
    print(f"\nValidation OK — elements: {len(parsed.elements)}")


if __name__ == "__main__":
    main()
