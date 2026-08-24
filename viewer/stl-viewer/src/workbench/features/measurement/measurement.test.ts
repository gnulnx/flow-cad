import { describe, expect, it } from 'vitest'
import type { ExactFeature, Point3 } from '../../contracts'
import {
  createDistanceMeasurement,
  createEdgeLengthMeasurement,
  featureLabel,
  findScreenSpaceSnap,
  formatMm,
  isMeasurementStale,
  type ScreenPoint,
  type MeasurementFeature,
  type SnapCandidate,
} from './measurement'

const project = (point: Point3): ScreenPoint => ({
  x: point[0] * 10,
  y: point[1] * 10,
  depth: 0,
  visible: true,
})

function pointFeature(id: string, kind: 'vertex' | 'edge_midpoint' | 'circle_center', pointMm: Point3): ExactFeature {
  return { id, kind, pointMm, quality: 'exact', source: 'step_topology' }
}

function candidate(id: string, kind: SnapCandidate['kind'], pointMm: Point3, quality: SnapCandidate['quality'] = 'Exact'): SnapCandidate {
  return {
    featureId: id,
    kind,
    quality,
    label: featureLabel(kind, quality),
    pointMm,
    screen: project(pointMm),
    distancePx: 0,
  }
}

describe('replacement exact measurement math', () => {
  it('finds projected point targets without requiring a mesh face hit', () => {
    const features: ExactFeature[] = [
      pointFeature('vertex:0', 'vertex', [10, 10, 0]),
      pointFeature('midpoint:0', 'edge_midpoint', [15, 10, 0]),
      pointFeature('center:0', 'circle_center', [20, 10, 0]),
    ]

    expect(findScreenSpaceSnap({ x: 102, y: 99 }, features, project)).toMatchObject({
      featureId: 'vertex:0',
      label: 'Exact vertex',
      pointMm: [10, 10, 0],
    })
    expect(findScreenSpaceSnap({ x: 151, y: 101 }, features, project)?.label).toBe('Exact edge midpoint')
    expect(findScreenSpaceSnap({ x: 200, y: 100 }, features, project)?.label).toBe('Exact circle center')
    expect(findScreenSpaceSnap({ x: 260, y: 100 }, features, project)).toBeNull()
  })

  it('snaps to the closest projected location along a line edge and exposes exact length', () => {
    const edge: ExactFeature = {
      id: 'line_edge:0',
      kind: 'line_edge',
      startMm: [0, 0, 0],
      endMm: [10, 0, 0],
      midpointMm: [5, 0, 0],
      lengthMm: 10,
      quality: 'exact',
      source: 'step_topology',
    }

    const snap = findScreenSpaceSnap({ x: 74, y: 4 }, [edge], project)
    expect(snap).toMatchObject({
      kind: 'line_edge',
      pointMm: [7.4, 0, 0],
      edge: { lengthMm: 10 },
    })
    expect(snap?.label).toBe('Exact line edge · 10.00 mm')

    if (!snap) throw new Error('expected edge snap')
    expect(createEdgeLengthMeasurement('edge-measurement', snap, {
      partUuid: 'part-1',
      artifactRevision: 'revision-1',
    })).toMatchObject({
      kind: 'edge_length',
      totalMm: 10,
      deltaMm: [10, 0, 0],
      binding: { featureIds: ['line_edge:0'] },
    })
  })

  it('creates a revision-bound two-click distance with total and signed XYZ deltas', () => {
    const measurement = createDistanceMeasurement(
      'distance-1',
      candidate('vertex:0', 'vertex', [1, 2, 3]),
      candidate('circle_center:0', 'circle_center', [4, 6, 15]),
      { partUuid: 'part-1', artifactRevision: 'revision-1' },
    )

    expect(measurement).toMatchObject({
      quality: 'Exact',
      totalMm: 13,
      deltaMm: [3, 4, 12],
      binding: {
        partUuid: 'part-1',
        artifactRevision: 'revision-1',
        featureIds: ['vertex:0', 'circle_center:0'],
      },
    })
    expect(isMeasurementStale(measurement, 'part-1', 'revision-1')).toBe(false)
    expect(isMeasurementStale(measurement, 'part-1', 'revision-2')).toBe(true)
    expect(isMeasurementStale(measurement, 'part-2', 'revision-1')).toBe(true)
    expect(formatMm(measurement.deltaMm[0])).toBe('3.00 mm')
  })

  it('keeps exact topology ahead of a closer approximate mesh sample', () => {
    const approximate: MeasurementFeature = {
      id: 'mesh_vertex:0',
      kind: 'vertex',
      quality: 'approximate',
      source: 'mesh_sample',
      pointMm: [10, 10, 0],
    }
    const exact = pointFeature('vertex:exact', 'vertex', [10.5, 10, 0])

    expect(findScreenSpaceSnap({ x: 100, y: 100 }, [approximate, exact], project)).toMatchObject({
      featureId: 'vertex:exact',
      quality: 'Exact',
    })
  })

  it('creates an Approximate two-click result from sampled mesh and free-point targets', () => {
    const measurement = createDistanceMeasurement(
      'mesh-distance',
      candidate('mesh_edge:1', 'line_edge', [0, 0, 0], 'Approximate'),
      candidate('mesh_free:2', 'free_point', [0, 3, 4], 'Approximate'),
      { partUuid: 'mesh-part', artifactRevision: 'mesh-revision' },
    )

    expect(measurement).toMatchObject({
      title: 'Approximate line edge to Approximate free point',
      quality: 'Approximate',
      totalMm: 5,
      binding: { featureIds: ['mesh_edge:1', 'mesh_free:2'] },
    })
  })

  it('keeps projected snap search inside the interaction SLO for a dense selected part', () => {
    const features = Array.from({ length: 5_000 }, (_, index) => pointFeature(
      `vertex:${index}`,
      'vertex',
      [index % 100, Math.floor(index / 100), 0],
    ))
    const durations: number[] = []
    for (let iteration = 0; iteration < 40; iteration += 1) {
      const started = performance.now()
      findScreenSpaceSnap({ x: 503, y: 247 }, features, project)
      durations.push(performance.now() - started)
    }
    durations.sort((left, right) => left - right)
    const average = durations.reduce((sum, duration) => sum + duration, 0) / durations.length
    const p95 = durations[Math.ceil(durations.length * 0.95) - 1]

    expect(average).toBeLessThan(16)
    expect(p95).toBeLessThan(33)
  })
})
