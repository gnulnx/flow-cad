from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import rich_click as click


PROJECT_ROOT = Path(__file__).resolve().parents[3]


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


def reload_viewer(backend_url: str = "http://127.0.0.1:8000") -> dict[str, object]:
    """Ask the running viewer to refresh registry, export, and source state."""
    url = backend_url.rstrip("/") + "/api/reload"
    request = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise click.ClickException(f"Viewer API is not reachable at {backend_url}. Is `flow start` running?") from exc
    return payload


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
