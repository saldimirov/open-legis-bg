from pathlib import Path
from open_legis.validate.eli import check_eli

_VALID_XML = Path("tests/data/validate_valid.xml").read_text(encoding="utf-8")


def _place(root: Path, act_type: str, year: str, slug: str, date: str, xml: str) -> None:
    p = root / act_type / year / slug / "expressions" / f"{date}.bul.xml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(xml, encoding="utf-8")


def test_standard_slug_counted(tmp_path):
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", _VALID_XML)
    result = check_eli(tmp_path)
    assert result.stats["standard"] == 1
    assert result.stats["nonstandard"] == 0


def test_nonstandard_slug_flagged(tmp_path):
    xml = _VALID_XML.replace("dv-26-24-1", "custom-slug")
    _place(tmp_path, "zakon", "2024", "custom-slug", "2024-03-30", xml)
    result = check_eli(tmp_path)
    assert result.stats["nonstandard"] == 1
    assert any(i.code == "NONSTANDARD_SLUG" and i.severity == "info" for i in result.issues)


def test_postanovlenie_number_detected(tmp_path):
    xml = _VALID_XML.replace(
        'value="Закон за тест" name="short"',
        'value="Постановление № 193 ОТ 28 АВГУСТ 2012 Г." name="short"',
    ).replace("zakon", "postanovlenie").replace("dv-26-24-1", "dv-68-12-1")
    _place(tmp_path, "postanovlenie", "2024", "dv-68-12-1", "2024-03-30", xml)
    result = check_eli(tmp_path)
    assert result.stats.get("postanovlenie_with_number", 0) == 1


def test_recommendation_always_present(tmp_path):
    _place(tmp_path, "zakon", "2024", "dv-26-24-1", "2024-03-30", _VALID_XML)
    result = check_eli(tmp_path)
    assert any(i.code == "ELI_RECOMMENDATION" for i in result.issues)
    assert all(i.severity == "info" for i in result.issues)
