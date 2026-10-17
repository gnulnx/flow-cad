"""Portable project snapshots, independent of manufacturing/release status."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

from flow_cad.sdk import load_manifest

EXCLUDED = {'.git', '.flow', '.venv', '.runtime', 'node_modules', '__pycache__', '.pytest_cache'}


def export_workspace(root: Path, context) -> dict:
    root = root.resolve()
    manifest_path = root / 'flowcad.project.yaml'
    manifest_bytes = manifest_path.read_bytes()
    manifest = load_manifest(manifest_path)
    try:
        tracked = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root, check=True,
                                 capture_output=True).stdout.split(b'\0')
        sources = {Path(os.fsdecode(p)) for p in tracked if p}
    except (OSError, subprocess.CalledProcessError):
        sources = {p.relative_to(root) for p in root.rglob('*') if p.is_file()}
    sources = {p for p in sources if p.parts[0] != 'exports'
               and not EXCLUDED.intersection(p.parts) and not any(part.startswith('.env') for part in p.parts)
               and not any(part.endswith('.egg-info') for part in p.parts)}
    # Include new project source as well as tracked source; all declared exports
    # are explicit, so stale exported designs never enter through this walk.
    sources.update(p.relative_to(root) for p in (root / manifest.python_package).rglob('*')
                   if p.is_file() and not EXCLUDED.intersection(p.parts)
                   and p.suffix not in {'.pyc', '.pyo'})
    sources.add(Path('flowcad.project.yaml'))
    missing = []
    for part in manifest.parts:
        if part.status.value in {'retired','superseded'}:
            continue
        for artifact in part.artifacts:
            path = Path(artifact.path)
            if (root/path).is_file(): sources.add(path)
            else: missing.append({'part':part.key,'kind':artifact.kind,'path':artifact.path})
    for assembly in manifest.assemblies:
        for artifact in assembly.artifacts:
            path=Path(artifact.path)
            if (root/path).is_file(): sources.add(path)
            else: missing.append({'assembly':assembly.key,'kind':artifact.kind,'path':artifact.path})
    sources = sorted(sources)
    destination = root / '.flow/handoff' / f'workspace-{context.job_id}.tar.gz'
    destination.parent.mkdir(parents=True, exist_ok=True)
    context.report('package', .05, f'Packaging {len(sources)} project and current artifact files')
    digests = {}
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='workspace-') as temporary:
        pending = Path(temporary)/'workspace.tar.gz'
        with tarfile.open(pending, 'w:gz', compresslevel=1, dereference=True) as archive:
            for index, relative in enumerate(sources):
                context.checkpoint()
                source=root/relative
                if relative.is_absolute() or not source.resolve().is_relative_to(root):
                    raise ValueError(f'Workspace path escapes project: {relative}')
                if not source.is_file():
                    raise ValueError(f'Workspace source disappeared: {relative}')
                before=source.stat()
                digest=hashlib.sha256()
                with source.open('rb') as stream:
                    for block in iter(lambda:stream.read(1024*1024), b''):
                        context.checkpoint();digest.update(block)
                archive.add(source, arcname=f'{manifest.project_id}/{relative}', recursive=False)
                after=source.stat()
                if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                    raise ValueError(f'Workspace changed during export: {relative}; retry')
                digests[relative.as_posix()]=digest.hexdigest()
                if index % 10 == 0:
                    context.report('package', .05+.85*(index+1)/len(sources),f'Packaged {index+1}/{len(sources)} files')
            if manifest_path.read_bytes()!=manifest_bytes:
                raise ValueError('Project manifest changed during export; retry')
            report={'schema_version':1,'project_id':manifest.project_id,
                    'manufacturing_release':False,'missing_artifacts':missing,'sha256':digests}
            data=(json.dumps(report,indent=2)+'\n').encode()
            info=tarfile.TarInfo(f'{manifest.project_id}/WORKSPACE_EXPORT.json');info.size=len(data)
            archive.addfile(info,io.BytesIO(data))
            readme=("Portable Flow CAD workspace snapshot.\n\nInstall Flow CAD on the destination, "
                    "then run `python -m pip install -e .`, `flow sync`, and `flow start` in this folder.\n"
                    "Open the project print list for slicer paths and readiness.\n"
                    "This snapshot includes available artifacts; it does not rebuild missing parts or certify fabrication.\n"
                    "WORKSPACE_EXPORT.json lists missing artifacts and file SHA-256 values.\n").encode()
            info=tarfile.TarInfo(f'{manifest.project_id}/OPEN_WORKSPACE.txt');info.size=len(readme)
            archive.addfile(info,io.BytesIO(readme))
        context.checkpoint()
        os.replace(pending,destination)
    return {'bundle_path':destination.relative_to(root).as_posix(),
            'download_url':f'/api/workbench/v1/build/workspace/{context.job_id}',
            'file_count':len(digests),'missing_artifact_count':len(missing),
            'manufacturing_release':False}
