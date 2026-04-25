"""Unit tests for DV body text cleaning functions."""
from open_legis.scraper.rtf_parser import _strip_dv_page_headers, _strip_word_metadata, _clean_body


def test_strip_dv_page_header_basic():
    lines = [
        "Текст преди",
        "Държавен вестник",
        "Министерство на вътрешните работи          брой: 17, от дата 13.2.2026 г.   Официален раздел / МИНИСТЕРСТВА И ДРУГИ ВЕДОМСТВА    стр.47",
        "Текст след",
    ]
    assert _strip_dv_page_headers(lines) == ["Текст преди", "Текст след"]


def test_strip_dv_page_header_drops_orphaned_institution_line():
    lines = [
        "Текст преди",
        "Държавен вестник",
        "Президент на Републиката          брой: 36, от дата 17.4.2026 г.   Официален раздел / ПРЕЗИДЕНТ НА РЕПУБЛИКАТА    стр.2",
        "МИНИСТЕРСТВО НА ВЪТРЕШНИТЕ РАБОТИ",
        "Текст след",
    ]
    result = _strip_dv_page_headers(lines)
    assert result == ["Текст преди", "Текст след"]


def test_strip_dv_page_header_multiple():
    lines = [
        "Ред 1",
        "Държавен вестник",
        "Народно събрание          брой: 99, от дата 1.12.2025 г.   Официален раздел / НАРОДНО СЪБРАНИЕ    стр.1",
        "Ред 2",
        "Държавен вестник",
        "Народно събрание          брой: 99, от дата 1.12.2025 г.   Официален раздел / НАРОДНО СЪБРАНИЕ    стр.5",
        "Ред 3",
    ]
    assert _strip_dv_page_headers(lines) == ["Ред 1", "Ред 2", "Ред 3"]


def test_strip_dv_page_header_no_match():
    lines = ["Нормален текст", "Без заглавие на страница"]
    assert _strip_dv_page_headers(lines) == lines


def test_strip_word_metadata_block():
    lines = [
        "Нормален текст преди",
        "800x600",
        "Normal",
        "0",
        "21",
        "false",
        "false",
        "false",
        "BG",
        "X-NONE",
        "X-NONE",
        "MicrosoftInternetExplorer4",
        "Нормален текст след",
    ]
    assert _strip_word_metadata(lines) == ["Нормален текст преди", "Нормален текст след"]


def test_strip_word_metadata_no_match():
    lines = ["Нормален текст", "800 апартамента", "Нещо друго"]
    assert _strip_word_metadata(lines) == lines


def test_clean_body_strips_both():
    lines = [
        "ЗАКОН ЗА НЕЩО",
        "Държавен вестник",
        "НС          брой: 1, от дата 1.1.2026 г.   Официален раздел / НАРОДНО СЪБРАНИЕ    стр.1",
        "800x600",
        "Normal",
        "0",
        "false",
        "BG",
        "X-NONE",
        "X-NONE",
        "MicrosoftInternetExplorer4",
        "Текст на закона",
    ]
    result = _clean_body(lines)
    assert result == ["ЗАКОН ЗА НЕЩО", "Текст на закона"]
