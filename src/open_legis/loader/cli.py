from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from open_legis.loader.akn_parser import ParsedAkn, parse_akn_file
from open_legis.loader.validators import validate_parsed
from open_legis.model import schema as m


def load_directory(root: Path, engine: Engine) -> None:
    files = sorted(Path(root).rglob("*.bul.xml"))
    parsed_by_file = [(f, parse_akn_file(f)) for f in files]
    for f, p in parsed_by_file:
        validate_parsed(p, source_path=f)

    with Session(engine) as session:
        for f, p in parsed_by_file:
            _upsert(session, p)
        _recompute_is_latest(session)
        _populate_paths(session)
        session.commit()


def _upsert(session: Session, p: ParsedAkn) -> None:
    work = session.scalars(
        select(m.Work).where(m.Work.eli_uri == p.work.eli_uri)
    ).one_or_none()
    if work is None:
        work = m.Work(
            eli_uri=p.work.eli_uri,
            act_type=m.ActType(p.work.act_type),
            title=p.work.title,
            dv_broy=p.work.dv_broy,
            dv_year=p.work.dv_year,
            dv_position=p.work.dv_position,
            adoption_date=p.work.adoption_date,
            issuing_body=p.work.issuing_body,
            status=m.ActStatus.IN_FORCE,
        )
        session.add(work)
        session.flush()
    else:
        work.title = p.work.title
        work.adoption_date = p.work.adoption_date
        work.issuing_body = p.work.issuing_body

    expr = session.scalars(
        select(m.Expression).where(
            m.Expression.work_id == work.id,
            m.Expression.expression_date == p.expression.expression_date,
            m.Expression.language == p.expression.language,
        )
    ).one_or_none()
    akn_xml = Path(p.expression.source_file).read_text()
    if expr is None:
        expr = m.Expression(
            work_id=work.id,
            expression_date=p.expression.expression_date,
            language=p.expression.language,
            akn_xml=akn_xml,
            source_file=p.expression.source_file,
            is_latest=False,
        )
        session.add(expr)
        session.flush()
    else:
        expr.akn_xml = akn_xml
        expr.source_file = p.expression.source_file

    session.query(m.Element).filter(m.Element.expression_id == expr.id).delete(
        synchronize_session=False
    )
    session.flush()

    for e in p.elements:
        session.add(
            m.Element(
                expression_id=expr.id,
                e_id=e.e_id,
                parent_e_id=e.parent_e_id,
                element_type=m.ElementType(e.element_type),
                num=e.num,
                heading=e.heading,
                text=e.text,
                sequence=e.sequence,
            )
        )
    session.flush()


def _recompute_is_latest(session: Session) -> None:
    session.execute(
        m.Expression.__table__.update().values(is_latest=False)
    )
    session.flush()
    from sqlalchemy import func

    row_subq = (
        select(
            m.Expression.id,
            func.row_number()
            .over(
                partition_by=(m.Expression.work_id, m.Expression.language),
                order_by=m.Expression.expression_date.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    latest_ids = session.execute(
        select(row_subq.c.id).where(row_subq.c.rn == 1)
    ).scalars().all()
    if latest_ids:
        session.execute(
            m.Expression.__table__.update()
            .where(m.Expression.id.in_(latest_ids))
            .values(is_latest=True)
        )


def _populate_paths(session: Session) -> None:
    from sqlalchemy import text

    session.execute(m.Element.__table__.update().values(path=None))
    session.flush()

    session.execute(
        text(
            "UPDATE element SET path = text2ltree(regexp_replace(e_id, '[^A-Za-z0-9_]', '_', 'g')) "
            "WHERE parent_e_id IS NULL"
        )
    )
    session.flush()

    while True:
        res = session.execute(
            text(
                """
                UPDATE element child
                SET path = parent.path
                  || text2ltree(regexp_replace(child.e_id, '[^A-Za-z0-9_]', '_', 'g'))
                FROM element parent
                WHERE child.parent_e_id = parent.e_id
                  AND child.expression_id = parent.expression_id
                  AND child.path IS NULL
                  AND parent.path IS NOT NULL
                """
            )
        )
        if res.rowcount == 0:
            break
    session.flush()
