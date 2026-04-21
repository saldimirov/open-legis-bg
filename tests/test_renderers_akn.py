from lxml import etree

from open_legis.api.renderers.akn_render import render_expression_akn, render_element_akn
from open_legis.model import schema as m


def test_render_expression_akn_roundtrips_xml():
    expr = m.Expression(akn_xml="<akomaNtoso><act/></akomaNtoso>")
    body = render_expression_akn(expr)
    assert body.startswith(b"<")
    root = etree.fromstring(body)
    assert etree.QName(root.tag).localname == "akomaNtoso"


def test_render_element_akn_returns_subtree():
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">'
        "<act><body>"
        '<article eId="art_1"><num>\u0427\u043b. 1</num></article>'
        '<article eId="art_2"><num>\u0427\u043b. 2</num></article>'
        "</body></act></akomaNtoso>"
    ).encode("utf-8")
    expr = m.Expression(akn_xml=xml.decode("utf-8"))
    el = m.Element(
        e_id="art_1", element_type=m.ElementType.ARTICLE, num="Чл. 1", text=None, sequence=0
    )
    body = render_element_akn(expr, el)
    root = etree.fromstring(body)
    assert root.get("eId") == "art_1"
