import { describe, expect, it } from 'vitest'
import type { WorkbenchOccurrence } from '../../contracts'
import {
  deriveApproximateMeshFeatures,
  MAX_APPROXIMATE_EDGES,
  MAX_APPROXIMATE_PICK_TRIANGLES,
  MAX_APPROXIMATE_VERTICES,
} from './approximate'

const placement: WorkbenchOccurrence = {
  assemblyId: 'active',
  id: 'mesh-main',
  translationMm: [10, 20, 30],
  rotationDeg: [0, 0, 90],
}

describe('bounded approximate mesh targets', () => {
  it('derives transformed, unmistakably approximate vertices and triangle edges', () => {
    const result = deriveApproximateMeshFeatures(new Float32Array([
      0, 0, 0,
      2, 0, 0,
      0, 2, 0,
    ]), placement)

    expect(result.features).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'vertex', quality: 'approximate', source: 'mesh_sample', pointMm: [10, 20, 30] }),
      expect.objectContaining({ kind: 'line_edge', quality: 'approximate', source: 'mesh_sample', lengthMm: 2 }),
    ]))
    expect(result.pickPositions).toHaveLength(9)
    expect(result.sampledTriangleCount).toBe(1)
  })

  it('keeps extraction and pointer-facing candidate counts bounded for a large triangle soup', () => {
    const triangleCount = 100_000
    const positions = new Float32Array(triangleCount * 9)
    for (let index = 0; index < positions.length; index += 1) positions[index] = index % 997

    const started = performance.now()
    const result = deriveApproximateMeshFeatures(positions, placement)
    const elapsedMs = performance.now() - started

    expect(result.sampledVertexCount).toBeLessThanOrEqual(MAX_APPROXIMATE_VERTICES)
    expect(result.sampledEdgeCount).toBeLessThanOrEqual(MAX_APPROXIMATE_EDGES)
    expect(result.sampledTriangleCount).toBeLessThanOrEqual(MAX_APPROXIMATE_PICK_TRIANGLES)
    expect(result.pickPositions.length).toBeLessThanOrEqual(MAX_APPROXIMATE_PICK_TRIANGLES * 9)
    expect(elapsedMs).toBeLessThan(100)
  })
})
