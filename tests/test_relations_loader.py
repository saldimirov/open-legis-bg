from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.loader.cli import load_directory
from open_legis.loader.relations import load_relations
from open_legis.model import schema as m
from open_legis.model.db import make_engine


def _make_fixture_xml(slug: str, eli: str, year: str, expr_date: str, dv_num: str) -> str:
    src = Path("tests/data/minimal_act.xml").read_text()
    src = src.replace("/eli/bg/zakon/2000/test", eli)
    src = src.replace("/akn/bg/act/2000/test", f"/akn/bg/act/{year}/{slug}")
    # replace all date attributes (works for FRBRWork/FRBRExpression/FRBRManifestation dates)
    src = src.replace('date="2000-01-01"', f'date="{expr_date}"')
    # replace publication number to ensure unique (dv_broy, dv_year, dv_position)
    src = src.replace('number="1" showAs', f'number="{dv_num}" showAs')
    return src


def test_relations_create_amendment_and_reference_rows(pg_url, tmp_path, monkeypatch):
    fixture_defs = [
        ("zzd",     "/eli/bg/zakon/1950/zzd",     "1950", "1950-01-01", "1"),
        ("dv-67-25", "/eli/bg/zakon/2025/dv-67-25", "2025", "2025-01-01", "67"),
    ]
    for slug, eli, year, expr_date, dv_num in fixture_defs:
        dest = tmp_path / "fixtures" / "akn" / "zakon" / year / slug / "expressions"
        dest.mkdir(parents=True)
        xml = _make_fixture_xml(slug, eli, year, expr_date, dv_num)
        (dest / f"{expr_date}.bul.xml").write_text(xml)

    rel_dir = tmp_path / "fixtures" / "akn" / "relations"
    rel_dir.mkdir()
    (rel_dir / "amendments.yaml").write_text(
        "amendments:\n"
        "  - amending: /eli/bg/zakon/2025/dv-67-25\n"
        "    target:   /eli/bg/zakon/1950/zzd\n"
        "    target_e_id: art_1\n"
        "    operation: substitution\n"
        "    effective_date: 2025-08-15\n"
    )
    (rel_dir / "references.yaml").write_text(
        "references:\n"
        "  - source_eli:  /eli/bg/zakon/1950/zzd/1950-01-01/bul\n"
        "    source_e_id: art_1__para_1\n"
        "    target_eli:  /eli/bg/zakon/2025/dv-67-25\n"
        "    target_e_id: art_1\n"
        "    type: cites\n"
    )

    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )

    load_directory(tmp_path / "fixtures" / "akn", engine=eng)
    load_relations(rel_dir, engine=eng)

    with Session(eng) as s:
        amends = s.scalars(select(m.Amendment)).all()
        assert len(amends) == 1
        assert amends[0].operation == m.AmendmentOp.SUBSTITUTION
        refs = s.scalars(select(m.Reference)).all()
        assert len(refs) == 1
        assert refs[0].reference_type == m.ReferenceType.CITES
