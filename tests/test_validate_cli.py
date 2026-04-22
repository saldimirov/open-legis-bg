import json
from pathlib import Path

from typer.testing import CliRunner

from open_legis.cli import app

runner = CliRunner()

_VALID_XML = Path("tests/data/validate_valid.xml").read_text(encoding="utf-8")
_VALID_INDEX = json.dumps([{"year": 2024, "broy": 26, "idObj": 9999}])


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create minimal valid mirror + fixture tree."""
    mirror = tmp_path / "mirror"
    (mirror / "2024").mkdir(parents=True)
    (mirror / "2024" / "026-9999.rtf").write_bytes(b"x" * 2048)

    idx = tmp_path / ".dv-index.json"
    idx.write_text(_VALID_INDEX)

    fixtures = tmp_path / "akn"
    p = fixtures / "zakon" / "2024" / "dv-26-24-1" / "expressions" / "2024-03-30.bul.xml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_VALID_XML)

    return fixtures, mirror, idx


def test_validate_mirror_layer_only(tmp_path):
    fixtures, mirror, idx = _setup(tmp_path)
    result = runner.invoke(app, [
        "validate",
        "--fixtures", str(fixtures),
        "--mirror", str(mirror),
        "--index-file", str(idx),
        "--layer", "mirror",
    ])
    assert result.exit_code == 0
    assert "MIRROR" in result.output.upper()


def test_validate_fixtures_layer_only(tmp_path):
    fixtures, mirror, idx = _setup(tmp_path)
    result = runner.invoke(app, [
        "validate",
        "--fixtures", str(fixtures),
        "--mirror", str(mirror),
        "--index-file", str(idx),
        "--layer", "fixtures",
    ])
    assert result.exit_code == 0
    assert "FIXTURES" in result.output.upper()


def test_validate_json_output(tmp_path):
    fixtures, mirror, idx = _setup(tmp_path)
    out_json = tmp_path / "report.json"
    runner.invoke(app, [
        "validate",
        "--fixtures", str(fixtures),
        "--mirror", str(mirror),
        "--index-file", str(idx),
        "--layer", "mirror",
        "--json", str(out_json),
    ])
    assert out_json.exists()
    data = json.loads(out_json.read_text())
    assert "layers" in data
    assert data["layers"][0]["name"] == "mirror"


def test_validate_exits_1_on_error(tmp_path):
    """Missing mirror file should cause exit code 1."""
    fixtures, mirror, idx = _setup(tmp_path)
    idx.write_text(json.dumps([
        {"year": 2024, "broy": 26, "idObj": 9999},
        {"year": 2024, "broy": 99, "idObj": 8888},  # missing
    ]))
    result = runner.invoke(app, [
        "validate",
        "--fixtures", str(fixtures),
        "--mirror", str(mirror),
        "--index-file", str(idx),
        "--layer", "mirror",
    ])
    assert result.exit_code == 1
