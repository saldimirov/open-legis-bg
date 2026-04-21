import datetime as dt

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.api.negotiation import Format, media_type, pick_format
from open_legis.api.rate_limit import limiter
from open_legis.api.renderers.akn_render import render_element_akn, render_expression_akn
from open_legis.api.renderers.json_render import render_element, render_expression, render_work
from open_legis.api.renderers.rdf_render import render_expression_ttl, render_work_ttl
from open_legis.api.errors import ELI_ERRORS
from open_legis.loader.uri import EliUri, build_eli
from open_legis.model import schema as m

router = APIRouter(tags=["eli"])

_ACT_TYPES = "zakon | zid | byudjet | kodeks | ratifikatsiya | naredba | postanovlenie | pravilnik | reshenie_ns | konstitutsiya"
_FORMAT_DESC = "Override content negotiation: `json` (default), `akn` (Akoma Ntoso XML), `ttl` / `turtle` (RDF Turtle)."

_MULTI_FORMAT_RESPONSES = {
    200: {
        "description": "The requested resource. Format depends on content negotiation: JSON (default), Akoma Ntoso XML, or RDF Turtle.",
        "content": {
            "application/json": {"schema": {"type": "object"}},
            "application/akn+xml": {"schema": {"type": "string"}},
            "text/turtle": {"schema": {"type": "string"}},
        },
    },
    **ELI_ERRORS,
}


def _parse_year(year_s: str) -> int:
    try:
        return int(year_s)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid year: {year_s!r}") from e


def _with_cache(response: Response) -> Response:
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@router.get(
    "/eli/bg/{act_type}/{year}/{slug}",
    summary="Get a work",
    description="Returns the abstract legislative act (FRBR *Work*). Supports JSON, Akoma Ntoso XML, and RDF Turtle via content negotiation.",
    responses=_MULTI_FORMAT_RESPONSES,
)
@limiter.limit("300/minute")
def get_work(
    request: Request,
    act_type: str = Path(..., description=f"Act type. One of: {_ACT_TYPES}."),
    year: str = Path(..., description="Publication year, e.g. `2024`."),
    slug: str = Path(..., description="Act slug, e.g. `za-darzhavnia-byudzhet`."),
    accept: str = Header(default="", description="Standard HTTP `Accept` header for content negotiation."),
    format: str | None = Query(None, description=_FORMAT_DESC),
    s: Session = Depends(get_session),
) -> Response:
    year_int = _parse_year(year)
    eli = build_eli(EliUri(act_type=act_type, year=year_int, slug=slug))
    work = s.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work not found: {eli}")
    try:
        fmt = pick_format(accept=accept, override=format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if fmt is Format.JSON:
        return _with_cache(Response(content=render_work(work).model_dump_json(by_alias=True), media_type="application/json"))
    if fmt is Format.TURTLE:
        base = str(request.base_url).rstrip("/")
        return _with_cache(Response(content=render_work_ttl(work, base=base), media_type="text/turtle; charset=utf-8"))
    expr = s.scalars(select(m.Expression).where(m.Expression.work_id == work.id, m.Expression.is_latest.is_(True))).one_or_none()
    if expr is None:
        raise HTTPException(status_code=406, detail="No AKN expression available")
    return _with_cache(Response(content=render_expression_akn(expr), media_type=media_type(fmt)))


@router.get(
    "/eli/bg/{act_type}/{year}/{slug}/{date}/{lang}",
    summary="Get an expression",
    description="Returns a specific dated version (*Expression*) of a legislative act. `date` may be an ISO date or `latest`.",
    responses=_MULTI_FORMAT_RESPONSES,
)
@limiter.limit("300/minute")
def get_expression(
    request: Request,
    act_type: str = Path(..., description=f"Act type. One of: {_ACT_TYPES}."),
    year: str = Path(..., description="Publication year."),
    slug: str = Path(..., description="Act slug."),
    date: str = Path(..., description="ISO date (`YYYY-MM-DD`) or `latest`."),
    lang: str = Path(..., description="BCP-47 language code, e.g. `bul`."),
    accept: str = Header(default="", description="Standard HTTP `Accept` header for content negotiation."),
    format: str | None = Query(None, description=_FORMAT_DESC),
    s: Session = Depends(get_session),
) -> Response:
    year_int = _parse_year(year)
    expr = _resolve_expression(s, act_type, year_int, slug, date, lang)
    try:
        fmt = pick_format(accept=accept, override=format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if fmt is Format.JSON:
        return _with_cache(Response(content=render_expression(expr).model_dump_json(by_alias=True), media_type="application/json"))
    if fmt is Format.TURTLE:
        base = str(request.base_url).rstrip("/")
        return _with_cache(Response(content=render_expression_ttl(expr, base=base), media_type="text/turtle; charset=utf-8"))
    return _with_cache(Response(content=render_expression_akn(expr), media_type=media_type(fmt)))


@router.get(
    "/eli/bg/{act_type}/{year}/{slug}/{date}/{lang}/{element_path:path}",
    summary="Get an element",
    description="Returns a specific structural element (article, paragraph, chapter, §…). `element_path` is a slash-separated AKN eId, e.g. `art_5/para_2`.",
    responses=_MULTI_FORMAT_RESPONSES | {404: {"description": "Work, expression, or element not found."}},
)
@limiter.limit("300/minute")
def get_element(
    request: Request,
    act_type: str = Path(..., description=f"Act type. One of: {_ACT_TYPES}."),
    year: str = Path(..., description="Publication year."),
    slug: str = Path(..., description="Act slug."),
    date: str = Path(..., description="ISO date (`YYYY-MM-DD`) or `latest`."),
    lang: str = Path(..., description="BCP-47 language code, e.g. `bul`."),
    element_path: str = Path(..., description="Slash-separated AKN eId path, e.g. `art_5/para_2`."),
    accept: str = Header(default="", description="Standard HTTP `Accept` header for content negotiation."),
    format: str | None = Query(None, description=_FORMAT_DESC),
    s: Session = Depends(get_session),
) -> Response:
    year_int = _parse_year(year)
    expr = _resolve_expression(s, act_type, year_int, slug, date, lang)
    e_id = element_path.replace("/", "__")
    el = s.scalars(select(m.Element).where(m.Element.expression_id == expr.id, m.Element.e_id == e_id)).one_or_none()
    if el is None:
        raise HTTPException(status_code=404, detail=f"Element {e_id} not found")
    try:
        fmt = pick_format(accept=accept, override=format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if fmt is Format.JSON:
        return _with_cache(Response(content=render_element(expr, el).model_dump_json(by_alias=True), media_type="application/json"))
    if fmt is Format.TURTLE:
        base = str(request.base_url).rstrip("/")
        return _with_cache(Response(content=render_expression_ttl(expr, base=base), media_type="text/turtle; charset=utf-8"))
    return _with_cache(Response(content=render_element_akn(expr, el), media_type=media_type(fmt)))


def _resolve_expression(s: Session, act_type: str, year: int, slug: str, date: str, lang: str) -> m.Expression:
    eli = f"/eli/bg/{act_type}/{year}/{slug}"
    work = s.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work not found: {eli}")
    if date == "latest":
        expr = s.scalars(select(m.Expression).where(m.Expression.work_id == work.id, m.Expression.language == lang, m.Expression.is_latest.is_(True))).one_or_none()
    else:
        try:
            expr_date = dt.date.fromisoformat(date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Bad date: {date}") from e
        expr = s.scalars(
            select(m.Expression)
            .where(m.Expression.work_id == work.id, m.Expression.language == lang, m.Expression.expression_date <= expr_date)
            .order_by(m.Expression.expression_date.desc())
            .limit(1)
        ).one_or_none()
    if expr is None:
        raise HTTPException(status_code=404, detail=f"No expression for {eli} @ {date}/{lang}")
    return expr
