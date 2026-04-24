from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from open_legis.loader.akn_parser import ParsedAkn, parse_akn_file
from open_legis.loader.validators import validate_parsed
from open_legis.model import schema as m


def load_directory(root: Path, engine: Engine) -> None:
    files = sorted(Path(root).rglob("*.bul.xml"))

    parsed_by_file: list[tuple[Path, ParsedAkn]] = []
    parse_errors = 0
    for f in files:
        try:
            p = parse_akn_file(f)
            validate_parsed(p, source_path=f)
            parsed_by_file.append((f, p))
        except Exception as exc:
            print(f"  SKIP {f}: {exc}", flush=True)
            parse_errors += 1

    if parse_errors:
        print(f"  {parse_errors} file(s) skipped due to parse errors", flush=True)

    total = len(parsed_by_file)
    print(f"Loading {total} fixtures...", flush=True)

    skip_count = 0
    expr_ids: set[int] = set()

    with Session(engine) as session:
        for i, (_, p) in enumerate(parsed_by_file, 1):
            if i % 100 == 0 or i == total:
                print(f"  {i}/{total}", flush=True)
            expr_id = _upsert(session, p)
            if expr_id is None:
                skip_count += 1
            else:
                expr_ids.add(expr_id)

        if skip_count:
            print(f"  {skip_count} fixture(s) skipped (position conflict)", flush=True)

        _recompute_is_latest(session)
        _populate_paths(session, expr_ids)
        session.commit()

    print(f"Loaded {len(expr_ids)} expressions", flush=True)

    relations_dir = Path(root) / "relations"
    if relations_dir.exists():
        from open_legis.loader.relations import load_relations
        load_relations(relations_dir, engine=engine)


def _upsert(session: Session, p: ParsedAkn) -> Optional[int]:
    work = session.scalars(
        select(m.Work).where(m.Work.eli_uri == p.work.eli_uri)
    ).one_or_none()
    if work is None:
        pos_work = session.scalars(
            select(m.Work).where(
                m.Work.dv_broy == p.work.dv_broy,
                m.Work.dv_year == p.work.dv_year,
                m.Work.dv_position == p.work.dv_position,
            )
        ).one_or_none()
        if pos_work is not None and pos_work.act_type.value == p.work.act_type:
            # Same type, different slug — skip to avoid eli_uri/akn_xml mismatch
            print(
                f"  SKIP position conflict: {p.work.eli_uri} vs existing {pos_work.eli_uri}",
                flush=True,
            )
            return None
        elif pos_work is not None:
            # Different type at same DV position — scraper conflict, skip
            print(
                f"  SKIP type conflict at dv={p.work.dv_broy}/{p.work.dv_year} pos={p.work.dv_position}",
                flush=True,
            )
            return None

    issuer = None
    if p.work.issuer:
        try:
            issuer = m.Issuer(p.work.issuer)
        except ValueError:
            pass

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
            issuer=issuer,
            status=m.ActStatus.IN_FORCE,
        )
        session.add(work)
        session.flush()
    else:
        work.title = p.work.title
        work.adoption_date = p.work.adoption_date
        work.issuing_body = p.work.issuing_body
        if issuer is not None:
            work.issuer = issuer

    expr = session.scalars(
        select(m.Expression).where(
            m.Expression.work_id == work.id,
            m.Expression.expression_date == p.expression.expression_date,
            m.Expression.language == p.expression.language,
        )
    ).one_or_none()
    if expr is None:
        expr = m.Expression(
            work_id=work.id,
            expression_date=p.expression.expression_date,
            language=p.expression.language,
            akn_xml=p.expression.akn_xml,
            source_file=p.expression.source_file,
            is_latest=False,
        )
        session.add(expr)
        session.flush()
    else:
        expr.akn_xml = p.expression.akn_xml
        expr.source_file = p.expression.source_file

    session.query(m.Element).filter(m.Element.expression_id == expr.id).delete(
        synchronize_session=False
    )
    session.flush()

    _MAX_TEXT = 200_000  # tsvector limit is ~1 MB; cap each element well below it
    for e in p.elements:
        text = e.text
        if text and len(text) > _MAX_TEXT:
            text = text[:_MAX_TEXT]
        session.add(
            m.Element(
                expression_id=expr.id,
                e_id=e.e_id,
                parent_e_id=e.parent_e_id,
                element_type=m.ElementType(e.element_type),
                num=e.num,
                heading=e.heading,
                text=text,
                sequence=e.sequence,
            )
        )
    session.flush()
    return expr.id


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


def _populate_paths(session: Session, expression_ids: set[int]) -> None:
    from sqlalchemy import text

    if not expression_ids:
        return

    ids = list(expression_ids)

    session.execute(
        text("UPDATE element SET path = NULL WHERE expression_id = ANY(:ids)"),
        {"ids": ids},
    )
    session.flush()

    session.execute(
        text(
            "UPDATE element SET path = text2ltree(regexp_replace(e_id, '[^A-Za-z0-9_]', '_', 'g')) "
            "WHERE parent_e_id IS NULL AND expression_id = ANY(:ids)"
        ),
        {"ids": ids},
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
                  AND child.expression_id = ANY(:ids)
                """
            ),
            {"ids": ids},
        )
        if res.rowcount == 0:
            break
    session.flush()
