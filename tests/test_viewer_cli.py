from click.testing import CliRunner

from flow_cad.cli import flow
from flow_cad.viewer import cli as viewer_cli
from flow_cad.viewer.cli import _resolve_viewer_ports, _viewer_env


def test_viewer_cli_start_help_is_registered() -> None:
    result = CliRunner().invoke(flow, ["viewer", "start", "--help"])

    assert result.exit_code == 0
    assert "Start the viewer API" in result.output
    assert "--backend-port" in result.output
    assert "--port-search-span" in result.output


def test_viewer_cli_reload_help_is_registered() -> None:
    result = CliRunner().invoke(flow, ["viewer", "reload", "--help"])

    assert result.exit_code == 0
    assert "Ask the running viewer" in result.output
    assert "--backend-url" in result.output


def test_flow_start_help_includes_dynamic_port_scan() -> None:
    result = CliRunner().invoke(flow, ["start", "--help"])

    assert result.exit_code == 0
    assert "--port-search-span" in result.output


def test_viewer_port_resolution_skips_busy_ports(monkeypatch) -> None:
    busy_ports = {8000, 3000}
    monkeypatch.setattr(viewer_cli, "_port_is_available", lambda _host, port: port not in busy_ports)

    backend_port, frontend_port = _resolve_viewer_ports(
        backend_host="127.0.0.1",
        backend_port=8000,
        frontend_host="127.0.0.1",
        frontend_port=3000,
        search_span=10,
    )

    assert backend_port == 8001
    assert frontend_port == 3001


def test_viewer_port_resolution_keeps_backend_and_frontend_distinct(monkeypatch) -> None:
    monkeypatch.setattr(viewer_cli, "_port_is_available", lambda _host, _port: True)

    backend_port, frontend_port = _resolve_viewer_ports(
        backend_host="127.0.0.1",
        backend_port=8000,
        frontend_host="127.0.0.1",
        frontend_port=8000,
        search_span=10,
    )

    assert backend_port == 8000
    assert frontend_port == 8001


def test_viewer_env_sets_frontend_api_fallback(tmp_path) -> None:
    env = _viewer_env(tmp_path, "http://127.0.0.1:8123")

    assert env["FLOW_CAD_PROJECT_ROOT"] == str(tmp_path.resolve())
    assert env["FLOW_CAD_NO_VITE_OPEN"] == "1"
    assert env["VITE_FLOW_CAD_API"] == "http://127.0.0.1:8123"
