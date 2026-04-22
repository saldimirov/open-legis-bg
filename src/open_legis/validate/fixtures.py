# src/open_legis/validate/fixtures.py
from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from open_legis.validate import Issue, LayerResult

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NS = {"akn": _AKN_NS}
# {act_type}/{year}/{slug}/expressions/{date}.bul.xml
_PATH_RE = re.compile(
    r"^(?P<act_type>[^/]+)/(?P<year>\d{4})/(?P<slug>[^/]+)"
    r"/expressions/(?P<date>\d{4}-\d{2}-\d{2})\.bul\.xml$"
)


def check_fixtures(fixtures_root: Path) -> LayerResult:
    issues: list[Issue] = []
    files = sorted(fixtures_root.rglob("*.bul.xml"))
    checked = 0

    for f in files:
        rel = f.relative_to(fixtures_root).as_posix()
        checked += 1

        try:
            tree = etree.parse(str(f))
        except etree.XMLSyntaxError as exc:
            issues.append(Issue("error", "MALFORMED_XML",
                f"Not valid XML: {exc}", rel))
            continue

        root = tree.getroot()

        # Title: warn if name="short" absent (some older fixtures may only have name="eli")
        if not root.xpath("//akn:FRBRalias[@name='short']", namespaces=_NS):
            issues.append(Issue("warn", "MISSING_TITLE",
                "FRBRalias name='short' absent — title not machine-readable", rel))

        # Body must have at least one child
        body = root.find(f"{{{_AKN_NS}}}act/{{{_AKN_NS}}}body")
        if body is None or len(body) == 0:
            issues.append(Issue("error", "EMPTY_BODY",
                "<body> is absent or has no child elements", rel))

        # Path structure
        m = _PATH_RE.match(rel)
        if not m:
            issues.append(Issue("warn", "BAD_PATH",
                "Path doesn't match {act_type}/{year}/{slug}/expressions/{date}.bul.xml",
                rel))
            continue

        path_act_type = m.group("act_type")
        path_year = m.group("year")
        path_slug = m.group("slug")

        # ELI in XML must match path
        eli_nodes = root.xpath("//akn:FRBRalias[@name='eli']", namespaces=_NS)
        if eli_nodes:
            eli_other = eli_nodes[0].get("other", "")
            expected = f"/eli/bg/{path_act_type}/{path_year}/{path_slug}"
            if eli_other != expected:
                issues.append(Issue("warn", "ELI_MISMATCH",
                    f"ELI in XML ({eli_other!r}) doesn't match path ({expected!r})", rel))

    counts = {
        "checked": checked,
        "malformed": sum(1 for i in issues if i.code == "MALFORMED_XML"),
        "empty_body": sum(1 for i in issues if i.code == "EMPTY_BODY"),
        "eli_mismatch": sum(1 for i in issues if i.code == "ELI_MISMATCH"),
    }
    return LayerResult(name="fixtures", issues=issues, stats=counts)
