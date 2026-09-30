import { readFileSync } from 'node:fs'
import process from 'node:process'
import { act, createRoot, extend } from '@react-three/fiber'
import { expect, it, vi } from 'vitest'
import * as THREE from 'three'
import { AssemblyModel, describeComponents } from '../src/workbench/features/viewport/ModelCanvas'
import { displayGeometryCache, type DisplayComponent } from '../src/workbench/features/viewport/displayGeometry'
import type { WorkbenchPart } from '../src/workbench/contracts'
import type { LoadedAssemblyPart } from '../src/workbench/features/viewport/useAssemblyDisplayQueue'

// Optional downstream artifact acceptance; no product paths or fixtures in the runtime.
const fixturePath = process.env.FLOW_CAD_INSPECTION_GLB
extend(THREE)

it.skipIf(!fixturePath)('hides and restores every component of the supplied GLB in the real R3F scene graph', async () => {
  const bytes = readFileSync(fixturePath!)
  const model: LoadedAssemblyPart = {
    key: 'external-fixture:revision', format: 'glb', artifactBytes: Uint8Array.from(bytes).buffer,
    part: { uuid: 'external-fixture', key: 'external_fixture', displayArtifact: { contentHash: 'fixture-sha' } } as WorkbenchPart,
    occurrences: [{ id: 'fixture-occurrence', assemblyId: 'active', translationMm: [0, 0, 0], rotationDeg: [0, 0, 0] }],
  }
  const canvas = document.createElement('canvas')
  const gl = { render: vi.fn(), setPixelRatio: vi.fn(), setSize: vi.fn(), domElement: canvas,
    forceContextLoss: vi.fn(), renderLists: { dispose: vi.fn() } } as unknown as THREE.WebGLRenderer
  const root = createRoot(canvas).configure({ gl, frameloop: 'never', size: { width: 1000, height: 700, top: 0, left: 0 } })
  let items: DisplayComponent[] = []
  const props = { model, selectedKey: null, measureMode: false, onSelect: vi.fn(),
    onReady: (_key: string, _uuid: string, components: DisplayComponent[]) => { items = components }, onRemoved: vi.fn(), onError: vi.fn() }
  let store: ReturnType<typeof root.render>
  const renderScene = async (hiddenKeys: Set<string>) => {
    await act(async () => { store = root.render(<AssemblyModel {...props} hiddenKeys={hiddenKeys} />) })
  }
  const meshes = () => {
    const result: THREE.Mesh[] = []
    store.getState().scene.traverse((object) => { if (object instanceof THREE.Mesh) result.push(object) })
    return result
  }
  await renderScene(new Set())
  expect(props.onError).not.toHaveBeenCalled()
  expect(items.length).toBeGreaterThan(1)
  if (process.env.FLOW_CAD_INSPECTION_COMPONENT_COUNT) expect(items.length).toBe(Number(process.env.FLOW_CAD_INSPECTION_COMPONENT_COUNT))
  const components = describeComponents(model, items)
  expect(new Set(components.map((item) => item.key)).size).toBe(items.length)
  expect(meshes()).toHaveLength(items.length)
  const original = meshes()
  const positions = original.map((mesh) => Array.from(mesh.geometry.getAttribute('position').array))
  const colors = original.map((mesh) => (mesh.material as THREE.MeshStandardMaterial).color.getHexString())
  await renderScene(new Set(components.slice(1).map((item) => item.key)))
  expect(meshes().filter((mesh) => mesh.visible)).toHaveLength(1)
  await renderScene(new Set(components.map((item) => item.key)))
  expect(meshes().every((mesh) => !mesh.visible)).toBe(true)
  displayGeometryCache.clear()
  await renderScene(new Set())
  expect(meshes().every((mesh) => mesh.visible)).toBe(true)
  meshes().forEach((mesh, index) => {
    expect(mesh).toBe(original[index])
    expect(Array.from(mesh.geometry.getAttribute('position').array)).toEqual(positions[index])
    expect((mesh.material as THREE.MeshStandardMaterial).color.getHexString()).toBe(colors[index])
  })
  expect(props.onRemoved).not.toHaveBeenCalled()
  console.info(`GLB acceptance: ${components.length} components; isolate, hide all, restore; identical geometry and colors.`)
  await act(async () => root.unmount())
  displayGeometryCache.clear()
}, 30000)
