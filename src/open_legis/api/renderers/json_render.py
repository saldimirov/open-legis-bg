from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from open_legis.api.schemas import (
    DvRef,
    ElementOut,
    ExpressionOut,
    Links,
    ResourceOut,
    WorkOut,
)
from open_legis.loader.uri import EliUri, build_eli
from open_legis.model import schema as m


def _work_eli(work: m.Work) -> EliUri:
    parts = work.eli_uri.strip("/").split("/")
    return EliUri(act_type=parts[2], year=int(parts[3]), slug=parts[4])


def _work_out(work: m.Work) -> WorkOut:
    return WorkOut(
        uri=work.eli_uri,
        title=work.title,
        title_short=work.title_short,
        type=work.act_type.value,
        dv_ref=DvRef(broy=work.dv_broy, year=work.dv_year, position=work.dv_position),
        external_ids={x.source.value: x.external_value for x in work.external_ids},
    )


def render_work(work: m.Work) -> ResourceOut:
    return ResourceOut(
        uri=work.eli_uri,
        work=_work_out(work),
        expression=None,
        element=None,
        links=Links(self=work.eli_uri, work=work.eli_uri),
    )


def render_expression(expr: m.Expression) -> ResourceOut:
    work = expr.work
    w_eli = _work_eli(work)
    expr_uri = build_eli(EliUri(
        act_type=w_eli.act_type, year=w_eli.year, slug=w_eli.slug,
        expression_date=expr.expression_date, language=expr.language,
    ))
    session = object_session(expr)
    assert session is not None
    elements = session.scalars(
        select(m.Element)
        .where(m.Element.expression_id == expr.id)
        .order_by(m.Element.sequence)
    ).all()
    root_children = _build_children_tree(elements, parent_e_id=None)
    synthetic = ElementOut(e_id="", type="root", children=root_children)

    return ResourceOut(
        uri=expr_uri,
        work=_work_out(work),
        expression=ExpressionOut(
            date=expr.expression_date, lang=expr.language, is_latest=expr.is_latest
        ),
        element=synthetic,
        links=Links(
            self=expr_uri,
            work=work.eli_uri,
            akn_xml=expr_uri + "?format=akn",
            rdf=expr_uri + "?format=ttl",
        ),
    )


def render_element(expr: m.Expression, el: m.Element) -> ResourceOut:
    work = expr.work
    w_eli = _work_eli(work)
    session = object_session(expr)
    assert session is not None
    elements = session.scalars(
        select(m.Element)
        .where(m.Element.expression_id == expr.id)
        .order_by(m.Element.sequence)
    ).all()
    children = _build_children_tree(elements, parent_e_id=el.e_id)
    element_out = ElementOut(
        e_id=el.e_id,
        type=el.element_type.value,
        num=el.num,
        heading=el.heading,
        text=el.text,
        children=children,
    )
    elem_path = el.e_id.replace("__", "/")
    uri = build_eli(EliUri(
        act_type=w_eli.act_type, year=w_eli.year, slug=w_eli.slug,
        expression_date=expr.expression_date, language=expr.language,
        element_path=elem_path,
    ))
    expr_uri = build_eli(EliUri(
        act_type=w_eli.act_type, year=w_eli.year, slug=w_eli.slug,
        expression_date=expr.expression_date, language=expr.language,
    ))
    return ResourceOut(
        uri=uri,
        work=_work_out(work),
        expression=ExpressionOut(
            date=expr.expression_date, lang=expr.language, is_latest=expr.is_latest
        ),
        element=element_out,
        links=Links(
            self=uri,
            work=work.eli_uri,
            expression=expr_uri,
            akn_xml=uri + "?format=akn",
            rdf=uri + "?format=ttl",
        ),
    )


def _build_children_tree(
    elements: list[m.Element], parent_e_id: str | None
) -> list[ElementOut]:
    direct = [e for e in elements if e.parent_e_id == parent_e_id]
    return [
        ElementOut(
            e_id=e.e_id,
            type=e.element_type.value,
            num=e.num,
            heading=e.heading,
            text=e.text,
            children=_build_children_tree(elements, parent_e_id=e.e_id),
        )
        for e in direct
    ]
