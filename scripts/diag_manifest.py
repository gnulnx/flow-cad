#!/usr/bin/env python3
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from flow_cad.registry import REGISTRY, PartRole

def get_source():
    return {f"b3/exports/step/{p.module_id}/{p.filename}" for p in REGISTRY.values() if p.role == PartRole.PRINTABLE}

def get_manifest():
    content = Path("docs/PRINT_MANIFEST.md").read_text()
    section = re.search(r"## Active Lower Chassis Print Set\s*.*?(?=\n##|$)", content, re.DOTALL | re.MULTILINE)
    return {p for p in re.findall(r"`([^`]+\.step)`", section.group(0)) if "b3/exports/step/" in p}

source = get_source()
manifest = get_manifest()
print("\n--- SOURCE REGISTRY ---\n")
for p in sorted(source): print(p)
print("\n--- MANIFEST ---\n")
for p in sorted(manifest):
    print(f"{p} {'✓' if p in source else '✗'}")
print(f"\nSource: {len(source)}, Manifest: {len(manifest)}")
print("  - MATCHED", len(source & manifest))
print("  - MISSING FROM MANIFEST", len(source - manifest))
print("  - EXTRA IN MANIFEST", len(manifest - source))
