from rdflib import DCTERMS, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from open_legis.model import schema as m

ELI = Namespace("http://data.europa.eu/eli/ontology#")


def render_work_ttl(work: m.Work, base: str = "") -> str:
    g = _graph_with_prefixes()
    work_iri = URIRef(f"{base}{work.eli_uri}")

    g.add((work_iri, RDF.type, ELI.LegalResource))
    g.add((work_iri, ELI.id_local, Literal(work.eli_uri)))
    g.add((work_iri, ELI.type_document, Literal(work.act_type.value)))
    g.add((work_iri, DCTERMS.title, Literal(work.title, lang="bg")))
    if work.title_short:
        g.add((work_iri, ELI.title_short, Literal(work.title_short, lang="bg")))
    if work.adoption_date:
        g.add((work_iri, ELI.date_document, Literal(work.adoption_date, datatype=XSD.date)))
    g.add((work_iri, ELI.id_local, Literal(f"ДВ бр. {work.dv_broy}/{work.dv_year}")))
    if work.issuing_body:
        g.add((work_iri, ELI.passed_by, Literal(work.issuing_body, lang="bg")))
    g.add((work_iri, ELI.in_force, Literal(work.status == m.ActStatus.IN_FORCE)))
    return g.serialize(format="turtle")


def render_expression_ttl(expr: m.Expression, base: str = "") -> str:
    g = _graph_with_prefixes()
    work = expr.work
    work_iri = URIRef(f"{base}{work.eli_uri}")
    expr_iri = URIRef(
        f"{base}{work.eli_uri}/{expr.expression_date.isoformat()}/{expr.language}"
    )

    g.add((work_iri, RDF.type, ELI.LegalResource))
    g.add((work_iri, ELI.is_realized_by, expr_iri))

    g.add((expr_iri, RDF.type, ELI.LegalExpression))
    g.add((expr_iri, ELI.realizes, work_iri))
    g.add((expr_iri, ELI.language, Literal(expr.language)))
    g.add(
        (expr_iri, ELI.version_date, Literal(expr.expression_date, datatype=XSD.date))
    )
    g.add((expr_iri, DCTERMS.title, Literal(work.title, lang="bg")))
    return g.serialize(format="turtle")


def _graph_with_prefixes() -> Graph:
    g = Graph()
    g.bind("eli", ELI)
    g.bind("dcterms", DCTERMS)
    return g
