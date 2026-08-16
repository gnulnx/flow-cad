#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URDF = Path.home() / "BLR" / "DojoV2" / "src" / "dojo" / "assets" / "B2_v2.urdf"
THREE_ROOT = REPO_ROOT / "viewer" / "stl-viewer" / "node_modules" / "three"


def _is_within(path: Path, root: Path) -> bool:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def _resolve_urdf(path_text: str) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    if path.suffix.lower() != ".urdf":
        raise ValueError("Path must end with .urdf")
    if not (_is_within(path, Path.home()) or _is_within(path, REPO_ROOT)):
        raise ValueError(f"Path must be under {Path.home()} or {REPO_ROOT}")
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    return path


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Quick URDF Viewer</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0b0f14;
      color: #e5edf5;
    }
    body { margin: 0; min-height: 100vh; overflow: hidden; }
    #app { display: grid; grid-template-rows: auto 1fr; width: 100vw; height: 100vh; }
    .toolbar {
      display: grid;
      grid-template-columns: minmax(180px, 1fr) auto auto auto auto;
      gap: 8px;
      align-items: center;
      padding: 10px 12px;
      background: #111820;
      border-bottom: 1px solid #233141;
    }
    input[type="text"] {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid #334457;
      border-radius: 6px;
      padding: 8px 10px;
      background: #0b1118;
      color: #e5edf5;
      font-size: 13px;
    }
    button, .file-label {
      border: 1px solid #334457;
      border-radius: 6px;
      padding: 8px 10px;
      background: #172231;
      color: #e5edf5;
      font-size: 13px;
      cursor: pointer;
      white-space: nowrap;
    }
    button:hover, .file-label:hover { border-color: #4f84c4; background: #1b2a3b; }
    .file-label input { display: none; }
    .toggle {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: #cbd6e2;
      font-size: 13px;
      white-space: nowrap;
    }
    .main { position: relative; min-height: 0; }
    #canvas { width: 100%; height: 100%; display: block; }
    .panel {
      position: absolute;
      top: 14px;
      right: 14px;
      width: min(360px, calc(100vw - 28px));
      max-height: calc(100vh - 92px);
      overflow: auto;
      border: 1px solid #263646;
      border-radius: 8px;
      background: rgba(10, 15, 21, 0.92);
      box-shadow: 0 18px 42px rgba(0, 0, 0, 0.35);
    }
    .panel h1 {
      margin: 0;
      padding: 12px 14px;
      font-size: 14px;
      font-weight: 700;
      border-bottom: 1px solid #263646;
    }
    .stats, .list { padding: 12px 14px; }
    .stats {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      border-bottom: 1px solid #263646;
    }
    .stat { border: 1px solid #253646; border-radius: 6px; padding: 8px; background: #0f1720; }
    .stat strong { display: block; font-size: 18px; color: #f8fbff; }
    .stat span { display: block; margin-top: 2px; font-size: 11px; color: #9fb0c1; }
    .list h2 { margin: 0 0 8px; font-size: 12px; color: #9fb0c1; text-transform: uppercase; letter-spacing: 0; }
    .list ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 5px; }
    .list li { font-size: 12px; color: #d8e3ee; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 5px; }
    .error {
      position: absolute;
      left: 14px;
      bottom: 14px;
      max-width: min(720px, calc(100vw - 28px));
      border: 1px solid #7f1d1d;
      border-radius: 8px;
      padding: 10px 12px;
      background: rgba(69, 10, 10, 0.92);
      color: #fecaca;
      font-size: 13px;
      display: none;
    }
    @media (max-width: 760px) {
      .toolbar { grid-template-columns: 1fr 1fr; }
      .toolbar input[type="text"] { grid-column: 1 / -1; }
      .panel { top: auto; bottom: 14px; max-height: 42vh; }
    }
  </style>
</head>
<body>
  <div id="app">
    <div class="toolbar">
      <input id="path" type="text" />
      <button id="loadPath">Load Path</button>
      <label class="file-label">Open File<input id="file" type="file" accept=".urdf,.xml" /></label>
      <label class="toggle"><input id="showVisuals" type="checkbox" checked /> Visual</label>
      <label class="toggle"><input id="showCollisions" type="checkbox" checked /> Collision</label>
    </div>
    <div class="main">
      <canvas id="canvas"></canvas>
      <aside class="panel">
        <h1 id="title">Quick URDF Viewer</h1>
        <div class="stats">
          <div class="stat"><strong id="linkCount">0</strong><span>links</span></div>
          <div class="stat"><strong id="jointCount">0</strong><span>joints</span></div>
          <div class="stat"><strong id="visualCount">0</strong><span>visuals</span></div>
          <div class="stat"><strong id="collisionCount">0</strong><span>collisions</span></div>
        </div>
        <div class="list">
          <h2>Chassis Collisions</h2>
          <ul id="collisionList"></ul>
        </div>
      </aside>
      <div id="error" class="error"></div>
    </div>
  </div>
  <script type="module">
    import * as THREE from '/node_modules/three/build/three.module.js'
    import { OrbitControls } from '/node_modules/three/examples/jsm/controls/OrbitControls.js'

    const defaultPath = __DEFAULT_PATH__
    const pathInput = document.getElementById('path')
    const loadPathButton = document.getElementById('loadPath')
    const fileInput = document.getElementById('file')
    const showVisuals = document.getElementById('showVisuals')
    const showCollisions = document.getElementById('showCollisions')
    const errorBox = document.getElementById('error')
    const canvas = document.getElementById('canvas')

    pathInput.value = defaultPath

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setClearColor(0x0b0f14, 1)
    const scene = new THREE.Scene()
    scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 2.5))
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.8)
    keyLight.position.set(2, 3, 5)
    scene.add(keyLight)
    const camera = new THREE.PerspectiveCamera(45, 1, 0.001, 100)
    camera.position.set(0.75, -1.1, 0.72)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.target.set(0, 0, 0.12)
    scene.add(new THREE.GridHelper(1.2, 24, 0x334155, 0x1f2937))

    const modelGroup = new THREE.Group()
    scene.add(modelGroup)

    function setError(message) {
      errorBox.style.display = message ? 'block' : 'none'
      errorBox.textContent = message || ''
    }

    function parseNumbers(text, fallback = []) {
      if (!text) return fallback
      const values = text.trim().split(/\s+/).map(Number)
      return values.every(Number.isFinite) ? values : fallback
    }

    function originMatrix(element) {
      const origin = element.querySelector(':scope > origin')
      const xyz = parseNumbers(origin?.getAttribute('xyz'), [0, 0, 0])
      const rpy = parseNumbers(origin?.getAttribute('rpy'), [0, 0, 0])
      const matrix = new THREE.Matrix4()
      const position = new THREE.Vector3(xyz[0], xyz[1], xyz[2])
      const quaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(rpy[0], rpy[1], rpy[2], 'XYZ'))
      matrix.compose(position, quaternion, new THREE.Vector3(1, 1, 1))
      return matrix
    }

    function colorForVisual(element, materials) {
      const materialName = element.querySelector(':scope > material')?.getAttribute('name')
      return materials.get(materialName) || { color: 0x4f8cc9, opacity: 0.48 }
    }

    function geometryFromElement(element) {
      const geometry = element.querySelector(':scope > geometry')
      if (!geometry) return null
      const box = geometry.querySelector(':scope > box')
      if (box) {
        const size = parseNumbers(box.getAttribute('size'))
        if (size.length === 3) return new THREE.BoxGeometry(size[0], size[1], size[2])
      }
      const cylinder = geometry.querySelector(':scope > cylinder')
      if (cylinder) {
        const radius = Number(cylinder.getAttribute('radius'))
        const length = Number(cylinder.getAttribute('length'))
        if (Number.isFinite(radius) && Number.isFinite(length)) {
          const shape = new THREE.CylinderGeometry(radius, radius, length, 48)
          shape.rotateX(Math.PI / 2)
          return shape
        }
      }
      const sphere = geometry.querySelector(':scope > sphere')
      if (sphere) {
        const radius = Number(sphere.getAttribute('radius'))
        if (Number.isFinite(radius)) return new THREE.SphereGeometry(radius, 32, 16)
      }
      return null
    }

    function parseUrdf(xmlText) {
      const documentXml = new DOMParser().parseFromString(xmlText, 'application/xml')
      const parserError = documentXml.querySelector('parsererror')
      if (parserError) throw new Error(parserError.textContent.trim())
      const robot = documentXml.querySelector('robot')
      if (!robot) throw new Error('No <robot> root found.')

      const materials = new Map()
      for (const material of robot.querySelectorAll(':scope > material')) {
        const name = material.getAttribute('name')
        const rgba = parseNumbers(material.querySelector('color')?.getAttribute('rgba'))
        if (name && rgba.length >= 3) {
          materials.set(name, {
            color: new THREE.Color(rgba[0], rgba[1], rgba[2]),
            opacity: Number.isFinite(rgba[3]) ? rgba[3] : 1,
          })
        }
      }

      const links = new Map()
      for (const link of robot.querySelectorAll(':scope > link')) {
        const name = link.getAttribute('name')
        if (name) links.set(name, link)
      }

      const children = new Set()
      const jointsByParent = new Map()
      const joints = Array.from(robot.querySelectorAll(':scope > joint')).map((joint) => {
        const parent = joint.querySelector(':scope > parent')?.getAttribute('link')
        const child = joint.querySelector(':scope > child')?.getAttribute('link')
        if (child) children.add(child)
        const record = { name: joint.getAttribute('name') || '', parent, child, element: joint }
        if (parent) {
          const bucket = jointsByParent.get(parent) || []
          bucket.push(record)
          jointsByParent.set(parent, bucket)
        }
        return record
      })
      const rootLink = Array.from(links.keys()).find((name) => !children.has(name)) || Array.from(links.keys())[0]
      const linkWorld = new Map()
      linkWorld.set(rootLink, new THREE.Matrix4())
      const queue = [rootLink]
      while (queue.length) {
        const parent = queue.shift()
        const parentWorld = linkWorld.get(parent)
        for (const joint of jointsByParent.get(parent) || []) {
          if (!joint.child || !parentWorld) continue
          linkWorld.set(joint.child, parentWorld.clone().multiply(originMatrix(joint.element)))
          queue.push(joint.child)
        }
      }

      const visuals = []
      const collisions = []
      for (const [linkName, linkElement] of links) {
        const world = linkWorld.get(linkName) || new THREE.Matrix4()
        for (const visual of linkElement.querySelectorAll(':scope > visual')) {
          const geometry = geometryFromElement(visual)
          if (!geometry) continue
          visuals.push({
            kind: 'visual',
            linkName,
            name: visual.getAttribute('name') || linkName,
            geometry,
            matrix: world.clone().multiply(originMatrix(visual)),
            material: colorForVisual(visual, materials),
          })
        }
        for (const collision of linkElement.querySelectorAll(':scope > collision')) {
          const geometry = geometryFromElement(collision)
          if (!geometry) continue
          collisions.push({
            kind: 'collision',
            linkName,
            name: collision.getAttribute('name') || linkName,
            geometry,
            matrix: world.clone().multiply(originMatrix(collision)),
          })
        }
      }
      return { robotName: robot.getAttribute('name') || 'robot', links, joints, visuals, collisions }
    }

    function clearModel() {
      for (const child of [...modelGroup.children]) {
        modelGroup.remove(child)
        child.traverse?.((object) => {
          if (object.geometry) object.geometry.dispose()
          if (object.material) object.material.dispose?.()
        })
      }
    }

    function addPrimitive(record) {
      const material = record.kind === 'collision'
        ? new THREE.MeshStandardMaterial({ color: 0xf97316, transparent: true, opacity: 0.28, roughness: 0.9 })
        : new THREE.MeshStandardMaterial({
          color: record.material.color,
          transparent: record.material.opacity < 1,
          opacity: record.material.opacity,
          roughness: 0.7,
          metalness: 0.1,
        })
      const mesh = new THREE.Mesh(record.geometry, material)
      mesh.applyMatrix4(record.matrix)
      mesh.userData.kind = record.kind
      modelGroup.add(mesh)
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(record.geometry, 20),
        new THREE.LineBasicMaterial({ color: record.kind === 'collision' ? 0xffc266 : 0x8fc7ff }),
      )
      edges.applyMatrix4(record.matrix)
      edges.userData.kind = record.kind
      modelGroup.add(edges)
    }

    function fitCamera() {
      const box = new THREE.Box3().setFromObject(modelGroup)
      if (box.isEmpty()) return
      const center = box.getCenter(new THREE.Vector3())
      const size = box.getSize(new THREE.Vector3())
      const radius = Math.max(size.x, size.y, size.z, 0.1)
      controls.target.copy(center)
      camera.position.copy(center).add(new THREE.Vector3(radius * 1.4, -radius * 2.0, radius * 1.25))
      camera.near = Math.max(radius / 200, 0.001)
      camera.far = Math.max(radius * 20, 10)
      camera.updateProjectionMatrix()
      controls.update()
    }

    function updateVisibility() {
      const wantVisuals = showVisuals.checked
      const wantCollisions = showCollisions.checked
      modelGroup.traverse((object) => {
        if (object.userData.kind === 'visual') object.visible = wantVisuals
        if (object.userData.kind === 'collision') object.visible = wantCollisions
      })
    }

    function renderUrdf(xmlText, label) {
      clearModel()
      const model = parseUrdf(xmlText)
      for (const record of model.visuals) addPrimitive(record)
      for (const record of model.collisions) addPrimitive(record)
      document.getElementById('title').textContent = `${model.robotName} ${label ? '- ' + label : ''}`
      document.getElementById('linkCount').textContent = String(model.links.size)
      document.getElementById('jointCount').textContent = String(model.joints.length)
      document.getElementById('visualCount').textContent = String(model.visuals.length)
      document.getElementById('collisionCount').textContent = String(model.collisions.length)
      const list = document.getElementById('collisionList')
      list.replaceChildren(...model.collisions
        .filter((item) => item.linkName === 'chassis_link')
        .slice(0, 80)
        .map((item) => {
          const li = document.createElement('li')
          li.textContent = item.name
          return li
        }))
      updateVisibility()
      fitCamera()
      setError('')
    }

    async function loadFromPath() {
      const path = pathInput.value.trim()
      const response = await fetch(`/api/urdf?path=${encodeURIComponent(path)}`)
      const payload = await response.json()
      if (!response.ok || !payload.ok) throw new Error(payload.error || `Failed to load ${path}`)
      renderUrdf(payload.xml, payload.path)
    }

    loadPathButton.addEventListener('click', () => loadFromPath().catch((error) => setError(error.message)))
    pathInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') loadFromPath().catch((error) => setError(error.message))
    })
    fileInput.addEventListener('change', async () => {
      const file = fileInput.files?.[0]
      if (!file) return
      try {
        renderUrdf(await file.text(), file.name)
      } catch (error) {
        setError(error.message)
      }
    })
    showVisuals.addEventListener('change', updateVisibility)
    showCollisions.addEventListener('change', updateVisibility)

    function resize() {
      const rect = canvas.getBoundingClientRect()
      renderer.setSize(rect.width, rect.height, false)
      camera.aspect = rect.width / Math.max(rect.height, 1)
      camera.updateProjectionMatrix()
    }
    window.addEventListener('resize', resize)
    function tick() {
      resize()
      controls.update()
      renderer.render(scene, camera)
      requestAnimationFrame(tick)
    }
    tick()
    loadFromPath().catch((error) => setError(error.message))
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    default_path: str = str(DEFAULT_URDF)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = HTML.replace("__DEFAULT_PATH__", json.dumps(self.default_path))
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/urdf":
            query = parse_qs(parsed.query)
            path_text = query.get("path", [self.default_path])[0]
            try:
                urdf_path = _resolve_urdf(path_text)
                self._send_json(200, {"ok": True, "path": str(urdf_path), "xml": urdf_path.read_text(encoding="utf-8")})
            except Exception as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
            return
        if parsed.path.startswith("/node_modules/three/"):
            relative = Path(unquote(parsed.path.removeprefix("/node_modules/three/")))
            candidate = (THREE_ROOT / relative).resolve()
            if _is_within(candidate, THREE_ROOT) and candidate.exists() and candidate.is_file():
                content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                self._send(200, candidate.read_bytes(), content_type)
                return
        if parsed.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        self._send_json(404, {"ok": False, "error": "not found"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Start a quick local URDF primitive viewer.")
    parser.add_argument("urdf", nargs="?", default=str(DEFAULT_URDF), help="Initial .urdf path to load.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()

    if not THREE_ROOT.exists():
        raise SystemExit(f"Missing Three.js dependency directory: {THREE_ROOT}")
    Handler.default_path = str(_resolve_urdf(args.urdf))
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Serving quick URDF viewer at {url}")
    print(f"Initial URDF: {Handler.default_path}")
    if args.open_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
