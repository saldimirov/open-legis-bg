from __future__ import annotations

from pathlib import Path

from lxml import etree

from open_legis.scraper.dv_to_akn import detect_act_type
from open_legis.validate import Issue, LayerResult

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NS = {"akn": _AKN_NS}

# Old compound reshenie_* fixture directories map to the new flat "reshenie" type
_DIR_REMAP: dict[str, str] = {
    "reshenie_ks":   "reshenie",
    "reshenie_ns":   "reshenie",
    "reshenie_ms":   "reshenie",
    "reshenie_kevr": "reshenie",
    "reshenie_kfn":  "reshenie",
    "reshenie_nhif": "reshenie",
}


def check_classification(fixtures_root: Path) -> LayerResult:
    issues: list[Issue] = []
    checked = 0

    for f in sorted(fixtures_root.rglob("*.bul.xml")):
        rel = f.relative_to(fixtures_root).as_posix()
        parts = rel.split("/")
        if len(parts) < 4:
            continue
        dir_act_type = _DIR_REMAP.get(parts[0], parts[0])

        try:
            tree = etree.parse(str(f))
        except etree.XMLSyntaxError:
            continue  # already flagged by Layer 2

        short_nodes = tree.xpath("//akn:FRBRalias[@name='short']", namespaces=_NS)
        if not short_nodes:
            continue  # already flagged by Layer 2 as MISSING_TITLE

        title = short_nodes[0].get("value", "")
        checked += 1

        detected, _ = detect_act_type(title)

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
                    f"Directory={parts[0]!r} but title detects as {detected!r}: "
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
