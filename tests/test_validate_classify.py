from pathlib import Path
import pytest
from open_legis.validate.classify import check_classification

_AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"

_VALID_XML = Path("tests/data/validate_valid.xml").read_text(encoding="utf-8")


def _place(root: Path, act_type: str, slug: str, title: str) -> Path:
    xml = _VALID_XML.replace(
        'value="Закон за тест" name="short"',
        f'value="{title}" name="short"',
    ).replace(
        'other="/eli/bg/zakon/2024/dv-26-24-1"',
        f'other="/eli/bg/{act_type}/2024/{slug}"',
    )
    p = root / act_type / "2024" / slug / "expressions" / "2024-03-30.bul.xml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(xml, encoding="utf-8")
    return p


def test_correct_type_no_issues(tmp_path):
    _place(tmp_path, "zakon", "dv-26-24-1", "Закон за тест")
    result = check_classification(tmp_path)
    assert not any(i.code == "TYPE_MISMATCH" for i in result.issues)


def test_type_mismatch_detected(tmp_path):
    # File is in zakon/ but title is a Решение
    _place(tmp_path, "zakon", "dv-26-24-1", "Решение за нещо")
    result = check_classification(tmp_path)
    assert any(i.code == "TYPE_MISMATCH" and i.severity == "error" for i in result.issues)


def test_reshenie_wrong_body(tmp_path):
    # File is in reshenie_kevr/ but title has КФН body → should fire RESHENIE_WRONG_BODY
    _place(tmp_path, "reshenie_kevr", "dv-80-16-8",
           "Решение № 689 от 26 септември 2016 г. на КФН")
    result = check_classification(tmp_path)
    assert any(i.code == "RESHENIE_WRONG_BODY" and i.severity == "error" for i in result.issues)


def test_reshenie_correct_body(tmp_path):
    # File is in reshenie_kevr/ and title has КЕВР → no issues
    _place(tmp_path, "reshenie_kevr", "dv-80-16-8",
           "Решение № 689 от 26 септември 2016 г. на КЕВР")
    result = check_classification(tmp_path)
    assert not any(i.code in ("TYPE_MISMATCH", "RESHENIE_WRONG_BODY") for i in result.issues)


def test_undetected_title_warned(tmp_path):
    _place(tmp_path, "zakon", "dv-26-24-1", "Инструкция за нещо непознато")
    result = check_classification(tmp_path)
    assert any(i.code == "UNDETECTED" and i.severity == "warn" for i in result.issues)


def test_reshenie_undetected_body(tmp_path):
    # reshenie_ks directory but no matching body keyword → RESHENIE_UNDETECTED
    _place(tmp_path, "reshenie_ks", "dv-80-16-8",
           "Решение № 3 от 2016 г. на Конституционния съд")
    result = check_classification(tmp_path)
    assert any(i.code == "RESHENIE_UNDETECTED" and i.severity == "warn" for i in result.issues)


def test_postanovlenie_correct(tmp_path):
    _place(tmp_path, "postanovlenie", "dv-68-12-1",
           "Постановление № 193 ОТ 28 АВГУСТ 2012 Г. за определяне")
    result = check_classification(tmp_path)
    assert not any(i.code == "TYPE_MISMATCH" for i in result.issues)
