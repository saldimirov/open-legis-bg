from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from open_legis.validate import Issue, LayerResult

_SLUG_RE = re.compile(r"^dv-(\d+)-\d+-(\d+)$")

_ISSUE_THRESHOLDS: dict[str, int] = {
    "zakon": 3, "kodeks": 3, "byudjet": 3, "konstitutsiya": 1,
    "naredba": 8, "pravilnik": 8, "postanovlenie": 8, "zid": 8, "ratifikatsiya": 8,
    "reshenie_ns": 15, "reshenie_ms": 15, "reshenie_kevr": 15,
    "reshenie_kfn": 15, "reshenie_nhif": 15,
}


def _title_similarity(a: str, b: str) -> float:
    """Word-level similarity — more robust than char-level for Cyrillic titles."""
    wa = a.lower().split()
    wb = b.lower().split()
    return SequenceMatcher(None, wa, wb).ratio()


def _check_duplicates(session: Session, issues: list[Issue]) -> dict[str, int]:
    groups = session.execute(text("""
        SELECT
            lower(act_type::text)                        AS act_type,
            dv_broy,
            dv_year,
            COUNT(*)                                     AS cnt,
            array_agg(eli_uri    ORDER BY dv_position)  AS uris,
            array_agg(title      ORDER BY dv_position)  AS titles,
            array_agg(dv_position ORDER BY dv_position) AS positions
        FROM work
        GROUP BY act_type, dv_broy, dv_year
        HAVING COUNT(*) > 1
    """)).fetchall()

    overcounts = 0
    fragments = 0
    pos_gaps = 0

    for row in groups:
        act_type, broy, year, cnt, uris, titles, positions = row
        threshold = _ISSUE_THRESHOLDS.get(act_type, 8)

        if cnt > threshold:
            issues.append(Issue(
                severity="warn",
                code="ISSUE_OVERCOUNT",
                message=f"{act_type} DV {broy}/{year}: {cnt} acts (threshold={threshold})",
                path=f"dv-{broy}-{year % 100:02d}",
                detail=f"URIs: {', '.join(uris[:5])}",
            ))
            overcounts += 1

        for i in range(len(titles)):
            for j in range(i + 1, len(titles)):
                sim = _title_similarity(titles[i], titles[j])
                if sim > 0.6:
                    issues.append(Issue(
                        severity="error",
                        code="PROBABLE_FRAGMENT",
                        message=(
                            f"{act_type} DV {broy}/{year}: similar titles at "
                            f"pos {positions[i]}&{positions[j]} — likely parser split"
                        ),
                        path=uris[i],
                        detail=(
                            f"similarity={sim:.2f}\n"
                            f"      A: {titles[i][:80]}\n"
                            f"      B: {titles[j][:80]}"
                        ),
                    ))
                    fragments += 1

        if len(positions) >= 3:
            gaps = [positions[k + 1] - positions[k] for k in range(len(positions) - 1)]
            avg_gap = sum(gaps) / len(gaps)
            if avg_gap > 3 and all(p % 2 == 0 for p in positions):
                issues.append(Issue(
                    severity="warn",
                    code="POSITION_GAPS",
                    message=(
                        f"{act_type} DV {broy}/{year}: positions {positions} "
                        f"look like page numbers (avg gap={avg_gap:.1f})"
                    ),
                    path=f"dv-{broy}-{year % 100:02d}",
                ))
                pos_gaps += 1

    return {"overcounts": overcounts, "fragments": fragments, "position_gaps": pos_gaps}


def check_db(fixtures_root: Path, session: Session) -> LayerResult:
    issues: list[Issue] = []

    # Count fixture XML files per act_type
    fixture_counts: dict[str, int] = {}
    for f in fixtures_root.rglob("*.bul.xml"):
        parts = f.relative_to(fixtures_root).parts
        if len(parts) < 4:
            continue
        act_type = parts[0]
        fixture_counts[act_type] = fixture_counts.get(act_type, 0) + 1

    # DB counts per act_type — use lower() because SQLAlchemy stores enum member names
    # (e.g. 'ZAKON') but fixture dirs use lowercase values (e.g. 'zakon')
    db_rows = session.execute(text(
        "SELECT lower(act_type::text), COUNT(*) FROM work GROUP BY act_type"
    )).fetchall()
    db_counts: dict[str, int] = {r[0]: r[1] for r in db_rows}

    for act_type, fx_count in sorted(fixture_counts.items()):
        db_count = db_counts.get(act_type, 0)
        if db_count == 0:
            issues.append(Issue(
                severity="error",
                code="TYPE_NOT_IN_DB",
                message=f"{act_type}: {fx_count} fixtures present but 0 DB rows",
                path=act_type,
                detail="All fixtures of this type failed to load",
            ))
        elif db_count < fx_count:
            issues.append(Issue(
                severity="warn",
                code="COVERAGE_GAP",
                message=f"{act_type}: {fx_count} fixtures but only {db_count} DB rows ({fx_count - db_count} missing)",
                path=act_type,
            ))

    # Per-fixture: verify each DV-slugged fixture has a matching DB row
    fixture_coords: list[tuple[int, int, int, str]] = []  # (broy, year, pos, rel_path)
    for f in fixtures_root.rglob("*.bul.xml"):
        parts = f.relative_to(fixtures_root).parts
        if len(parts) < 4:
            continue
        slug = parts[2]
        m = _SLUG_RE.match(slug)
        if not m:
            continue  # non-DV slug (test fixtures, etc.)
        broy = int(m.group(1))
        year = int(parts[1])
        position = int(m.group(2))
        rel = f.relative_to(fixtures_root).as_posix()
        fixture_coords.append((broy, year, position, rel))

    if fixture_coords:
        all_rows = session.execute(
            text("SELECT dv_broy, dv_year, dv_position FROM work")
        ).fetchall()
        db_coords = set(all_rows)

        for broy, year, position, rel in fixture_coords:
            if (broy, year, position) not in db_coords:
                issues.append(Issue(
                    severity="error",
                    code="FIXTURE_NOT_LOADED",
                    message=f"Fixture not found in DB: dv_broy={broy} dv_year={year} dv_position={position}",
                    path=rel,
                    detail=f"Expected work with (dv_broy={broy}, dv_year={year}, dv_position={position})",
                ))

    # Works with 0 elements
    zero_elem_rows = session.execute(text("""
        SELECT w.eli_uri
        FROM work w
        JOIN expression e ON e.work_id = w.id AND e.is_latest = true
        LEFT JOIN element el ON el.expression_id = e.id
        GROUP BY w.id, w.eli_uri
        HAVING COUNT(el.id) = 0
    """)).fetchall()
    for row in zero_elem_rows:
        issues.append(Issue(
            severity="warn",
            code="ZERO_ELEMENTS",
            message=f"Work has no parsed elements: {row[0]}",
            path=row[0],
        ))

    dup_stats = _check_duplicates(session, issues)
    return LayerResult(
        name="db",
        issues=issues,
        stats={
            "fixture_types": len(fixture_counts),
            "db_types": len(db_counts),
            "type_not_in_db": sum(1 for i in issues if i.code == "TYPE_NOT_IN_DB"),
            "coverage_gaps": sum(1 for i in issues if i.code == "COVERAGE_GAP"),
            "fixture_not_loaded": sum(1 for i in issues if i.code == "FIXTURE_NOT_LOADED"),
            "zero_elements": len(zero_elem_rows),
            **dup_stats,
        },
    )
