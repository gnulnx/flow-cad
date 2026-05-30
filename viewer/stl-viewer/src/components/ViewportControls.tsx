import { useEffect, useRef, type MutableRefObject } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'
import type { ModelData, RotationMode, ViewerOccurrence } from '../types'

const WORLD_UP = new THREE.Vector3(0, 0, 1)
const FIT_DIRECTION = new THREE.Vector3(1, 0.9, 1).normalize()
const ROTATE_SPEED = 0.006
const PAN_SPEED = 0.0015
const MIN_DISTANCE = 2
const MAX_TURNTABLE_PITCH = THREE.MathUtils.degToRad(89)

interface ViewportControlsProps {
  models: ModelData[]
  activeName: string | null
  fitRequest: number
  frameSelectedRequest: number
  rotationMode: RotationMode
  measurementActive?: boolean
}

type DragMode = 'rotate' | 'pan'

interface DragState {
  mode: DragMode
  pointerId: number
  startX: number
  startY: number
  lastX: number
  lastY: number
  startPivot: THREE.Vector3
  startPosition: THREE.Vector3
  startUp: THREE.Vector3
  startRight: THREE.Vector3
  startBack: THREE.Vector3
  startArcball: THREE.Vector3
  startTurntable: TurntableState
}

interface TurntableState {
  yaw: number
  pitch: number
  distance: number
}

function occurrenceRotation(occurrence: ViewerOccurrence): [number, number, number] {
  return [
    THREE.MathUtils.degToRad(occurrence.rotation[0]),
    THREE.MathUtils.degToRad(occurrence.rotation[1]),
    THREE.MathUtils.degToRad(occurrence.rotation[2]),
  ]
}

function occurrenceMatrix(occurrence: ViewerOccurrence) {
  const position = new THREE.Vector3(...occurrence.location)
  const rotation = occurrenceRotation(occurrence)
  const quaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(rotation[0], rotation[1], rotation[2]))
  return new THREE.Matrix4().compose(position, quaternion, new THREE.Vector3(1, 1, 1))
}

function boundsForModels(models: ModelData[], partId?: string | null) {
  const box = new THREE.Box3()
  let hasBounds = false

  models.forEach((model) => {
    if (partId && model.partId !== partId) return

    model.geometry.computeBoundingBox()
    const geometryBox = model.geometry.boundingBox
    if (!geometryBox) return

    model.occurrences.forEach((occurrence) => {
      box.union(geometryBox.clone().applyMatrix4(occurrenceMatrix(occurrence)))
      hasBounds = true
    })
  })

  return hasBounds ? box : null
}

function cameraBasis(position: THREE.Vector3, pivot: THREE.Vector3, up: THREE.Vector3) {
  const back = position.clone().sub(pivot).normalize()
  const forward = back.clone().multiplyScalar(-1)
  const right = forward.cross(up).normalize()

  if (right.lengthSq() < 0.0001) {
    right.set(1, 0, 0)
  }

  return { right, back }
}

function applyLookAt(camera: THREE.PerspectiveCamera, pivot: THREE.Vector3, preserveWorldUp: boolean) {
  if (preserveWorldUp) {
    camera.up.copy(WORLD_UP)
  }
  camera.lookAt(pivot)
  camera.updateMatrixWorld()
}

function turntableStateFromCamera(camera: THREE.PerspectiveCamera, pivot: THREE.Vector3): TurntableState {
  const offset = camera.position.clone().sub(pivot)
  const distance = Math.max(offset.length(), MIN_DISTANCE)

  return {
    yaw: Math.atan2(offset.y, offset.x),
    pitch: THREE.MathUtils.clamp(Math.asin(THREE.MathUtils.clamp(offset.z / distance, -1, 1)), -MAX_TURNTABLE_PITCH, MAX_TURNTABLE_PITCH),
    distance,
  }
}

function turntableOffset({ yaw, pitch, distance }: TurntableState) {
  const horizontalDistance = Math.cos(pitch) * distance
  return new THREE.Vector3(
    Math.cos(yaw) * horizontalDistance,
    Math.sin(yaw) * horizontalDistance,
    Math.sin(pitch) * distance,
  )
}

function applyTurntablePose(camera: THREE.PerspectiveCamera, pivot: THREE.Vector3, state: TurntableState) {
  // Turntable keeps yaw/pitch as scalar state. World Z defines yaw; it does not flatten pitch.
  camera.position.copy(pivot).add(turntableOffset(state))
  applyLookAt(camera, pivot, true)
}

function fitCameraToBox(camera: THREE.PerspectiveCamera, box: THREE.Box3, pivot: THREE.Vector3) {
  const center = box.getCenter(new THREE.Vector3())
  const size = box.getSize(new THREE.Vector3())
  const radius = Math.max(size.length() / 2, 1)
  const fov = THREE.MathUtils.degToRad(camera.fov)
  const distance = (radius / Math.sin(fov / 2)) * 1.25

  pivot.copy(center)
  camera.up.copy(WORLD_UP)
  camera.position.copy(center).addScaledVector(FIT_DIRECTION, distance)
  camera.near = Math.max(distance / 1000, 0.01)
  camera.far = Math.max(distance * 1000, 2000)
  camera.updateProjectionMatrix()
  applyLookAt(camera, pivot, true)
}

function fallbackCamera(camera: THREE.PerspectiveCamera, pivot: THREE.Vector3) {
  pivot.set(0, 0, 0)
  camera.up.copy(WORLD_UP)
  camera.position.set(140, 110, 140)
  camera.near = 0.1
  camera.far = 2000
  camera.updateProjectionMatrix()
  applyLookAt(camera, pivot, true)
}

export function dollyCameraTowardPivot(camera: THREE.PerspectiveCamera, pivot: THREE.Vector3, factor: number) {
  const offset = camera.position.clone().sub(pivot)
  const distance = offset.length()

  if (distance <= MIN_DISTANCE && factor <= 1) {
    return false
  }

  const nextDistance = Math.max(distance * factor, MIN_DISTANCE)
  camera.position.copy(pivot).add(offset.setLength(nextDistance))
  return true
}

function projectArcball(clientX: number, clientY: number, element: HTMLElement) {
  const rect = element.getBoundingClientRect()
  const scale = Math.min(rect.width, rect.height)
  const x = ((clientX - rect.left) * 2 - rect.width) / scale
  const y = (rect.height - (clientY - rect.top) * 2) / scale
  const lengthSq = x * x + y * y

  if (lengthSq <= 1) {
    return new THREE.Vector3(x, y, Math.sqrt(1 - lengthSq))
  }

  return new THREE.Vector3(x, y, 0).normalize()
}

function setOrbitPose(
  camera: THREE.PerspectiveCamera,
  pivot: THREE.Vector3,
  offset: THREE.Vector3,
  up: THREE.Vector3,
  preserveWorldUp: boolean,
) {
  if (offset.length() < MIN_DISTANCE) {
    offset.setLength(MIN_DISTANCE)
  }
  camera.position.copy(pivot).add(offset)
  camera.up.copy(up.normalize())
  applyLookAt(camera, pivot, preserveWorldUp)
}

function turntableOrbit(
  camera: THREE.PerspectiveCamera,
  drag: DragState,
  dx: number,
  dy: number,
  stateRef: MutableRefObject<TurntableState>,
) {
  stateRef.current = {
    yaw: drag.startTurntable.yaw - dx * ROTATE_SPEED,
    pitch: THREE.MathUtils.clamp(drag.startTurntable.pitch - dy * ROTATE_SPEED, -MAX_TURNTABLE_PITCH, MAX_TURNTABLE_PITCH),
    distance: drag.startTurntable.distance,
  }
  applyTurntablePose(camera, drag.startPivot, stateRef.current)
}

function freeOrbit(camera: THREE.PerspectiveCamera, drag: DragState, dx: number, dy: number) {
  const yaw = -dx * ROTATE_SPEED
  const pitch = -dy * ROTATE_SPEED
  const startOffset = drag.startPosition.clone().sub(drag.startPivot)
  const yawQuaternion = new THREE.Quaternion().setFromAxisAngle(drag.startUp, yaw)
  const pitchAxis = drag.startRight.clone().applyQuaternion(yawQuaternion)
  const pitchQuaternion = new THREE.Quaternion().setFromAxisAngle(pitchAxis, pitch)

  const offset = startOffset.clone().applyQuaternion(yawQuaternion).applyQuaternion(pitchQuaternion)
  const up = drag.startUp.clone().applyQuaternion(yawQuaternion).applyQuaternion(pitchQuaternion)
  setOrbitPose(camera, drag.startPivot, offset, up, false)
}

function arcballOrbit(camera: THREE.PerspectiveCamera, drag: DragState, currentArcball: THREE.Vector3) {
  // The virtual sphere gives a screen-space axis; the camera basis maps that axis into world space.
  const axis = drag.startArcball.clone().cross(currentArcball)
  const axisLength = axis.length()
  if (axisLength < 0.0001) return

  const angle = Math.atan2(axisLength, THREE.MathUtils.clamp(drag.startArcball.dot(currentArcball), -1, 1))
  const screenAxis = axis.divideScalar(axisLength)
  const worldAxis = drag.startRight.clone().multiplyScalar(screenAxis.x)
    .add(drag.startUp.clone().multiplyScalar(screenAxis.y))
    .add(drag.startBack.clone().multiplyScalar(screenAxis.z))
    .normalize()
  const quaternion = new THREE.Quaternion().setFromAxisAngle(worldAxis, angle)
  const offset = drag.startPosition.clone().sub(drag.startPivot).applyQuaternion(quaternion)
  const up = drag.startUp.clone().applyQuaternion(quaternion)

  setOrbitPose(camera, drag.startPivot, offset, up, false)
}

export default function ViewportControls({
  models,
  activeName,
  fitRequest,
  frameSelectedRequest,
  rotationMode,
  measurementActive = false,
}: ViewportControlsProps) {
  const { camera, gl, invalidate } = useThree()
  const pivotRef = useRef(new THREE.Vector3())
  const hasPivotRef = useRef(false)
  const dragRef = useRef<DragState | null>(null)
  const rotationModeRef = useRef(rotationMode)
  const measurementActiveRef = useRef(measurementActive)
  const turntableStateRef = useRef<TurntableState>({ yaw: 0, pitch: 0, distance: 1 })
  const frameSelectedRequestRef = useRef(frameSelectedRequest)
  const fitRequestRef = useRef<number | null>(null)

  useEffect(() => {
    rotationModeRef.current = rotationMode
    if (!(camera instanceof THREE.PerspectiveCamera)) return

    turntableStateRef.current = turntableStateFromCamera(camera, pivotRef.current)
    if (rotationMode === 'turntable') {
      applyTurntablePose(camera, pivotRef.current, turntableStateRef.current)
      invalidate()
    }
  }, [camera, invalidate, rotationMode])

  useEffect(() => {
    measurementActiveRef.current = measurementActive
  }, [measurementActive])

  useEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera)) return
    if (fitRequestRef.current === fitRequest) return
    fitRequestRef.current = fitRequest

    const box = boundsForModels(models)
    if (box) {
      fitCameraToBox(camera, box, pivotRef.current)
      hasPivotRef.current = true
    } else {
      fallbackCamera(camera, pivotRef.current)
      hasPivotRef.current = true
    }
    turntableStateRef.current = turntableStateFromCamera(camera, pivotRef.current)
    invalidate()
  }, [camera, fitRequest, invalidate, models])

  useEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera)) return
    if (frameSelectedRequestRef.current === frameSelectedRequest) return
    frameSelectedRequestRef.current = frameSelectedRequest

    const box = (activeName ? boundsForModels(models, activeName) : null) ?? boundsForModels(models)
    if (!box) return

    fitCameraToBox(camera, box, pivotRef.current)
    hasPivotRef.current = true
    turntableStateRef.current = turntableStateFromCamera(camera, pivotRef.current)
    invalidate()
  }, [activeName, camera, frameSelectedRequest, invalidate, models])

  useEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera)) return
    if (hasPivotRef.current) return

    const box = boundsForModels(models)
    if (box) {
      box.getCenter(pivotRef.current)
      hasPivotRef.current = true
      turntableStateRef.current = turntableStateFromCamera(camera, pivotRef.current)
    }
  }, [camera, models])

  useEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera)) return

    const element = gl.domElement

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0 && event.button !== 1 && event.button !== 2) return
      if (measurementActiveRef.current && event.button === 0) return

      const pivot = pivotRef.current.clone()
      const { right, back } = cameraBasis(camera.position, pivot, camera.up)
      const mode: DragMode = event.button === 1 || event.button === 2 ? 'pan' : 'rotate'

      dragRef.current = {
        mode,
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        lastX: event.clientX,
        lastY: event.clientY,
        startPivot: pivot,
        startPosition: camera.position.clone(),
        startUp: camera.up.clone().normalize(),
        startRight: right,
        startBack: back,
        startArcball: projectArcball(event.clientX, event.clientY, element),
        startTurntable: turntableStateRef.current,
      }
      element.setPointerCapture(event.pointerId)
      event.preventDefault()
    }

    const onPointerMove = (event: PointerEvent) => {
      const drag = dragRef.current
      if (!drag || drag.pointerId !== event.pointerId) return

      if (drag.mode === 'pan') {
        const dx = event.clientX - drag.lastX
        const dy = event.clientY - drag.lastY
        const distance = Math.max(camera.position.distanceTo(pivotRef.current), MIN_DISTANCE)
        const scale = distance * PAN_SPEED
        const { right } = cameraBasis(camera.position, pivotRef.current, camera.up)
        const up = camera.up.clone().normalize()
        const delta = right.multiplyScalar(-dx * scale).add(up.multiplyScalar(dy * scale))

        camera.position.add(delta)
        pivotRef.current.add(delta)
        turntableStateRef.current = turntableStateFromCamera(camera, pivotRef.current)
        drag.lastX = event.clientX
        drag.lastY = event.clientY
        applyLookAt(camera, pivotRef.current, rotationModeRef.current === 'turntable')
      } else {
        const dx = event.clientX - drag.startX
        const dy = event.clientY - drag.startY

        if (rotationModeRef.current === 'arcball') {
          arcballOrbit(camera, drag, projectArcball(event.clientX, event.clientY, element))
          turntableStateRef.current = turntableStateFromCamera(camera, drag.startPivot)
        } else if (rotationModeRef.current === 'free_orbit') {
          freeOrbit(camera, drag, dx, dy)
          turntableStateRef.current = turntableStateFromCamera(camera, drag.startPivot)
        } else {
          turntableOrbit(camera, drag, dx, dy, turntableStateRef)
        }
        pivotRef.current.copy(drag.startPivot)
      }

      invalidate()
      event.preventDefault()
    }

    const endDrag = (event: PointerEvent) => {
      const drag = dragRef.current
      if (!drag || drag.pointerId !== event.pointerId) return
      dragRef.current = null
      if (element.hasPointerCapture(event.pointerId)) {
        element.releasePointerCapture(event.pointerId)
      }
      event.preventDefault()
    }

    const onWheel = (event: WheelEvent) => {
      const factor = Math.exp(THREE.MathUtils.clamp(event.deltaY, -600, 600) * 0.001)

      if (dollyCameraTowardPivot(camera, pivotRef.current, factor)) {
        turntableStateRef.current = turntableStateFromCamera(camera, pivotRef.current)
        applyLookAt(camera, pivotRef.current, rotationModeRef.current === 'turntable')
        invalidate()
      }
      event.preventDefault()
    }

    const onContextMenu = (event: MouseEvent) => {
      event.preventDefault()
    }

    element.addEventListener('pointerdown', onPointerDown)
    element.addEventListener('pointermove', onPointerMove)
    element.addEventListener('pointerup', endDrag)
    element.addEventListener('pointercancel', endDrag)
    element.addEventListener('wheel', onWheel, { passive: false })
    element.addEventListener('contextmenu', onContextMenu)

    return () => {
      element.removeEventListener('pointerdown', onPointerDown)
      element.removeEventListener('pointermove', onPointerMove)
      element.removeEventListener('pointerup', endDrag)
      element.removeEventListener('pointercancel', endDrag)
      element.removeEventListener('wheel', onWheel)
      element.removeEventListener('contextmenu', onContextMenu)
    }
  }, [camera, gl.domElement, invalidate])

  return null
}
