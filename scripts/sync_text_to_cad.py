#!/usr/bin/env python3
"""Mirror B3 STEP files into text-to-cad and build viewer sidecars."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from flow_cad.paths import require_existing, resolve_tool_config  # noqa: E402
from flow_cad.params import ChassisParams  # noqa: E402
from scripts.create_exports_bundle import create_bundle  # noqa: E402


PARAMS = ChassisParams()
TOOL_CONFIG = resolve_tool_config(PROJECT_ROOT)
TEXT_TO_CAD_ROOT = TOOL_CONFIG.text_to_cad_root
TEXT_TO_CAD_PYTHON = TOOL_CONFIG.text_to_cad_python
VIEWER_REL_DIR = Path("models/b3_balance_bot/stage1_lower_chassis")
ASSEMBLY_VIEWER_REL_DIR = Path("models/b3_balance_bot")

ASSEMBLY_FILENAME = "b3_lower_chassis_assembly.step"
EXPORTS_BUNDLE_FILENAME = "exports.tar.gz"


def run(command: list[str | Path], cwd: Path) -> None:
    printable = " ".join(str(part) for part in command)
    print(f"$ {printable}", flush=True)
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def require_path(path: Path, label: str) -> None:
    require_existing(path, label)


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def sidecar_source_name(path: Path) -> str | None:
    if not path.name.startswith("."):
        return None
    name = path.name[1:]
    if name.endswith(".glb"):
        return name[:-4]
    return name


def generate_project_steps() -> None:
    # Run the standard CAD build pipeline
    run(["flow", "cad", "build"], cwd=PROJECT_ROOT)


def remove_step_sidecars(directory: Path, filename: str) -> None:
    for sidecar in (directory / f".{filename}", directory / f".{filename}.glb"):
        if sidecar.exists():
            remove_path(sidecar)


def copy_steps_to_viewer() -> tuple[Path, Path]:
    source_dir = PROJECT_ROOT / PARAMS.project_id / "exports" / "step"
    dest_dir = TEXT_TO_CAD_ROOT / VIEWER_REL_DIR
    assembly_dest_dir = TEXT_TO_CAD_ROOT / ASSEMBLY_VIEWER_REL_DIR
    require_path(source_dir, f"{PARAMS.project_id.upper()} STEP source directory")

    dest_dir.mkdir(parents=True, exist_ok=True)
    assembly_dest_dir.mkdir(parents=True, exist_ok=True)

    # Find all generated STEP files recursively
    step_paths = list(source_dir.rglob("*.step"))
    active_filenames = {p.name for p in step_paths}

    for path in dest_dir.glob("*.step"):
        if path.name not in active_filenames:
            path.unlink()
    for sidecar in dest_dir.glob(".*"):
        src_name = sidecar_source_name(sidecar)
        if src_name and src_name not in active_filenames:
            remove_path(sidecar)

    for src_path in step_paths:
        filename = src_path.name
        if filename == ASSEMBLY_FILENAME:
            continue
        remove_step_sidecars(dest_dir, filename)
        shutil.copy2(src_path, dest_dir / filename)

    assembly_source = source_dir / "lower_chassis" / ASSEMBLY_FILENAME
    remove_step_sidecars(assembly_dest_dir, ASSEMBLY_FILENAME)
    shutil.copy2(assembly_source, assembly_dest_dir / ASSEMBLY_FILENAME)

    return dest_dir, assembly_dest_dir


def generate_viewer_assets(dest_dir: Path) -> None:
    step_cli = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "step"
    require_path(step_cli, "text-to-cad STEP generator")

    for path in dest_dir.glob("*.step"):
        run([TEXT_TO_CAD_PYTHON, step_cli, "--kind", "part", path], cwd=TEXT_TO_CAD_ROOT)


def generate_top_level_assembly_asset(assembly_dest_dir: Path) -> None:
    step_cli = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "step"
    require_path(step_cli, "text-to-cad STEP generator")
    target = assembly_dest_dir / ASSEMBLY_FILENAME
    run([TEXT_TO_CAD_PYTHON, step_cli, "--kind", "assembly", target], cwd=TEXT_TO_CAD_ROOT)


def rebuild_root_exports_bundle() -> Path:
    bundle_path = PROJECT_ROOT / EXPORTS_BUNDLE_FILENAME
    if bundle_path.exists():
        bundle_path.unlink()
    return create_bundle(PROJECT_ROOT, EXPORTS_BUNDLE_FILENAME)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-cad-generate",
        action="store_true",
        help="Only mirror existing STEP files and regenerate viewer sidecars.",
    )
    args = parser.parse_args()

    require_existing(TEXT_TO_CAD_ROOT, "text-to-cad root", env_var="TEXT_TO_CAD_ROOT")
    require_existing(TEXT_TO_CAD_PYTHON, "text-to-cad Python", env_var="TEXT_TO_CAD_PYTHON")

    if not args.skip_cad_generate:
        generate_project_steps()
    dest_dir, assembly_dest_dir = copy_steps_to_viewer()
    generate_viewer_assets(dest_dir)
    generate_top_level_assembly_asset(assembly_dest_dir)
    bundle_path = rebuild_root_exports_bundle()

    viewer_url = (
        "http://127.0.0.1:4178/"
        "?dir=models/b3_balance_bot"
        "&file=b3_lower_chassis_assembly.step"
    )
    print()
    print(f"Mirrored STEP files to: {dest_dir}")
    print(f"Mirrored top-level assembly to: {assembly_dest_dir / ASSEMBLY_FILENAME}")
    print(f"Rebuilt exports bundle: {bundle_path}")
    print(f"CAD Explorer URL: {viewer_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
