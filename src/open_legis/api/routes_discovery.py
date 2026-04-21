from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.api.schemas import DvRef, WorkList, WorkListItem
from open_legis.model import schema as m
from open_legis.search.query import search as _search

router = APIRouter(tags=["discovery"])


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
