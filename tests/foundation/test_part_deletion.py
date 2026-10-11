from __future__ import annotations

import json
import shutil
import time
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from flow_cad.registry import get_part, sync_project
from flow_cad.registry.db import connect_readonly, database_path
from flow_cad.registry.deletion import PartDeleteNotFound, delete_part
from flow_cad.sdk import ArtifactSpec, dump_manifest, load_manifest
from flow_cad.viewer.api import create_workbench_app


@pytest.fixture
def project(tmp_path):
    shutil.copytree(Path(__file__).resolve().parents[1] / 'fixtures/projects/minimal_alpha', tmp_path, dirs_exist_ok=True)
    manifest = load_manifest(tmp_path / 'flowcad.project.yaml')
    for artifact in manifest.parts[0].artifacts:
        path = tmp_path / artifact.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'unchanged artifact')
    sync_project(tmp_path, force=True)
    return tmp_path


def test_delete_removes_declared_references_and_survives_sync(project):
    original = (project / 'flowcad.project.yaml').read_bytes()
    started = time.perf_counter()
    result = delete_part(project, 'original_alpha_panel')
    assert time.perf_counter() - started < 1
    assert result['removed_occurrences'] == 1
    assert not load_manifest(project / 'flowcad.project.yaml').parts
    assert not load_manifest(project / 'flowcad.project.yaml').assemblies[0].occurrences
    with closing(connect_readonly(database_path(project))) as connection:
        for table in ('parts', 'part_aliases', 'source_definitions', 'assembly_occurrences', 'artifacts', 'artifact_dependencies'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
    recovery = project / result['recovery_path']
    assert (recovery / 'flowcad.project.yaml').read_bytes() == original
    for relative in result['removed_files']:
        assert not (project / relative).exists()
        assert (recovery / 'files' / relative).read_bytes() == b'unchanged artifact'
    sync_project(project, force=True)
    assert get_part(project, 'alpha_panel') is None


def test_delete_preserves_shared_exports_source_and_immutable_inputs(project):
    path = project / 'flowcad.project.yaml'
    original = load_manifest(path)
    first = original.parts[0]
    frozen = project / 'references/input.step'
    frozen.parent.mkdir()
    frozen.write_bytes(b'frozen')
    first = replace(first, artifacts=(*first.artifacts, ArtifactSpec(kind='glb', path='references/input.step')))
    other = replace(first, uuid=uuid4(), key='survivor', aliases=())
    path.write_text(dump_manifest(replace(original, parts=(first, other))))
    sync_project(project)
    result = delete_part(project, str(first.uuid))
    assert result['removed_files'] == []
    assert frozen.read_bytes() == b'frozen'
    assert (project / first.artifacts[0].path).is_file()
    assert get_part(project, 'survivor') is not None


def test_delete_clears_preview_and_invalidates_affected_assembly_export(project):
    path = project / 'flowcad.project.yaml'
    original = load_manifest(path)
    assembly_file = project / 'exports/assembly.step'
    assembly_file.write_bytes(b'old assembly')
    assembly = replace(original.assemblies[0], artifacts=(ArtifactSpec(kind='step', path='exports/assembly.step'),))
    path.write_text(dump_manifest(replace(original, assemblies=(assembly,))))
    preview = project / '.flow/workbench/preview-placement.json'
    preview.parent.mkdir(parents=True)
    preview.write_text(json.dumps({'target_part_uuid': str(original.parts[0].uuid)}))
    delete_part(project, 'alpha_panel')
    assert not preview.exists()
    assert not assembly_file.exists()
    assert not load_manifest(path).assemblies[0].artifacts


def test_delete_rolls_back_files_index_and_manifest_on_write_failure(project, monkeypatch):
    original = (project / 'flowcad.project.yaml').read_bytes()
    def fail(*args):
        raise OSError('injected disk failure')
    monkeypatch.setattr('flow_cad.registry.deletion._write_atomic', fail)
    with pytest.raises(OSError, match='disk failure'):
        delete_part(project, 'alpha_panel')
    assert (project / 'flowcad.project.yaml').read_bytes() == original
    assert get_part(project, 'alpha_panel') is not None
    assert (project / 'exports/step/alpha_panel.step').read_bytes() == b'unchanged artifact'


def test_missing_part_does_not_change_manifest(project):
    original = (project / 'flowcad.project.yaml').read_bytes()
    with pytest.raises(PartDeleteNotFound):
        delete_part(project, 'unknown')
    assert (project / 'flowcad.project.yaml').read_bytes() == original


def test_delete_preserves_export_symlink_target(project, tmp_path_factory):
    target = tmp_path_factory.mktemp('outside') / 'external.step'
    target.write_bytes(b'external')
    path = project / 'exports/step/alpha_panel.step'
    path.unlink()
    path.symlink_to(target)
    delete_part(project, 'alpha_panel')
    assert path.is_symlink()
    assert target.read_bytes() == b'external'


def test_delete_http_and_cors(project):
    with TestClient(create_workbench_app(project, enable_default_chat_provider=False)) as client:
        preflight = client.options('/api/parts/alpha_panel', headers={
            'Origin': 'http://127.0.0.1:3002', 'Access-Control-Request-Method': 'DELETE'})
        assert preflight.status_code == 200
        response = client.delete('/api/parts/11111111-1111-4111-8111-111111111111')
        assert response.status_code == 200, response.text
        assert not client.get('/api/parts').json()['parts']
        assert client.delete('/api/parts/alpha_panel').status_code == 404


def test_delete_rejects_active_job_without_changes(project):
    with TestClient(create_workbench_app(project, enable_default_chat_provider=False)) as client:
        client.app.state.job_service.store.create(request_id='active-build', kind='part-build')
        response = client.delete('/api/parts/alpha_panel')
        assert response.status_code == 409
        assert get_part(project, 'alpha_panel') is not None


def test_unrelated_display_job_does_not_block_delete(project):
    with TestClient(create_workbench_app(project, enable_default_chat_provider=False)) as client:
        client.app.state.job_service.store.create(request_id='old-display-job', kind='display-scene')
        assert client.delete('/api/parts/alpha_panel').status_code == 200
