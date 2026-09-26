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
    geometry.computeVertexNormals()
    return [{ id: 'mesh', label: 'STL mesh', geometry, color: new THREE.Color('#7792a3'), opacity: 1 }]
  }
  const gltf = await new GLTFLoader().parseAsync(bytes, '')
  gltf.scene.rotation.x = Math.PI / 2
  gltf.scene.scale.setScalar(1000)
  gltf.scene.updateMatrixWorld(true)
  const result: DisplayComponent[] = []
  gltf.scene.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return
    const material = (Array.isArray(object.material) ? object.material[0] : object.material) as THREE.MeshStandardMaterial
    const geometry = object.geometry.clone().applyMatrix4(object.matrixWorld)
    geometry.computeVertexNormals()
    result.push({ id: object.userData.componentId ?? String(result.length),
      label: object.userData.label ?? object.name ?? 'Component', geometry,
      color: material.color.clone(), opacity: material.opacity })
    object.geometry.dispose()
    for (const item of Array.isArray(object.material) ? object.material : [object.material]) item.dispose()
  })
  if (!result.length) throw new Error('Color display contains no components')
  return result
}

