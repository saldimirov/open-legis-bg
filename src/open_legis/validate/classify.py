from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from open_legis.scraper.dv_to_akn import detect_act_type
from open_legis.validate import Issue, LayerResult

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NS = {"akn": _AKN_NS}

# Court decision subtype patterns (from the DV index page, issue 80 from 2016 has KEVR decisions)
_COURT_SUBTYPES = {
    # ЖЗ = Supreme Court of Cassation (Жалба Касационна)
    r"ЖЗ": "reshenie_kevr",
    # БЗ = Supreme Administrative Court
    r"БЗ": "reshenie_bs",
    # ВАС = Supreme Administrative Court (alternate)
    r"ВАС": "reshenie_vas",
    # КС = Constitutional Court
    r"КС": "reshenie_cc",
}


def _detect_court_subtype(title: str) -> str | None:
    """Detect court decision subtype from title suffix patterns like '№ 689-ЖЗ'."""
    # Match patterns like "Решение № 689-ХХ" where ХХ is the court abbreviation
    m = re.search(r"№\s+\d+\s*-\s*([А-Я]+)", title)
    if m:
        suffix = m.group(1)
        for pattern, subtype in _COURT_SUBTYPES.items():
            if pattern in suffix:
                return subtype
    return None


def check_classification(fixtures_root: Path) -> LayerResult:
    issues: list[Issue] = []
    checked = 0

    for f in sorted(fixtures_root.rglob("*.bul.xml")):
        rel = f.relative_to(fixtures_root).as_posix()
        parts = rel.split("/")
        if len(parts) < 4:
            continue
        dir_act_type = parts[0]

        try:
            tree = etree.parse(str(f))
        except etree.XMLSyntaxError:
            continue  # already flagged by Layer 2

        short_nodes = tree.xpath("//akn:FRBRalias[@name='short']", namespaces=_NS)
        if not short_nodes:
            continue  # already flagged by Layer 2 as MISSING_TITLE

        title = short_nodes[0].get("value", "")
        detected = detect_act_type(title)
        checked += 1

        # Handle court decisions: detect_act_type returns "_court", we need to check subtype
        if detected == "_court":
            subtype = _detect_court_subtype(title)
            if subtype:
                detected = subtype
            else:
                # Generic court decision without specific subtype
                detected = "reshenie_court"

        if detected == "_other":
            issues.append(Issue(
                severity="warn",
                code="UNDETECTED",
                message=f"Could not classify title: {title[:80]!r}",
                path=rel,
            ))
            continue

        if detected != dir_act_type:
            issues.append(Issue(
                severity="error",
                code="TYPE_MISMATCH",
                message=(
                    f"Directory={dir_act_type!r} but title detects as {detected!r}: "
                    f"{title[:80]!r}"
                ),
                path=rel,
                detail=f"expected={dir_act_type}, detected={detected}",
            ))

    return LayerResult(
        name="classify",
        issues=issues,
        stats={
            "checked": checked,
            "mismatches": sum(1 for i in issues if i.code == "TYPE_MISMATCH"),
            "undetected": sum(1 for i in issues if i.code == "UNDETECTED"),
        },
    )
