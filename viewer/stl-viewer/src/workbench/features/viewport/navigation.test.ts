import { describe, expect, it } from 'vitest'
import * as THREE from 'three'
import {
  dollyFrame,
  fitFrameToBounds,
  MAX_TURNTABLE_PITCH,
  MIN_CAMERA_DISTANCE,
  orbitArcball,
  orbitFree,
  orbitTurntable,
  panFrame,
  pointerIntent,
  projectArcball,
  WORLD_UP,
  type CameraFrame,
} from './navigation'
import { pendingFrameBounds } from './NavigationControls'

function frame(): CameraFrame {
  return {
    position: new THREE.Vector3(100, 80, 70),
    pivot: new THREE.Vector3(10, -4, 7),
    up: WORLD_UP.clone(),
  }
}

describe('replacement workbench navigation contract', () => {
  it('maps left drag to rotate and both alternate buttons to pan', () => {
    expect(pointerIntent(0)).toBe('rotate')
    expect(pointerIntent(0, false)).toBeNull()
    expect(pointerIntent(1)).toBe('pan')
    expect(pointerIntent(2)).toBe('pan')
    expect(pointerIntent(4)).toBeNull()
  })

  it('keeps turntable world Z-up, drag direction, pivot, and pitch clamp', () => {
    const start = frame()
    const right = orbitTurntable(start, 30, 0)
    const extreme = orbitTurntable(start, 0, 100000)
    const offset = extreme.position.clone().sub(extreme.pivot)
    const pitch = Math.asin(offset.z / offset.length())

    expect(right.position.x).not.toBeCloseTo(start.position.x)
    expect(right.pivot.toArray()).toEqual(start.pivot.toArray())
    expect(right.up.toArray()).toEqual([0, 0, 1])
    expect(pitch).toBeCloseTo(MAX_TURNTABLE_PITCH)
  })

  it('supports free-orbit and arcball without forcing their local up back to Z', () => {
    const start = frame()
    const free = orbitFree(start, 24, 19)
    const arcball = orbitArcball(
      start,
      new THREE.Vector3(0, 0, 1),
      new THREE.Vector3(0.2, -0.15, Math.sqrt(1 - 0.2 ** 2 - 0.15 ** 2)),
    )

    expect(free.position.distanceTo(start.pivot)).toBeCloseTo(start.position.distanceTo(start.pivot))
    expect(free.up.toArray()).not.toEqual(WORLD_UP.toArray())
    expect(arcball.position.toArray()).not.toEqual(start.position.toArray())
    expect(arcball.pivot.toArray()).toEqual(start.pivot.toArray())
  })

  it('projects pointer coordinates onto a normalized virtual arcball', () => {
    const projected = projectArcball(50, 50, { left: 0, top: 0, width: 100, height: 100 })
    expect(projected.toArray()).toEqual([0, 0, 1])
    expect(projectArcball(200, 50, { left: 0, top: 0, width: 100, height: 100 }).length()).toBeCloseTo(1)
  })

  it('pans camera and pivot together while wheel dolly preserves the pivot ray', () => {
    const start = frame()
    const panned = panFrame(start, 20, -13)
    const cameraDelta = panned.position.clone().sub(start.position)
    const pivotDelta = panned.pivot.clone().sub(start.pivot)
    const beforeRay = start.position.clone().sub(start.pivot).normalize()
    const dolly = dollyFrame(start, -300)

    expect(cameraDelta.distanceTo(pivotDelta)).toBeLessThan(1e-10)
    expect(dolly.position.distanceTo(start.pivot)).toBeLessThan(start.position.distanceTo(start.pivot))
    expect(dolly.position.clone().sub(start.pivot).normalize().distanceTo(beforeRay)).toBeLessThan(1e-10)
    expect(dollyFrame({ ...start, position: start.pivot.clone().addScalar(.1) }, -600).position.distanceTo(start.pivot)).toBeCloseTo(MIN_CAMERA_DISTANCE)
  })

  it('fits and frames the supplied occurrence bounds around their true center', () => {
    const fitted = fitFrameToBounds({ min: [-10, 20, 4], max: [30, 50, 24] })
    expect(fitted.pivot.toArray()).toEqual([10, 35, 14])
    expect(fitted.up.toArray()).toEqual([0, 0, 1])
    expect(fitted.position.distanceTo(fitted.pivot)).toBeGreaterThan(Math.sqrt(40 ** 2 + 30 ** 2 + 20 ** 2) / 2)
  })

  it('keeps an initial fit request pending until progressive geometry has bounds', () => {
    const bounds = { min: [-10, 20, 4] as [number, number, number], max: [30, 50, 24] as [number, number, number] }

    expect(pendingFrameBounds(-1, 0, null)).toBeNull()
    expect(pendingFrameBounds(-1, 0, bounds)).toBe(bounds)
    expect(pendingFrameBounds(0, 0, bounds)).toBeNull()
  })
})
