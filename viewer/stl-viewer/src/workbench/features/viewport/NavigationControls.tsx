import { useEffect, useRef } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'
import type { Bounds3 } from '../../contracts'
import {
  dollyFrame,
  fitFrameToBounds,
  orbitArcball,
  orbitFree,
  orbitTurntable,
  panFrame,
  pointerIntent,
  projectArcball,
  WORLD_UP,
  type CameraFrame,
  type RotationMode,
} from './navigation'

interface NavigationControlsProps {
  rotationMode: RotationMode
  visibleBounds: Bounds3 | null
  selectedBounds: Bounds3 | null
  fitRequest: number
  frameSelectedRequest: number
  measureMode: boolean
}

interface DragState {
  pointerId: number
  intent: 'rotate' | 'pan'
  startX: number
  startY: number
  lastX: number
  lastY: number
  startFrame: CameraFrame
  startArcball: THREE.Vector3
}

function frameFromCamera(camera: THREE.PerspectiveCamera, pivot: THREE.Vector3): CameraFrame {
  return { position: camera.position.clone(), pivot: pivot.clone(), up: camera.up.clone().normalize() }
}

function applyFrame(camera: THREE.PerspectiveCamera, frame: CameraFrame) {
  camera.position.copy(frame.position)
  camera.up.copy(frame.up)
  camera.lookAt(frame.pivot)
  camera.updateMatrixWorld()
}

export function NavigationControls({
  rotationMode,
  visibleBounds,
  selectedBounds,
  fitRequest,
  frameSelectedRequest,
  measureMode,
}: NavigationControlsProps) {
  const { camera, gl, invalidate } = useThree()
  const pivotRef = useRef(new THREE.Vector3())
  const dragRef = useRef<DragState | null>(null)
  const modeRef = useRef(rotationMode)
  const measureModeRef = useRef(measureMode)
  const fitRequestRef = useRef(-1)
  const frameRequestRef = useRef(-1)

  useEffect(() => {
    modeRef.current = rotationMode
    if (!(camera instanceof THREE.PerspectiveCamera) || rotationMode !== 'turntable') return
    camera.up.copy(WORLD_UP)
    camera.lookAt(pivotRef.current)
    invalidate()
  }, [camera, invalidate, rotationMode])

  useEffect(() => {
    measureModeRef.current = measureMode
  }, [measureMode])

  useEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera) || fitRequestRef.current === fitRequest) return
    fitRequestRef.current = fitRequest
    if (!visibleBounds) return
    const frame = fitFrameToBounds(visibleBounds, camera.fov)
    pivotRef.current.copy(frame.pivot)
    applyFrame(camera, frame)
    invalidate()
  }, [camera, fitRequest, invalidate, visibleBounds])

  useEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera) || frameRequestRef.current === frameSelectedRequest) return
    frameRequestRef.current = frameSelectedRequest
    const bounds = selectedBounds ?? visibleBounds
    if (!bounds) return
    const frame = fitFrameToBounds(bounds, camera.fov)
    pivotRef.current.copy(frame.pivot)
    applyFrame(camera, frame)
    invalidate()
  }, [camera, frameSelectedRequest, invalidate, selectedBounds, visibleBounds])

  useEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera)) return
    const element = gl.domElement

    const pointerDown = (event: PointerEvent) => {
      const intent = pointerIntent(event.button, !measureModeRef.current)
      if (!intent) return
      const rect = element.getBoundingClientRect()
      dragRef.current = {
        pointerId: event.pointerId,
        intent,
        startX: event.clientX,
        startY: event.clientY,
        lastX: event.clientX,
        lastY: event.clientY,
        startFrame: frameFromCamera(camera, pivotRef.current),
        startArcball: projectArcball(event.clientX, event.clientY, rect),
      }
      element.setPointerCapture(event.pointerId)
      event.preventDefault()
    }

    const pointerMove = (event: PointerEvent) => {
      const drag = dragRef.current
      if (!drag || drag.pointerId !== event.pointerId) return
      let next: CameraFrame
      if (drag.intent === 'pan') {
        next = panFrame(frameFromCamera(camera, pivotRef.current), event.clientX - drag.lastX, event.clientY - drag.lastY)
        drag.lastX = event.clientX
        drag.lastY = event.clientY
      } else {
        const dx = event.clientX - drag.startX
        const dy = event.clientY - drag.startY
        if (modeRef.current === 'arcball') {
          const rect = element.getBoundingClientRect()
          next = orbitArcball(drag.startFrame, drag.startArcball, projectArcball(event.clientX, event.clientY, rect))
        } else if (modeRef.current === 'free-orbit') {
          next = orbitFree(drag.startFrame, dx, dy)
        } else {
          next = orbitTurntable(drag.startFrame, dx, dy)
        }
      }
      pivotRef.current.copy(next.pivot)
      applyFrame(camera, next)
      invalidate()
      event.preventDefault()
    }

    const pointerEnd = (event: PointerEvent) => {
      const drag = dragRef.current
      if (!drag || drag.pointerId !== event.pointerId) return
      dragRef.current = null
      if (element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId)
      event.preventDefault()
    }

    const wheel = (event: WheelEvent) => {
      const next = dollyFrame(frameFromCamera(camera, pivotRef.current), event.deltaY)
      applyFrame(camera, next)
      invalidate()
      event.preventDefault()
    }

    const contextMenu = (event: MouseEvent) => event.preventDefault()
    element.addEventListener('pointerdown', pointerDown)
    element.addEventListener('pointermove', pointerMove)
    element.addEventListener('pointerup', pointerEnd)
    element.addEventListener('pointercancel', pointerEnd)
    element.addEventListener('wheel', wheel, { passive: false })
    element.addEventListener('contextmenu', contextMenu)
    return () => {
      element.removeEventListener('pointerdown', pointerDown)
      element.removeEventListener('pointermove', pointerMove)
      element.removeEventListener('pointerup', pointerEnd)
      element.removeEventListener('pointercancel', pointerEnd)
      element.removeEventListener('wheel', wheel)
      element.removeEventListener('contextmenu', contextMenu)
    }
  }, [camera, gl.domElement, invalidate])

  return null
}
