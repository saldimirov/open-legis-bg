"""Tests for batch scraper: unofficial JSON fixture emission."""
import json
from unittest.mock import patch

from open_legis.scraper.batch import process_issue_local


_LONG_BODY = " думи за пълнеж" * 8  # > 80 chars


def _make_fake_materials():
    return [
        ("Закон за нещо важно" + _LONG_BODY, "Текст на закона" + _LONG_BODY, "official", None),
        ("Съобщение от съда за дело 123" + _LONG_BODY, "Подробности за делото" + _LONG_BODY, "unofficial", "Съобщения"),
    ]


def test_process_issue_local_emits_unofficial_json(tmp_path):
    out_root = tmp_path / "fixtures"
    local_rtf = tmp_path / "dv-36-26.rtf"
    local_rtf.write_bytes(b"fake rtf")

    with patch("open_legis.scraper.batch.parse_local_issue", return_value=_make_fake_materials()):
        with patch("open_legis.scraper.batch.convert_material") as mock_convert:
            mock_convert.return_value = ("dv-36-26-1", "<xml/>")
            process_issue_local(
                issue_tuple=(1, 36, 2026, "2026-04-17"),
                local_path_str=str(local_rtf),
                allowed_types={"zakon", "zid", "kodeks", "naredba", "postanovlenie",
                               "pravilnik", "reshenie", "ukaz", "ratifikatsiya",
                               "byudjet", "konstitutsiya"},
                out_root_str=str(out_root),
                resume=False,
            )

    json_files = list((out_root / "dv-unofficial" / "2026").glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    assert data["section"] == "unofficial"
    assert data["category"] == "Съобщения"
    assert data["dv_year"] == 2026
    assert data["dv_broy"] == 36


def test_process_issue_local_no_unofficial_json_when_all_official(tmp_path):
    out_root = tmp_path / "fixtures"
    local_rtf = tmp_path / "dv-36-26.rtf"
    local_rtf.write_bytes(b"fake rtf")

    official_only = [
        ("Закон за нещо" + _LONG_BODY, "Текст" + _LONG_BODY, "official", None),
    ]
    with patch("open_legis.scraper.batch.parse_local_issue", return_value=official_only):
        with patch("open_legis.scraper.batch.convert_material") as mock_convert:
            mock_convert.return_value = ("dv-36-26-1", "<xml/>")
            process_issue_local(
                issue_tuple=(1, 36, 2026, "2026-04-17"),
                local_path_str=str(local_rtf),
                allowed_types={"zakon"},
                out_root_str=str(out_root),
                resume=False,
            )

    unofficial_dir = out_root / "dv-unofficial"
    assert not unofficial_dir.exists() or not list(unofficial_dir.rglob("*.json"))
