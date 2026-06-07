from click.testing import CliRunner
from auto_hub.cli import main


def test_help_succeeds():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "auto_hub" in result.output


def test_list_shows_no_projects_by_default():
    runner = CliRunner()
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "No projects registered yet" in result.output


def test_show_unknown_project():
    runner = CliRunner()
    result = runner.invoke(main, ["show", "nonexistent"])
    assert result.exit_code == 0
    assert "not found" in result.output
