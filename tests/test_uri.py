import datetime as dt

import pytest

from open_legis.loader.uri import EliUri, parse_eli, build_eli


def test_parse_work_uri():
    u = parse_eli("/eli/bg/zakon/1950/zzd")
    assert u.act_type == "zakon"
    assert u.year == 1950
    assert u.slug == "zzd"
    assert u.expression_date is None
    assert u.language is None
    assert u.element_path is None


def test_parse_expression_uri():
    u = parse_eli("/eli/bg/zakon/1950/zzd/2024-01-01/bul")
    assert u.expression_date == dt.date(2024, 1, 1)
    assert u.language == "bul"


def test_parse_latest_expression():
    u = parse_eli("/eli/bg/zakon/1950/zzd/latest/bul")
    assert u.expression_date == "latest"
    assert u.language == "bul"


def test_parse_element_uri():
    u = parse_eli("/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45/para_1/point_3")
    assert u.element_path == "art_45/para_1/point_3"
    assert u.e_id() == "art_45__para_1__point_3"


def test_build_round_trip():
    u = EliUri(
        act_type="zakon", year=1950, slug="zzd",
        expression_date=dt.date(2024, 1, 1), language="bul",
        element_path="art_45/para_1",
    )
    assert build_eli(u) == "/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_45/para_1"


@pytest.mark.parametrize("bad", [
    "/eli/bg",
    "/eli/bg/zakon",
    "/eli/xx/zakon/1950/zzd",           # wrong jurisdiction
    "/eli/bg/zakon/nineteen/zzd",        # non-numeric year
    "/eli/bg/zakon/1950/zzd/2024-13-40/bul",  # bad date
    "/eli/bg/zakon/1950/zzd/2024-01-01",      # missing language
])
def test_parse_rejects_bad_uris(bad):
    with pytest.raises(ValueError):
        parse_eli(bad)
