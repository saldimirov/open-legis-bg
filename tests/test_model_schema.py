import datetime as dt

from sqlalchemy.orm import Session

from open_legis.model import schema as m


def test_work_and_expression_roundtrip(session: Session, engine):
    m.Base.metadata.create_all(engine)
    work = m.Work(
        eli_uri="/eli/bg/zakon/1950/zzd",
        act_type=m.ActType.ZAKON,
        title="Закон за задълженията и договорите",
        title_short="ЗЗД",
        number=None,
        adoption_date=dt.date(1950, 11, 22),
        dv_broy=275,
        dv_year=1950,
        dv_position=1,
        issuing_body="Народно събрание",
        status=m.ActStatus.IN_FORCE,
    )
    session.add(work)
    session.flush()

    expr = m.Expression(
        work_id=work.id,
        expression_date=dt.date(2024, 1, 1),
        language="bul",
        akn_xml="<akomaNtoso/>",
        source_file="fixtures/akn/zakon/1950/zzd/expressions/2024-01-01.bul.xml",
        is_latest=True,
    )
    session.add(expr)
    session.commit()

    refetched = session.query(m.Work).filter_by(eli_uri="/eli/bg/zakon/1950/zzd").one()
    assert refetched.title_short == "ЗЗД"
    assert len(refetched.expressions) == 1
    assert refetched.expressions[0].language == "bul"


def test_element_unique_constraint(session: Session, engine):
    m.Base.metadata.create_all(engine)
    work = m.Work(
        eli_uri="/eli/bg/zakon/2000/test",
        act_type=m.ActType.ZAKON,
        title="Test",
        dv_broy=1,
        dv_year=2000,
        dv_position=1,
        status=m.ActStatus.IN_FORCE,
    )
    session.add(work)
    session.flush()
    expr = m.Expression(
        work_id=work.id,
        expression_date=dt.date(2000, 1, 1),
        language="bul",
        akn_xml="<x/>",
        source_file="x",
        is_latest=True,
    )
    session.add(expr)
    session.flush()
    e1 = m.Element(
        expression_id=expr.id,
        e_id="art_1",
        parent_e_id=None,
        element_type=m.ElementType.ARTICLE,
        num="Чл. 1",
        heading="",
        text="x",
        sequence=0,
    )
    session.add(e1)
    session.commit()

    dup = m.Element(
        expression_id=expr.id,
        e_id="art_1",
        parent_e_id=None,
        element_type=m.ElementType.ARTICLE,
        num="Чл. 1",
        heading="",
        text="y",
        sequence=1,
    )
    session.add(dup)
    from sqlalchemy.exc import IntegrityError

    import pytest

    with pytest.raises(IntegrityError):
        session.commit()
