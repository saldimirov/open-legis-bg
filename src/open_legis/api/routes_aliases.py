from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.model import schema as m

router = APIRouter(tags=["aliases"])


@router.get("/by-dv/{year}/{broy}/{position}")
def by_dv(
    year: int, broy: int, position: int, s: Session = Depends(get_session)
) -> RedirectResponse:
    work = s.scalars(
        select(m.Work).where(
            m.Work.dv_year == year,
            m.Work.dv_broy == broy,
            m.Work.dv_position == position,
        )
    ).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    return RedirectResponse(url=work.eli_uri, status_code=301)


@router.get("/by-external/{source}/{external_id}")
def by_external(
    source: str, external_id: str, s: Session = Depends(get_session)
) -> RedirectResponse:
    try:
        src_enum = m.ExternalSource(source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}") from e
    ext = s.scalars(
        select(m.ExternalId).where(
            m.ExternalId.source == src_enum,
            m.ExternalId.external_value == external_id,
        )
    ).one_or_none()
    if ext is None:
        raise HTTPException(status_code=404, detail="External ID not found")
    return RedirectResponse(url=ext.work.eli_uri, status_code=301)
