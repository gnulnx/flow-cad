#!/usr/bin/env python3
"""Convert STEP files to STL for browser-based 3D viewing."""
import argparse
import sys
from pathlib import Path

try:
    import cadquery as cq
except ImportError:
    print("ERROR: cadquery not found. Install with: pip install cadquery")
    sys.exit(1)


def convert_step(step_path: Path, stl_path: Path) -> None:
    """Convert a single STEP file to STL."""
    shape = cq.importers.importStep(str(step_path))
    cq.exporters.export(shape, str(stl_path), "STL")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert STEP to STL for browser viewing")
    parser.add_argument("step_path", help="Path to STEP file")
    parser.add_argument("-o", "--output", help="Output STL path (default: same name with .stl)")
    args = parser.parse_args()

    step_path = Path(args.step_path).resolve()
    if not step_path.exists():
        print(f"ERROR: {step_path} not found")
        sys.exit(1)

    stl_path = Path(args.output) if args.output else step_path.with_suffix(".stl")
    convert_step(step_path, stl_path)
    print(f"Converted: {step_path} -> {stl_path}")


if __name__ == "__main__":
    main()
