import * as THREE from 'three'
import { describe, expect, it } from 'vitest'
import { arcballQuaternionForDrag, dollyCameraTowardPivot, turntableStateForDrag } from './ViewportControls'

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

describe('ViewportControls rotation direction', () => {
  it('keeps turntable left-right direction while inverting up-down pitch direction', () => {
    const start = { yaw: 0.4, pitch: 0.2, distance: 100 }

    expect(turntableStateForDrag(start, 20, 0).yaw).toBeLessThan(start.yaw)
    expect(turntableStateForDrag(start, 0, 20).pitch).toBeGreaterThan(start.pitch)
    expect(turntableStateForDrag(start, 0, -20).pitch).toBeLessThan(start.pitch)
  })

  it('inverts arcball drag direction on both screen axes', () => {
    const dragBasis = {
      startArcball: new THREE.Vector3(0, 0, 1),
      startRight: new THREE.Vector3(1, 0, 0),
      startUp: new THREE.Vector3(0, 1, 0),
      startBack: new THREE.Vector3(0, 0, 1),
    }
    const cameraOffset = new THREE.Vector3(0, 0, 10)
    const rightDrag = new THREE.Vector3(0.2, 0, Math.sqrt(1 - 0.2 ** 2))
    const downDrag = new THREE.Vector3(0, -0.2, Math.sqrt(1 - 0.2 ** 2))

    const rightOffset = cameraOffset.clone().applyQuaternion(arcballQuaternionForDrag(dragBasis, rightDrag)!)
    const downOffset = cameraOffset.clone().applyQuaternion(arcballQuaternionForDrag(dragBasis, downDrag)!)

    expect(rightOffset.x).toBeLessThan(0)
    expect(downOffset.y).toBeGreaterThan(0)
  })
})
