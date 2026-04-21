import datetime as dt

from rdflib import Graph

from open_legis.api.renderers.rdf_render import render_work_ttl, render_expression_ttl
from open_legis.model import schema as m


def _work_fixture() -> m.Work:
    return m.Work(
        eli_uri="/eli/bg/zakon/2000/test",
        act_type=m.ActType.ZAKON,
        title="Test",
        title_short="T",
        dv_broy=1,
        dv_year=2000,
        dv_position=1,
        adoption_date=dt.date(2000, 1, 1),
        issuing_body="Народно събрание",
        status=m.ActStatus.IN_FORCE,
    )


def test_render_work_ttl_parses_and_has_eli_properties():
    ttl = render_work_ttl(_work_fixture(), base="https://data.open-legis.bg")
    g = Graph().parse(data=ttl, format="turtle")
    assert len(g) > 0
    assert "http://data.europa.eu/eli/ontology#" in ttl
    assert "/eli/bg/zakon/2000/test" in ttl


def test_render_expression_ttl_links_to_work():
    work = _work_fixture()
    expr = m.Expression(
        expression_date=dt.date(2000, 1, 1),
        language="bul",
        akn_xml="<x/>",
        source_file="x",
        is_latest=True,
    )
    expr.work = work
    ttl = render_expression_ttl(expr, base="https://data.open-legis.bg")
    g = Graph().parse(data=ttl, format="turtle")
    assert any("is_realized_by" in str(p) or "realized_by" in str(p) for _, p, _ in g)
