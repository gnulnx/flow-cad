#!/usr/bin/env python3
"""Mirror Erb STEP files into text-to-cad and build viewer sidecars."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_TO_CAD_ROOT = Path(os.environ.get("TEXT_TO_CAD_ROOT", "/Users/jfurr/text-to-cad")).expanduser()
TEXT_TO_CAD_PYTHON = Path(
    os.environ.get("TEXT_TO_CAD_PYTHON", str(TEXT_TO_CAD_ROOT / ".venv" / "bin" / "python"))
).expanduser()
VIEWER_REL_DIR = Path("models/erb_balance_bot/stage1_lower_chassis_expanded_payload")

STEP_FILENAMES = [
    "erb_lower_chassis_left_side_plate.step",
    "erb_lower_chassis_right_side_plate.step",
    "erb_lower_chassis_front_panel.step",
    "erb_lower_chassis_rear_panel.step",
    "erb_lower_chassis_bottom_tray.step",
    "erb_lower_chassis_top_lid.step",
    "erb_axle_insert_tight.step",
    "erb_axle_insert_medium.step",
    "erb_axle_insert_loose.step",
    "erb_equipment_shelf.step",
    "erb_lower_chassis_assembly.step",
]

ASSEMBLY_FILENAME = "erb_lower_chassis_assembly.step"


def run(command: list[str | Path], cwd: Path) -> None:
    printable = " ".join(str(part) for part in command)
    print(f"$ {printable}", flush=True)
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def require_path(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def generate_project_steps() -> None:
    require_path(TEXT_TO_CAD_PYTHON, "text-to-cad Python")
    generator = PROJECT_ROOT / "cad" / "erb_lower_chassis.py"
    require_path(generator, "Erb CAD generator")
    run([TEXT_TO_CAD_PYTHON, generator], cwd=PROJECT_ROOT)


def copy_steps_to_viewer() -> Path:
    source_dir = PROJECT_ROOT / "exports" / "step"
    dest_dir = TEXT_TO_CAD_ROOT / VIEWER_REL_DIR
    require_path(source_dir, "Erb STEP source directory")

    dest_dir.mkdir(parents=True, exist_ok=True)
    active_files = set(STEP_FILENAMES)
    for path in dest_dir.glob("erb_*.step"):
        if path.name not in active_files:
            path.unlink()
    for sidecar in dest_dir.glob(".erb_*.step"):
        if sidecar.name[1:] not in active_files and sidecar.is_dir():
            shutil.rmtree(sidecar)

    for filename in STEP_FILENAMES:
        source = source_dir / filename
        require_path(source, f"STEP source {filename}")
        sidecar = dest_dir / f".{filename}"
        if sidecar.exists():
            shutil.rmtree(sidecar)
        shutil.copy2(source, dest_dir / filename)

    return dest_dir


def generate_viewer_assets(dest_dir: Path) -> None:
    gen_part = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "gen_step_part"
    gen_assembly = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "gen_step_assembly"
    require_path(gen_part, "text-to-cad gen_step_part")
    require_path(gen_assembly, "text-to-cad gen_step_assembly")

    for filename in STEP_FILENAMES:
        target = dest_dir / filename
        if filename == ASSEMBLY_FILENAME:
            run([TEXT_TO_CAD_PYTHON, gen_assembly, target, "--summary"], cwd=TEXT_TO_CAD_ROOT)
        else:
            run([TEXT_TO_CAD_PYTHON, gen_part, target, "--summary"], cwd=TEXT_TO_CAD_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-cad-generate",
        action="store_true",
        help="Only mirror existing STEP files and regenerate viewer sidecars.",
    )
    args = parser.parse_args()

    require_path(TEXT_TO_CAD_ROOT, "text-to-cad root")
    require_path(TEXT_TO_CAD_PYTHON, "text-to-cad Python")

    if not args.skip_cad_generate:
        generate_project_steps()
    dest_dir = copy_steps_to_viewer()
    generate_viewer_assets(dest_dir)

    viewer_url = (
        "http://127.0.0.1:4178/"
        "?dir=models/erb_balance_bot/stage1_lower_chassis_expanded_payload"
        "&file=erb_lower_chassis_assembly.step"
    )
    print()
    print(f"Mirrored STEP files to: {dest_dir}")
    print(f"CAD Explorer URL: {viewer_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
