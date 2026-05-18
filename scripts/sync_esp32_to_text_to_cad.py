#!/usr/bin/env python3
"""Mirror Erb ESP32 holder STEP files into text-to-cad and build sidecars."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEXT_TO_CAD_ROOT = Path.home() / "BLR" / "text-to-cad"
TEXT_TO_CAD_ROOT = Path(os.environ.get("TEXT_TO_CAD_ROOT", str(DEFAULT_TEXT_TO_CAD_ROOT))).expanduser()
TEXT_TO_CAD_PYTHON = Path(
    os.environ.get("TEXT_TO_CAD_PYTHON", str(TEXT_TO_CAD_ROOT / ".venv" / "bin" / "python"))
).expanduser()
VIEWER_REL_DIR = Path("models/erb_balance_bot/esp32_wroom_holder")

STEP_FILENAMES = [
    "erb_esp32_wroom_holder_base.step",
    "erb_esp32_wroom_holder_lid.step",
    "erb_esp32_wroom_holder_assembly.step",
]

ASSEMBLY_FILENAME = "erb_esp32_wroom_holder_assembly.step"


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
    generator = PROJECT_ROOT / "cad" / "erb_esp32_wroom_holder.py"
    require_path(generator, "Erb ESP32 holder CAD generator")
    run([TEXT_TO_CAD_PYTHON, generator], cwd=PROJECT_ROOT)


def copy_steps_to_viewer() -> Path:
    source_dir = PROJECT_ROOT / "exports" / "step" / "esp32_wroom_holder"
    dest_dir = TEXT_TO_CAD_ROOT / VIEWER_REL_DIR
    require_path(source_dir, "ESP32 holder STEP source directory")

    dest_dir.mkdir(parents=True, exist_ok=True)
    active_files = set(STEP_FILENAMES)
    for path in dest_dir.glob("erb_esp32_wroom*.step"):
        if path.name not in active_files:
            path.unlink()
    for sidecar in dest_dir.glob(".erb_esp32_wroom*"):
        if sidecar_source_name(sidecar) not in active_files:
            remove_path(sidecar)

    for filename in STEP_FILENAMES:
        source = source_dir / filename
        require_path(source, f"STEP source {filename}")
        for sidecar in (dest_dir / f".{filename}", dest_dir / f".{filename}.glb"):
            if sidecar.exists():
                remove_path(sidecar)
        shutil.copy2(source, dest_dir / filename)

    return dest_dir


def generate_viewer_assets(dest_dir: Path) -> None:
    step_cli = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "step"
    require_path(step_cli, "text-to-cad STEP generator")

    for filename in STEP_FILENAMES:
        target = dest_dir / filename
        if filename == ASSEMBLY_FILENAME:
            run([TEXT_TO_CAD_PYTHON, step_cli, "--kind", "assembly", target], cwd=TEXT_TO_CAD_ROOT)
        else:
            run([TEXT_TO_CAD_PYTHON, step_cli, "--kind", "part", target], cwd=TEXT_TO_CAD_ROOT)


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
        "?dir=models/erb_balance_bot/esp32_wroom_holder"
        "&file=erb_esp32_wroom_holder_assembly.step"
    )
    print()
    print(f"Mirrored STEP files to: {dest_dir}")
    print(f"CAD Explorer URL: {viewer_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
