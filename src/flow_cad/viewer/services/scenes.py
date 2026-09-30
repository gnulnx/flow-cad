"""Revision-bound display scenes prepared by the shared CAD process pool."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

from flow_cad.measurement.service import ExactFeatureService

# v3 discards direct previews written with sRGB factors by build123d 0.13.
SCENE_VERSION = 3


class DisplaySceneService:
    def __init__(self, root: Path, pool=None):
        self.root = root.resolve()
        self.authority = ExactFeatureService(root)
        self.cache = self.root / ".flow/cache/display-scenes" / f"v{SCENE_VERSION}"
        self.pool = pool
        self._locks = {}
        self._locks_guard = threading.Lock()

    def paths(self, revision):
        return self.cache / f"{revision}.glb", self.cache / f"{revision}.json"

    def lookup(self, part_uuid, revision):
        binding = self.authority.resolve_binding(part_uuid, revision)
        glb, metadata = self.paths(binding.artifact_revision)
        try:
            payload = json.loads(metadata.read_text())
            source = self.authority._safe_artifact_path(binding)
            if (payload["artifact_revision"] != revision or payload["version"] != SCENE_VERSION
                    or glb.stat().st_size != payload["byte_count"]):
                return binding, None
            stat = source.stat()
            identity = [stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
            if payload.get("source_identity") != identity:
                self.authority._verified_artifact(binding)
        except (OSError, ValueError, KeyError, TypeError):
            return binding, None
        return binding, payload

    def publish(self, binding, output, stats):
        """Publish a completed preview only while its exact source is still current."""
        self.authority.resolve_binding(binding.part_uuid, binding.artifact_revision)
        source, _ = self.authority._verified_artifact(binding)
        stat = source.stat()
        payload = {**stats, 'status': 'ready', 'version': SCENE_VERSION,
                   'artifact_revision': binding.artifact_revision,
                   'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                   'byte_count': output.stat().st_size,
                   'source_identity': [stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]}
        self.cache.mkdir(parents=True, exist_ok=True)
        glb, metadata = self.paths(binding.artifact_revision)
        with tempfile.TemporaryDirectory(prefix='publish-', dir=self.cache) as temporary:
            pending = Path(temporary) / 'metadata.json'
            pending.write_text(json.dumps(payload))
            os.replace(output, glb)
            os.replace(pending, metadata)
        return payload

    def build(self, binding, context):
        with self._locks_guard:
            lock = self._locks.setdefault(binding.artifact_revision, threading.Lock())
        while not lock.acquire(timeout=.05):
            context.checkpoint()
        owned_pool = None
        try:
            context.checkpoint()
            _, cached = self.lookup(binding.part_uuid, binding.artifact_revision)
            if cached:
                return cached
            context.report('verify_step', .05, 'Verifying STEP colors and components')
            source, _ = self.authority._verified_artifact(binding)
            pool = self.pool
            if pool is None:
                from flow_cad.config import load_flow_config
                from flow_cad.workers.pool import CadWorkerPool
                pool = owned_pool = CadWorkerPool(self.root, load_flow_config(self.root))
            self.cache.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='scene-', dir=self.cache) as temporary:
                output = Path(temporary) / 'scene.glb'
                context.report('display_scene', .15, 'Preparing component colors')
                stats = pool.run('scene', (source, output), context, priority=10)
                context.checkpoint()
                context.report('publish_scene', .95, 'Publishing component colors')
                return self.publish(binding, output, stats)
        finally:
            lock.release()
            if owned_pool is not None:
                owned_pool.close()
