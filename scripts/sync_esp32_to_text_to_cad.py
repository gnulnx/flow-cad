#!/usr/bin/env python3
"""Mirror Erb ESP32 holder STEP files into text-to-cad and build sidecars."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_TO_CAD_ROOT = Path(os.environ.get("TEXT_TO_CAD_ROOT", "/Users/jfurr/text-to-cad")).expanduser()
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
    for sidecar in dest_dir.glob(".erb_esp32_wroom*.step"):
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
        "?dir=models/erb_balance_bot/esp32_wroom_holder"
        "&file=erb_esp32_wroom_holder_assembly.step"
    )
    print()
    print(f"Mirrored STEP files to: {dest_dir}")
    print(f"CAD Explorer URL: {viewer_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
