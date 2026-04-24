"""Server-rendered HTML UI routes."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_legis.api.deps import get_session
from open_legis.model import schema as m
from open_legis.search.query import search as _search

router = APIRouter(include_in_schema=False)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_DV_BASE = "https://dv.parliament.bg/DVWeb"

# idObj lookup for linking to original DV source — loaded once at startup
def _load_dv_id_index() -> dict[tuple[int, int], int]:
    for candidate in [Path(".dv-index.json"), Path(__file__).parents[4] / ".dv-index.json"]:
        if candidate.exists():
            try:
                entries = json.loads(candidate.read_text())
                return {(e["year"], e["broy"]): e["idObj"] for e in entries}
            except Exception:
                pass
    return {}

_DV_ID_BY_ISSUE: dict[tuple[int, int], int] = _load_dv_id_index()

TYPE_LABELS: dict[str, str] = {
    "zakon":         "Закон",
    "zid":           "Изменение / Отмяна",
    "byudjet":       "Бюджетен закон",
    "kodeks":        "Кодекс",
    "naredba":       "Наредба",
    "postanovlenie": "Постановление",
    "pravilnik":     "Правилник",
    "reshenie":      "Решение",
    "ratifikatsiya": "Ратификация",
    "ukaz":          "Указ",
    "instruktsiya":  "Инструкция",
    "tarifa":        "Тарифа",
    "zapoved":       "Заповед",
    "deklaratsiya":  "Декларация",
    "opredelenie":   "Определение",
    "dogovor":       "Договор",
    "saobshtenie":   "Съобщение",
    "konstitutsiya": "Конституция",
}

# Order for filter tabs on the index/browse page
TYPE_FILTER_ORDER: list[tuple[str, str]] = [
    ("", "Всички"),
    ("zakon", "Закони"),
    ("zid", "Изменения и отмяна"),
    ("kodeks", "Кодекси"),
    ("naredba", "Наредби"),
    ("byudjet", "Бюджетни закони"),
    ("ratifikatsiya", "Ратификации"),
    ("postanovlenie", "Постановления"),
    ("pravilnik", "Правилници"),
    ("reshenie", "Решения"),
    ("ukaz", "Укази"),
    ("instruktsiya", "Инструкции"),
    ("tarifa", "Тарифи"),
    ("zapoved", "Заповеди"),
    ("deklaratsiya", "Декларации"),
    ("opredelenie", "Определения"),
    ("dogovor", "Договори"),
    ("saobshtenie", "Съобщения"),
    ("konstitutsiya", "Конституция"),
]

_CATEGORY_DESCS: dict[str, str] = {
    "zakon":         "Основните нормативни актове на Народното събрание",
    "zid":           "Закони за изменение, допълнение или отмяна на съществуващи актове",
    "byudjet":       "Годишни закони за държавния бюджет",
    "kodeks":        "Систематизирани сборници от правни норми",
    "naredba":       "Подзаконови нормативни актове на изпълнителната власт",
    "ratifikatsiya": "Закони за ратифициране на международни договори",
    "postanovlenie": "Постановления на Министерски съвет",
    "pravilnik":     "Правилници за прилагане на закони",
    "reshenie":      "Решения на НС, МС, КС, ВАС и регулаторни органи",
    "ukaz":          "Укази на президента",
    "instruktsiya":  "Инструкции на министерства и ведомства",
    "tarifa":        "Тарифи за държавни такси",
    "zapoved":       "Заповеди на министри и ръководители",
    "deklaratsiya":  "Декларации на НС и МС",
    "opredelenie":   "Определения на съдилища",
    "dogovor":       "Международни договори",
    "saobshtenie":   "Официални съобщения",
    "konstitutsiya": "Конституцията на Република България и международни основни актове",
}

# Order for category cards on the landing page
_CATEGORY_ORDER = [
    "zakon", "zid", "kodeks", "naredba", "byudjet",
    "ratifikatsiya", "postanovlenie", "pravilnik",
    "reshenie", "ukaz", "instruktsiya", "tarifa",
    "zapoved", "deklaratsiya", "opredelenie", "dogovor",
    "saobshtenie", "konstitutsiya",
]

PAGE_SIZE = 20


def _fix_title(title: str) -> str:
    if not title:
        return title
    alpha = [c for c in title if c.isalpha()]
    if not alpha:
        return title
    upper_ratio = sum(1 for c in alpha if c == c.upper()) / len(alpha)
    if upper_ratio > 0.6:
        return title[0].upper() + title[1:].lower()
    return title


templates.env.filters["fix_title"] = _fix_title


def _ctx(**kwargs: Any) -> dict[str, Any]:
    return {"type_labels": TYPE_LABELS, **kwargs}


ISSUER_LABELS: dict[str, str] = {
    "ns":           "Народно събрание",
    "ms":           "Министерски съвет",
    "president":    "Президент",
    "ministry":     "Министерство",
    "commission":   "Регулаторна комисия",
    "agency":       "Агенция",
    "court":        "Съд",
    "ks":           "Конституционен съд",
    "vas":          "ВАС",
    "vss":          "ВСС",
    "bnb":          "БНБ",
    "municipality": "Община",
    "other":        "Друго",
}


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    type: str | None = None,
    issuer: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    s: Session = Depends(get_session),
) -> HTMLResponse:
    if not type and not q and not issuer:
        return _landing_page(request, s)
    return _index_page(request, s, type=type, issuer=issuer, q=q, page=page)


def _landing_page(request: Request, s: Session) -> HTMLResponse:
    total = s.scalar(select(func.count(m.Work.id))) or 0

    # Featured: the real Bulgarian constitution first, then major kodeks (oldest)
    _BKR_URI = "/eli/bg/konstitutsiya/1991/krb"
    bkr = s.scalar(select(m.Work).where(m.Work.eli_uri == _BKR_URI))
    kodeks_works = s.scalars(
        select(m.Work)
        .where(m.Work.act_type == m.ActType.KODEKS)
        .order_by(m.Work.dv_year.asc(), m.Work.dv_broy.asc())
        .limit(7)
    ).all()
    featured = []
    if bkr:
        featured.append({"uri": bkr.eli_uri, "type": bkr.act_type.value, "title": bkr.title})
    featured += [{"uri": w.eli_uri, "type": w.act_type.value, "title": w.title} for w in kodeks_works]

    # Category cards with counts
    counts_rows = s.execute(
        select(m.Work.act_type, func.count(m.Work.id)).group_by(m.Work.act_type)
    ).all()
    counts = {row[0].value: row[1] for row in counts_rows}
    categories = [
        {
            "type": t,
            "label": TYPE_LABELS.get(t, t),
            "count": counts.get(t, 0),
            "desc": _CATEGORY_DESCS.get(t, ""),
        }
        for t in _CATEGORY_ORDER
        if counts.get(t, 0) > 0
    ]

    # Recent: last 10 by DV issue
    recent_works = s.scalars(
        select(m.Work)
        .order_by(m.Work.dv_year.desc(), m.Work.dv_broy.desc(), m.Work.dv_position)
        .limit(10)
    ).all()
    recent = [
        {
            "uri": w.eli_uri,
            "type": w.act_type.value,
            "title": w.title,
            "dv_ref": {"broy": w.dv_broy, "year": w.dv_year},
        }
        for w in recent_works
    ]

    return templates.TemplateResponse(
        request,
        "landing.html",
        _ctx(total=total, featured=featured, categories=categories, recent=recent),
    )


def _index_page(
    request: Request,
    s: Session,
    type: str | None,
    issuer: str | None,
    q: str | None,
    page: int,
) -> HTMLResponse:
    db_q = select(m.Work).order_by(m.Work.dv_year.desc(), m.Work.dv_broy.desc(), m.Work.dv_position)
    if type:
        try:
            db_q = db_q.where(m.Work.act_type == m.ActType(type.lower()))
        except ValueError:
            pass
    if issuer:
        try:
            db_q = db_q.where(m.Work.issuer == m.Issuer(issuer.lower()))
        except ValueError:
            pass
    if q:
        db_q = db_q.where(m.Work.title.ilike(f"%{q}%"))

    total = s.scalar(select(func.count()).select_from(db_q.subquery())) or 0
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    works = s.scalars(db_q.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()

    items = [
        {
            "uri": w.eli_uri,
            "title": w.title,
            "type": w.act_type.value,
            "issuer": w.issuer.value if w.issuer else None,
            "dv_ref": {"broy": w.dv_broy, "year": w.dv_year},
        }
        for w in works
    ]

    # Build issuer counts for the current type filter (for issuer chips)
    issuer_q = select(m.Work.issuer, func.count(m.Work.id)).where(m.Work.issuer.isnot(None)).group_by(m.Work.issuer)
    if type:
        try:
            issuer_q = issuer_q.where(m.Work.act_type == m.ActType(type.lower()))
        except ValueError:
            pass
    issuer_counts = {row[0].value: row[1] for row in s.execute(issuer_q).all()}

    return templates.TemplateResponse(
        request,
        "index.html",
        _ctx(
            works=items,
            total=total,
            page=page,
            total_pages=total_pages,
            current_type=type or "",
            current_issuer=issuer or "",
            q=q or "",
            type_filter_order=TYPE_FILTER_ORDER,
            issuer_labels=ISSUER_LABELS,
            issuer_counts=issuer_counts,
        ),
    )


@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    s: Session = Depends(get_session),
) -> HTMLResponse:
    hits, total = _search(s, q=q, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    items = [
        {
            "work_uri": h.work_uri,
            "work_title": h.work_title,
            "type": h.work_type.lower(),
            "expression_date": h.expression_date,
            "e_id": h.e_id,
            "num": h.num,
            "snippet": h.snippet,
        }
        for h in hits
    ]

    return templates.TemplateResponse(
        request,
        "search.html",
        _ctx(items=items, q=q, total=total, page=page, total_pages=total_pages),
    )


@router.get("/ui/eli/bg/{act_type}/{year}/{slug}", response_class=HTMLResponse)
def work_page(
    request: Request,
    act_type: str,
    year: int,
    slug: str,
    s: Session = Depends(get_session),
) -> HTMLResponse:
    eli = f"/eli/bg/{act_type}/{year}/{slug}"
    work = s.scalars(select(m.Work).where(m.Work.eli_uri == eli)).one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail="Актът не е намерен")

    expr = s.scalars(
        select(m.Expression).where(
            m.Expression.work_id == work.id,
            m.Expression.is_latest.is_(True),
        )
    ).one_or_none()

    elements: list[dict] = []
    preface: list[str] = []
    expression_date = None
    adoption_date = None

    if expr:
        expression_date = expr.expression_date.isoformat()
        if work.adoption_date:
            adoption_date = work.adoption_date.isoformat()

        try:
            from lxml import etree
            NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
            root = etree.fromstring(expr.akn_xml.encode())
            for p in root.findall(f".//{{{NS}}}preface/{{{NS}}}p"):
                if p.text and p.text.strip():
                    preface.append(p.text.strip())
        except Exception:
            pass

        db_elements = s.scalars(
            select(m.Element)
            .where(m.Element.expression_id == expr.id)
            .order_by(m.Element.sequence)
        ).all()
        elements = _build_element_tree(db_elements, parent_e_id=None)

    expr_uri = (
        f"{work.eli_uri}/{expr.expression_date.isoformat()}/{expr.language}"
        if expr else work.eli_uri
    )

    # Amendment timeline — group per-article rows by ZID
    amendment_rows = s.execute(
        select(m.Amendment, m.Work)
        .join(m.Work, m.Amendment.amending_work_id == m.Work.id)
        .where(m.Amendment.target_work_id == work.id)
        .order_by(m.Amendment.effective_date, m.Work.dv_broy)
    ).all()

    # Group by amending ZID (preserve insertion order = chronological)
    _zid_groups: dict = {}
    for amendment, zid_work in amendment_rows:
        key = str(zid_work.id)
        if key not in _zid_groups:
            _zid_groups[key] = {
                "uri": zid_work.eli_uri,
                "title": zid_work.title,
                "dv_broy": zid_work.dv_broy,
                "dv_year": zid_work.dv_year,
                "date": amendment.effective_date.isoformat(),
                "is_omnibus": False,
                "changes": [],
            }
        _zid_groups[key]["changes"].append({
            "e_id": amendment.target_e_id,
            "operation": amendment.operation.value,
            "notes": amendment.notes,
        })

    # Flag omnibus: ZID amends more than one target work
    if _zid_groups:
        omnibus_ids = {
            str(row[0])
            for row in s.execute(
                select(m.Amendment.amending_work_id)
                .where(m.Amendment.amending_work_id.in_(
                    [a.amending_work_id for a, _ in amendment_rows]
                ))
                .group_by(m.Amendment.amending_work_id)
                .having(func.count(func.distinct(m.Amendment.target_work_id)) > 1)
            ).all()
        }
        for key, grp in _zid_groups.items():
            grp["is_omnibus"] = key in omnibus_ids

    amended_by_list = list(_zid_groups.values())

    # Per-article change index: e_id → list of (date, operation, zid_uri)
    article_changes: dict[str, list[dict]] = defaultdict(list)
    for grp in amended_by_list:
        for ch in grp["changes"]:
            if ch["e_id"]:
                article_changes[ch["e_id"]].append({
                    "date": grp["date"],
                    "operation": ch["operation"],
                    "zid_uri": grp["uri"],
                })

    # What this ZID amends (if it's a ZID itself)
    amends_rows = s.execute(
        select(m.Amendment, m.Work)
        .join(m.Work, m.Amendment.target_work_id == m.Work.id)
        .where(m.Amendment.amending_work_id == work.id)
        .order_by(m.Work.title)
    ).all()
    seen_targets: set = set()
    amends_list = []
    for amendment, target_work in amends_rows:
        if target_work.id not in seen_targets:
            seen_targets.add(target_work.id)
            amends_list.append({
                "uri": target_work.eli_uri,
                "title": target_work.title,
            })

    work_data = {
        "uri": work.eli_uri,
        "expr_uri": expr_uri,
        "title": work.title,
        "type": work.act_type.value,
        "dv_ref": {"broy": work.dv_broy, "year": work.dv_year},
        "issuing_body": work.issuing_body,
    }

    return templates.TemplateResponse(
        request,
        "work.html",
        _ctx(
            work=work_data,
            elements=elements,
            preface=preface,
            expression_date=expression_date,
            adoption_date=adoption_date,
            amended_by=amended_by_list,
            amends=amends_list,
            article_changes=dict(article_changes),
        ),
    )


_REVIEW_THRESHOLD = 0.9


@router.get("/ui/admin/amendments/review", response_class=HTMLResponse)
def admin_amendments_review(
    request: Request,
    s: Session = Depends(get_session),
) -> HTMLResponse:
    from open_legis.loader.amendment_matcher import match_all

    all_matches = match_all(s, min_score=0.45)
    existing_keys = set(
        s.execute(
            select(m.Amendment.amending_work_id, m.Amendment.target_work_id)
        ).all()
    )

    review_matches = []
    for r in all_matches:
        if r.score >= _REVIEW_THRESHOLD:
            continue
        if (r.zid.id, r.target.id) not in existing_keys:
            continue
        review_matches.append({
            "amending_id": str(r.zid.id),
            "target_id": str(r.target.id),
            "amending_uri": r.zid.eli_uri,
            "target_uri": r.target.eli_uri,
            "amending_title": r.zid.title,
            "target_title": r.target.title,
            "amending_dv_broy": r.zid.dv_broy,
            "amending_dv_year": r.zid.dv_year,
            "score": r.score,
            "extracted": r.extracted,
        })

    return templates.TemplateResponse(
        request,
        "admin_amendments.html",
        _ctx(matches=review_matches, threshold=_REVIEW_THRESHOLD),
    )


@router.post("/ui/admin/amendments/{amending_id}/{target_id}/delete")
def admin_amendment_delete(
    amending_id: str,
    target_id: str,
    s: Session = Depends(get_session),
) -> Response:
    import uuid
    s.execute(
        m.Amendment.__table__.delete().where(
            m.Amendment.amending_work_id == uuid.UUID(amending_id),
            m.Amendment.target_work_id == uuid.UUID(target_id),
        )
    )
    s.commit()
    return Response(status_code=204)


@router.post("/ui/admin/amendments/{amending_id}/{target_id}/keep")
def admin_amendment_keep(
    amending_id: str,
    target_id: str,
) -> Response:
    return Response(status_code=204)


def _build_element_tree(
    elements: list[m.Element], parent_e_id: str | None, depth: int = 0
) -> list[dict]:
    if depth > 8:
        return []
    direct = [e for e in elements if e.parent_e_id == parent_e_id]
    result = []
    for e in direct:
        children = _build_element_tree(elements, parent_e_id=e.e_id, depth=depth + 1)
        result.append(
            {
                "e_id": e.e_id,
                "type": e.element_type.value,
                "num": e.num,
                "heading": e.heading,
                "text": e.text,
                "children": children,
            }
        )
    return result


@router.get("/dv", response_class=HTMLResponse)
def dv_index(
    request: Request,
    year: int | None = None,
    s: Session = Depends(get_session),
) -> HTMLResponse:
    # All years with issue + act counts
    year_rows = s.execute(
        select(
            m.Work.dv_year,
            func.count(func.distinct(m.Work.dv_broy)).label("issue_count"),
            func.count(m.Work.id).label("act_count"),
        )
        .where(m.Work.dv_year >= 2003)  # corpus start
        .group_by(m.Work.dv_year)
        .order_by(m.Work.dv_year.desc())
    ).all()
    years = [{"year": r[0], "issue_count": r[1], "act_count": r[2]} for r in year_rows]

    issues = []
    if year:
        issue_rows = s.execute(
            select(
                m.Work.dv_broy,
                func.count(m.Work.id).label("act_count"),
            )
            .where(m.Work.dv_year == year)
            .group_by(m.Work.dv_broy)
            .order_by(m.Work.dv_broy.desc())
        ).all()
        issues = [{"broy": r[0], "act_count": r[1], "year": year} for r in issue_rows]

    return templates.TemplateResponse(
        request,
        "dv_index.html",
        _ctx(years=years, issues=issues, current_year=year),
    )


@router.get("/dv/{year}/{broy}", response_class=HTMLResponse)
def dv_issue(
    request: Request,
    year: int,
    broy: int,
    s: Session = Depends(get_session),
) -> HTMLResponse:
    works = s.scalars(
        select(m.Work)
        .where(m.Work.dv_year == year, m.Work.dv_broy == broy)
        .order_by(m.Work.dv_position)
    ).all()
    if not works:
        raise HTTPException(status_code=404, detail="Брой не е намерен")

    items = [
        {
            "uri": w.eli_uri,
            "title": w.title,
            "type": w.act_type.value,
            "position": w.dv_position,
            "issuer": w.issuer.value if w.issuer else None,
            "adoption_date": w.adoption_date.isoformat() if w.adoption_date else None,
        }
        for w in works
    ]

    # Prev/next issues
    prev_issue = s.execute(
        select(m.Work.dv_broy, m.Work.dv_year)
        .where(
            (m.Work.dv_year == year) & (m.Work.dv_broy < broy)
            | (m.Work.dv_year < year)
        )
        .order_by(m.Work.dv_year.desc(), m.Work.dv_broy.desc())
        .limit(1)
    ).first()
    next_issue = s.execute(
        select(m.Work.dv_broy, m.Work.dv_year)
        .where(
            (m.Work.dv_year == year) & (m.Work.dv_broy > broy)
            | (m.Work.dv_year > year)
        )
        .order_by(m.Work.dv_year.asc(), m.Work.dv_broy.asc())
        .limit(1)
    ).first()

    id_obj = _DV_ID_BY_ISSUE.get((year, broy))
    dv_source_url = f"{_DV_BASE}/showMaterialFiles.faces?idObj={id_obj}" if id_obj else None

    return templates.TemplateResponse(
        request,
        "dv_issue.html",
        _ctx(
            year=year,
            broy=broy,
            items=items,
            prev_issue={"year": prev_issue[1], "broy": prev_issue[0]} if prev_issue else None,
            next_issue={"year": next_issue[1], "broy": next_issue[0]} if next_issue else None,
            dv_source_url=dv_source_url,
        ),
    )
