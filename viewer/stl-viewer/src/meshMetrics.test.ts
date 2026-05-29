import { BoxGeometry, BufferGeometry, Float32BufferAttribute } from 'three'
import { describe, expect, it } from 'vitest'
import { calculateMeshMetrics, estimateWeightGrams } from './meshMetrics'

describe('mesh metrics', () => {
  it('calculates physical bounds, volume, and surface area for an indexed solid mesh', () => {
    const geometry = new BoxGeometry(10, 20, 30)

    const metrics = calculateMeshMetrics(geometry)

    expect(metrics.triangleCount).toBe(12)
    expect(metrics.bounds.size.toArray()).toEqual([10, 20, 30])
    expect(metrics.volumeMm3).toBeCloseTo(6000)
    expect(metrics.volumeCm3).toBeCloseTo(6)
    expect(metrics.surfaceAreaMm2).toBeCloseTo(2200)
    expect(metrics.surfaceAreaCm2).toBeCloseTo(22)
    expect(metrics.quality.isLikelyClosed).toBe(true)
    expect(metrics.quality.warnings).toEqual([])
  })

  it('returns the same solid volume for translated non-indexed geometry', () => {
    const geometry = new BoxGeometry(10, 10, 10).toNonIndexed()
    geometry.translate(42, -17, 9)

    const metrics = calculateMeshMetrics(geometry)

    expect(metrics.triangleCount).toBe(12)
    expect(metrics.bounds.center.toArray()).toEqual([42, -17, 9])
    expect(metrics.volumeMm3).toBeCloseTo(1000)
    expect(metrics.surfaceAreaMm2).toBeCloseTo(600)
    expect(metrics.quality.isLikelyClosed).toBe(true)
  })

  it('flags open meshes so quote consumers know volume is only an estimate', () => {
    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new Float32BufferAttribute([
      0, 0, 0,
      10, 0, 0,
      0, 10, 0,
    ], 3))

    const metrics = calculateMeshMetrics(geometry)

    expect(metrics.triangleCount).toBe(1)
    expect(metrics.surfaceAreaMm2).toBeCloseTo(50)
    expect(metrics.volumeMm3).toBeCloseTo(0)
    expect(metrics.quality.isLikelyClosed).toBe(false)
    expect(metrics.quality.boundaryEdgeCount).toBe(3)
    expect(metrics.quality.warnings).toContain('Mesh is not closed; volume should be treated as an estimate.')
  })

  it('estimates material weight from mesh volume, density, and infill factor', () => {
    expect(estimateWeightGrams(5000, 1.24, 0.4)).toBeCloseTo(2.48)
  })
})
