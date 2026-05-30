from __future__ import annotations
import tarfile
from pathlib import Path

EXCLUDED_NAMES = {".DS_Store", "__pycache__"}
EXCLUDED_SUFFIXES = {".FCBak", ".pyc", ".pyo"}

def should_include(path: Path, exports_dir: Path, active_export_paths: set[Path] | None = None) -> bool:
    try:
        relative_parts = path.relative_to(exports_dir).parts if path != exports_dir else ()
    except ValueError:
        # If it's not relative to exports_dir, it's likely the 'exports' arcname itself during filtering
        return True
        
    for part in relative_parts:
        if part in EXCLUDED_NAMES:
            return False
        if part.startswith("."):
            return False
        if any(part.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
            return False
    relative_path = Path(*relative_parts) if relative_parts else Path()
    if active_export_paths is not None:
        if relative_path.suffix in {".step", ".stl", ".svg"}:
            return relative_path in active_export_paths
        if relative_parts and relative_parts[0] in {"step", "stl", "snapshots"}:
            return any(relative_path == active_path or relative_path in active_path.parents for active_path in active_export_paths)
    return True

def create_bundle(
    exports_dir: Path,
    output_dir: Path,
    bundle_name: str = "exports.tar.gz",
    active_export_paths: set[Path] | None = None,
) -> Path:
    if not exports_dir.exists():
        raise FileNotFoundError(f"exports directory not found: {exports_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    if not bundle_name.endswith(".tar.gz"):
        bundle_name = f"{bundle_name}.tar.gz"

    bundle_path = output_dir / bundle_name
    
    if bundle_path.exists():
        bundle_path.unlink()

    with tarfile.open(bundle_path, "w:gz") as archive:
        archive.add(
            exports_dir,
            arcname="exports",
            filter=lambda info: info if should_include(Path(info.name), Path("exports"), active_export_paths) else None,
        )
    return bundle_path
