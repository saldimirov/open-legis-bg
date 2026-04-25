"""Top-level worker functions for parallel scraping with ProcessPoolExecutor."""
from __future__ import annotations


def process_issue_local(
    issue_tuple: tuple,           # (idObj, broy, year, date)
    local_path_str: str,
    allowed_types: set[str],
    out_root_str: str,
    resume: bool,
) -> tuple[int, int, list[str]]:
    """Parse one DV issue from a local RTF file and write AKN fixtures.

    Returns (saved, skipped, log_lines).  Top-level so it can be pickled
    by ProcessPoolExecutor.
    """
    from pathlib import Path

    from open_legis.scraper.dv_client import DvIssue
    from open_legis.scraper.rtf_parser import parse_local_issue
    from open_legis.scraper.dv_to_akn import detect_act_type, convert_material

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

    # Dedup within issue: same (act_type, title prefix) → keep longest body
    seen: dict[tuple[str, str], tuple[int, str]] = {}
    for position, (title, body, _section, _category) in enumerate(raw_materials, start=1):
        if not title:
            continue
        act_type, _ = detect_act_type(title)
        if act_type not in allowed_types:
            continue
        key = (act_type, title.strip().lower()[:120])
        if key not in seen or len(body) > len(seen[key][1]):
            seen[key] = (position, body)

    for (act_type, _), (position, body) in seen.items():
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

    return saved, skipped, logs
