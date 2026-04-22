from __future__ import annotations

from pathlib import Path

from lxml import etree

from open_legis.scraper.dv_to_akn import detect_act_type
from open_legis.validate import Issue, LayerResult

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NS = {"akn": _AKN_NS}

_RESHENIE_BODY: list[tuple[str, str]] = [
    ("Народното събрание", "reshenie_ns"),
    ("Решение за", "reshenie_ns"),
    ("КЕВР", "reshenie_kevr"),
    ("ДКЕВР", "reshenie_kevr"),
    ("КФН", "reshenie_kfn"),
    ("РД-НС", "reshenie_nhif"),
    ("Министерски съвет", "reshenie_ms"),
]


def _detect_reshenie_subtype(title: str) -> str | None:
    for keyword, subtype in _RESHENIE_BODY:
        if keyword in title:
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
        checked += 1

        if dir_act_type.startswith("reshenie_"):
            expected = _detect_reshenie_subtype(title)
            if expected is None:
                issues.append(Issue(
                    severity="warn",
                    code="UNDETECTED",
                    message=f"Cannot determine reshenie subtype from title: {title[:80]!r}",
                    path=rel,
                ))
            elif expected != dir_act_type:
                issues.append(Issue(
                    severity="error",
                    code="RESHENIE_WRONG_BODY",
                    message=(
                        f"Directory={dir_act_type!r} but body keywords suggest {expected!r}: "
                        f"{title[:80]!r}"
                    ),
                    path=rel,
                    detail=f"expected={dir_act_type}, detected_body={expected}",
                ))
            continue  # reshenie handled; don't fall through to generic TYPE_MISMATCH

        detected = detect_act_type(title)

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
            "reshenie_wrong_body": sum(1 for i in issues if i.code == "RESHENIE_WRONG_BODY"),
        },
    )
