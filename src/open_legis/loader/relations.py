import datetime as dt
import logging
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from open_legis.loader.uri import parse_eli
from open_legis.model import schema as m

log = logging.getLogger(__name__)


def load_relations(root: Path, engine: Engine) -> None:
    with Session(engine) as session:
        session.query(m.Amendment).delete()
        session.query(m.Reference).delete()
        session.flush()

        amends_file = Path(root) / "amendments.yaml"
        if amends_file.exists():
            for entry in (yaml.safe_load(amends_file.read_text()) or {}).get("amendments", []):
                try:
                    _insert_amendment(session, entry)
                except Exception as exc:
                    log.warning("amendment skipped %s: %s", entry, exc)

        refs_file = Path(root) / "references.yaml"
        if refs_file.exists():
            for entry in (yaml.safe_load(refs_file.read_text()) or {}).get("references", []):
                try:
                    _insert_reference(session, entry)
                except Exception as exc:
                    log.warning("reference skipped %s: %s", entry, exc)

        session.commit()


def _lookup_work(session: Session, eli: str) -> Optional[m.Work]:
    return session.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()


def _lookup_expression(session: Session, eli: str) -> Optional[m.Expression]:
    u = parse_eli(eli)
    w = _lookup_work(session, f"/eli/bg/{u.act_type}/{u.year}/{u.slug}")
    if w is None:
        return None
    if isinstance(u.expression_date, str) or u.expression_date is None:
        return session.scalars(
            select(m.Expression)
            .where(m.Expression.work_id == w.id, m.Expression.is_latest.is_(True))
        ).one_or_none()
    return session.scalars(
        select(m.Expression).where(
            m.Expression.work_id == w.id,
            m.Expression.expression_date == u.expression_date,
            m.Expression.language == (u.language or "bul"),
        )
    ).one_or_none()


def _insert_amendment(session: Session, entry: dict) -> None:
    amending = _lookup_work(session, entry["amending"])
    target = _lookup_work(session, entry["target"])
    if amending is None or target is None:
        missing = entry["amending"] if amending is None else entry["target"]
        raise ValueError(f"Work not found: {missing!r}")
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
    if src_expr is None:
        raise ValueError(f"Expression not found: {entry['source_eli']!r}")
    target_work = _lookup_work(session, entry["target_eli"])
    session.add(
        m.Reference(
            source_expression_id=src_expr.id,
            source_e_id=entry["source_e_id"],
            raw_text=entry.get("raw_text", ""),
            target_work_id=target_work.id if target_work is not None else None,
            target_e_id=entry.get("target_e_id"),
            resolved=target_work is not None,
            reference_type=m.ReferenceType(entry["type"]),
        )
    )
