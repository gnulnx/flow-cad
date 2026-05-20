#!/usr/bin/env python3
"""
Validate that docs/PRINT_MANIFEST.md matches the printable parts in src/flow_cad/registry.py.

This ensures that what we tell users to print is exactly what's marked as PRINTABLE
in the source registry, preventing stale or missing entries in documentation.
"""

from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

# Add src to path for imports if running directly
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from flow_cad.registry import REGISTRY, PartRole


def get_printable_step_paths() -> set[str]:
    """
    Extract all printable STEP paths from the source registry.
    Returns paths in the format: b3/exports/step/{module}/{filename}
    """
    printable = []
    for part in REGISTRY.values():
        if part.role == PartRole.PRINTABLE:
            path = f"b3/exports/step/{part.module_id}/{part.filename}"
            printable.append(path)
    return set(printable)


def parse_manifest_printables(manifest_path: Path) -> set[str]:
    """
    Extract STEP paths from the 'Active Lower Chassis Print Set' section of manifest.
    Ignores reference/inspection parts listed in other sections.
    """
    if not manifest_path.exists():
        return set()

    content = manifest_path.read_text(encoding="utf-8")
    
    # Find the 'Active Lower Chassis Print Set' section
    in_section = False
    paths = []
    for line in content.splitlines():
        if line.startswith("## Active Lower Chassis Print Set"):
            in_section = True
            continue
        elif line.startswith("## ") and in_section:
            break
        if in_section:
            match = re.search(r"`([^`]+\.step)`", line)
            if match: paths.append(match.group(1))
    return {p if p.startswith("b3/exports/") else f"b3/exports/{p}" for p in paths if ".step" in p}
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate print manifest against source registry"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "docs/PRINT_MANIFEST.md",
        help="Path to the print manifest file.",
    )
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Error: Manifest not found at {args.manifest}")
        return 1

    source_printable = get_printable_step_paths()
    manifest_printable = parse_manifest_printables(args.manifest)

    missing_from_manifest = source_printable - manifest_printable
    extra_in_manifest = manifest_printable - source_printable

    if not missing_from_manifest and not extra_in_manifest:
        print("✅ Print manifest is in sync with registry.")
        return 0

    print("❌ PRINT MANIFEST DRIFT DETECTED\n")
    
    if missing_from_manifest:
        print(f"Missing from manifest ({len(missing_from_manifest)} parts):")
        for p in sorted(missing_from_manifest):
            print(f"  - {p}")
        print()
    
    if extra_in_manifest:
        print(f"Extra in manifest ({len(extra_in_manifest)} parts):")
        for p in sorted(extra_in_manifest):
            print(f"  - {p}")
        print()
    
    print("Run 'flow cad build' to regenerate exports, then update the manifest.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
