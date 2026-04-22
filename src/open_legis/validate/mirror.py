from __future__ import annotations

import json
from pathlib import Path

from open_legis.validate import Issue, LayerResult

_MIN_SIZE = 1024


def check_mirror(index_path: Path, mirror_root: Path) -> LayerResult:
    entries = json.loads(index_path.read_text(encoding="utf-8"))
    issues: list[Issue] = []
    checked = 0

    for entry in entries:
        year = entry["year"]
        broy = entry["broy"]
        idobj = entry["idObj"]
        stem = f"{broy:03d}-{idobj}"

        rtf = mirror_root / str(year) / f"{stem}.rtf"
        pdf = mirror_root / str(year) / f"{stem}.pdf"

        if rtf.exists():
            found = rtf
        elif pdf.exists():
            found = pdf
        else:
            issues.append(Issue(
                severity="error",
                code="MISSING_FILE",
                message=f"DV {year} broy {broy} (idObj={idobj}) not in mirror",
                path=str(mirror_root / str(year) / stem),
                detail=f"Expected {rtf} or {pdf}",
            ))
            checked += 1
            continue

        if found.stat().st_size < _MIN_SIZE:
            issues.append(Issue(
                severity="warn",
                code="TOO_SMALL",
                message=f"DV {year} broy {broy}: {found.name} is {found.stat().st_size} bytes (< {_MIN_SIZE})",
                path=str(found),
            ))
        checked += 1

    missing = sum(1 for i in issues if i.code == "MISSING_FILE")
    too_small = sum(1 for i in issues if i.code == "TOO_SMALL")
    return LayerResult(
        name="mirror",
        issues=issues,
        stats={"checked": checked, "missing": missing, "too_small": too_small},
    )
