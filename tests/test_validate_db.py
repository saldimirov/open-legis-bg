from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine
from open_legis.validate.db import check_db, _title_similarity


@pytest.fixture
def loaded_db(pg_url, tmp_path):
    """Fresh DB loaded with the minimal test fixture."""
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
    dest = tmp_path / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    (dest / "2000-01-01.bul.xml").write_text(
        Path("tests/data/minimal_act.xml").read_text()
    )
    load_directory(tmp_path / "akn", engine=eng)
    return eng, tmp_path / "akn"


def test_loaded_work_no_errors(loaded_db):
    eng, fixtures_root = loaded_db
    with Session(eng) as session:
        result = check_db(fixtures_root, session)
    assert not any(i.code == "TYPE_NOT_IN_DB" for i in result.issues)
    assert not any(i.code == "FIXTURE_NOT_LOADED" for i in result.issues)


def test_type_not_in_db_detected(loaded_db):
    eng, fixtures_root = loaded_db
    # Add a reshenie_kevr fixture that is NOT loaded into DB (not a valid ActType)
    extra = fixtures_root / "reshenie_kevr" / "2016" / "dv-80-16-8" / "expressions"
    extra.mkdir(parents=True)
    (extra / "2016-10-11.bul.xml").write_text(
        Path("tests/data/validate_valid.xml").read_text()
        .replace("zakon", "reshenie_kevr")
        .replace("dv-26-24-1", "dv-80-16-8")
        .replace("2024", "2016")
        .replace("2024-03-30", "2016-10-11")
    )
    with Session(eng) as session:
        result = check_db(fixtures_root, session)
    assert any(i.code == "TYPE_NOT_IN_DB" and "reshenie_kevr" in i.message for i in result.issues)


def test_zero_elements_flagged(loaded_db):
    eng, fixtures_root = loaded_db
    with Session(eng) as session:
        session.execute(text("DELETE FROM element"))
        session.commit()
    with Session(eng) as session:
        result = check_db(fixtures_root, session)
    assert any(i.code == "ZERO_ELEMENTS" for i in result.issues)


def test_title_similarity_same():
    assert _title_similarity("Закон за тест", "Закон за тест") == 1.0


def test_title_similarity_different():
    assert _title_similarity("Закон за тест", "Постановление за нещо") < 0.4


def test_probable_fragment_detected(loaded_db):
    """Two works in the same issue with near-identical titles should be flagged."""
    eng, fixtures_root = loaded_db
    with Session(eng) as session:
        # The loaded minimal_act.xml has dv_broy=1, dv_year=2000, dv_position=1, title="Test Act"
        # Insert a second work in the same DV issue with a very similar title
        session.execute(text("""
            INSERT INTO work (id, eli_uri, act_type, title, dv_broy, dv_year, dv_position, status)
            VALUES (
                gen_random_uuid(),
                '/eli/bg/zakon/2000/test-fragment',
                'ZAKON'::act_type,
                'Test Act (continued)',
                1, 2000, 2,
                'IN_FORCE'::act_status
            )
        """))
        session.commit()
    with Session(eng) as session:
        result = check_db(fixtures_root, session)
    assert any(i.code == "PROBABLE_FRAGMENT" for i in result.issues)


def test_issue_overcount_flagged(loaded_db):
    """More than threshold zakoni in a single issue should warn."""
    eng, fixtures_root = loaded_db
    with Session(eng) as session:
        for pos in range(2, 8):  # add 6 more, total=7, threshold=3
            session.execute(text(f"""
                INSERT INTO work (id, eli_uri, act_type, title, dv_broy, dv_year, dv_position, status)
                VALUES (
                    gen_random_uuid(),
                    '/eli/bg/zakon/2000/extra-{pos}',
                    'ZAKON'::act_type,
                    'Completely Different Law {pos}',
                    1, 2000, {pos},
                    'IN_FORCE'::act_status
                )
            """))
        session.commit()
    with Session(eng) as session:
        result = check_db(fixtures_root, session)
    assert any(i.code == "ISSUE_OVERCOUNT" for i in result.issues)
