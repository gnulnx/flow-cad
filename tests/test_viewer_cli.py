import json

from click.testing import CliRunner

from flow_cad.cli import flow
from flow_cad.viewer import cli as viewer_cli
from flow_cad.viewer.cli import _resolve_viewer_ports, _viewer_env, _write_viewer_runtime


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


def test_flow_reload_uses_project_runtime_backend(tmp_path, monkeypatch) -> None:
    requests = []
    _write_viewer_runtime(tmp_path, {"backend_url": "http://127.0.0.1:8124"})

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            return False

        @staticmethod
        def read() -> bytes:
            return json.dumps({"revision": 8}).encode("utf-8")

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr(viewer_cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(flow, ["reload"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Reloaded viewer revision 8" in result.output
    assert requests[0][0].full_url == "http://127.0.0.1:8124/api/reload"


def test_flow_refresh_verifies_project_root_and_reports_artifact(tmp_path, monkeypatch) -> None:
    _write_viewer_runtime(tmp_path, {"backend_url": "http://127.0.0.1:8125"})
    calls = []

    class Response:
        def __init__(self, payload: dict[str, object]):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            return False

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if request.full_url == "http://127.0.0.1:8125/api/health":
            return Response({"ok": True, "project_root": str(tmp_path), "revision": 1})
        assert request.full_url == "http://127.0.0.1:8125/api/refresh"
        assert json.loads(request.data.decode("utf-8")) == {
            "part_id": "rear_panel",
            "force_model_refetch": True,
        }
        return Response(
            {
                "ok": True,
                "revision": 2,
                "rendered_artifacts": [
                    {
                        "id": "rear_panel",
                        "artifact_path": "exports/step/rear_panel.step",
                        "artifact_size": 123,
                        "artifact_hash": "abcdef1234567890",
                        "model_url": "/api/parts/rear_panel/model?v=abcdef1234567890",
                    }
                ],
            }
        )

    monkeypatch.setattr(viewer_cli.urllib.request, "urlopen", fake_urlopen)

    result = CliRunner().invoke(
        flow,
        ["refresh", "--project-root", str(tmp_path), "--part", "rear_panel", "--force-model-refetch"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Refreshed viewer revision 2" in result.output
    assert "artifact rear_panel: exports/step/rear_panel.step size=123 hash=abcdef1234567890" in result.output
    assert [call[0].full_url for call in calls] == [
        "http://127.0.0.1:8125/api/health",
        "http://127.0.0.1:8125/api/refresh",
    ]


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


def test_viewer_env_sets_frontend_api_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_CAD_AGENT_RUNTIME", "fake")
    env = _viewer_env(tmp_path, "http://127.0.0.1:8123")

    assert env["FLOW_CAD_PROJECT_ROOT"] == str(tmp_path.resolve())
    assert env["FLOW_CAD_NO_VITE_OPEN"] == "1"
    assert env["VITE_FLOW_CAD_API"] == "http://127.0.0.1:8123"


def test_viewer_env_autoselects_codex_when_available(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FLOW_CAD_AGENT_RUNTIME", raising=False)
    monkeypatch.delenv("FLOW_CAD_AGENT_RUNTIME_ENDPOINT", raising=False)
    monkeypatch.setattr(viewer_cli.shutil, "which", lambda command: "/usr/bin/codex" if command == "codex" else None)

    env = _viewer_env(tmp_path, "http://127.0.0.1:8123")

    assert env["FLOW_CAD_AGENT_RUNTIME"] == "codex"
    assert env["FLOW_CAD_AGENT_RUNTIME_AUTODETECTED"] == "codex"


def test_viewer_env_respects_explicit_agent_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_CAD_AGENT_RUNTIME", "fake")
    monkeypatch.delenv("FLOW_CAD_AGENT_RUNTIME_ENDPOINT", raising=False)
    monkeypatch.setattr(viewer_cli.shutil, "which", lambda _command: "/usr/bin/codex")

    env = _viewer_env(tmp_path, "http://127.0.0.1:8123")

    assert env["FLOW_CAD_AGENT_RUNTIME"] == "fake"
    assert "FLOW_CAD_AGENT_RUNTIME_AUTODETECTED" not in env


def test_viewer_env_respects_project_agent_config(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("FLOW_CAD_AGENT_RUNTIME", raising=False)
    monkeypatch.delenv("FLOW_CAD_AGENT_RUNTIME_ENDPOINT", raising=False)
    monkeypatch.setattr(viewer_cli.shutil, "which", lambda _command: "/usr/bin/codex")
    config_path = tmp_path / ".flow" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """
[agent]
default_profile = "local-fast"

[agent.profiles.local-fast]
provider = "llama-cpp"
endpoint = "http://127.0.0.1:1234/v1"
model = "local-test"
""",
        encoding="utf-8",
    )

    env = _viewer_env(tmp_path, "http://127.0.0.1:8123")

    assert "FLOW_CAD_AGENT_RUNTIME" not in env
    assert "FLOW_CAD_AGENT_RUNTIME_AUTODETECTED" not in env
