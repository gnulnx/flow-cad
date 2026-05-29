from click.testing import CliRunner

from flow_cad.cli import flow


def test_viewer_cli_start_help_is_registered() -> None:
    result = CliRunner().invoke(flow, ["viewer", "start", "--help"])

    assert result.exit_code == 0
    assert "Start the viewer API" in result.output
    assert "--backend-port" in result.output


def test_viewer_cli_reload_help_is_registered() -> None:
    result = CliRunner().invoke(flow, ["viewer", "reload", "--help"])

    assert result.exit_code == 0
    assert "Ask the running viewer" in result.output
    assert "--backend-url" in result.output
