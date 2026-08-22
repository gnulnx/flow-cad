from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _subprocess_environment() -> dict[str, str]:
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH")
    source_root = str(REPOSITORY_ROOT / "src")
    environment["PYTHONPATH"] = (
        f"{source_root}{os.pathsep}{existing}" if existing else source_root
    )
    return environment


def test_cli_import_is_lightweight_and_does_not_load_cad_kernel() -> None:
    started = time.perf_counter()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import flow_cad.cli; print('build123d' in sys.modules)",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=_subprocess_environment(),
    )
    elapsed = time.perf_counter() - started

    assert result.stdout.strip() == "False"
    assert elapsed < 1.0


def test_flow_init_stays_below_two_second_hard_gate(tmp_path: Path) -> None:
    project_root = tmp_path / "performance_project"
    project_root.mkdir()

    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "flow_cad.cli", "init"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
        env=_subprocess_environment(),
    )
    elapsed = time.perf_counter() - started

    assert "Initialized Flow CAD project" in result.stdout
    assert elapsed < 2.0
