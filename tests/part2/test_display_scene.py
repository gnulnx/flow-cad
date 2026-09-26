import json
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from flow_cad.registry import sync_project
from flow_cad.viewer.api import create_workbench_app
from flow_cad.viewer.scene_export import export_scene
from test_exact_measurement_api import _step_project, PART_UUID


def glb_document(path):
    data = path.read_bytes()
    magic, version, size = struct.unpack_from('<III', data)
    assert (magic, version, size) == (0x46546C67, 2, len(data))
    length = struct.unpack_from('<I', data, 12)[0]
    return json.loads(data[20:20+length])


def test_colors_names_repeated_occurrences_and_nested_locations(tmp_path):
    from build123d import Box, Color, Compound, Location, export_step
    a = Box(10, 20, 30).solid()
    a.label, a.color = 'blue axle', Color(.1, .3, .7)
    a = a.moved(Location((50, 0, 15)))
    b = Box(4, 6, 8).solid()
    b.label, b.color = 'red bracket', Color(.8, .1, .2)
    nested = Compound(children=[a, b]).moved(Location((100, 20, 30)))
    shape = Compound(children=[nested, a.moved(Location((-80, 0, 0)))])
    step, glb = tmp_path/'colors.step', tmp_path/'colors.glb'
    export_step(shape, step)
    stats = export_scene(step, glb)
    assert stats == {'component_count': 3, 'color_count': 2}
    doc = glb_document(glb)
    assert len({node['extras']['componentId'] for node in doc['nodes']}) == 3
    assert any('blue' in node['name'] for node in doc['nodes'])
    colors = [m['pbrMetallicRoughness']['baseColorFactor'] for m in doc['materials']]
    assert colors[0] == pytest.approx([.1, .3, .7, 1], abs=1e-6)
    # Recover original mm/Z-up bounds from GLB's metre/Y-up accessors.
    boxes = [doc['accessors'][m['primitives'][0]['attributes']['POSITION']] for m in doc['meshes']]
    actual_min = [min(b['min'][0] for b in boxes)*1000, -max(b['max'][2] for b in boxes)*1000, min(b['min'][1] for b in boxes)*1000]
    actual_max = [max(b['max'][0] for b in boxes)*1000, -min(b['min'][2] for b in boxes)*1000, max(b['max'][1] for b in boxes)*1000]
    expected = shape.bounding_box()
    assert actual_min == pytest.approx(tuple(expected.min), abs=.001)
    assert actual_max == pytest.approx(tuple(expected.max), abs=.001)


def test_scene_api_jobs_cache_and_revision_guard(tmp_path):
    root, step, revision = _step_project(tmp_path)
    app = create_workbench_app(root, enable_default_chat_provider=False)
    endpoint = f'/api/parts/{PART_UUID}/display-scene'
    params = {'artifact_revision': revision}
    with TestClient(app) as client:
        assert client.get('/api/project').json()['display_scene_version'] == 2
        response = client.get(endpoint, params=params)
        assert response.json() == {'status': 'job_required'}
        assert not (root/'.flow/cache/display-scenes').exists()
        queued = client.post(endpoint+'/jobs', params=params).json()
        assert 'cancel_url' in queued
        duplicate = client.post(endpoint+'/jobs', params=params).json()
        assert duplicate.get('job_id', queued['job_id']) == queued['job_id']
        job = app.state.job_service.wait(queued['job_id'], timeout=30)
        assert job.state.value == 'succeeded', job.error
        scene = client.get(endpoint, params=params).json()
        assert scene['component_count'] == 1
        response = client.get(endpoint+'/model', params=params)
        assert response.headers['content-type'] == 'model/gltf-binary'
        assert response.content[:4] == b'glTF'
        assert client.get(endpoint, params={'artifact_revision': '0'*64}).status_code == 409
        step.write_text(step.read_text()+'\nCHANGED\n')
        assert client.get(endpoint, params=params).status_code == 409


def test_parent_assembly_colors_survive_uncolored_leaf_wrappers(tmp_path):
    from build123d import Box, Color, Compound, export_step
    # Color on the assembly wrapper, as on the robot's wheels and shell parts.
    black = Compound(label='black wheel', children=[Box(10, 20, 30)])
    black.color = Color(.08, .09, .11)
    blue = Compound(label='blue enclosure', children=[Box(15, 20, 30).translate((30, 0, 0))])
    blue.color = Color(.035, .34, .70)
    step, glb = tmp_path/'assembly-colors.step', tmp_path/'assembly-colors.glb'
    export_step(Compound(children=[black, blue]), step)
    export_scene(step, glb)
    doc = glb_document(glb)
    colors = [m['pbrMetallicRoughness']['baseColorFactor'] for m in doc['materials']]
    assert any(c == pytest.approx([.08, .09, .11, 1], abs=1e-6) for c in colors)
    assert any(c == pytest.approx([.035, .34, .70, 1], abs=1e-6) for c in colors)


def test_capture_tools_use_project_storage_without_legacy_loader(monkeypatch, tmp_path):
    from flow_cad.mcp import server
    import importlib
    registry = importlib.import_module('flow_cad.tools.registry')
    root, _, _ = _step_project(tmp_path)
    monkeypatch.setenv('FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS', str(root))
    def forbidden(*args, **kwargs):
        raise AssertionError('screen capture must not load legacy project/runtime')
    for module in (server, registry):
        monkeypatch.setattr(module, 'ViewerService', forbidden)
        service = module.agent_screen_service(str(root))
        assert service.project_root == root
        assert service.request_capture({'purpose': 'colors'})['status'] == 'pending'
        with pytest.raises(ValueError, match='outside allowed'):
            module.agent_screen_service(str(tmp_path/'outside'))
