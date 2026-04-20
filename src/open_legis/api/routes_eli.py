import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.api.renderers.json_render import render_element, render_expression, render_work
from open_legis.api.schemas import ResourceOut
from open_legis.loader.uri import EliUri, build_eli
from open_legis.model import schema as m

router = APIRouter(tags=["eli"])


def _parse_year(year_s: str) -> int:
    try:
        return int(year_s)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid year: {year_s!r}") from e


@router.get("/eli/bg/{act_type}/{year}/{slug}", response_model=ResourceOut)
def get_work(act_type: str, year: str, slug: str, s: Session = Depends(get_session)) -> ResourceOut:
    year_int = _parse_year(year)
    eli = build_eli(EliUri(act_type=act_type, year=year_int, slug=slug))
    work = s.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work not found: {eli}")
    return render_work(work)


@router.get("/eli/bg/{act_type}/{year}/{slug}/{date}/{lang}", response_model=ResourceOut)
def get_expression(
    act_type: str, year: str, slug: str, date: str, lang: str,
    s: Session = Depends(get_session),
) -> ResourceOut:
    year_int = _parse_year(year)
    expr = _resolve_expression(s, act_type, year_int, slug, date, lang)
    return render_expression(expr)


@router.get("/eli/bg/{act_type}/{year}/{slug}/{date}/{lang}/{element_path:path}", response_model=ResourceOut)
def get_element(
    act_type: str, year: str, slug: str, date: str, lang: str, element_path: str,
    s: Session = Depends(get_session),
) -> ResourceOut:
    year_int = _parse_year(year)
    expr = _resolve_expression(s, act_type, year_int, slug, date, lang)
    e_id = element_path.replace("/", "__")
    el = s.scalars(
        select(m.Element).where(
            m.Element.expression_id == expr.id, m.Element.e_id == e_id
        )
    ).one_or_none()
    if el is None:
        raise HTTPException(status_code=404, detail=f"Element {e_id} not found")
    return render_element(expr, el)


def _resolve_expression(
    s: Session, act_type: str, year: int, slug: str, date: str, lang: str
) -> m.Expression:
    eli = f"/eli/bg/{act_type}/{year}/{slug}"
    work = s.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work not found: {eli}")
    if date == "latest":
        expr = s.scalars(
            select(m.Expression).where(
                m.Expression.work_id == work.id,
                m.Expression.language == lang,
                m.Expression.is_latest.is_(True),
            )
        ).one_or_none()
    else:
        try:
            expr_date = dt.date.fromisoformat(date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Bad date: {date}") from e
        expr = s.scalars(
            select(m.Expression)
            .where(
                m.Expression.work_id == work.id,
                m.Expression.language == lang,
                m.Expression.expression_date <= expr_date,
            )
            .order_by(m.Expression.expression_date.desc())
            .limit(1)
        ).one_or_none()
    if expr is None:
        raise HTTPException(status_code=404, detail=f"No expression for {eli} @ {date}/{lang}")
    return expr
