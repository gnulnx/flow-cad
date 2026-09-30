import { act, createRoot, extend } from '@react-three/fiber'
import { waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import * as THREE from 'three'
import { AssemblyModel, componentKey, describeComponents } from './ModelCanvas'
import * as display from './displayGeometry'
import type { LoadedAssemblyPart } from './useAssemblyDisplayQueue'
import type { WorkbenchPart } from '../../contracts'

extend(THREE)
afterEach(() => { vi.restoreAllMocks(); display.displayGeometryCache.clear() })

const model: LoadedAssemblyPart = {
  key: 'view:revision-1',
  part: { uuid: 'view', key: 'saved_view', displayArtifact: { contentHash: 'revision-1' } } as WorkbenchPart,
  occurrences: [
    { id: 'left', assemblyId: 'active', translationMm: [0, 0, 0], rotationDeg: [0, 0, 0] },
    { id: 'right', assemblyId: 'active', translationMm: [20, 0, 0], rotationDeg: [0, 0, 90] },
  ],
  artifactBytes: new TextEncoder().encode('solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 10 0\nendloop\nendfacet\nendsolid triangle').buffer,
  format: 'stl',
}

it('keeps real R3F meshes and cache leases across hide/show, and hidden parts cannot block ray picking', async () => {
  const acquire = vi.spyOn(display, 'acquireDisplay')
  const canvas = document.createElement('canvas')
  const gl = { render: vi.fn(), setPixelRatio: vi.fn(), setSize: vi.fn(), domElement: canvas,
    forceContextLoss: vi.fn(), renderLists: { dispose: vi.fn() } } as unknown as THREE.WebGLRenderer
  const root = createRoot(canvas).configure({ gl, frameloop: 'never', size: { width: 400, height: 300, top: 0, left: 0 } })
  const props = { model, selectedKey: null, measureMode: false, onSelect: vi.fn(), onReady: vi.fn(), onRemoved: vi.fn(), onError: vi.fn() }
  let store: ReturnType<typeof root.render>
  const renderScene = async (hiddenKeys: Set<string>, nextModel = model) => {
    await act(async () => { store = root.render(<AssemblyModel {...props} model={nextModel} hiddenKeys={hiddenKeys} />) })
  }
  const meshes = () => {
    const items: THREE.Mesh[] = []
    store.getState().scene.traverse((object) => { if (object instanceof THREE.Mesh) items.push(object) })
    return items
  }
  await renderScene(new Set())
  await waitFor(() => expect(meshes()).toHaveLength(2))
  expect(props.onError).not.toHaveBeenCalled()
  const [left, right] = meshes()
  expect(left.geometry).toBe(right.geometry)
  const geometry = left.geometry
  const dispose = vi.spyOn(geometry, 'dispose')
  const key = componentKey(model.key, 'left', 'mesh', 0)
  const worldPosition = right.getWorldPosition(new THREE.Vector3()).toArray()
  expect(worldPosition).toEqual([20, 0, 0])

  await renderScene(new Set([key]))
  expect(meshes()[0]).toBe(left)
  expect(left.visible).toBe(false)
  expect(right.visible).toBe(true)
  const ray = new THREE.Raycaster(new THREE.Vector3(2, 2, 10), new THREE.Vector3(0, 0, -1))
  store!.getState().scene.updateMatrixWorld(true)
  expect(ray.intersectObject(left)).toHaveLength(0)

  await renderScene(new Set([key, componentKey(model.key, 'right', 'mesh', 0)]))
  expect(meshes().every((mesh) => !mesh.visible)).toBe(true)
  display.displayGeometryCache.clear() // active lease protects even a wholly hidden view
  expect(dispose).not.toHaveBeenCalled()
  await renderScene(new Set())
  expect(meshes()[0].geometry).toBe(geometry)
  expect(meshes().every((mesh) => mesh.visible)).toBe(true)
  expect(ray.intersectObject(left)).toHaveLength(1)
  expect(right.getWorldPosition(new THREE.Vector3()).toArray()).toEqual(worldPosition)
  expect(acquire).toHaveBeenCalledTimes(1)
  expect(props.onRemoved).not.toHaveBeenCalled()

  const handlers = (left as THREE.Mesh & { __r3f: { handlers: { onClick(event: object): void } } }).__r3f.handlers
  handlers.onClick({ delta: 8, button: 0, stopPropagation: vi.fn() })
  expect(props.onSelect).not.toHaveBeenCalled()
  handlers.onClick({ delta: 0, button: 0, stopPropagation: vi.fn() })
  expect(props.onSelect).toHaveBeenCalledWith(key)

  await renderScene(new Set(), { ...model, key: 'view:revision-2' })
  expect(acquire).toHaveBeenCalledTimes(2)
  await act(async () => root.unmount())
  expect(props.onRemoved).toHaveBeenCalled()
})

it('describes every nested component and repeated occurrence with distinct identities and installed bounds', () => {
  const items = [0, 1].map(() => ({ id: 'duplicate-id', label: 'motor_cover', geometry: new THREE.BoxGeometry(2, 4, 6), color: new THREE.Color('#aaaaaa'), opacity: 1 }))
  const components = describeComponents(model, items)
  expect(components).toHaveLength(4)
  expect(new Set(components.map((item) => item.key)).size).toBe(4)
  expect(components.map((item) => item.label)).toEqual(['motor cover (1)', 'motor cover (2)', 'motor cover (3)', 'motor cover (4)'])
  expect(components[2].bounds.min[0]).toBeCloseTo(18)
  expect(components[2].bounds.max[1]).toBeCloseTo(1)
  items.forEach((item) => item.geometry.dispose())
})
