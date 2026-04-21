"""Server-rendered HTML UI routes."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.model import schema as m
from open_legis.search.query import search as _search

router = APIRouter(include_in_schema=False)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

TYPE_LABELS: dict[str, str] = {
    "zakon": "Закон",
    "zid": "ЗИД",
    "kodeks": "Кодекс",
    "naredba": "Наредба",
    "postanovlenie": "Постановление",
    "pravilnik": "Правилник",
    "reshenie_ns": "Решение на НС",
    "ukaz": "Указ",
    "konstitutsiya": "Конституция",
}

PAGE_SIZE = 20


def _ctx(**kwargs: Any) -> dict[str, Any]:
    return {"type_labels": TYPE_LABELS, **kwargs}


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    type: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    s: Session = Depends(get_session),
) -> HTMLResponse:
    db_q = select(m.Work).order_by(m.Work.dv_year.desc(), m.Work.dv_broy.desc(), m.Work.dv_position)
    if type:
        try:
            db_q = db_q.where(m.Work.act_type == m.ActType(type.lower()))
        except ValueError:
            pass
    if q:
        db_q = db_q.where(m.Work.title.ilike(f"%{q}%"))

    total = s.scalar(select(func.count()).select_from(db_q.subquery())) or 0
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    works = s.scalars(db_q.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()

    items = [
        {
            "uri": w.eli_uri,
            "title": w.title,
            "type": w.act_type.value.lower(),
            "dv_ref": {"broy": w.dv_broy, "year": w.dv_year},
        }
        for w in works
    ]

    return templates.TemplateResponse(
        request,
        "index.html",
        _ctx(
            works=items,
            total=total,
            page=page,
            total_pages=total_pages,
            current_type=type or "",
            q=q or "",
        ),
    )


@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    s: Session = Depends(get_session),
) -> HTMLResponse:
    hits, total = _search(s, q=q, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    items = [
        {
            "work_uri": h.work_uri,
            "work_title": h.work_title,
            "type": h.work_type.lower(),
            "expression_date": h.expression_date,
            "num": h.num,
            "snippet": h.snippet,
        }
        for h in hits
    ]

    return templates.TemplateResponse(
        request,
        "search.html",
        _ctx(items=items, q=q, total=total, page=page, total_pages=total_pages),
    )


@router.get("/ui/eli/bg/{act_type}/{year}/{slug}", response_class=HTMLResponse)
def work_page(
    request: Request,
    act_type: str,
    year: int,
    slug: str,
    s: Session = Depends(get_session),
) -> HTMLResponse:
    eli = f"/eli/bg/{act_type}/{year}/{slug}"
    work = s.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail="Актът не е намерен")

    expr = s.scalars(
        select(m.Expression).where(
            m.Expression.work_id == work.id,
            m.Expression.is_latest.is_(True),
        )
    ).one_or_none()

    elements: list[dict] = []
    preface: list[str] = []
    expression_date = None
    adoption_date = None

    if expr:
        expression_date = expr.expression_date.isoformat()
        if work.adoption_date:
            adoption_date = work.adoption_date.isoformat()

        # Extract preface from AKN XML
        try:
            from lxml import etree
            NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
            root = etree.fromstring(expr.akn_xml.encode())
            for p in root.findall(f".//{{{NS}}}preface/{{{NS}}}p"):
                if p.text and p.text.strip():
                    preface.append(p.text.strip())
        except Exception:
            pass

        db_elements = s.scalars(
            select(m.Element)
            .where(m.Element.expression_id == expr.id)
            .order_by(m.Element.sequence)
        ).all()
        elements = _build_element_tree(db_elements, parent_e_id=None)

    work_data = {
        "uri": work.eli_uri,
        "title": work.title,
        "type": work.act_type.value.lower(),
        "dv_ref": {"broy": work.dv_broy, "year": work.dv_year},
        "issuing_body": work.issuing_body,
    }

    return templates.TemplateResponse(
        request,
        "work.html",
        _ctx(
            work=work_data,
            elements=elements,
            preface=preface,
            expression_date=expression_date,
            adoption_date=adoption_date,
        ),
    )


def _build_element_tree(
    elements: list[m.Element], parent_e_id: str | None, depth: int = 0
) -> list[dict]:
    if depth > 5:
        return []
    direct = [e for e in elements if e.parent_e_id == parent_e_id]
    result = []
    for e in direct:
        children = _build_element_tree(elements, parent_e_id=e.e_id, depth=depth + 1)
        result.append(
            {
                "e_id": e.e_id,
                "type": e.element_type.value,
                "num": e.num,
                "heading": e.heading,
                "text": e.text,
                "children": children,
            }
        )
    return result
