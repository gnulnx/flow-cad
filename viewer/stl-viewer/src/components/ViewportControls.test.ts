import * as THREE from 'three'
import { describe, expect, it } from 'vitest'
import { dollyCameraTowardPivot } from './ViewportControls'

describe('ViewportControls camera dolly', () => {
  it('zooms along the existing pivot vector without changing orbit angle', () => {
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 2000)
    const pivot = new THREE.Vector3(5, -3, 2)
    camera.position.set(35, 27, 32)
    const beforeDirection = camera.position.clone().sub(pivot).normalize()

    const moved = dollyCameraTowardPivot(camera, pivot, 0.5)
    const afterDirection = camera.position.clone().sub(pivot).normalize()

    expect(moved).toBe(true)
    expect(afterDirection.x).toBeCloseTo(beforeDirection.x)
    expect(afterDirection.y).toBeCloseTo(beforeDirection.y)
    expect(afterDirection.z).toBeCloseTo(beforeDirection.z)
    expect(camera.position.distanceTo(pivot)).toBeCloseTo(25.980762)
  })

  it('does not move closer than the minimum camera distance', () => {
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 2000)
    const pivot = new THREE.Vector3(0, 0, 0)
    camera.position.set(3, 0, 0)

    expect(dollyCameraTowardPivot(camera, pivot, 0.1)).toBe(true)
    expect(camera.position.distanceTo(pivot)).toBeCloseTo(2)
    expect(dollyCameraTowardPivot(camera, pivot, 0.5)).toBe(false)
    expect(camera.position.distanceTo(pivot)).toBeCloseTo(2)
  })
})
