import { describe, expect, it } from 'vitest'
import * as THREE from 'three'
import { measurementProjection } from './projection'

const rect = { left: 100, top: 50, right: 900, bottom: 650, width: 800, height: 600 } as DOMRect
describe('measurement projection', () => {
  it('picks an explicit XY plane through its anchor and roundtrips through the screen', () => {
    const camera = new THREE.PerspectiveCamera(42, 4 / 3, .1, 10000)
    camera.position.set(0, 0, 100)
    camera.lookAt(0, 0, 0)
    const source = measurementProjection(camera, () => rect)
    const target = source.pickPlanePoint!(600, 300, 'xy', [0, 0, 12])!
    expect(target.quality).toBe('Approximate')
    expect(target.pointMm[2]).toBeCloseTo(12)
    const screen = source.createProjector()(target.pointMm)!
    expect(screen.x).toBeCloseTo(600)
    expect(screen.y).toBeCloseTo(300)
    expect(source.pickPlanePoint!(500, 350, 'xz', [0, 0, 0])).toBeNull()
    expect(source.pickPlanePoint!(99, 300, 'xy', [0, 0, 0])).toBeNull()
  })

  it('keeps a view-plane drag at the starting camera depth', () => {
    const camera = new THREE.PerspectiveCamera(42, 4 / 3, .1, 10000)
    camera.position.set(100, 80, 120)
    camera.lookAt(0, 0, 0)
    const source = measurementProjection(camera, () => rect)
    const anchor: [number, number, number] = [10, 20, 30]
    const target = source.pickPlanePoint!(600, 400, 'view', anchor)!
    const delta = new THREE.Vector3(...target.pointMm).sub(new THREE.Vector3(...anchor))
    expect(delta.dot(camera.getWorldDirection(new THREE.Vector3()))).toBeCloseTo(0)
  })
})
