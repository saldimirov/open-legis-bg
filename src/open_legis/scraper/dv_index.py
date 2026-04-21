"""Crawl dv.parliament.bg broeveList to build a complete issue index."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

import httpx

from open_legis.scraper.dv_client import DvIssue, _HEADERS

_BASE = "https://dv.parliament.bg/DVWeb"


_ISSUE_PAT = re.compile(
    r"\[\'broi_\',\'(\d+)\'\].*?\[\'idObj\',\'(\d+)\'\].*?\[\'date_izd_\',\'(\d{4}-\d{2}-\d{2})\'\]",
    re.DOTALL,
)
_TOTAL_PAT = re.compile(r"Намерени резултати:\s*(\d+)")
_VS_PAT = re.compile(r'name="javax\.faces\.ViewState"[^>]+value="([^"]+)"')


def _parse_issues(html: str) -> list[DvIssue]:
    issues = []
    for broy_s, idObj_s, date in _ISSUE_PAT.findall(html):
        issues.append(
            DvIssue(
                idObj=int(idObj_s),
                broy=int(broy_s),
                year=int(date[:4]),
                date=date,
            )
        )
    return issues


def crawl_year(year: int, sleep: float = 1.0) -> list[DvIssue]:
    """Fetch the complete issue list for a calendar year."""
    all_issues: list[DvIssue] = []

    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=30) as c:
        # Initial GET to get session + ViewState
        r = c.get(f"{_BASE}/broeveList.faces")
        vs_m = _VS_PAT.search(r.text)
        if not vs_m:
            raise RuntimeError("Could not extract ViewState from broeveList")
        vs = vs_m.group(1)

        # POST search with date range
        time.sleep(sleep)
        r = c.post(
            f"{_BASE}/broeveList.faces",
            data={
                "broi_form_SUBMIT": "1",
                "broi_form:btnFind11.x": "10",
                "broi_form:btnFind11.y": "10",
                "broi_form:from_date": f"1.1.{year}",
                "broi_form:to_date": f"31.12.{year}",
                "javax.faces.ViewState": vs,
                "broi_form:not_first": "1",
                "active_tab": "2",
                "broi_": "",
                "idObj": "",
                "razdel_": "",
                "date_izd_": "",
                "broi_form:_link_hidden_": "",
                "broi_form:_idcl": "",
                "id_": "",
            },
        )

        total_m = _TOTAL_PAT.search(r.text)
        total = int(total_m.group(1)) if total_m else 0
        pages = (total + 9) // 10

        page_issues = _parse_issues(r.text)
        all_issues.extend(page_issues)

        vs_m = _VS_PAT.search(r.text)
        if vs_m:
            vs = vs_m.group(1)

        for page in range(2, pages + 1):
            time.sleep(sleep)
            r = c.post(
                f"{_BASE}/broeveList.faces",
                data={
                    "broi_form_SUBMIT": "1",
                    "broi_form:_idcl": "broi_form:next_",
                    "javax.faces.ViewState": vs,
                    "broi_form:not_first": "1",
                    "active_tab": "2",
                    "broi_form:from_date": f"1.1.{year}",
                    "broi_form:to_date": f"31.12.{year}",
                    "broi_": "",
                    "idObj": "",
                    "razdel_": "",
                    "date_izd_": "",
                    "broi_form:_link_hidden_": "",
                    "id_": "",
                },
            )
            page_issues = _parse_issues(r.text)
            all_issues.extend(page_issues)
            vs_m = _VS_PAT.search(r.text)
            if vs_m:
                vs = vs_m.group(1)

    # Strict year filter — the date boundary on the server can be fuzzy
    return [i for i in all_issues if i.year == year]


def crawl_years(
    from_year: int,
    to_year: int,
    sleep: float = 1.0,
    progress_cb=None,
) -> list[DvIssue]:
    all_issues: list[DvIssue] = []
    for year in range(from_year, to_year + 1):
        if progress_cb:
            progress_cb(f"indexing year {year}...")
        issues = crawl_year(year, sleep=sleep)
        all_issues.extend(issues)
    return all_issues


def save_index(issues: list[DvIssue], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {"idObj": i.idObj, "broy": i.broy, "year": i.year, "date": i.date}
        for i in issues
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def load_index(path: Path) -> list[DvIssue]:
    data = json.loads(path.read_text())
    return [DvIssue(**d) for d in data]
