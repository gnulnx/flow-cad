import type { BufferGeometry, Vector3 } from 'three'

export interface ModelData {
  name: string
  geometry: BufferGeometry
  color: string
  wireframeColor: string
  bounds: {
    min: Vector3
    max: Vector3
    size: Vector3
    center: Vector3
  }
}
