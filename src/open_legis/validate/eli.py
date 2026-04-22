from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from open_legis.validate import Issue, LayerResult

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NS = {"akn": _AKN_NS}
_SLUG_RE = re.compile(r"^dv-\d+-\d{2}-\d+$")

_NUMBER_PATTERNS: dict[str, re.Pattern[str]] = {
    "postanovlenie": re.compile(r"Постановление\s+№\s+\d+", re.IGNORECASE),
    "naredba": re.compile(r"Наредба\s+№\s+[\w\-/]+", re.IGNORECASE),
    "pravilnik": re.compile(r"Правилник\s+№\s+[\w\-/]+", re.IGNORECASE),
    "reshenie_kevr": re.compile(r"Решение\s+№\s+[\w\-]+"),
}
_NUMBER_PATTERNS["reshenie_kfn"] = _NUMBER_PATTERNS["reshenie_kevr"]
_NUMBER_PATTERNS["reshenie_nhif"] = _NUMBER_PATTERNS["reshenie_kevr"]


def check_eli(fixtures_root: Path) -> LayerResult:
    issues: list[Issue] = []
    slug_counts: dict[str, int] = {"standard": 0, "nonstandard": 0}
    number_stats: dict[str, dict[str, int]] = {}

    for f in sorted(fixtures_root.rglob("*.bul.xml")):
        parts = f.relative_to(fixtures_root).parts
        if len(parts) < 3:
            continue
        act_type, _year, slug = parts[0], parts[1], parts[2]
        rel = f.relative_to(fixtures_root).as_posix()

        if _SLUG_RE.match(slug):
            slug_counts["standard"] += 1
        else:
            slug_counts["nonstandard"] += 1
            issues.append(Issue(
                severity="info",
                code="NONSTANDARD_SLUG",
                message=f"Slug {slug!r} doesn't follow dv-N-NN-N pattern",
                path=rel,
            ))

        if act_type not in _NUMBER_PATTERNS:
            continue

        if act_type not in number_stats:
            number_stats[act_type] = {"total": 0, "has_number": 0}
        number_stats[act_type]["total"] += 1

        try:
            tree = etree.parse(f)
            aliases = tree.xpath("//akn:FRBRalias[@name='short']", namespaces=_NS)
            if aliases:
                title = aliases[0].get("value", "")
                if _NUMBER_PATTERNS[act_type].search(title):
                    number_stats[act_type]["has_number"] += 1
        except etree.XMLSyntaxError:
            pass

    for act_type, stats in number_stats.items():
        if stats["total"] == 0:
            continue
        pct = stats["has_number"] / stats["total"] * 100
        issues.append(Issue(
            severity="info",
            code="NUMBER_COVERAGE",
            message=(
                f"{act_type}: {stats['has_number']}/{stats['total']} ({pct:.0f}%) "
                f"have parseable official numbers"
            ),
            path=act_type,
            detail="Populate work.number for human-readable display; keep current slugs",
        ))

    issues.append(Issue(
        severity="info",
        code="ELI_RECOMMENDATION",
        message="Current dv-N-NN-N slugs are stable — do not change after launch",
        detail=(
            "Recommended: populate work.number (already in schema) for acts with "
            "official numbers; no URI changes needed"
        ),
    ))

    extra_stats = {
        f"{k}_with_number": v["has_number"] for k, v in number_stats.items()
    }
    return LayerResult(
        name="eli",
        issues=issues,
        stats={**slug_counts, **extra_stats},
    )
