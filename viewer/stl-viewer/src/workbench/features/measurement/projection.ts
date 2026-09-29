import * as THREE from 'three'
import type { Point3 } from '../../contracts'
import type { MeasurementPlane, MeasurementProjectionSource } from './measurement'

export function measurementProjection(camera: THREE.Camera, getRect: () => DOMRect): MeasurementProjectionSource {
  return {
    createProjector: () => {
      camera.updateMatrixWorld()
      const rect = getRect()
      const projected = new THREE.Vector3()
      const view = new THREE.Vector3()
      return (point) => {
        view.set(...point).applyMatrix4(camera.matrixWorldInverse)
        projected.set(...point).project(camera)
        return {
          x: rect.left + (projected.x + 1) * rect.width / 2,
          y: rect.top + (1 - projected.y) * rect.height / 2,
          depth: projected.z,
          clipW: camera instanceof THREE.PerspectiveCamera ? -view.z : 1,
          visible: projected.z >= -1 && projected.z <= 1,
        }
      }
    },
    pickPlanePoint: (x, y, plane, anchor) => {
      camera.updateMatrixWorld()
      const rect = getRect()
      if (!rect.width || !rect.height || x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null
      const normal = planeNormal(plane, camera)
      const raycaster = new THREE.Raycaster()
      raycaster.setFromCamera(new THREE.Vector2((x - rect.left) / rect.width * 2 - 1, 1 - (y - rect.top) / rect.height * 2), camera)
      if (Math.abs(raycaster.ray.direction.dot(normal)) < 1e-6) return null
      const hit = raycaster.ray.intersectPlane(new THREE.Plane().setFromNormalAndCoplanarPoint(normal, new THREE.Vector3(...anchor)), new THREE.Vector3())
      if (!hit) return null
      const pointMm = hit.toArray() as Point3
      const depth = hit.clone().project(camera).z
      if (depth < -1 || depth > 1) return null
      return {
        featureId: `plane:${plane}:${pointMm.map((value) => value.toFixed(6)).join(',')}`,
        kind: 'free_point', quality: 'Approximate', label: `${plane === 'view' ? 'View' : plane.toUpperCase()} plane point`,
        pointMm, screen: { x, y, depth, visible: true }, distancePx: 0,
      }
    },
  }
}

function planeNormal(plane: MeasurementPlane, camera: THREE.Camera): THREE.Vector3 {
  if (plane === 'xy') return new THREE.Vector3(0, 0, 1)
  if (plane === 'xz') return new THREE.Vector3(0, 1, 0)
  if (plane === 'yz') return new THREE.Vector3(1, 0, 0)
  return camera.getWorldDirection(new THREE.Vector3())
}
