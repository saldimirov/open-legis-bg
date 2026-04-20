from pathlib import Path

from open_legis.loader.akn_parser import parse_akn_file


def test_parse_minimal_act(tmp_path):
    parsed = parse_akn_file(Path("tests/data/minimal_act.xml"))
    assert parsed.work.eli_uri == "/eli/bg/zakon/2000/test"
    assert parsed.work.title == "Test Act"
    assert parsed.expression.language == "bul"
    assert parsed.expression.expression_date.isoformat() == "2000-01-01"
    assert len(parsed.elements) == 5  # 2 articles + 3 paragraphs
    e_ids = [e.e_id for e in parsed.elements]
    assert "art_1" in e_ids
    assert "art_1__para_1" in e_ids
    assert "art_2__para_1" in e_ids
    para = next(e for e in parsed.elements if e.e_id == "art_1__para_1")
    assert para.parent_e_id == "art_1"
    assert para.element_type == "paragraph"
    assert para.num == "(1)"
    assert "първа алинея" in para.text
