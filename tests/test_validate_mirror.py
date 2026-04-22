import json
from pathlib import Path

from open_legis.validate import Issue, LayerResult
from open_legis.validate.mirror import check_mirror


def _write_index(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries))


def test_issue_creation():
    issue = Issue(severity="error", code="MISSING_FILE", message="not found")
    assert issue.severity == "error"
    assert issue.code == "MISSING_FILE"
    assert issue.path is None


def test_layer_result_error_count():
    result = LayerResult(
        name="mirror",
        issues=[
            Issue("error", "MISSING_FILE", "gone"),
            Issue("warn", "TOO_SMALL", "tiny"),
        ],
        stats={"checked": 2},
    )
    errors = [i for i in result.issues if i.severity == "error"]
    assert len(errors) == 1


def test_mirror_all_present(tmp_path):
    idx = tmp_path / "index.json"
    mirror = tmp_path / "mirror"
    (mirror / "2024").mkdir(parents=True)
    (mirror / "2024" / "001-1234.rtf").write_bytes(b"x" * 2048)
    _write_index(idx, [{"year": 2024, "broy": 1, "idObj": 1234}])

    result = check_mirror(idx, mirror)
    assert result.stats["checked"] == 1
    assert result.stats["missing"] == 0
    assert result.stats["too_small"] == 0
    assert result.issues == []


def test_mirror_missing_file(tmp_path):
    idx = tmp_path / "index.json"
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    _write_index(idx, [{"year": 2024, "broy": 1, "idObj": 1234}])

    result = check_mirror(idx, mirror)
    assert result.stats["missing"] == 1
    assert any(i.code == "MISSING_FILE" and i.severity == "error" for i in result.issues)


def test_mirror_too_small(tmp_path):
    idx = tmp_path / "index.json"
    mirror = tmp_path / "mirror"
    (mirror / "2024").mkdir(parents=True)
    (mirror / "2024" / "001-1234.rtf").write_bytes(b"x" * 100)
    _write_index(idx, [{"year": 2024, "broy": 1, "idObj": 1234}])

    result = check_mirror(idx, mirror)
    assert result.stats["too_small"] == 1
    assert any(i.code == "TOO_SMALL" and i.severity == "warn" for i in result.issues)


def test_mirror_pdf_accepted(tmp_path):
    idx = tmp_path / "index.json"
    mirror = tmp_path / "mirror"
    (mirror / "1995").mkdir(parents=True)
    (mirror / "1995" / "005-9999.pdf").write_bytes(b"x" * 2048)
    _write_index(idx, [{"year": 1995, "broy": 5, "idObj": 9999}])

    result = check_mirror(idx, mirror)
    assert result.stats["missing"] == 0


def test_mirror_multiple_entries(tmp_path):
    idx = tmp_path / "index.json"
    mirror = tmp_path / "mirror"
    (mirror / "2024").mkdir(parents=True)
    (mirror / "2024" / "001-1111.rtf").write_bytes(b"x" * 2048)
    # 002-2222 intentionally missing
    _write_index(idx, [
        {"year": 2024, "broy": 1, "idObj": 1111},
        {"year": 2024, "broy": 2, "idObj": 2222},
    ])

    result = check_mirror(idx, mirror)
    assert result.stats["checked"] == 2
    assert result.stats["missing"] == 1
