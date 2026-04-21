from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.api.schemas import DvRef, WorkList, WorkListItem
from open_legis.model import schema as m

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
