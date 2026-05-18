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
DEFAULT_TEXT_TO_CAD_ROOT = Path.home() / "BLR" / "text-to-cad"
TEXT_TO_CAD_ROOT = Path(os.environ.get("TEXT_TO_CAD_ROOT", str(DEFAULT_TEXT_TO_CAD_ROOT))).expanduser()
TEXT_TO_CAD_PYTHON = Path(
    os.environ.get("TEXT_TO_CAD_PYTHON", str(TEXT_TO_CAD_ROOT / ".venv" / "bin" / "python"))
).expanduser()
VIEWER_REL_DIR = Path("models/erb_balance_bot/stage1_lower_chassis")
ASSEMBLY_VIEWER_REL_DIR = Path("models/erb_balance_bot")

STEP_FILENAMES = [
    "erb_lower_chassis_left_side_plate.step",
    "erb_lower_chassis_right_side_plate.step",
    "erb_lower_chassis_front_panel.step",
    "erb_lower_chassis_rear_panel.step",
    "erb_lower_chassis_rear_panel_body.step",
    "erb_lower_chassis_rear_panel_bumpout.step",
    "erb_lower_chassis_rear_panel_detachable.step",
    "erb_lower_chassis_rear_panel_detachable_body.step",
    "erb_lower_chassis_rear_panel_detachable_bumpout.step",
    "erb_lower_chassis_rear_panel_vented.step",
    "erb_lower_chassis_bottom_tray.step",
    "erb_lower_chassis_top_lid.step",
    "erb_axle_insert_tight.step",
    "erb_axle_insert_medium.step",
    "erb_axle_insert_loose.step",
    "erb_equipment_shelf.step",
    "erb_equipment_shelf_side_cable.step",
    "erb_equipment_shelf_side_cable_shallow.step",
    "erb_equipment_shelf_four_way_cable_shallow.step",
    "erb_equipment_shelf_service_fit.step",
    "erb_shelf_spacer_block_55mm.step",
    "erb_upper_wide_center_adapter_deck.step",
    "erb_upper_wide_center_compute_bay.step",
    "erb_upper_wide_left_overwheel_pod.step",
    "erb_upper_wide_right_overwheel_pod.step",
    "erb_upper_wide_center_crossmember.step",
    "erb_upper_wide_side_crossmember.step",
    "erb_upper_perception_pod.step",
    "erb_reference_wheel_pair.step",
    "erb_reference_axle_pair.step",
    "erb_reference_wheel_axle_pair.step",
    "erb_top_dome_plain.step",
    "erb_top_dome_sensor_mockup.step",
    "erb_top_dome_prototypes.step",
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
    require_path(TEXT_TO_CAD_PYTHON, "text-to-cad Python")
    generators = [
        PROJECT_ROOT / "cad" / "erb_lower_chassis.py",
        PROJECT_ROOT / "cad" / "erb_top_dome.py",
    ]
    for generator in generators:
        require_path(generator, f"Erb CAD generator {generator.name}")
        run([TEXT_TO_CAD_PYTHON, generator], cwd=PROJECT_ROOT)


def remove_step_sidecars(directory: Path, filename: str) -> None:
    for sidecar in (directory / f".{filename}", directory / f".{filename}.glb"):
        if sidecar.exists():
            remove_path(sidecar)


def copy_steps_to_viewer() -> tuple[Path, Path]:
    source_dir = PROJECT_ROOT / "exports" / "step"
    dest_dir = TEXT_TO_CAD_ROOT / VIEWER_REL_DIR
    assembly_dest_dir = TEXT_TO_CAD_ROOT / ASSEMBLY_VIEWER_REL_DIR
    require_path(source_dir, "Erb STEP source directory")

    dest_dir.mkdir(parents=True, exist_ok=True)
    assembly_dest_dir.mkdir(parents=True, exist_ok=True)
    active_files = set(STEP_FILENAMES)
    for path in dest_dir.glob("erb_*.step"):
        if path.name not in active_files:
            path.unlink()
    for sidecar in dest_dir.glob(".erb_*"):
        if sidecar_source_name(sidecar) not in active_files:
            remove_path(sidecar)

    for filename in STEP_FILENAMES:
        source = source_dir / filename
        require_path(source, f"STEP source {filename}")
        remove_step_sidecars(dest_dir, filename)
        shutil.copy2(source, dest_dir / filename)

    assembly_source = source_dir / ASSEMBLY_FILENAME
    remove_step_sidecars(assembly_dest_dir, ASSEMBLY_FILENAME)
    shutil.copy2(assembly_source, assembly_dest_dir / ASSEMBLY_FILENAME)

    return dest_dir, assembly_dest_dir


def generate_viewer_assets(dest_dir: Path) -> None:
    step_cli = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "step"
    require_path(step_cli, "text-to-cad STEP generator")

    for filename in STEP_FILENAMES:
        target = dest_dir / filename
        if filename == ASSEMBLY_FILENAME:
            run([TEXT_TO_CAD_PYTHON, step_cli, "--kind", "assembly", target], cwd=TEXT_TO_CAD_ROOT)
        else:
            run([TEXT_TO_CAD_PYTHON, step_cli, "--kind", "part", target], cwd=TEXT_TO_CAD_ROOT)


def generate_top_level_assembly_asset(assembly_dest_dir: Path) -> None:
    step_cli = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "step"
    require_path(step_cli, "text-to-cad STEP generator")
    target = assembly_dest_dir / ASSEMBLY_FILENAME
    run([TEXT_TO_CAD_PYTHON, step_cli, "--kind", "assembly", target], cwd=TEXT_TO_CAD_ROOT)


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
    dest_dir, assembly_dest_dir = copy_steps_to_viewer()
    generate_viewer_assets(dest_dir)
    generate_top_level_assembly_asset(assembly_dest_dir)

    viewer_url = (
        "http://127.0.0.1:4178/"
        "?dir=models/erb_balance_bot"
        "&file=erb_lower_chassis_assembly.step"
    )
    print()
    print(f"Mirrored STEP files to: {dest_dir}")
    print(f"Mirrored top-level assembly to: {assembly_dest_dir / ASSEMBLY_FILENAME}")
    print(f"CAD Explorer URL: {viewer_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
