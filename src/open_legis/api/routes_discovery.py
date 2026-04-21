from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.api.schemas import DvRef, WorkList, WorkListItem
from open_legis.model import schema as m
from open_legis.model.schema import Amendment as Amend, Reference as Ref
from open_legis.search.query import search as _search

router = APIRouter(tags=["discovery"])


# ---------------------------------------------------------------------------
# Pydantic models for edge / expression endpoints
# ---------------------------------------------------------------------------


class AmendmentItem(BaseModel):
    amending_uri: str
    target_uri: str
    target_e_id: str | None
    operation: str
    effective_date: str
    notes: str | None


class AmendmentList(BaseModel):
    items: list[AmendmentItem]


class ReferenceItem(BaseModel):
    source_expression_uri: str
    source_e_id: str
    target_uri: str | None
    target_e_id: str | None
    type: str


class ReferenceList(BaseModel):
    items: list[ReferenceItem]


class ExpressionItem(BaseModel):
    uri: str
    date: str
    language: str
    is_latest: bool


class ExpressionList(BaseModel):
    items: list[ExpressionItem]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _work_by_slug(s: Session, slug: str) -> m.Work:
    work = s.scalars(select(m.Work).where(m.Work.eli_uri.endswith(f"/{slug}"))).first()
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work slug not found: {slug}")
    return work


@router.get("/works", response_model=WorkList)
def list_works(
    type: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    s: Session = Depends(get_session),
) -> WorkList:
    q = select(m.Work)
    if type:
        q = q.where(m.Work.act_type == m.ActType(type))
    total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
    works = s.scalars(q.offset((page - 1) * page_size).limit(page_size)).all()
    return WorkList(
        items=[
            WorkListItem(
                uri=w.eli_uri,
                title=w.title,
                type=w.act_type.value,
                dv_ref=DvRef(broy=w.dv_broy, year=w.dv_year),
            )
            for w in works
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


class SearchItem(BaseModel):
    work_uri: str
    work_title: str
    type: str
    expression_date: str
    e_id: str
    num: str | None
    snippet: str
    rank: float


class SearchResponse(BaseModel):
    items: list[SearchItem]
    total: int
    page: int
    page_size: int


@router.get("/search", response_model=SearchResponse)
def search_route(
    q: str = Query(..., min_length=1),
    type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    s: Session = Depends(get_session),
) -> SearchResponse:
    hits, total = _search(
        s, q=q, act_type=type, limit=page_size, offset=(page - 1) * page_size
    )
    items = [
        SearchItem(
            work_uri=h.work_uri,
            work_title=h.work_title,
            type=h.work_type,
            expression_date=h.expression_date,
            e_id=h.e_id,
            num=h.num,
            snippet=h.snippet,
            rank=h.rank,
        )
        for h in hits
    ]
    return SearchResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/works/{slug}/amendments", response_model=AmendmentList)
def amendments(
    slug: str,
    direction: str = Query("in", pattern="^(in|out)$"),
    s: Session = Depends(get_session),
) -> AmendmentList:
    work = _work_by_slug(s, slug)
    col = Amend.target_work_id if direction == "in" else Amend.amending_work_id
    rows = s.scalars(select(Amend).where(col == work.id)).all()
    amend_work_uri_by_id = {
        w.id: w.eli_uri for w in s.scalars(select(m.Work)).all()
    }
    return AmendmentList(
        items=[
            AmendmentItem(
                amending_uri=amend_work_uri_by_id[a.amending_work_id],
                target_uri=amend_work_uri_by_id[a.target_work_id],
                target_e_id=a.target_e_id,
                operation=a.operation.value,
                effective_date=a.effective_date.isoformat(),
                notes=a.notes,
            )
            for a in rows
        ]
    )


@router.get("/works/{slug}/references", response_model=ReferenceList)
def references(
    slug: str,
    direction: str = Query("in", pattern="^(in|out)$"),
    s: Session = Depends(get_session),
) -> ReferenceList:
    work = _work_by_slug(s, slug)
    if direction == "in":
        rows = s.scalars(select(Ref).where(Ref.target_work_id == work.id)).all()
    else:
        expr_ids = [
            e.id
            for e in s.scalars(
                select(m.Expression).where(m.Expression.work_id == work.id)
            ).all()
        ]
        rows = (
            s.scalars(select(Ref).where(Ref.source_expression_id.in_(expr_ids))).all()
            if expr_ids
            else []
        )

    expr_uri_by_id = {}
    for e in s.scalars(select(m.Expression)).all():
        w = e.work
        expr_uri_by_id[e.id] = (
            f"{w.eli_uri}/{e.expression_date.isoformat()}/{e.language}"
        )
    work_uri_by_id = {w.id: w.eli_uri for w in s.scalars(select(m.Work)).all()}

    return ReferenceList(
        items=[
            ReferenceItem(
                source_expression_uri=expr_uri_by_id[r.source_expression_id],
                source_e_id=r.source_e_id,
                target_uri=work_uri_by_id.get(r.target_work_id) if r.target_work_id else None,
                target_e_id=r.target_e_id,
                type=r.reference_type.value,
            )
            for r in rows
        ]
    )


@router.get("/works/{slug}/expressions", response_model=ExpressionList)
def expressions_list(slug: str, s: Session = Depends(get_session)) -> ExpressionList:
    work = _work_by_slug(s, slug)
    exprs = s.scalars(
        select(m.Expression)
        .where(m.Expression.work_id == work.id)
        .order_by(m.Expression.expression_date.asc())
    ).all()
    return ExpressionList(
        items=[
            ExpressionItem(
                uri=f"{work.eli_uri}/{e.expression_date.isoformat()}/{e.language}",
                date=e.expression_date.isoformat(),
                language=e.language,
                is_latest=e.is_latest,
            )
            for e in exprs
        ]
    )
