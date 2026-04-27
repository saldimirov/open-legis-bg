"""Top-level worker functions for parallel scraping with ProcessPoolExecutor."""
from __future__ import annotations

import json
from pathlib import Path

from open_legis.scraper.dv_client import DvIssue
from open_legis.scraper.dv_to_akn import convert_material, detect_act_type
from open_legis.scraper.rtf_parser import parse_local_issue


def process_issue_local(
    issue_tuple: tuple,
    local_path_str: str,
    allowed_types: set[str],
    out_root_str: str,
    resume: bool,
) -> tuple[int, int, list[str]]:
    """Parse one DV issue from a local RTF file and write AKN + unofficial JSON fixtures.

    Returns (saved, skipped, log_lines).  Top-level so it can be pickled
    by ProcessPoolExecutor.
    """
    idObj, broy, year, date = issue_tuple
    issue = DvIssue(idObj=idObj, broy=broy, year=year, date=date)
    local_path = Path(local_path_str)
    out_root = Path(out_root_str)

    logs: list[str] = []
    saved = skipped = 0

    try:
        raw_materials = parse_local_issue(local_path)
    except Exception as exc:
        return 0, 0, [f"  ERROR parsing {local_path.name}: {exc}"]

    if not raw_materials:
        return 0, 0, []

    # Separate official and unofficial; dedup each independently.
    seen_official: dict[tuple[str, str], tuple[int, str]] = {}
    seen_unofficial: dict[str, tuple[int, str, str | None]] = {}

    for position, (title, body, section, category) in enumerate(raw_materials, start=1):
        if not title:
            continue
        if section == "unofficial":
            key = title.strip().lower()[:120]
            if key not in seen_unofficial or len(body) > len(seen_unofficial[key][1]):
                seen_unofficial[key] = (position, body, category)
        else:
            act_type, _ = detect_act_type(title)
            if act_type not in allowed_types:
                continue
            key = (act_type, title.strip().lower()[:120])
            if key not in seen_official or len(body) > len(seen_official[key][1]):
                seen_official[key] = (position, body)

    # Write official AKN fixtures.
    for (act_type, _), (position, body) in seen_official.items():
        title = raw_materials[position - 1][0]
        try:
            slug, xml = convert_material(
                title=title, body=body, idMat=0,
                issue=issue, position=position,
            )
        except Exception as exc:
            logs.append(f"  ERROR converting {title[:50]!r}: {exc}")
            continue

        expr_dir = out_root / act_type / str(issue.year) / slug / "expressions"
        akn_path = expr_dir / f"{issue.date}.bul.xml"

        if resume and akn_path.exists():
            skipped += 1
            continue

        expr_dir.mkdir(parents=True, exist_ok=True)
        akn_path.write_text(xml, encoding="utf-8")
        logs.append(f"  + {act_type}: {title[:65]}")
        saved += 1

    # Write unofficial JSON fixtures.
    for _key, (position, body, category) in seen_unofficial.items():
        title = raw_materials[position - 1][0]
        unofficial_dir = out_root / "dv-unofficial" / str(issue.year)
        json_path = unofficial_dir / f"{issue.broy:03d}-{position}.json"

        if resume and json_path.exists():
            skipped += 1
            continue

        unofficial_dir.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps({
                "dv_year": issue.year,
                "dv_broy": issue.broy,
                "dv_position": position,
                "section": "unofficial",
                "category": category,
                "title": title,
                "body": body,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logs.append(f"  + unofficial [{category or '?'}]: {title[:65]}")

    return saved, skipped, logs
