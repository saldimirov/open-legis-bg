"""HTTP client for dv.parliament.bg."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx


_BASE = "https://dv.parliament.bg/DVWeb"
_HEADERS = {
    "User-Agent": "open-legis/0.1 (+https://github.com/open-legis/open-legis; research use)",
    "Accept-Language": "bg,en;q=0.9",
}


@dataclass
class DvIssue:
    idObj: int
    broy: int
    year: int
    date: str  # YYYY-MM-DD


@dataclass
class DvMaterial:
    idMat: int
    idObj: int
    title: str
    section: str
    page: int


def _get(url: str, params: dict | None = None, timeout: float = 20.0) -> str:
    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=timeout) as c:
        r = c.get(url, params=params)
        r.raise_for_status()
        return r.text


def get_issue_list_page(page: int = 1) -> list[DvIssue]:
    """Fetch one page (10 issues) from broeveList.faces via GET.

    The page is a JSF form but the initial GET works for page 1.
    Subsequent pages require POST with ViewState; for simplicity we
    extract idObj values from the inline onclick JavaScript.
    """
    html = _get(f"{_BASE}/broeveList.faces")
    return _parse_issue_list(html)


def get_issue_list_for_year(year: int) -> list[DvIssue]:
    """Fetch all issues for a specific year using the search form."""
    # The broeveList page supports filtering by date range via POST,
    # but the initial GET returns the most recent 10 issues.
    # We use the materiali.faces enumeration approach instead:
    # issue idObj values are roughly sequential. We find the range by
    # inspecting the visible issues and extrapolating.
    #
    # Simpler: crawl by iterating idObj values and checking the year.
    raise NotImplementedError("Use iter_issues_by_idobj instead")


def _parse_issue_list(html: str) -> list[DvIssue]:
    """Extract (idObj, broy, year, date) from broeveList HTML."""
    issues: list[DvIssue] = []
    # onclick="...[[\'broi_\',\'36\'],[\'idObj\',\'12461\'],[\'date_izd_\',\'2026-04-17\']...]"
    pattern = re.compile(
        r"\[\'broi_\',\'(\d+)\'\].*?\[\'idObj\',\'(\d+)\'\].*?\[\'date_izd_\',\'(\d{4}-\d{2}-\d{2})\'\]",
        re.DOTALL,
    )
    for m in pattern.finditer(html):
        broy = int(m.group(1))
        idObj = int(m.group(2))
        date_str = m.group(3)
        year = int(date_str[:4])
        issues.append(DvIssue(idObj=idObj, broy=broy, year=year, date=date_str))
    return issues


def get_issue_materials(idObj: int, sleep: float = 0.5) -> list[DvMaterial]:
    """Fetch material list for a given issue."""
    time.sleep(sleep)
    html = _get(f"{_BASE}/materiali.faces", params={"idObj": idObj})
    return _parse_materials(html, idObj)


def _parse_materials(html: str, idObj: int) -> list[DvMaterial]:
    materials: list[DvMaterial] = []

    # Find section header
    section = ""
    sec_m = re.search(r"titleHead[^>]*>([^<]+)", html)
    if sec_m:
        section = sec_m.group(1).strip()

    # Each row: idMat=XXXX ... стр. N ... title text
    row_pattern = re.compile(
        r'idMat=(\d+)[^>]*>.*?стр\.\s*(\d+)',
        re.DOTALL,
    )
    # Also grab title from showMaterialDV link anchor text
    title_pattern = re.compile(
        r'showMaterialDV\.jsp[^?]*\?idMat=(\d+)[^>]*>.*?<[^/]',
        re.DOTALL,
    )

    seen: set[int] = set()
    seq = 0
    for m in row_pattern.finditer(html):
        idMat = int(m.group(1))
        if idMat in seen:
            continue
        seen.add(idMat)
        seq += 1
        materials.append(
            DvMaterial(idMat=idMat, idObj=idObj, title="", section=section, page=seq)
        )
    return materials


def get_material_text(idMat: int, sleep: float = 0.5) -> tuple[str, str]:
    """Return (title, body_text) for a material.

    Fetches showMaterialDV.jsp and extracts clean text.
    """
    time.sleep(sleep)
    html = _get(f"{_BASE}/showMaterialDV.jsp", params={"idMat": idMat})
    return _parse_material_html(html)


def _parse_material_html(html: str) -> tuple[str, str]:
    # Remove scripts and styles
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)

    # Extract title from tdHead1 span
    title_m = re.search(r'tdHead1[^>]*>([^<]+)', html)
    title = title_m.group(1).strip().replace("\xa0", " ") if title_m else ""

    # Convert HTML to plain text
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)

    # Decode common HTML entities
    text = (
        text.replace("&#160;", " ")
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&bdquo;", "\u201e")
        .replace("&ldquo;", "\u201c")
        .replace("&rdquo;", "\u201d")
        .replace("&laquo;", "\u00ab")
        .replace("&raquo;", "\u00bb")
        .replace("&ndash;", "\u2013")
        .replace("&mdash;", "\u2014")
        .replace("&sect;", "\u00a7")
        .replace("&bull;", "\u2022")
        .replace("&deg;", "\u00b0")
    )

    # Collapse whitespace (preserve newlines)
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    body = "\n".join(lines)

    # Strip Word artifact header ("800x600 Normal 0 21 false...")
    body = re.sub(r"800x600[^\n]*MicrosoftInternetExplorer4\s*", "", body)

    return title.strip(), body.strip()


def get_issue_metadata(idObj: int) -> Optional[DvIssue]:
    """Return DvIssue metadata by fetching the first material's page.

    materiali.faces header always shows TODAY's issue number, so we
    extract broy/date from the first material's showMaterialDV page instead.
    """
    mat_html = _get(f"{_BASE}/materiali.faces", params={"idObj": idObj})
    first_mat = re.search(r"idMat=(\d+)", mat_html)
    if not first_mat:
        return None
    idMat = int(first_mat.group(1))
    time.sleep(0.3)
    mat_page = _get(f"{_BASE}/showMaterialDV.jsp", params={"idMat": idMat})
    m = re.search(r"брой:\s*(\d+)[^,]*,\s*от дата\s*([\d.]+)\s*г", mat_page)
    if not m:
        return None
    broy = int(m.group(1))
    date_parts = m.group(2).strip().split(".")
    if len(date_parts) == 3:
        day, mon, yr = date_parts
        date_str = f"{yr}-{int(mon):02d}-{int(day):02d}"
        year = int(yr)
    else:
        return None
    return DvIssue(idObj=idObj, broy=broy, year=year, date=date_str)
