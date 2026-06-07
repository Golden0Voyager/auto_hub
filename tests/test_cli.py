from click.testing import CliRunner

from auto_hub.cli import main


def test_help_succeeds():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "auto_hub" in result.output


def test_list_shows_projects():
    runner = CliRunner()
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "Registered projects" in result.output
    assert "auto_pdf" in result.output


def test_show_unknown_project():
    runner = CliRunner()
    result = runner.invoke(main, ["show", "nonexistent"])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_show_known_project():
    runner = CliRunner()
    result = runner.invoke(main, ["show", "auto_pdf"])
    assert result.exit_code == 0
    assert "auto_pdf" in result.output
    assert "Type:" in result.output


def test_status_command():
    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "Registered:" in result.output


def test_env_command():
    runner = CliRunner()
    result = runner.invoke(main, ["env", "auto_pdf"])
    assert result.exit_code == 0
    assert "LLM_API_KEY" in result.output
