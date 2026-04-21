from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.api.errors import COMMON_ERRORS
from open_legis.api.rate_limit import limiter
from open_legis.api.schemas import DvRef, WorkList, WorkListItem
from open_legis.model import schema as m
from open_legis.model.schema import Amendment as Amend, Reference as Ref
from open_legis.search.query import search as _search

router = APIRouter(tags=["discovery"])


class AmendmentItem(BaseModel):
    amending_uri: str = Field(..., description="ELI URI of the amending act (ЗИД).")
    target_uri: str = Field(..., description="ELI URI of the act being amended.")
    target_e_id: str | None = Field(None, description="Specific element targeted, if known.")
    operation: str = Field(..., description="Amendment operation: `insert`, `replace`, `delete`, or `repeal`.")
    effective_date: str = Field(..., description="ISO date when the amendment took effect.")
    notes: str | None = Field(None, description="Free-text annotation from the amendment text.")


class AmendmentList(BaseModel):
    items: list[AmendmentItem]


class ReferenceItem(BaseModel):
    source_expression_uri: str = Field(..., description="ELI URI of the expression that contains the reference.")
    source_e_id: str = Field(..., description="AKN eId of the element that contains the reference text.")
    target_uri: str | None = Field(None, description="ELI URI of the referenced work. Null if not yet resolved.")
    target_e_id: str | None = Field(None, description="Specific element referenced, if known.")
    type: str = Field(..., description="Reference type, e.g. `cites`.")


class ReferenceList(BaseModel):
    items: list[ReferenceItem]


class ExpressionItem(BaseModel):
    uri: str = Field(..., description="Full ELI URI of this expression.")
    date: str = Field(..., description="ISO effective date.")
    language: str = Field(..., description="BCP-47 language code.")
    is_latest: bool = Field(..., description="True if this is the current version.")


class ExpressionList(BaseModel):
    items: list[ExpressionItem]


class SearchItem(BaseModel):
    work_uri: str = Field(..., description="ELI URI of the matching act.")
    work_title: str = Field(..., description="Full title of the act.")
    type: str = Field(..., description="Act type key.")
    expression_date: str = Field(..., description="ISO date of the expression where the match was found.")
    e_id: str = Field(..., description="AKN eId of the matching element.")
    num: str | None = Field(None, description="Element number as displayed in the law, e.g. `Чл. 42.`")
    snippet: str = Field(..., description="Highlighted text snippet around the match (HTML `<mark>` tags).")
    rank: float = Field(..., description="Full-text search rank score (higher = more relevant).")


class SearchResponse(BaseModel):
    items: list[SearchItem]
    total: int = Field(..., description="Total matching elements (across all pages).")
    page: int = Field(..., description="Current page (1-based).")
    page_size: int = Field(..., description="Items per page.")


def _work_by_slug(s: Session, slug: str) -> m.Work:
    work = s.scalars(select(m.Work).where(m.Work.eli_uri.endswith(f"/{slug}"))).first()
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work slug not found: {slug}")
    return work


@router.get("/works", response_model=WorkList, summary="List works", description="Returns a paginated list of all legislative acts, optionally filtered by act type.", responses=COMMON_ERRORS)
@limiter.limit("120/minute")
def list_works(
    request: Request,
    type: Optional[str] = Query(None, description="Filter by act type, e.g. `zakon`, `zid`, `byudjet`."),
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(50, ge=1, le=200, description="Items per page (max 200)."),
    s: Session = Depends(get_session),
) -> WorkList:
    q = select(m.Work)
    if type:
        q = q.where(m.Work.act_type == m.ActType(type))
    total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
    works = s.scalars(q.offset((page - 1) * page_size).limit(page_size)).all()
    return WorkList(
        items=[WorkListItem(uri=w.eli_uri, title=w.title, type=w.act_type.value, dv_ref=DvRef(broy=w.dv_broy, year=w.dv_year)) for w in works],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Full-text search",
    description="Searches the full text of all legislative acts using PostgreSQL `tsvector` (Bulgarian `simple` dictionary). Results ranked by relevance.",
    responses=COMMON_ERRORS,
)
@limiter.limit("60/minute")
def search_route(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query. Supports Bulgarian text; no special syntax required."),
    type: str | None = Query(None, description="Restrict results to a single act type, e.g. `zakon`."),
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(50, ge=1, le=100, description="Results per page (max 100)."),
    s: Session = Depends(get_session),
) -> SearchResponse:
    hits, total = _search(s, q=q, act_type=type, limit=page_size, offset=(page - 1) * page_size)
    return SearchResponse(
        items=[SearchItem(work_uri=h.work_uri, work_title=h.work_title, type=h.work_type, expression_date=h.expression_date, e_id=h.e_id, num=h.num, snippet=h.snippet, rank=h.rank) for h in hits],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/works/{slug}/amendments",
    response_model=AmendmentList,
    summary="List amendments for a work",
    description="`direction=in` lists acts that amended *this* act. `direction=out` lists acts that *this* act amended.",
    responses=COMMON_ERRORS,
)
def amendments(
    slug: str = Path(..., description="Final path segment of the ELI URI, e.g. `za-darzhavnia-byudzhet`."),
    direction: str = Query("in", pattern="^(in|out)$", description="`in` — amendments received; `out` — amendments made."),
    s: Session = Depends(get_session),
) -> AmendmentList:
    work = _work_by_slug(s, slug)
    col = Amend.target_work_id if direction == "in" else Amend.amending_work_id
    rows = s.scalars(select(Amend).where(col == work.id)).all()
    amend_work_uri_by_id = {w.id: w.eli_uri for w in s.scalars(select(m.Work)).all()}
    return AmendmentList(items=[AmendmentItem(amending_uri=amend_work_uri_by_id[a.amending_work_id], target_uri=amend_work_uri_by_id[a.target_work_id], target_e_id=a.target_e_id, operation=a.operation.value, effective_date=a.effective_date.isoformat(), notes=a.notes) for a in rows])


@router.get(
    "/works/{slug}/references",
    response_model=ReferenceList,
    summary="List cross-references for a work",
    description="`direction=in` returns other acts that cite *this* act. `direction=out` returns all references within this act's expressions.",
    responses=COMMON_ERRORS,
)
def references(
    slug: str = Path(..., description="Final path segment of the ELI URI."),
    direction: str = Query("in", pattern="^(in|out)$", description="`in` — inbound citations; `out` — outbound references."),
    s: Session = Depends(get_session),
) -> ReferenceList:
    work = _work_by_slug(s, slug)
    if direction == "in":
        rows = s.scalars(select(Ref).where(Ref.target_work_id == work.id)).all()
    else:
        expr_ids = [e.id for e in s.scalars(select(m.Expression).where(m.Expression.work_id == work.id)).all()]
        rows = s.scalars(select(Ref).where(Ref.source_expression_id.in_(expr_ids))).all() if expr_ids else []

    expr_uri_by_id = {e.id: f"{e.work.eli_uri}/{e.expression_date.isoformat()}/{e.language}" for e in s.scalars(select(m.Expression)).all()}
    work_uri_by_id = {w.id: w.eli_uri for w in s.scalars(select(m.Work)).all()}
    return ReferenceList(items=[ReferenceItem(source_expression_uri=expr_uri_by_id[r.source_expression_id], source_e_id=r.source_e_id, target_uri=work_uri_by_id.get(r.target_work_id) if r.target_work_id else None, target_e_id=r.target_e_id, type=r.reference_type.value) for r in rows])


@router.get("/works/{slug}/expressions", response_model=ExpressionList, summary="List expressions for a work", description="Returns all known versions of a legislative act, ordered by date ascending.", responses=COMMON_ERRORS)
def expressions_list(
    slug: str = Path(..., description="Final path segment of the ELI URI."),
    s: Session = Depends(get_session),
) -> ExpressionList:
    work = _work_by_slug(s, slug)
    exprs = s.scalars(select(m.Expression).where(m.Expression.work_id == work.id).order_by(m.Expression.expression_date.asc())).all()
    return ExpressionList(items=[ExpressionItem(uri=f"{work.eli_uri}/{e.expression_date.isoformat()}/{e.language}", date=e.expression_date.isoformat(), language=e.language, is_latest=e.is_latest) for e in exprs])
