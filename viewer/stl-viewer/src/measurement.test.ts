import { BufferGeometry, Float32BufferAttribute, Matrix4, Vector3 } from 'three'
import { describe, expect, it } from 'vitest'
import {
  buildMeshSnapFeatures,
  freePointTarget,
  measurementSnapFeaturesForModel,
  resolveEdgeLength,
  resolveMeasurement,
  targetFromFeature,
} from './measurement'
import type { SnapFeature } from './types'

describe('measurement helpers', () => {
  it('labels point-to-point measurements with feature types and deltas', () => {
    const start = freePointTarget(new Vector3(0, 0, 0))
    const end = freePointTarget(new Vector3(3, 4, 12))

    const measurement = resolveMeasurement(start, end)

    expect(measurement.label).toBe('Free Point -> Free Point')
    expect(measurement.distance).toBe(13)
    expect(measurement.delta.toArray()).toEqual([3, 4, 12])
    expect(measurement.qualityLabel).toBe('Approximate')
  })

  it('uses shortest true 3D distance for edge-to-edge measurements', () => {
    const edgeA = targetFromFeature(lineFeature('a', [0, 0, 0], [10, 0, 0]), new Matrix4(), 'part', 'occ')
    const edgeB = targetFromFeature(lineFeature('b', [5, 5, 2], [5, 5, 10]), new Matrix4(), 'part', 'occ')

    if (!edgeA || !edgeB) throw new Error('expected edge targets')
    const measurement = resolveMeasurement(edgeA, edgeB)

    expect(measurement.label).toBe('Line Edge -> Line Edge')
    expect(measurement.startPoint.toArray()).toEqual([5, 0, 0])
    expect(measurement.endPoint.toArray()).toEqual([5, 5, 2])
    expect(measurement.distance).toBeCloseTo(Math.sqrt(29))
  })

  it('creates edge-length measurements from line edge targets', () => {
    const edge = targetFromFeature(lineFeature('edge', [1, 2, 3], [1, 8, 3]), new Matrix4(), 'part', 'occ')

    if (!edge) throw new Error('expected edge target')
    const measurement = resolveEdgeLength(edge)

    expect(measurement?.label).toBe('Edge Length')
    expect(measurement?.distance).toBe(6)
    expect(measurement?.delta.toArray()).toEqual([0, 6, 0])
    expect(measurement?.qualityLabel).toBe('Approximate')
  })

  it('creates edge-length measurements from edge midpoint targets', () => {
    const midpoint = targetFromFeature({
      id: 'midpoint',
      kind: 'edge_midpoint',
      label: 'Edge Midpoint',
      point: [5, 0, 0],
      edge_start: [0, 0, 0],
      edge_end: [10, 0, 0],
    }, new Matrix4(), 'part', 'occ')

    if (!midpoint) throw new Error('expected midpoint target')
    const measurement = resolveEdgeLength(midpoint)

    expect(measurement?.label).toBe('Edge Length')
    expect(measurement?.distance).toBe(10)
  })

  it('builds best-effort mesh vertices and edges for STL-only files', () => {
    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new Float32BufferAttribute([
      0, 0, 0,
      10, 0, 0,
      0, 10, 0,
    ], 3))

    const features = buildMeshSnapFeatures(geometry)

    expect(features.some((feature) => feature.kind === 'vertex')).toBe(true)
    expect(features.some((feature) => feature.kind === 'line_edge' && feature.label === 'Line Edge')).toBe(true)
    expect(features.some((feature) => feature.kind === 'edge_midpoint')).toBe(true)
    expect(features.every((feature) => feature.quality_label === 'Approximate')).toBe(true)
  })

  it('uses backend snap features without mesh fallback for exact STEP models', () => {
    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new Float32BufferAttribute([
      0, 0, 0,
      10, 0, 0,
      0, 10, 0,
    ], 3))
    const backendFeature: SnapFeature = {
      id: 'backend-edge',
      kind: 'line_edge',
      label: 'Line Edge',
      point: [5, 0, 0],
      start: [0, 0, 0],
      end: [10, 0, 0],
      source: 'step_topology',
      quality: 'exact',
      quality_label: 'Exact',
    }

    const features = measurementSnapFeaturesForModel({
      geometry,
      snapFeatures: [backendFeature],
      capabilities: {
        display_mesh: true,
        mesh_metrics: true,
        exact_topology: true,
        exact_snap: true,
        exact_measurement: true,
        approximate_measurement: false,
        exact_editing: false,
        mesh_only: false,
      },
    })

    expect(features).toEqual([backendFeature])
  })
})

function lineFeature(id: string, start: [number, number, number], end: [number, number, number]): SnapFeature {
  return {
    id,
    kind: 'line_edge',
    label: 'Line Edge',
    point: [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2, (start[2] + end[2]) / 2],
    start,
    end,
    length: new Vector3(...start).distanceTo(new Vector3(...end)),
  }
}
