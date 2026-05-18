"""Portable path and external-tool discovery helpers."""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ToolConfig:
    project_root: Path
    text_to_cad_root: Path
    text_to_cad_python: Path
    freecad_cmd: Path | None


def expand_config_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


def parse_local_toml(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    values: dict[str, str] = {}
    for key in ("TEXT_TO_CAD_ROOT", "TEXT_TO_CAD_PYTHON", "FREECAD_CMD"):
        if key in data:
            values[key] = str(data[key])
    tools = data.get("tools", {})
    if isinstance(tools, dict):
        for key in ("TEXT_TO_CAD_ROOT", "TEXT_TO_CAD_PYTHON", "FREECAD_CMD"):
            if key in tools:
                values[key] = str(tools[key])
    return values


def read_local_config(project_root: Path = PROJECT_ROOT) -> dict[str, str]:
    values = parse_env_file(project_root / ".env")
    values.update(parse_local_toml(project_root / ".erb-cad.local.toml"))
    return values


def config_value(name: str, env: Mapping[str, str], local: Mapping[str, str], default: str | None = None) -> str | None:
    return env.get(name) or local.get(name) or default


def discover_freecad_cmd(
    env: Mapping[str, str],
    local: Mapping[str, str],
    *,
    which=shutil.which,
    candidates: tuple[Path, ...] | None = None,
) -> Path | None:
    configured = config_value("FREECAD_CMD", env, local)
    if configured:
        return expand_config_path(configured)

    for executable in ("freecadcmd", "FreeCADCmd"):
        found = which(executable)
        if found:
            return Path(found)

    platform_candidates = candidates or (
        Path("/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"),
        Path("/Applications/FreeCAD.app/Contents/MacOS/FreeCAD"),
    )
    for candidate in platform_candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_tool_config(
    project_root: Path = PROJECT_ROOT,
    *,
    env: Mapping[str, str] | None = None,
) -> ToolConfig:
    effective_env = os.environ if env is None else env
    local = read_local_config(project_root)

    text_to_cad_root_value = config_value(
        "TEXT_TO_CAD_ROOT",
        effective_env,
        local,
        str(Path.home() / "BLR" / "text-to-cad"),
    )
    assert text_to_cad_root_value is not None
    text_to_cad_root = expand_config_path(text_to_cad_root_value)

    text_to_cad_python_value = config_value(
        "TEXT_TO_CAD_PYTHON",
        effective_env,
        local,
        str(text_to_cad_root / ".venv" / "bin" / "python"),
    )
    assert text_to_cad_python_value is not None

    return ToolConfig(
        project_root=project_root,
        text_to_cad_root=text_to_cad_root,
        text_to_cad_python=expand_config_path(text_to_cad_python_value),
        freecad_cmd=discover_freecad_cmd(effective_env, local),
    )


def require_existing(path: Path, label: str, *, env_var: str | None = None) -> None:
    if path.exists():
        return
    hint = f" Set {env_var} to override this path." if env_var else ""
    raise FileNotFoundError(f"{label} not found: {path}.{hint}")
