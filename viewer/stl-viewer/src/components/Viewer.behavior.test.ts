import { Vector3 } from 'three'
import { describe, expect, it } from 'vitest'
import { resolveMeasurement } from '../measurement'
import type { MeasurementTarget } from '../measurement'
import {
  defaultTapeResolveMode,
  editMoveCenterAfterDrag,
  measurementLabelOffsetAfterDrag,
  measurementResolveModesDiffer,
  pickedTapeTarget,
  shouldPreviewEdgeLength,
  snapReleaseDistance,
  snapScore,
} from './Viewer'

function target(overrides: Partial<MeasurementTarget> = {}): MeasurementTarget {
  return {
    id: 'target',
    kind: 'line_edge',
    label: 'Line Edge',
    point: new Vector3(0, 0, 0),
    quality: 'exact',
    qualityLabel: 'Exact',
    ...overrides,
  }
}

describe('viewer snap behavior contract', () => {
  it('prefers exact feature targets over free surface points at the same screen distance', () => {
    const feature = target({ id: 'feature', kind: 'line_edge' })
    const face = target({ id: 'face', kind: 'face_point', label: 'Face Point', quality: 'approximate', qualityLabel: 'Approximate' })

    expect(snapScore(feature, 20, null)).toBeLessThan(snapScore(face, 20, null))
  })

  it('keeps a current snap target favored without requiring a specific stickiness value', () => {
    const previous = target({ id: 'same-edge' })
    const candidate = target({ id: 'nearby-edge' })

    expect(snapScore(previous, 30, 'same-edge')).toBeLessThan(snapScore(candidate, 30, 'same-edge'))
  })

  it('uses a close-only snap release radius for all target types', () => {
    const current = target({ id: 'edge' })
    const newFeature = target({ id: 'other-edge' })
    const face = target({ id: 'face', kind: 'face_point', label: 'Face Point', quality: 'approximate', qualityLabel: 'Approximate' })

    expect(snapReleaseDistance(current, 'edge')).toBe(24)
    expect(snapReleaseDistance(newFeature, 'edge')).toBe(24)
    expect(snapReleaseDistance(face, 'edge')).toBe(24)
  })

  it('moves measurement HUD labels by pointer drag delta', () => {
    expect(
      measurementLabelOffsetAfterDrag(
        { x: 28, y: -88 },
        { x: 100, y: 140 },
        { x: 132, y: 109 },
      ),
    ).toEqual({ x: 60, y: -119 })
  })

  it('moves edit centers by the camera-plane pointer delta', () => {
    const nextCenter = editMoveCenterAfterDrag(
      new Vector3(10, 20, 30),
      new Vector3(1, 2, 3),
      new Vector3(4, 0, 8),
    )

    expect(nextCenter.toArray()).toEqual([13, 18, 35])
  })

  it('does not switch to edge-length preview during an active tape drag', () => {
    expect(shouldPreviewEdgeLength(true, target({ segment: { start: new Vector3(0, 0, 0), end: new Vector3(0, 10, 0) } }))).toBe(false)
    expect(shouldPreviewEdgeLength(false, target({ segment: { start: new Vector3(0, 0, 0), end: new Vector3(0, 10, 0) } }))).toBe(true)
  })

  it('defaults edge-to-edge tape drags to shortest feature distance', () => {
    const firstEdge = target({
      id: 'first-edge',
      point: new Vector3(4, 0, 0),
      segment: { start: new Vector3(0, 0, 0), end: new Vector3(0, 10, 0) },
    })
    const secondEdge = target({
      id: 'second-edge',
      point: new Vector3(6, 12, 4),
      segment: { start: new Vector3(0, 12, 0), end: new Vector3(0, 12, 10) },
    })

    const mode = defaultTapeResolveMode(firstEdge, secondEdge)
    const measurement = resolveMeasurement(firstEdge, secondEdge, mode)

    expect(mode).toBe('shortest')
    expect(measurement.startPoint.toArray()).toEqual([0, 10, 0])
    expect(measurement.endPoint.toArray()).toEqual([0, 12, 0])
    expect(measurement.distance).toBe(2)
  })

  it('keeps active tape drag previews on picked snap points', () => {
    const edge = target({
      point: new Vector3(4, 0, 0),
      segment: { start: new Vector3(0, 0, 0), end: new Vector3(0, 10, 0) },
      length: 10,
    })

    const dragTarget = pickedTapeTarget(edge)

    expect(dragTarget.label).toBe('Line Edge')
    expect(dragTarget.point.toArray()).toEqual([4, 0, 0])
    expect(dragTarget.segment).toBeUndefined()
    expect(edge.segment).toBeDefined()
  })

  it('keeps same-edge tape drags in picked mode instead of collapsing to zero shortest distance', () => {
    const firstPick = target({
      id: 'same-edge',
      point: new Vector3(4, 0, 0),
      segment: { start: new Vector3(0, 0, 0), end: new Vector3(0, 10, 0) },
    })
    const secondPick = target({
      id: 'same-edge',
      point: new Vector3(4, 6, 0),
      segment: { start: new Vector3(0, 0, 0), end: new Vector3(0, 10, 0) },
    })

    const mode = defaultTapeResolveMode(firstPick, secondPick)
    const measurement = resolveMeasurement(firstPick, secondPick, mode)

    expect(mode).toBe('picked')
    expect(measurement.startPoint.toArray()).toEqual([4, 0, 0])
    expect(measurement.endPoint.toArray()).toEqual([4, 6, 0])
  })

  it('shows a HUD mode toggle when shortest and picked measurements differ', () => {
    const firstEdge = target({
      id: 'first-edge',
      point: new Vector3(4, 0, 0),
      segment: { start: new Vector3(0, 0, 0), end: new Vector3(0, 10, 0) },
    })
    const secondEdge = target({
      id: 'second-edge',
      point: new Vector3(6, 12, 4),
      segment: { start: new Vector3(0, 12, 0), end: new Vector3(0, 12, 10) },
    })

    expect(measurementResolveModesDiffer(firstEdge, secondEdge)).toBe(true)
    expect(measurementResolveModesDiffer(target({ kind: 'vertex' }), target({ kind: 'vertex' }))).toBe(false)
  })
})
