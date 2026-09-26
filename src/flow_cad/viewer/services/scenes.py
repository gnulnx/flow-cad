"""Revision-bound display scenes built in serial disposable processes."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from flow_cad.measurement.service import ExactFeatureService

SCENE_VERSION = 1


class DisplaySceneService:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.authority = ExactFeatureService(root)
        self.cache = self.root / ".flow/cache/display-scenes" / f"v{SCENE_VERSION}"
        self.slot = threading.Lock()

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

    def build(self, binding, context):
        while not self.slot.acquire(timeout=.2):
            context.checkpoint()
        try:
            context.checkpoint()
            _, cached = self.lookup(binding.part_uuid, binding.artifact_revision)
            if cached:
                return cached
            context.report("verify_step", .05, "Verifying STEP colors and components")
            source, _ = self.authority._verified_artifact(binding)
            self.cache.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="scene-", dir=self.cache) as temporary:
                output = Path(temporary) / "scene.glb"
                with (Path(temporary) / "worker.log").open("w+") as log:
                    context.report("display_scene", .15, "Preparing component colors")
                    process = subprocess.Popen(
                        [sys.executable, "-m", "flow_cad.viewer.scene_export", str(source), str(output)],
                        stdout=log, stderr=log,
                        env={**os.environ, "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "1"},
                    )
                    try:
                        while process.poll() is None:
                            context.checkpoint()
                            try:
                                process.wait(timeout=.2)
                            except subprocess.TimeoutExpired:
                                pass
                        log.seek(0)
                        lines = log.read()
                        if process.returncode:
                            raise RuntimeError(f"Display conversion failed: {lines[-1500:]}")
                        stats = json.loads(lines.strip().splitlines()[-1])
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                context.checkpoint()
                self.authority.resolve_binding(binding.part_uuid, binding.artifact_revision)
                self.authority._verified_artifact(binding)
                stat = source.stat()
                payload = {**stats, "status": "ready", "version": SCENE_VERSION,
                           "artifact_revision": binding.artifact_revision,
                           "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                           "byte_count": output.stat().st_size,
                           "source_identity": [stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]}
                glb, metadata = self.paths(binding.artifact_revision)
                pending = Path(temporary) / "metadata.json"
                pending.write_text(json.dumps(payload))
                context.report("publish_scene", .95, "Publishing component colors")
                os.replace(output, glb)
                os.replace(pending, metadata)
                return payload
        finally:
            self.slot.release()
