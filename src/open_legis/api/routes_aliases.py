from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.api.errors import COMMON_ERRORS
from open_legis.model import schema as m

router = APIRouter(tags=["aliases"])


@router.get(
    "/by-dv/{year}/{broy}/{position}",
    summary="Look up by DV reference",
    description="Resolves a State Gazette reference (year + issue number + position) to its ELI URI and returns a `301` redirect.",
    responses={301: {"description": "Redirects to the canonical ELI URI."}, **COMMON_ERRORS},
)
def by_dv(
    year: int = Path(..., description="Publication year, e.g. `2024`."),
    broy: int = Path(..., description="DV issue number (брой), e.g. `98`."),
    position: int = Path(..., description="Position of the act within the issue (1-based)."),
    s: Session = Depends(get_session),
) -> RedirectResponse:
    work = s.scalars(select(m.Work).where(m.Work.dv_year == year, m.Work.dv_broy == broy, m.Work.dv_position == position)).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    return RedirectResponse(url=work.eli_uri, status_code=301)


@router.get(
    "/by-external/{source}/{external_id}",
    summary="Look up by external identifier",
    description="Resolves a known external identifier (e.g. an APIS ID) to its ELI URI and returns a `301` redirect.",
    responses={301: {"description": "Redirects to the canonical ELI URI."}, **COMMON_ERRORS},
)
def by_external(
    source: str = Path(..., description="External source key, e.g. `apis`."),
    external_id: str = Path(..., description="Identifier value in the external system."),
    s: Session = Depends(get_session),
) -> RedirectResponse:
    try:
        src_enum = m.ExternalSource(source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}") from e
    ext = s.scalars(select(m.ExternalId).where(m.ExternalId.source == src_enum, m.ExternalId.external_value == external_id)).one_or_none()
    if ext is None:
        raise HTTPException(status_code=404, detail="External ID not found")
    return RedirectResponse(url=ext.work.eli_uri, status_code=301)
