import * as THREE from 'three'
import type { Bounds3 } from '../../contracts'

export type RotationMode = 'turntable' | 'arcball' | 'free-orbit'
export type PointerIntent = 'rotate' | 'pan' | null

export const WORLD_UP = new THREE.Vector3(0, 0, 1)
export const MAX_TURNTABLE_PITCH = THREE.MathUtils.degToRad(89)
export const MIN_CAMERA_DISTANCE = 2

const ROTATE_SPEED = 0.006
const PAN_SPEED = 0.0015
const FIT_DIRECTION = new THREE.Vector3(1, 0.9, 1).normalize()

export interface CameraFrame {
  position: THREE.Vector3
  pivot: THREE.Vector3
  up: THREE.Vector3
}

export interface ViewportRect {
  left: number
  top: number
  width: number
  height: number
}

export function pointerIntent(button: number): PointerIntent {
  if (button === 0) return 'rotate'
  if (button === 1 || button === 2) return 'pan'
  return null
}

export function cloneFrame(frame: CameraFrame): CameraFrame {
  return {
    position: frame.position.clone(),
    pivot: frame.pivot.clone(),
    up: frame.up.clone(),
  }
}

export function projectArcball(clientX: number, clientY: number, rect: ViewportRect) {
  const scale = Math.max(Math.min(rect.width, rect.height), 1)
  const x = ((clientX - rect.left) * 2 - rect.width) / scale
  const y = (rect.height - (clientY - rect.top) * 2) / scale
  const lengthSq = x * x + y * y
  if (lengthSq <= 1) return new THREE.Vector3(x, y, Math.sqrt(1 - lengthSq))
  return new THREE.Vector3(x, y, 0).normalize()
}

function cameraBasis(frame: CameraFrame) {
  const back = frame.position.clone().sub(frame.pivot).normalize()
  const forward = back.clone().multiplyScalar(-1)
  const right = forward.cross(frame.up).normalize()
  if (right.lengthSq() < 0.0001) right.set(1, 0, 0)
  return { back, right }
}

export function orbitTurntable(start: CameraFrame, dx: number, dy: number): CameraFrame {
  const offset = start.position.clone().sub(start.pivot)
  const distance = Math.max(offset.length(), MIN_CAMERA_DISTANCE)
  const yaw = Math.atan2(offset.y, offset.x) - dx * ROTATE_SPEED
  const startPitch = Math.asin(THREE.MathUtils.clamp(offset.z / distance, -1, 1))
  const pitch = THREE.MathUtils.clamp(startPitch + dy * ROTATE_SPEED, -MAX_TURNTABLE_PITCH, MAX_TURNTABLE_PITCH)
  const horizontalDistance = Math.cos(pitch) * distance
  return {
    position: start.pivot.clone().add(new THREE.Vector3(
      Math.cos(yaw) * horizontalDistance,
      Math.sin(yaw) * horizontalDistance,
      Math.sin(pitch) * distance,
    )),
    pivot: start.pivot.clone(),
    up: WORLD_UP.clone(),
  }
}

export function orbitFree(start: CameraFrame, dx: number, dy: number): CameraFrame {
  const { right } = cameraBasis(start)
  const yaw = new THREE.Quaternion().setFromAxisAngle(start.up.clone().normalize(), -dx * ROTATE_SPEED)
  const pitchAxis = right.applyQuaternion(yaw).normalize()
  const pitch = new THREE.Quaternion().setFromAxisAngle(pitchAxis, -dy * ROTATE_SPEED)
  const offset = start.position.clone().sub(start.pivot).applyQuaternion(yaw).applyQuaternion(pitch)
  const up = start.up.clone().applyQuaternion(yaw).applyQuaternion(pitch).normalize()
  return {
    position: start.pivot.clone().add(offset),
    pivot: start.pivot.clone(),
    up,
  }
}

export function orbitArcball(start: CameraFrame, startArcball: THREE.Vector3, currentArcball: THREE.Vector3): CameraFrame {
  const { back, right } = cameraBasis(start)
  const axis = currentArcball.clone().cross(startArcball)
  const axisLength = axis.length()
  if (axisLength < 0.0001) return cloneFrame(start)
  const angle = Math.atan2(axisLength, THREE.MathUtils.clamp(startArcball.dot(currentArcball), -1, 1))
  const screenAxis = axis.divideScalar(axisLength)
  const worldAxis = right.multiplyScalar(screenAxis.x)
    .add(start.up.clone().normalize().multiplyScalar(screenAxis.y))
    .add(back.multiplyScalar(screenAxis.z))
    .normalize()
  const rotation = new THREE.Quaternion().setFromAxisAngle(worldAxis, angle)
  return {
    position: start.pivot.clone().add(start.position.clone().sub(start.pivot).applyQuaternion(rotation)),
    pivot: start.pivot.clone(),
    up: start.up.clone().applyQuaternion(rotation).normalize(),
  }
}

export function panFrame(frame: CameraFrame, dx: number, dy: number): CameraFrame {
  const distance = Math.max(frame.position.distanceTo(frame.pivot), MIN_CAMERA_DISTANCE)
  const { right } = cameraBasis(frame)
  const delta = right.multiplyScalar(-dx * distance * PAN_SPEED)
    .add(frame.up.clone().normalize().multiplyScalar(dy * distance * PAN_SPEED))
  return {
    position: frame.position.clone().add(delta),
    pivot: frame.pivot.clone().add(delta),
    up: frame.up.clone(),
  }
}

export function dollyFrame(frame: CameraFrame, wheelDeltaY: number): CameraFrame {
  const offset = frame.position.clone().sub(frame.pivot)
  const factor = Math.exp(THREE.MathUtils.clamp(wheelDeltaY, -600, 600) * 0.001)
  const nextDistance = Math.max(offset.length() * factor, MIN_CAMERA_DISTANCE)
  return {
    position: frame.pivot.clone().add(offset.setLength(nextDistance)),
    pivot: frame.pivot.clone(),
    up: frame.up.clone(),
  }
}

export function fitFrameToBounds(bounds: Bounds3, verticalFovDegrees = 42): CameraFrame {
  const box = new THREE.Box3(new THREE.Vector3(...bounds.min), new THREE.Vector3(...bounds.max))
  const center = box.getCenter(new THREE.Vector3())
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 1)
  const distance = (radius / Math.sin(THREE.MathUtils.degToRad(verticalFovDegrees) / 2)) * 1.25
  return {
    position: center.clone().addScaledVector(FIT_DIRECTION, distance),
    pivot: center,
    up: WORLD_UP.clone(),
  }
}
