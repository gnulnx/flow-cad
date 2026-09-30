"""Real spawned-process contracts, including native-call cancellation boundaries."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import threading
import time

import pytest

from flow_cad.config import CadResources, default_flow_config, load_flow_config, write_flow_config, FlowCadConfigError
from flow_cad.jobs import JobCancelled
from flow_cad.jobs.executor import PriorityExecutor
from flow_cad.workers.pool import CadWorkerPool, CadWorkerError, source_revision
from flow_cad.build.worker import run_scoped_part_build
from flow_cad.build.service import plan_scoped_part_build
from flow_cad.registry.sync import sync_project
from flow_cad.sdk import dump_manifest
from test_scoped_part_build import _manifest, _project_root, _write_package


class Context:
    def __init__(self):
        self.cancel = threading.Event()
        self.phases = []
    def checkpoint(self):
        if self.cancel.is_set():
            raise JobCancelled('test cancellation')
    def report(self, *args):
        self.phases.append(args[0])
        self.checkpoint()


def fixture_plan(tmp_path, body='return Box(params.width, 5, 6)', *, stl=False):
    root = _project_root(tmp_path, 'worker_fixture')
    _write_package(root, 'worker_fixture',
        params_source='from dataclasses import dataclass\n@dataclass\nclass Params:\n    width: float = 4.0\ndef provide_params():\n    return Params()\n',
        parts_source='from build123d import Box\nfrom pathlib import Path\nimport os, time\ndef make_panel(params):\n    '+body.replace('\n','\n    ')+'\n')
    manifest = _manifest('worker_fixture', stl=stl)
    (root/'flowcad.project.yaml').write_text(dump_manifest(manifest))
    sync_project(root)
    return plan_scoped_part_build(root, manifest, manifest.parts[0])


def test_pool_reuses_process_and_invalidates_transitive_source(tmp_path):
    plan = fixture_plan(tmp_path)
    config = replace(default_flow_config(), cad=CadResources(workers=1))
    pool = CadWorkerPool(plan.project_root, config)
    try:
        first = run_scoped_part_build(plan, Context(), pool=pool)
        pid = pool._workers[0].process.pid
        second = run_scoped_part_build(plan, Context(), pool=pool)
        assert pool._workers[0].process.pid == pid
        assert second['artifacts'] == first['artifacts']
        assert second['display_preview_ready'] is True
        from flow_cad.viewer.services.scenes import DisplaySceneService
        _, preview = DisplaySceneService(plan.project_root).lookup(str(plan.part_uuid), second['artifacts'][0]['sha256'])
        assert preview['status'] == 'ready'
        # Same-size source edit, forcing an unchanged mtime to defeat timestamp pyc validation.
        params = plan.project_root/'worker_fixture/params.py'
        original = params.stat()
        params.write_text(params.read_text().replace('4.0', '9.0'))
        import os
        os.utime(params, ns=(original.st_atime_ns, original.st_mtime_ns))
        third = run_scoped_part_build(plan, Context(), pool=pool)
        assert pool._workers[0].process.pid != pid
        assert third['artifacts'][0]['sha256'] != first['artifacts'][0]['sha256']
    finally:
        pool.close()


def test_warm_assembly_build_preserves_artifact_identity_and_revision(tmp_path):
    plan = fixture_plan(tmp_path,
        "from build123d import Compound, Location\n"
        "left = Box(4, 5, 6)\nleft.label = 'left'\n"
        "right = Box(4, 5, 6).moved(Location((10, 0, 0)))\nright.label = 'right'\n"
        "return Compound(label='assembly', children=[left, right])", stl=True)
    pool = CadWorkerPool(plan.project_root,
                         replace(default_flow_config(), cad=CadResources(workers=1)))
    try:
        first = run_scoped_part_build(plan, Context(), pool=pool)
        pid = pool._workers[0].process.pid
        second = run_scoped_part_build(plan, Context(), pool=pool)
        assert pool._workers[0].process.pid == pid
        assert second['artifacts'] == first['artifacts']
        assert second['artifact_changed'] is False
        assert second['viewer_revision'] == first['viewer_revision']
    finally:
        pool.close()


def test_cancellation_kills_busy_worker_preserves_outputs_and_recovers(tmp_path):
    plan = fixture_plan(tmp_path, "Path('entered').write_text(str(os.getpid()))\ntime.sleep(30)\nreturn Box(4, 5, 6)")
    destination = plan.artifacts[0].destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b'previous known-good output')
    pool = CadWorkerPool(plan.project_root, replace(default_flow_config(), cad=CadResources(workers=1)))
    context = Context()
    try:
        with ThreadPoolExecutor(1) as threads:
            task = threads.submit(run_scoped_part_build, plan, context, pool=pool)
            deadline = time.monotonic()+15
            while not (plan.project_root/'entered').exists() and time.monotonic()<deadline:
                time.sleep(.02)
            assert (plan.project_root/'entered').exists()
            context.cancel.set()
            with pytest.raises(JobCancelled):
                task.result(timeout=3)
        assert destination.read_bytes() == b'previous known-good output'
        assert not list((plan.project_root/'.flow/build-work').iterdir())
        assert pool._workers[0].process is None
        parts = plan.project_root/'worker_fixture/parts.py'
        parts.write_text('from build123d import Box\ndef make_panel(params):\n    return Box(4,5,6)\n')
        result = run_scoped_part_build(plan, Context(), pool=pool)
        assert result['display_preview_ready']
    finally:
        pool.close()


def test_crashed_worker_is_replaceable(tmp_path):
    plan = fixture_plan(tmp_path, 'os._exit(7)')
    pool = CadWorkerPool(plan.project_root, default_flow_config())
    try:
        with pytest.raises(CadWorkerError, match='exited'):
            run_scoped_part_build(plan, Context(), pool=pool)
        assert not list((plan.project_root/'.flow/build-work').iterdir())
    finally:
        pool.close()


def test_memory_limit_terminates_only_offending_worker(tmp_path, monkeypatch):
    plan = fixture_plan(tmp_path)
    pool = CadWorkerPool(plan.project_root, default_flow_config())
    monkeypatch.setattr('flow_cad.workers.pool._rss_mb', lambda pid: 99999)
    try:
        with pytest.raises(CadWorkerError, match='memory budget'):
            run_scoped_part_build(plan, Context(), pool=pool)
        assert all(worker.process is None for worker in pool._workers)
    finally:
        pool.close()


def test_two_processes_overlap_and_cross_runner_slots_stay_bounded(tmp_path):
    plan = fixture_plan(tmp_path, "Path(f'entered-{os.getpid()}').touch()\nwhile not Path('release').exists(): time.sleep(.02)\nreturn Box(4,5,6)")
    pool = CadWorkerPool(plan.project_root, default_flow_config())
    joining = CadWorkerPool(plan.project_root, default_flow_config())
    contexts = [Context() for _ in range(3)]
    try:
        with ThreadPoolExecutor(3) as threads:
            tasks = []
            for i, context in enumerate(contexts):
                directory = plan.project_root/f'stage-{i}'; directory.mkdir()
                tasks.append(threads.submit((pool if i<2 else joining).run, 'prepare_part', (plan,directory), context))
            deadline = time.monotonic()+15
            while len(list(plan.project_root.glob('entered-*')))<2 and time.monotonic()<deadline:
                time.sleep(.02)
            assert len(list(plan.project_root.glob('entered-*'))) == 2
            time.sleep(.2)
            assert len(list(plan.project_root.glob('entered-*'))) == 2
            (plan.project_root/'release').touch()
            for task in tasks:
                assert task.result(timeout=15)['preview']
    finally:
        for context in contexts: context.cancel.set()
        pool.close(); joining.close()


def test_interactive_jobs_overtake_queued_background_jobs():
    executor = PriorityExecutor(1)
    entered, release = threading.Event(), threading.Event()
    order = []
    first = executor.submit(lambda: (entered.set(), release.wait(3)), priority=10)
    assert entered.wait(1)
    background = executor.submit(lambda: order.append('background'), priority=10)
    interactive = executor.submit(lambda: order.append('interactive'), priority=0)
    release.set()
    for task in (first, background, interactive): task.result(timeout=3)
    executor.shutdown()
    assert order == ['interactive','background']


def test_typed_resource_config_roundtrip_and_validation(tmp_path):
    target = tmp_path/'.flow/config.toml'
    config = replace(default_flow_config(), cad=CadResources(workers=1, memory_mb=3072, native_threads=2))
    write_flow_config(config, target)
    loaded = load_flow_config(tmp_path, user_path=tmp_path/'absent')
    assert loaded.cad == config.cad
    target.write_text('[cad]\nworkers = 0\n')
    with pytest.raises(FlowCadConfigError, match='positive integer'):
        load_flow_config(tmp_path, user_path=tmp_path/'absent')


def test_same_part_requests_serialize_before_claiming_a_cad_worker(tmp_path):
    plan = fixture_plan(tmp_path, "Path(f'entered-{os.getpid()}').touch()\nwhile not Path('release').exists(): time.sleep(.02)\nreturn Box(4,5,6)")
    pool = CadWorkerPool(plan.project_root, default_flow_config())
    first, second = Context(), Context()
    try:
        with ThreadPoolExecutor(2) as threads:
            a = threads.submit(run_scoped_part_build, plan, first, pool=pool)
            deadline = time.monotonic()+15
            while not list(plan.project_root.glob('entered-*')) and time.monotonic()<deadline:
                time.sleep(.02)
            assert len(list(plan.project_root.glob('entered-*'))) == 1
            b = threads.submit(run_scoped_part_build, plan, second, pool=pool)
            time.sleep(.1)
            second.cancel.set()
            with pytest.raises(JobCancelled): b.result(timeout=3)
            assert sum(w.busy for w in pool._workers) == 1
            (plan.project_root/'release').touch()
            assert a.result(timeout=15)['display_preview_ready']
    finally:
        first.cancel.set(); second.cancel.set(); pool.close()


def test_preview_is_not_inflated_by_fine_print_stl_tessellation(tmp_path):
    import json, struct
    plan = fixture_plan(tmp_path, 'from build123d import Sphere\nreturn Sphere(20)', stl=True)
    pool = CadWorkerPool(plan.project_root, default_flow_config())
    try:
        result = run_scoped_part_build(plan, Context(), pool=pool)
        assert result['display_preview_ready']
        from flow_cad.viewer.services.scenes import DisplaySceneService
        scene_path, _ = DisplaySceneService(plan.project_root).paths(result['artifacts'][0]['sha256'])
        data = scene_path.read_bytes()
        length = struct.unpack_from('<I', data, 12)[0]
        scene = json.loads(data[20:20+length])
        display_triangles = sum(scene['accessors'][m['primitives'][0]['indices']]['count']//3 for m in scene['meshes'])
        stl = plan.artifacts[1].destination.read_bytes()
        print_triangles = struct.unpack_from('<I',stl,80)[0]
        assert display_triangles < print_triangles/2
    finally:
        pool.close()
