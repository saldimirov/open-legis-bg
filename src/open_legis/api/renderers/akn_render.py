from lxml import etree

from open_legis.model import schema as m

NS = {"akn": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}


def render_expression_akn(expr: m.Expression) -> bytes:
    return expr.akn_xml.encode("utf-8")


def render_element_akn(expr: m.Expression, el: m.Element) -> bytes:
    root = etree.fromstring(expr.akn_xml.encode("utf-8"))
    found = root.xpath(f"//*[@eId='{el.e_id}']", namespaces=NS)
    if not found:
        raise ValueError(f"eId {el.e_id!r} not found in stored AKN")
    return etree.tostring(found[0], xml_declaration=False, encoding="utf-8")
