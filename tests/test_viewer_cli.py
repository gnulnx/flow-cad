import json

from click.testing import CliRunner

from flow_cad.cli import flow
from flow_cad.viewer import cli as viewer_cli
from flow_cad.viewer.cli import _resolve_viewer_ports, _viewer_env


def test_flow_viewer_group_is_not_registered() -> None:
    result = CliRunner().invoke(flow, ["viewer", "--help"])

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_flow_start_help_is_registered() -> None:
    result = CliRunner().invoke(flow, ["start", "--help"])

    assert result.exit_code == 0
    assert "Start the Flow CAD workbench" in result.output
    assert "--backend-port" in result.output
    assert "--port-search-span" in result.output


def test_flow_reload_help_is_registered() -> None:
    result = CliRunner().invoke(flow, ["reload", "--help"])

    assert result.exit_code == 0
    assert "Ask the running Flow CAD workbench" in result.output
    assert "--backend-url" in result.output


def test_flow_reload_posts_to_running_viewer(monkeypatch) -> None:
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            return False

        @staticmethod
        def read() -> bytes:
            return json.dumps({"revision": 7}).encode("utf-8")

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr(viewer_cli.urllib.request, "urlopen", fake_urlopen)

    result = CliRunner().invoke(flow, ["reload", "--backend-url", "http://127.0.0.1:8123"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Reloaded viewer revision 7" in result.output
    assert len(requests) == 1
    request, timeout = requests[0]
    assert timeout == 5
    assert request.full_url == "http://127.0.0.1:8123/api/reload"
    assert request.get_method() == "POST"


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
