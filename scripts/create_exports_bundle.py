#!/usr/bin/env python3
"""Create a tar.gz handoff bundle containing the current exports directory."""

from __future__ import annotations

import argparse
import tarfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from flow_cad.params import ChassisParams
from flow_cad.registry import expected_step_relative_paths

P = ChassisParams()
EXPORTS_DIR = PROJECT_ROOT / P.project_id / "exports"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "handoff"
ACTIVE_STEP_PATHS = expected_step_relative_paths()


EXCLUDED_NAMES = {".DS_Store", "__pycache__"}
EXCLUDED_SUFFIXES = {".FCBak", ".pyc", ".pyo"}


def should_include(path: Path, exports_dir: Path = EXPORTS_DIR, active_step_paths: set[Path] | None = None) -> bool:
    relative_parts: Iterable[str] = path.relative_to(exports_dir).parts if path != exports_dir else ()
    for part in relative_parts:
        if part in EXCLUDED_NAMES:
            return False
        if part.startswith("."):
            return False
        if any(part.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
            return False
    relative_path = Path(*relative_parts) if relative_parts else Path()
    if active_step_paths is not None and relative_path.suffix == ".step":
        return relative_path in active_step_paths
    return True


def create_bundle(output_dir: Path, name: str | None = None, active_step_paths: set[Path] | None = None) -> Path:
    if not EXPORTS_DIR.exists():
        raise FileNotFoundError(f"exports directory not found: {EXPORTS_DIR}")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle_name = name or f"{P.project_id}-exports-{timestamp}.tar.gz"
    if not bundle_name.endswith(".tar.gz"):
        bundle_name = f"{bundle_name}.tar.gz"

    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = output_dir / bundle_name
    with tarfile.open(bundle_path, "w:gz") as archive:
        archive.add(
            EXPORTS_DIR,
            arcname="exports",
            filter=lambda info: info if should_include(Path(info.name), Path("exports"), active_step_paths) else None,
        )
    return bundle_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for the tar.gz bundle. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--name",
        help="Bundle filename. '.tar.gz' is appended when omitted.",
    )
    args = parser.parse_args()

    bundle_path = create_bundle(args.output_dir, args.name, ACTIVE_STEP_PATHS)
    print(f"Created exports handoff bundle: {bundle_path}")
    print(f"Copy to laptop with: scp {bundle_path} jfurr@laptop:/Users/jfurr/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
