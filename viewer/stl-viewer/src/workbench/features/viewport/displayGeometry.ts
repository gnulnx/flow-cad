import { ResourceCache } from './resourceCache'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'

export interface DisplayComponent {
  id: string
  label: string
  geometry: THREE.BufferGeometry
  color: THREE.Color
  opacity: number
}

export async function parseDisplay(bytes: ArrayBuffer, format: 'stl' | 'glb'): Promise<DisplayComponent[]> {
  if (format === 'stl') {
    const geometry = new STLLoader().parse(bytes)
    if (!geometry.getAttribute('normal')) geometry.computeVertexNormals()
    return [{ id: 'mesh', label: 'STL mesh', geometry, color: new THREE.Color('#7792a3'), opacity: 1 }]
  }
  const gltf = await new GLTFLoader().parseAsync(bytes, '')
  gltf.scene.rotation.x = Math.PI / 2
  gltf.scene.scale.setScalar(1000)
  gltf.scene.updateMatrixWorld(true)
  const result: DisplayComponent[] = []
  const usages = new Map<THREE.BufferGeometry, number>()
  gltf.scene.traverse((object) => {
    if (object instanceof THREE.Mesh) usages.set(object.geometry, (usages.get(object.geometry) ?? 0) + 1)
  })
  gltf.scene.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return
    const material = (Array.isArray(object.material) ? object.material[0] : object.material) as THREE.MeshStandardMaterial
    // GLTF may instance a geometry: only copy when another node owns it too.
    const shared = usages.get(object.geometry)! > 1
    const geometry = (shared ? object.geometry.clone() : object.geometry).applyMatrix4(object.matrixWorld)
    if (!geometry.getAttribute('normal')) geometry.computeVertexNormals()
    result.push({ id: object.userData.componentId ?? String(result.length),
      label: object.userData.label ?? object.name ?? 'Component', geometry,
      color: material.color.clone(), opacity: material.opacity })

    for (const item of Array.isArray(object.material) ? object.material : [object.material]) item.dispose()
  })
  usages.forEach((count, geometry) => { if (count > 1) geometry.dispose() })
  if (!result.length) throw new Error('Color display contains no components')
  return result
}


export const displayGeometryCache = new ResourceCache<DisplayComponent[]>(256 * 1024 * 1024,
  (items) => items.forEach((item) => item.geometry.dispose()))
const pending = new Map<string, Promise<DisplayComponent[]>>()

export async function acquireDisplay(key: string, bytes: ArrayBuffer, format: 'stl' | 'glb') {
  const cached = displayGeometryCache.get(key)
  if (cached) return { items: cached, release: displayGeometryCache.retain(key)! }
  let loading = pending.get(key)
  if (!loading) {
    loading = parseDisplay(bytes, format)
    pending.set(key, loading)
  }
  try {
    const items = await loading
    const buffers = new Set<ArrayBufferLike>()
    items.forEach(({ geometry }) => {
      Object.values(geometry.attributes).forEach((attribute) => buffers.add(attribute.array.buffer))
      if (geometry.index) buffers.add(geometry.index.array.buffer)
      geometry.computeBoundingBox()
    })
    const size = [...buffers].reduce((sum, buffer) => sum + buffer.byteLength, 0)
    return { items, release: displayGeometryCache.lease(key, items, size) }
  } finally {
    if (pending.get(key) === loading) pending.delete(key)
  }
}
