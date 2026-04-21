"""open-legis MCP server — exposes Bulgarian legislation to AI assistants."""
from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Optional

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from open_legis.model import schema as m
from open_legis.search.query import search as _search


# ---------------------------------------------------------------------------
# Session factory — shared with FastAPI deps (lru_cached), works for stdio too
# ---------------------------------------------------------------------------

def _get_factory() -> sessionmaker[Session]:
    from open_legis.api.deps import _session_factory
    return _session_factory()


mcp = FastMCP(
    "open-legis",
    instructions=(
        "Access the open-legis database of Bulgarian legislation. "
        "Laws are identified by ELI URIs of the form /eli/bg/{act_type}/{year}/{slug}. "
        "Use search_laws for full-text search, get_law for metadata, "
        "get_law_elements for structured article text, list_laws to browse by type/year, "
        "get_law_toc for structure overview, get_element for a single article."
    ),
)

ACT_TYPE_LABELS: dict[str, str] = {
    "konstitutsiya": "Конституция",
    "kodeks": "Кодекс",
    "zakon": "Закон",
    "zid": "Изменение / Отмяна",
    "ratifikatsiya": "Ратификация",
    "byudjet": "Бюджетен закон",
    "postanovlenie": "Постановление",
    "naredba": "Наредба",
    "pravilnik": "Правилник",
    "reshenie_ns": "Решение на НС",
    "reshenie_ms": "Решение на МС",
    "razporezhane": "Разпореждане",
    "ukaz": "Указ",
}

VALID_ACT_TYPES = list(ACT_TYPE_LABELS.keys())


def _resolve_expression(
    session: Session, work: m.Work, expression_date: Optional[str]
) -> m.Expression | None:
    q = select(m.Expression).where(m.Expression.work_id == work.id)
    if expression_date:
        q = q.where(m.Expression.expression_date == dt.date.fromisoformat(expression_date))
    else:
        q = q.where(m.Expression.is_latest.is_(True))
    return session.scalar(q)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_laws(
    q: str,
    act_type: Optional[str] = None,
    limit: Annotated[int, "Max results (1–100)"] = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Full-text search across all Bulgarian legislation.

    Args:
        q: Search terms in Bulgarian (e.g. "данък добавена стойност").
        act_type: Filter by type — one of: konstitutsiya, kodeks, zakon, zid,
            ratifikatsiya, byudjet, postanovlenie, naredba, pravilnik,
            reshenie_ns, reshenie_ms, razporezhane, ukaz. Omit for all types.
        limit: Number of results to return (max 100).
        offset: Pagination offset.

    Returns:
        dict with keys: hits (list of matches), total (int), q (str).
    """
    if not q.strip():
        return {"error": "empty query", "hits": [], "total": 0, "q": q}
    if act_type and act_type not in VALID_ACT_TYPES:
        return {
            "error": f"unknown act_type '{act_type}'. Valid: {', '.join(VALID_ACT_TYPES)}",
            "hits": [],
            "total": 0,
            "q": q,
        }
    limit = max(1, min(100, limit))

    with _get_factory()() as session:
        hits, total = _search(session, q, act_type=act_type, limit=limit, offset=offset)

    return {
        "q": q,
        "total": total,
        "offset": offset,
        "hits": [
            {
                "eli_uri": h.work_uri,
                "title": h.work_title,
                "act_type": h.work_type,
                "act_type_label": ACT_TYPE_LABELS.get(h.work_type, h.work_type),
                "expression_date": h.expression_date,
                "element_id": h.e_id,
                "element_num": h.num,
                "snippet": h.snippet,
                "rank": round(h.rank, 4),
            }
            for h in hits
        ],
    }


@mcp.tool()
def get_law(eli_uri: str) -> dict[str, Any]:
    """Get metadata for a specific law by its ELI URI.

    Args:
        eli_uri: The ELI identifier, e.g. /eli/bg/zakon/2023/123.

    Returns:
        Work metadata including title, act type, DV issue, status, adoption
        date, and a list of available expressions (dated versions).
    """
    with _get_factory()() as session:
        work = session.scalar(select(m.Work).where(m.Work.eli_uri == eli_uri))
        if work is None:
            return {"error": f"law not found: {eli_uri}"}

        expressions = [
            {
                "expression_date": expr.expression_date.isoformat(),
                "language": expr.language,
                "is_latest": expr.is_latest,
            }
            for expr in sorted(work.expressions, key=lambda e: e.expression_date)
        ]

    return {
        "eli_uri": work.eli_uri,
        "title": work.title,
        "title_short": work.title_short,
        "act_type": work.act_type.value,
        "act_type_label": ACT_TYPE_LABELS.get(work.act_type.value, work.act_type.value),
        "number": work.number,
        "adoption_date": work.adoption_date.isoformat() if work.adoption_date else None,
        "dv_issue": work.dv_broy,
        "dv_year": work.dv_year,
        "issuing_body": work.issuing_body,
        "status": work.status.value,
        "expressions": expressions,
    }


@mcp.tool()
def get_law_toc(eli_uri: str, expression_date: Optional[str] = None) -> dict[str, Any]:
    """Get the table of contents (structural outline) of a law — headings only, no body text.

    Use this to orient yourself in a large law before fetching specific elements.

    Args:
        eli_uri: The ELI URI of the law.
        expression_date: ISO date (YYYY-MM-DD) for a specific version. Defaults
            to the latest expression.

    Returns:
        dict with 'toc' list (type, num, heading, id, parent_id) and
        article_count for scale reference.
    """
    STRUCTURAL_TYPES = {
        m.ElementType.PART,
        m.ElementType.TITLE,
        m.ElementType.CHAPTER,
        m.ElementType.SECTION,
        m.ElementType.HCONTAINER,
    }

    with _get_factory()() as session:
        work = session.scalar(select(m.Work).where(m.Work.eli_uri == eli_uri))
        if work is None:
            return {"error": f"law not found: {eli_uri}"}

        try:
            expression = _resolve_expression(session, work, expression_date)
        except ValueError:
            return {"error": f"invalid date format: {expression_date}. Use YYYY-MM-DD."}
        if expression is None:
            return {"error": "expression not found"}

        all_elements = sorted(expression.elements, key=lambda e: e.sequence)
        toc = [
            {
                "id": e.e_id,
                "parent_id": e.parent_e_id,
                "type": e.element_type.value,
                "num": e.num,
                "heading": e.heading,
            }
            for e in all_elements
            if e.element_type in STRUCTURAL_TYPES
        ]
        article_count = sum(1 for e in all_elements if e.element_type == m.ElementType.ARTICLE)

    return {
        "eli_uri": eli_uri,
        "title": work.title,
        "expression_date": expression.expression_date.isoformat(),
        "article_count": article_count,
        "toc": toc,
    }


@mcp.tool()
def get_element(
    eli_uri: str, e_id: str, expression_date: Optional[str] = None
) -> dict[str, Any]:
    """Get a single element (article, paragraph, etc.) from a law by its element ID.

    Efficient alternative to get_law_elements when you only need one specific
    article — e.g. after search_laws returns a hit with an element_id.

    Args:
        eli_uri: The ELI URI of the law.
        e_id: Element identifier as returned by search_laws (e.g. "art-42-par-1").
        expression_date: ISO date (YYYY-MM-DD) for a specific version. Defaults
            to the latest expression.

    Returns:
        The element with its num, heading, text, type, and parent_id, plus
        immediate children for context.
    """
    with _get_factory()() as session:
        work = session.scalar(select(m.Work).where(m.Work.eli_uri == eli_uri))
        if work is None:
            return {"error": f"law not found: {eli_uri}"}

        try:
            expression = _resolve_expression(session, work, expression_date)
        except ValueError:
            return {"error": f"invalid date format: {expression_date}. Use YYYY-MM-DD."}
        if expression is None:
            return {"error": "expression not found"}

        element = session.scalar(
            select(m.Element)
            .where(m.Element.expression_id == expression.id)
            .where(m.Element.e_id == e_id)
        )
        if element is None:
            return {"error": f"element '{e_id}' not found in {eli_uri}"}

        children = session.scalars(
            select(m.Element)
            .where(m.Element.expression_id == expression.id)
            .where(m.Element.parent_e_id == e_id)
            .order_by(m.Element.sequence)
        ).all()

    return {
        "eli_uri": eli_uri,
        "expression_date": expression.expression_date.isoformat(),
        "element": {
            "id": element.e_id,
            "parent_id": element.parent_e_id,
            "type": element.element_type.value,
            "num": element.num,
            "heading": element.heading,
            "text": element.text,
        },
        "children": [
            {
                "id": c.e_id,
                "type": c.element_type.value,
                "num": c.num,
                "heading": c.heading,
                "text": c.text,
            }
            for c in children
        ],
    }


@mcp.tool()
def get_law_elements(
    eli_uri: str,
    expression_date: Optional[str] = None,
    element_types: Optional[str] = None,
) -> dict[str, Any]:
    """Get all structured text elements of a law (articles, paragraphs, etc.).

    For large laws (codes), prefer get_law_toc first to orient, then get_element
    for specific articles. Use this when you need the full text.

    Args:
        eli_uri: The ELI URI of the law.
        expression_date: ISO date (YYYY-MM-DD) for a specific version. Defaults
            to the latest expression.
        element_types: Comma-separated filter — any of: article, paragraph,
            point, chapter, section, part, title, hcontainer. Omit for all.

    Returns:
        dict with law metadata and 'elements' list ordered by sequence.
    """
    type_filter: Optional[set[str]] = None
    if element_types:
        type_filter = {t.strip() for t in element_types.split(",")}

    with _get_factory()() as session:
        work = session.scalar(select(m.Work).where(m.Work.eli_uri == eli_uri))
        if work is None:
            return {"error": f"law not found: {eli_uri}"}

        try:
            expression = _resolve_expression(session, work, expression_date)
        except ValueError:
            return {"error": f"invalid date format: {expression_date}. Use YYYY-MM-DD."}
        if expression is None:
            return {"error": "expression not found"}

        elements = sorted(expression.elements, key=lambda e: e.sequence)
        if type_filter:
            elements = [e for e in elements if e.element_type.value in type_filter]

        element_list = [
            {
                "id": e.e_id,
                "parent_id": e.parent_e_id,
                "type": e.element_type.value,
                "num": e.num,
                "heading": e.heading,
                "text": e.text,
                "sequence": e.sequence,
            }
            for e in elements
        ]

    return {
        "eli_uri": eli_uri,
        "title": work.title,
        "expression_date": expression.expression_date.isoformat(),
        "is_latest": expression.is_latest,
        "element_count": len(element_list),
        "elements": element_list,
    }


@mcp.tool()
def list_laws(
    act_type: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    limit: Annotated[int, "Max results (1–200)"] = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List laws in the database, optionally filtered by type, year, or status.

    Args:
        act_type: Filter by act type (see search_laws for valid values).
        year: Filter by DV publication year (e.g. 2023).
        status: Filter by status — one of: in_force, repealed,
            partially_in_force.
        limit: Max results (1–200).
        offset: Pagination offset.

    Returns:
        dict with 'laws' list and 'total' count.
    """
    if act_type and act_type not in VALID_ACT_TYPES:
        return {
            "error": f"unknown act_type '{act_type}'. Valid: {', '.join(VALID_ACT_TYPES)}",
            "laws": [],
            "total": 0,
        }
    if status and status not in ("in_force", "repealed", "partially_in_force"):
        return {
            "error": "status must be one of: in_force, repealed, partially_in_force",
            "laws": [],
            "total": 0,
        }
    limit = max(1, min(200, limit))

    with _get_factory()() as session:
        stmt = select(m.Work)
        if act_type:
            stmt = stmt.where(m.Work.act_type == m.ActType(act_type))
        if year:
            stmt = stmt.where(m.Work.dv_year == year)
        if status:
            stmt = stmt.where(m.Work.status == m.ActStatus(status))

        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = session.scalars(
            stmt.order_by(m.Work.dv_year.desc(), m.Work.dv_broy.desc(), m.Work.dv_position)
            .offset(offset)
            .limit(limit)
        ).all()

        laws = [
            {
                "eli_uri": w.eli_uri,
                "title": w.title,
                "title_short": w.title_short,
                "act_type": w.act_type.value,
                "act_type_label": ACT_TYPE_LABELS.get(w.act_type.value, w.act_type.value),
                "number": w.number,
                "adoption_date": w.adoption_date.isoformat() if w.adoption_date else None,
                "dv_issue": w.dv_broy,
                "dv_year": w.dv_year,
                "status": w.status.value,
            }
            for w in rows
        ]

    return {"total": total, "offset": offset, "laws": laws}


# ---------------------------------------------------------------------------
# Entry point (stdio — for Claude Desktop / Claude Code)
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
