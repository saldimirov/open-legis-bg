from typer.testing import CliRunner

from open_legis.cli import app


def test_cli_has_load_command():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "load" in result.output
    assert "dump" in result.output
    assert "new-fixture" in result.output
