import { Vector3 } from 'three'
import { describe, expect, it } from 'vitest'
import type { MeasurementTarget } from '../measurement'
import { snapReleaseDistance, snapScore } from './Viewer'

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

  it('allows the current snap target to release later than a newly entered target', () => {
    const current = target({ id: 'edge' })
    const newFeature = target({ id: 'other-edge' })
    const face = target({ id: 'face', kind: 'face_point', label: 'Face Point', quality: 'approximate', qualityLabel: 'Approximate' })

    expect(snapReleaseDistance(current, 'edge')).toBeGreaterThan(snapReleaseDistance(newFeature, 'edge'))
    expect(snapReleaseDistance(newFeature, 'edge')).toBeGreaterThan(snapReleaseDistance(face, 'edge'))
  })
})
