import datetime as dt
from pathlib import Path

import yaml
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from open_legis.loader.uri import parse_eli
from open_legis.model import schema as m


def load_relations(root: Path, engine: Engine) -> None:
    with Session(engine) as session:
        session.query(m.Amendment).delete()
        session.query(m.Reference).delete()
        session.flush()

        amends_file = Path(root) / "amendments.yaml"
        if amends_file.exists():
            for entry in (yaml.safe_load(amends_file.read_text()) or {}).get("amendments", []):
                _insert_amendment(session, entry)

        refs_file = Path(root) / "references.yaml"
        if refs_file.exists():
            for entry in (yaml.safe_load(refs_file.read_text()) or {}).get("references", []):
                _insert_reference(session, entry)

        session.commit()


def _lookup_work(session: Session, eli: str) -> m.Work:
    w = session.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if w is None:
        raise ValueError(f"Work not found: {eli!r}")
    return w


def _lookup_expression(session: Session, eli: str) -> m.Expression:
    u = parse_eli(eli)
    w = _lookup_work(session, f"/eli/bg/{u.act_type}/{u.year}/{u.slug}")
    if isinstance(u.expression_date, str) or u.expression_date is None:
        expr = session.scalars(
            select(m.Expression)
            .where(m.Expression.work_id == w.id, m.Expression.is_latest.is_(True))
        ).one_or_none()
    else:
        expr = session.scalars(
            select(m.Expression).where(
                m.Expression.work_id == w.id,
                m.Expression.expression_date == u.expression_date,
                m.Expression.language == (u.language or "bul"),
            )
        ).one_or_none()
    if expr is None:
        raise ValueError(f"Expression not found: {eli!r}")
    return expr


def _insert_amendment(session: Session, entry: dict) -> None:
    amending = _lookup_work(session, entry["amending"])
    target = _lookup_work(session, entry["target"])
    session.add(
        m.Amendment(
            amending_work_id=amending.id,
            target_work_id=target.id,
            target_e_id=entry.get("target_e_id"),
            operation=m.AmendmentOp(entry["operation"]),
            effective_date=dt.date.fromisoformat(str(entry["effective_date"])),
            notes=entry.get("notes"),
        )
    )


def _insert_reference(session: Session, entry: dict) -> None:
    src_expr = _lookup_expression(session, entry["source_eli"])
    target_work = _lookup_work(session, entry["target_eli"])
    session.add(
        m.Reference(
            source_expression_id=src_expr.id,
            source_e_id=entry["source_e_id"],
            raw_text=entry.get("raw_text", ""),
            target_work_id=target_work.id,
            target_e_id=entry.get("target_e_id"),
            resolved=target_work is not None,
            reference_type=m.ReferenceType(entry["type"]),
        )
    )
