import datetime as dt
from pathlib import Path

from open_legis.loader.scaffold import scaffold_fixture


def test_scaffold_creates_valid_skeleton(tmp_path):
    out = scaffold_fixture(
        root=tmp_path,
        act_type="zakon",
        year=2025,
        slug="demo",
        expression_date=dt.date(2025, 5, 1),
        language="bul",
        title="Demo Закон",
        dv_broy=10,
        dv_year=2025,
    )
    assert out.exists()
    content = out.read_text()
    assert "/eli/bg/zakon/2025/demo" in content
    assert "2025-05-01" in content
    from open_legis.loader.akn_parser import parse_akn_file
    parsed = parse_akn_file(out)
    assert parsed.work.eli_uri == "/eli/bg/zakon/2025/demo"
    assert parsed.expression.language == "bul"
