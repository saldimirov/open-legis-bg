import datetime as dt

from open_legis.api.schemas import (
    DvRef,
    ElementOut,
    ExpressionOut,
    Links,
    ResourceOut,
    WorkOut,
)


def test_resource_serialises_minimal_work():
    out = ResourceOut(
        uri="/eli/bg/zakon/1950/zzd",
        work=WorkOut(
            uri="/eli/bg/zakon/1950/zzd",
            title="ЗЗД",
            title_short="ЗЗД",
            type="zakon",
            dv_ref=DvRef(broy=275, year=1950),
            external_ids={"lex_bg": "2121934337"},
        ),
        expression=None,
        element=None,
        links=Links(self="/eli/bg/zakon/1950/zzd"),
    )
    d = out.model_dump(mode="json", by_alias=True)
    assert d["work"]["dv_ref"]["broy"] == 275
    assert d["_links"]["self"] == "/eli/bg/zakon/1950/zzd"


def test_expression_and_element_serialisation():
    ex = ExpressionOut(date=dt.date(2024, 1, 1), lang="bul", is_latest=True)
    el = ElementOut(
        e_id="art_1",
        type="article",
        num="Чл. 1",
        heading=None,
        text="...",
        children=[ElementOut(e_id="art_1__para_1", type="paragraph", num="(1)")],
    )
    assert ex.model_dump(mode="json")["date"] == "2024-01-01"
    assert el.model_dump(mode="json")["children"][0]["e_id"] == "art_1__para_1"
