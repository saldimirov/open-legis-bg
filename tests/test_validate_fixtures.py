# tests/test_validate_fixtures.py
from pathlib import Path
import pytest
from open_legis.validate.fixtures import check_fixtures

_VALID_XML = Path("tests/data/validate_valid.xml").read_text(encoding="utf-8")


def _place(root: Path, act_type: str, year: str, slug: str, date: str, xml: str) -> Path:
    p = root / act_type / year / slug / "expressions" / f"{date}.bul.xml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(xml, encoding="utf-8")
    return p


def test_valid_fixture_no_errors(tmp_path):
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", _VALID_XML)
    result = check_fixtures(tmp_path)
    assert result.stats["checked"] == 1
    assert not any(i.severity == "error" for i in result.issues)


def test_malformed_xml(tmp_path):
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", "not < xml >>")
    result = check_fixtures(tmp_path)
    assert any(i.code == "MALFORMED_XML" for i in result.issues)


def test_empty_body_flagged(tmp_path):
    xml = _VALID_XML.replace(
        "<body>\n      <article eId=\"art_1\">\n        <num>Чл. 1.</num>\n        <content><p>Тест.</p></content>\n      </article>\n    </body>",
        "<body></body>",
    )
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", xml)
    result = check_fixtures(tmp_path)
    assert any(i.code == "EMPTY_BODY" for i in result.issues)


def test_missing_title_warned(tmp_path):
    xml = _VALID_XML.replace(
        '<FRBRalias value="Закон за тест" name="short"/>\n          ',
        "",
    )
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", xml)
    result = check_fixtures(tmp_path)
    assert any(i.code == "MISSING_TITLE" for i in result.issues)


def test_eli_mismatch_warned(tmp_path):
    xml = _VALID_XML.replace(
        'other="/eli/bg/zakon/2024/dv-26-24-1"',
        'other="/eli/bg/zakon/2024/dv-99-24-1"',
    )
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", xml)
    result = check_fixtures(tmp_path)
    assert any(i.code == "ELI_MISMATCH" for i in result.issues)


def test_multiple_files_counted(tmp_path):
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", _VALID_XML)
    xml2 = _VALID_XML.replace("dv-26-24-1", "dv-27-24-1").replace("26-24-1", "27-24-1")
    _place(tmp_path, "zakon", "2024", "dv-27-24-1", "2024-04-02", xml2)
    result = check_fixtures(tmp_path)
    assert result.stats["checked"] == 2
