#!/usr/bin/env python3
"""Batch convert STEP files to STL for browser viewing.

Usage:
    python scripts/batch_convert_stl.py              # convert all STEP in b3/exports/step/
    python scripts/batch_convert_stl.py --dir b3/exports/step/
    python scripts/batch_convert_stl.py part1.step    # convert specific file
"""
import argparse
import sys
from pathlib import Path

try:
    import cadquery as cq
except ImportError:
    print("ERROR: cadquery not found. Install with: pip install cadquery")
    sys.exit(1)


def convert_file(step_path: Path, stl_dir: Path) -> Path:
    """Convert a single STEP file to STL in the target directory."""
    stl_path = stl_dir / (step_path.stem + ".stl")
    shape = cq.importers.importStep(str(step_path))
    cq.exporters.export(shape, str(stl_path), "STL")
    return stl_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch convert STEP to STL")
    parser.add_argument("paths", nargs="*", help="STEP files to convert")
    parser.add_argument("--dir", default="b3/exports/step/", help="Input directory")
    parser.add_argument("--out", default="b3/exports/stl/", help="Output directory")
    args = parser.parse_args()

    stl_dir = Path(args.out).resolve()
    stl_dir.mkdir(parents=True, exist_ok=True)

    if args.paths:
        paths = [Path(p).resolve() for p in args.paths]
    else:
        paths = list(Path(args.dir).resolve().rglob("*.step"))

    count = 0
    for step_path in paths:
        if step_path.exists():
            stl_path = convert_file(step_path, stl_dir)
            print(f"  {step_path.name} -> {stl_path.name}")
            count += 1
        else:
            print(f"  SKIP (not found): {step_path}")

    print(f"\nDone: {count} files converted to {stl_dir}")
    print("Open viewer with: npm --prefix viewer/stl-viewer run dev")
    print("Direct STL URL example: http://127.0.0.1:3000/?stl=/exports/stl/<subdir>/<file>.stl")


if __name__ == "__main__":
    main()
