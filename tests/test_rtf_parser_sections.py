"""Unit tests for section/category tracking in _split_acts."""
from open_legis.scraper.rtf_parser import _split_acts


_LONG_BODY = " думи за изпълнение на теста" * 5  # > 80 chars


def test_official_section_tagged():
    lines = [
        "ОФИЦИАЛЕН РАЗДЕЛ",
        "НАРОДНО СЪБРАНИЕ",
        f"ЗАКОН за нещо важно{_LONG_BODY}",
    ]
    results = _split_acts(lines, [])
    assert len(results) == 1
    title, body, section, category = results[0]
    assert section == "official"


def test_unofficial_section_tagged():
    body_text = "Съобщение от съда за дело номер 123" + _LONG_BODY
    lines = [
        "ОФИЦИАЛЕН РАЗДЕЛ",
        f"ЗАКОН за нещо{_LONG_BODY}",
        "НЕОФИЦИАЛЕН РАЗДЕЛ",
        "СЪОБЩЕНИЯ",
        body_text,
        "",
    ]
    results = _split_acts(lines, [])
    official = [r for r in results if r[2] == "official"]
    unofficial = [r for r in results if r[2] == "unofficial"]
    assert len(official) >= 1
    assert len(unofficial) >= 1


def test_unofficial_category_captured():
    body_text = "Покана за участие в търг за доставка на нещо" + _LONG_BODY
    lines = [
        "НЕОФИЦИАЛЕН РАЗДЕЛ",
        "ПОКАНИ",
        body_text,
        "",
    ]
    results = _split_acts(lines, [])
    assert len(results) == 1
    _, _, section, category = results[0]
    assert section == "unofficial"
    assert category is not None
    assert "Покани" in category or "ПОКАНИ" in category


def test_default_section_is_official():
    """Content before any section header defaults to official."""
    lines = [f"ЗАКОН за нещо{_LONG_BODY}"]
    results = _split_acts(lines, [])
    assert all(r[2] == "official" for r in results)


def test_section_switch_mid_document():
    body_text = "Обявление за публична продан" + _LONG_BODY
    lines = [
        "ОФИЦИАЛЕН РАЗДЕЛ",
        f"НАРЕДБА № 1 за нещо{_LONG_BODY}",
        "НЕОФИЦИАЛЕН РАЗДЕЛ",
        "ОБЯВЛЕНИЯ",
        body_text,
        "",
    ]
    results = _split_acts(lines, [])
    sections = {r[2] for r in results}
    assert "official" in sections
    assert "unofficial" in sections
