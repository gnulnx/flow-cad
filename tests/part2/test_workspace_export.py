import hashlib
import json
from pathlib import Path
import tarfile
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from flow_cad.sdk import ArtifactSpec, PartStatus, dump_manifest, load_manifest
from flow_cad.viewer.api import create_workbench_app
from flow_cad.viewer.services.workspace_export import export_workspace
from tests.rebuild.test_workbench_api import _project


class Context:
    job_id='fixture'
    def checkpoint(self): pass
    def report(self,*args): pass


def test_prototype_workspace_export_downloads_sources_current_artifacts_and_missing_list(tmp_path):
    root, *_ = _project(tmp_path)
    source=root/'workbench_project';source.mkdir();(source/'parts.py').write_text('def make_panel(): pass\n')
    (root/'.env').write_text('SECRET')
    (root/'.flow/private-token').write_text('SECRET')
    old=root/'exports/old.stl';old.write_text('old design')
    manifest=load_manifest(root/'flowcad.project.yaml')
    part=replace(manifest.parts[0],status=PartStatus.INSPECTION,
                 artifacts=(*manifest.parts[0].artifacts,ArtifactSpec(kind='glb',path='exports/pending.glb')))
    (root/'flowcad.project.yaml').write_text(dump_manifest(replace(manifest,parts=(part,))))
    with TestClient(create_workbench_app(root)) as client:
        response=client.post('/api/workbench/v1/build/workspace',json={'request_id':'portable'})
        assert response.status_code==202
        id=response.json()['job']['job_id']
        for _ in range(100):
            job=client.get(f'/api/workbench/v1/jobs/{id}').json()
            if job['state'] in {'succeeded','failed','cancelled'}:break
            time.sleep(.01)
        assert job['state']=='succeeded',job
        assert job['result']['missing_artifact_count']==1
        download=client.get(job['result']['download_url'])
        assert download.status_code==200
        archive=tmp_path/'download.tar.gz';archive.write_bytes(download.content)
        with tarfile.open(archive) as bundle:
            names=bundle.getnames();prefix='workbench_project/'
            assert prefix+'flowcad.project.yaml' in names
            assert prefix+'workbench_project/parts.py' in names
            assert prefix+'exports/stl/panel.stl' in names
            assert prefix+'exports/old.stl' not in names
            assert not any('.env' in n or '.flow/' in n for n in names)
            report=json.load(bundle.extractfile(prefix+'WORKSPACE_EXPORT.json'))
            assert report['manufacturing_release'] is False
            assert report['missing_artifacts']==[{'part':'panel','kind':'glb','path':'exports/pending.glb'}]
            for relative,digest in report['sha256'].items():
                assert hashlib.sha256(bundle.extractfile(prefix+relative).read()).hexdigest()==digest
            copied=tmp_path/'laptop';bundle.extractall(copied,filter='data')
        loaded=load_manifest(copied/prefix/'flowcad.project.yaml')
        assert loaded.parts[0].status is PartStatus.INSPECTION
        assert client.get('/api/workbench/v1/build/workspace/not-a-job').status_code==404


def test_workspace_export_refuses_escaped_source_and_does_not_publish(tmp_path):
    root,*_=_project(tmp_path)
    outside=tmp_path/'private';outside.write_text('private')
    package=root/'workbench_project';package.mkdir();(package/'escape.py').symlink_to(outside)
    with pytest.raises(ValueError,match='escapes project'):
        export_workspace(root,Context())
    assert not (root/'.flow/handoff/workspace-fixture.tar.gz').exists()
