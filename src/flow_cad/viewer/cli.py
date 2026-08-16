from __future__ import annotations

import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import rich_click as click

from flow_cad.config import load_flow_config


PROJECT_ROOT = Path(__file__).resolve().parents[3]
VIEWER_RUNTIME_FILENAME = "viewer-runtime.json"


def start_viewer(
    *,
    project_root: Path,
    backend_host: str = "127.0.0.1",
    backend_port: int = 8000,
    frontend_host: str = "127.0.0.1",
    frontend_port: int = 3000,
    port_search_span: int = 50,
    open_browser: bool = True,
) -> None:
    viewer_dir = PROJECT_ROOT / "viewer" / "stl-viewer"
    if not (viewer_dir / "node_modules").exists():
        raise click.ClickException("Viewer dependencies are missing. Run: npm --prefix viewer/stl-viewer install")

    backend_port, frontend_port = _resolve_viewer_ports(
        backend_host=backend_host,
        backend_port=backend_port,
        frontend_host=frontend_host,
        frontend_port=frontend_port,
        search_span=port_search_span,
    )
    backend_url = f"http://{backend_host}:{backend_port}"
    frontend_url = f"http://{frontend_host}:{frontend_port}/?api={backend_url}"
    env = _viewer_env(project_root, backend_url)

    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "flow_cad.viewer.app:app",
        "--host",
        backend_host,
        "--port",
        str(backend_port),
        "--no-access-log",
    ]
    frontend_cmd = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        frontend_host,
        "--port",
        str(frontend_port),
        "--strictPort",
    ]

    click.echo(f"Viewer API: {backend_url}")
    click.echo(f"Viewer UI:  {frontend_url}")
    backend_proc = subprocess.Popen(backend_cmd, cwd=project_root, env=env)
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=viewer_dir, env=env)
    _write_viewer_runtime(
        project_root,
        {
            "project_root": str(project_root.resolve()),
            "backend_url": backend_url,
            "frontend_url": frontend_url,
            "backend_pid": backend_proc.pid,
            "frontend_pid": frontend_proc.pid,
            "started_at": time.time(),
        },
    )

    try:
        if open_browser:
            time.sleep(1.5)
            webbrowser.open(frontend_url)
        while True:
            backend_status = backend_proc.poll()
            frontend_status = frontend_proc.poll()
            if backend_status is not None:
                raise click.ClickException(f"Viewer backend exited with status {backend_status}")
            if frontend_status is not None:
                raise click.ClickException(f"Viewer frontend exited with status {frontend_status}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        click.echo("Stopping viewer...")
    finally:
        _terminate_process(frontend_proc)
        _terminate_process(backend_proc)
        _clear_viewer_runtime(project_root, backend_url=backend_url)


def reload_viewer(backend_url: str | None = None, *, project_root: Path | None = None) -> dict[str, object]:
    """Ask the running viewer to refresh registry, export, and source state."""
    resolved_backend_url = _resolve_backend_url(backend_url, project_root=project_root)
    url = resolved_backend_url.rstrip("/") + "/api/reload"
    request = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise click.ClickException(f"Viewer API is not reachable at {resolved_backend_url}. Is `flow start` running?") from exc
    return payload


def refresh_viewer(
    *,
    backend_url: str | None = None,
    project_root: Path | None = None,
    part_id: str | None = None,
    force_model_refetch: bool = False,
) -> dict[str, object]:
    """Reload the project-aware viewer process and return rendered artifact identity."""
    resolved_project_root = (project_root or Path.cwd()).resolve()
    resolved_backend_url = _resolve_backend_url(backend_url, project_root=resolved_project_root)
    health = _get_json(resolved_backend_url.rstrip("/") + "/api/health")
    served_root = Path(str(health.get("project_root") or "")).resolve()
    if served_root != resolved_project_root:
        raise click.ClickException(
            "Viewer API project mismatch: "
            f"{resolved_backend_url} serves {served_root}, expected {resolved_project_root}."
        )
    payload = {
        "part_id": part_id,
        "force_model_refetch": force_model_refetch,
    }
    return _post_json(resolved_backend_url.rstrip("/") + "/api/refresh", payload)


def _viewer_runtime_path(project_root: Path) -> Path:
    return project_root.resolve() / ".flow" / VIEWER_RUNTIME_FILENAME


def _write_viewer_runtime(project_root: Path, payload: dict[str, object]) -> None:
    path = _viewer_runtime_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_viewer_runtime(project_root: Path) -> dict[str, object] | None:
    path = _viewer_runtime_path(project_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _clear_viewer_runtime(project_root: Path, *, backend_url: str) -> None:
    path = _viewer_runtime_path(project_root)
    current = _read_viewer_runtime(project_root)
    if current and current.get("backend_url") != backend_url:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _resolve_backend_url(backend_url: str | None, *, project_root: Path | None = None) -> str:
    if backend_url:
        return backend_url
    root = (project_root or Path.cwd()).resolve()
    runtime = _read_viewer_runtime(root)
    if runtime and isinstance(runtime.get("backend_url"), str) and runtime["backend_url"]:
        return str(runtime["backend_url"])
    return "http://127.0.0.1:8000"


def _get_json(url: str) -> dict[str, object]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise click.ClickException(f"Viewer API is not reachable at {url}. Is `flow start` running?") from exc
    return payload if isinstance(payload, dict) else {}


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise click.ClickException(f"Viewer API is not reachable at {url}. Is `flow start` running?") from exc
    return response_payload if isinstance(response_payload, dict) else {}


def _terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _viewer_env(project_root: Path, backend_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["FLOW_CAD_PROJECT_ROOT"] = str(project_root.resolve())
    env["FLOW_CAD_NO_VITE_OPEN"] = "1"
    env["VITE_FLOW_CAD_API"] = backend_url
    config = load_flow_config(project_root, env=env)
    profile = config.active_agent_profile()
    if (
        "FLOW_CAD_AGENT_RUNTIME" not in env
        and "FLOW_CAD_AGENT_RUNTIME_ENDPOINT" not in env
        and profile.normalized_provider == "fake"
        and shutil.which("codex")
    ):
        env["FLOW_CAD_AGENT_RUNTIME"] = "codex"
        env["FLOW_CAD_AGENT_RUNTIME_AUTODETECTED"] = "codex"
    return env


def _resolve_viewer_ports(
    *,
    backend_host: str,
    backend_port: int,
    frontend_host: str,
    frontend_port: int,
    search_span: int,
) -> tuple[int, int]:
    if search_span < 1:
        raise click.ClickException("--port-search-span must be at least 1")

    used: set[int] = set()
    resolved_backend_port = _find_available_port(backend_host, backend_port, search_span, used=used)
    used.add(resolved_backend_port)
    resolved_frontend_port = _find_available_port(frontend_host, frontend_port, search_span, used=used)
    return resolved_backend_port, resolved_frontend_port


def _find_available_port(host: str, preferred_port: int, search_span: int, *, used: set[int]) -> int:
    for port in range(preferred_port, preferred_port + search_span):
        if port in used:
            continue
        if _port_is_available(host, port):
            return port
    end_port = preferred_port + search_span - 1
    raise click.ClickException(f"No available port found for {host}:{preferred_port}-{end_port}")


def _port_is_available(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
    except OSError:
        return False
    return True
