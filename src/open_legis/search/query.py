from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from open_legis.model import schema as m


@dataclass
class SearchHit:
    work_uri: str
    work_title: str
    work_type: str
    expression_date: str
    e_id: str
    num: Optional[str]
    snippet: str
    rank: float


def search(
    session: Session,
    q: str,
    act_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SearchHit], int]:
    if not q.strip():
        raise ValueError("empty query")

    # Use 'simple' config — postgres:16-alpine lacks the 'bulgarian' snowball dictionary
    ts_query = func.plainto_tsquery("simple", q)
    stmt = (
        select(
            m.Work.eli_uri,
            m.Work.title,
            m.Work.act_type,
            m.Expression.expression_date,
            m.Element.e_id,
            m.Element.num,
            func.ts_headline(
                "simple",
                func.coalesce(m.Element.text, ""),
                ts_query,
                "StartSel=«,StopSel=»,MaxWords=30,MinWords=5",
            ).label("snippet"),
            func.ts_rank(text("element.tsv"), ts_query).label("rank"),
        )
        .select_from(m.Element)
        .join(m.Expression, m.Expression.id == m.Element.expression_id)
        .join(m.Work, m.Work.id == m.Expression.work_id)
        .where(m.Expression.is_latest.is_(True))
        .where(text("element.tsv @@ plainto_tsquery('simple', :q)").bindparams(q=q))
    )
    if act_type:
        stmt = stmt.where(m.Work.act_type == m.ActType(act_type))

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.scalar(total_stmt) or 0

    stmt = stmt.order_by(text("rank DESC")).offset(offset).limit(limit)
    rows = session.execute(stmt).all()

    hits = [
        SearchHit(
            work_uri=r.eli_uri,
            work_title=r.title,
            work_type=r.act_type.value,
            expression_date=r.expression_date.isoformat(),
            e_id=r.e_id,
            num=r.num,
            snippet=r.snippet or "",
            rank=float(r.rank or 0.0),
        )
        for r in rows
    ]
    return hits, total
