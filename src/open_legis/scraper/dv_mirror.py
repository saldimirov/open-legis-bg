"""Local mirror of DV issues as RTF/PDF files.

Download flow per issue:
  1. POST broeveList.faces with exact issue date → issue appears at row 0
  2. POST broeveList.faces with row-0 download button click
     - If binary response → PDF (older issues); save as .pdf
     - If HTML modal → parse idFileAtt, prefer RTF; save as .rtf
  3. Optionally GET fileUploadShowing.jsp for the RTF attachment

Storage: {out_dir}/{year}/{broy:03d}-{idObj}.rtf  (or .pdf for older issues)
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

import httpx

from open_legis.scraper.dv_client import DvIssue, _BASE, _HEADERS

_VS_PAT = re.compile(r'name="javax\.faces\.ViewState"[^>]+value="([^"]+)"')
_ATT_PAT = re.compile(
    r'fileUploadShowing[^"]+idFileAtt=(\d+)[^"]*"[^>]*>(.*?)</a>',
    re.DOTALL,
)


def issue_path(issue: DvIssue, out_dir: Path) -> Optional[Path]:
    """Return cached path if any variant exists, else None."""
    base = out_dir / str(issue.year) / f"{issue.broy:03d}-{issue.idObj}"
    for ext in (".rtf", ".pdf"):
        p = base.with_suffix(ext)
        if p.exists():
            return p
    return None


def _fmt_bg(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)}.{int(m)}.{y}"


def _viewstate(c: httpx.Client) -> str:
    r = c.get(f"{_BASE}/broeveList.faces")
    m = _VS_PAT.search(r.text)
    if not m:
        raise RuntimeError("ViewState not found")
    return m.group(1)


def download_issue(
    issue: DvIssue,
    out_dir: Path,
    sleep: float = 0.5,
    retries: int = 2,
) -> Optional[Path]:
    """Download RTF (or PDF) for one issue. Returns saved path or None."""
    if issue_path(issue, out_dir):
        return issue_path(issue, out_dir)

    dest_base = out_dir / str(issue.year) / f"{issue.broy:03d}-{issue.idObj}"
    dest_base.parent.mkdir(parents=True, exist_ok=True)

    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=60) as c:
                vs = _viewstate(c)
                time.sleep(sleep)

                # Step 1: search by exact date → issue lands at row 0
                date_bg = _fmt_bg(issue.date)
                r2 = c.post(f"{_BASE}/broeveList.faces", data={
                    "broi_form_SUBMIT": "1",
                    "broi_form:btnFind11.x": "10", "broi_form:btnFind11.y": "10",
                    "javax.faces.ViewState": vs,
                    "broi_form:not_first": "1", "active_tab": "2",
                    "broi_form:from_date": date_bg, "broi_form:to_date": date_bg,
                    "broi_": "", "idObj": "", "razdel_": "", "date_izd_": "",
                    "broi_form:_link_hidden_": "", "broi_form:_idcl": "", "id_": "",
                })
                vs2 = _VS_PAT.search(r2.text)
                if not vs2:
                    return None
                vs2 = vs2.group(1)

                ids = re.findall(r"\['idObj','(\d+)'\]", r2.text)
                row = ids.index(str(issue.idObj)) if str(issue.idObj) in ids else 0
                time.sleep(sleep)

                # Step 2: click download button
                r3 = c.post(f"{_BASE}/broeveList.faces", data={
                    "broi_form_SUBMIT": "1",
                    "id_": str(issue.idObj),
                    "broi_form:_link_hidden_": "",
                    "broi_form:_idcl": f"broi_form:dataTable1:{row}:_idJsp109",
                    "javax.faces.ViewState": vs2,
                })

                ct = r3.headers.get("content-type", "")

                if "html" in ct:
                    # Modal with multiple attachments — prefer RTF
                    atts = [
                        (att_id, re.sub(r"<[^>]+>", "", label).strip())
                        for att_id, label in _ATT_PAT.findall(r3.text)
                    ]
                    if not atts:
                        return None

                    # Prefer RTF; fall back to first attachment (usually PDF)
                    rtf_att = next(
                        (a for a in atts if "rtf" in a[1].lower() or "отворен" in a[1].lower()),
                        atts[0],
                    )
                    time.sleep(sleep)
                    rf = c.get(
                        f"{_BASE}/fileUploadShowing.jsp",
                        params={"idFileAtt": rtf_att[0], "allowCache": "true", "openDirectly": "true"},
                    )
                    rf.raise_for_status()

                    disp = rf.headers.get("content-disposition", "")
                    ext = ".rtf" if "rtf" in disp.lower() else ".pdf"
                    dest = dest_base.with_suffix(ext)
                    dest.write_bytes(rf.content)

                else:
                    # Binary response — PDF served directly
                    magic = r3.content[:4]
                    ext = ".pdf" if magic == b"%PDF" else ".bin"
                    dest = dest_base.with_suffix(ext)
                    dest.write_bytes(r3.content)

                return dest

        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(2.0)

    raise last_exc  # type: ignore[misc]


def mirror_issues(
    issues: list[DvIssue],
    out_dir: Path,
    workers: int = 4,
    sleep: float = 0.5,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> tuple[int, int, int]:
    """Download files for all issues. Returns (saved, skipped, failed)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    to_download = [i for i in issues if not issue_path(i, out_dir)]
    skipped = len(issues) - len(to_download)

    if progress_cb:
        progress_cb(f"{skipped} already cached, downloading {len(to_download)}")

    saved = failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_issue, iss, out_dir, sleep): iss for iss in to_download}
        for fut in as_completed(futures):
            iss = futures[fut]
            try:
                path = fut.result()
                if path:
                    saved += 1
                    if progress_cb:
                        progress_cb(f"  + {iss.year}/бр.{iss.broy} → {path.suffix}")
                else:
                    failed += 1
                    if progress_cb:
                        progress_cb(f"  - {iss.year}/бр.{iss.broy} no file available")
            except Exception as e:
                failed += 1
                if progress_cb:
                    progress_cb(f"  ! {iss.year}/бр.{iss.broy} error: {e}")

    return saved, skipped, failed
